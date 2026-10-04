"""
Collect raw issue / pull request discussion data from one GitHub repository.

Our dataset (the 10,000 newest issues+PRs created before 2026-09-01):
    python -m collector.collect --max-items 10000 --until 2026-09-01

Small test run (2 pages per step) into a separate folder:
    python -m collector.collect --max-items 300 --until 2026-09-01 --max-pages 2 --out data/pilot2

Everything (full history):
    python -m collector.collect

The script runs six steps. Each step saves the exact API responses as JSON Lines
(one JSON object per line) in  <out>/raw/<owner>__<repo>/ :

    1. repo              -> repo.json                (repository metadata)
    2. issues            -> issues.jsonl             (the selected issues AND pull requests)
    3. issue_comments    -> issue_comments.jsonl     (main conversation comments)
    4. review_comments   -> review_comments.jsonl    (inline comments on PR code)
    5. pr_details        -> pr_details.jsonl         (merged?, size, reviews, linked issues; GraphQL)
    6. pr_reviews_extra  -> pr_reviews_extra.jsonl   (extra reviews for PRs with > 50 reviews)

Progress is saved in _checkpoints.json after every page, so if the script stops
(Ctrl+C, network failure, laptop sleep) just run the same command again and it
continues where it left off.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from collector.github_api import GitHubClient

ALL_STEPS = ["repo", "issues", "issue_comments", "review_comments", "pr_details", "pr_reviews_extra"]

# Reviews fetched per PR inside the GraphQL query. PRs with more get step 6.
REVIEWS_PER_PR = 50

# Comment lists are read in "windows" of this many pages (100 comments each).
# GitHub refuses to go deeper than page 300 on some list endpoints, and deep pages
# are slow, so after WINDOW_PAGES pages we start a fresh query (see collect_comments).
WINDOW_PAGES = 50

PR_DETAILS_QUERY = """
query($owner: String!, $repo: String!, $cursor: String, $pageSize: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequests(first: $pageSize, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        databaseId
        createdAt
        isDraft
        state
        merged
        mergedAt
        mergedBy { login }
        mergeCommit { oid }
        commits { totalCount }
        additions
        deletions
        changedFiles
        reviewDecision
        baseRefName
        headRefName
        closingIssuesReferences(first: 20) {
          totalCount
          nodes { number repository { nameWithOwner } }
        }
        reviews(first: %d) {
          totalCount
          nodes {
            databaseId
            author { login __typename }
            authorAssociation
            state
            body
            submittedAt
            createdAt
            updatedAt
            url
          }
        }
      }
    }
  }
}
""" % REVIEWS_PER_PR


# ----------------------------------------------------------------------
# Small file helpers
# ----------------------------------------------------------------------
def append_jsonl(path, records):
    with open(path, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def count_lines(path):
    if not path.exists():
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for _ in f)


class Checkpoints:
    """Remembers how far each step got, stored in _checkpoints.json."""

    def __init__(self, path):
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {}

    def get(self, step):
        return self.data.setdefault(step, {"done": False, "next": None, "pages": 0})

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2))


def item_window(raw_dir):
    """Oldest and newest created_at among the collected items (None if nothing collected yet)."""
    dates = [item["created_at"] for item in read_jsonl(raw_dir / "issues.jsonl")]
    return (min(dates), max(dates)) if dates else (None, None)


# ----------------------------------------------------------------------
# Steps
# ----------------------------------------------------------------------
def collect_repo(client, owner, repo, raw_dir):
    data = client.get_json(f"/repos/{owner}/{repo}")
    (raw_dir / "repo.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"[repo] saved metadata for {data['full_name']}")


def collect_items(client, base, out_file, checkpoints, max_items, until, max_pages):
    """
    Step 2: list issues and PRs NEWEST FIRST, skip those created on/after `until`,
    and stop after `max_items` (0 = no limit).

    GitHub's "next" link for this endpoint contains a cursor (after=...), which is
    the only way to go beyond page 99 here.
    """
    step = "issues"
    state = checkpoints.get(step)
    if state["done"]:
        print(f"[{step}] already complete, skipping")
        return

    saved_ids = {item["id"] for item in read_jsonl(out_file)}  # items saved by earlier runs
    if state["next"]:
        url, params = state["next"], None
        print(f"[{step}] resuming with {len(saved_ids)} items already saved")
    else:
        url, params = f"{base}/issues", {"state": "all", "sort": "created", "direction": "desc", "per_page": 100}

    pages_this_run = 0
    for items, next_url in client.get_pages(url, params):
        keep = [i for i in items if (not until or i["created_at"] < until) and i["id"] not in saved_ids]
        if max_items:
            keep = keep[: max_items - len(saved_ids)]
        append_jsonl(out_file, keep)
        saved_ids.update(i["id"] for i in keep)

        state["pages"] += 1
        state["next"] = next_url
        state["done"] = next_url is None or bool(max_items and len(saved_ids) >= max_items)
        checkpoints.save()  # save AFTER writing, so no page is ever skipped
        pages_this_run += 1
        print(f"[{step}] page {state['pages']}: kept {len(keep)} of {len(items)}, total {len(saved_ids)}")
        if state["done"]:
            break
        if max_pages and pages_this_run >= max_pages:
            print(f"[{step}] stopped after {max_pages} pages (--max-pages)")
            break


def collect_comments(client, step, start_url, out_file, checkpoints, since, max_pages):
    """
    Steps 3 and 4: read a repository-wide comment list, oldest UPDATE first,
    in windows of WINDOW_PAGES pages.

    `since` = only comments updated at/after this time. Every comment on an item
    created after `since` was also written (and so updated) after `since`, so we get
    all comments of our selected items (plus some on older items, removed later).

    Why windows? GitHub stops at page 300 for /issues/comments without saying so.
    So after WINDOW_PAGES pages we start a fresh query with
    since = updated_at of the last comment we saw. A window that ends by itself
    (no next page) means we reached the newest comment.
    """
    state = checkpoints.get(step)
    if state["done"]:
        print(f"[{step}] already complete, skipping")
        return
    state.setdefault("since", since)
    state.setdefault("window", 1)
    state.setdefault("window_pages", 0)

    pages_this_run = 0
    while not state["done"]:
        if state["next"]:
            url, params = state["next"], None
        else:
            url, params = start_url, {"sort": "updated", "direction": "asc", "per_page": 100}
            if state["since"]:
                params["since"] = state["since"]

        for records, next_url in client.get_pages(url, params):
            append_jsonl(out_file, records)
            state["pages"] += 1
            state["window_pages"] += 1
            if records:
                state["last_updated"] = records[-1]["updated_at"]
            print(f"[{step}] window {state['window']}, page {state['window_pages']}: "
                  f"+{len(records)} (up to {state.get('last_updated')})")

            if next_url is None:
                state["done"], state["next"] = True, None
            elif state["window_pages"] >= WINDOW_PAGES:
                if state["last_updated"] == state["since"]:
                    raise RuntimeError(f"[{step}] window did not move forward; stopping to avoid a loop")
                # start a new window from the last comment we saw
                state["since"], state["next"] = state["last_updated"], None
                state["window"] += 1
                state["window_pages"] = 0
            else:
                state["next"] = next_url
            checkpoints.save()

            pages_this_run += 1
            if max_pages and pages_this_run >= max_pages:
                print(f"[{step}] stopped after {max_pages} pages (--max-pages)")
                return
            if state["done"] or state["next"] is None:
                break  # finished, or time for a new window


def collect_pr_details(client, owner, repo, out_file, checkpoints, max_pages, until, window_start, page_size=50):
    """
    Step 5: one GraphQL query returns details for `page_size` pull requests, NEWEST FIRST.
    Only PRs created inside the item window [window_start, until) are kept.
    """
    step = "pr_details"
    state = checkpoints.get(step)
    if state["done"]:
        print(f"[{step}] already complete, skipping")
        return

    pages_this_run = 0
    while True:
        variables = {"owner": owner, "repo": repo, "cursor": state["next"], "pageSize": page_size}
        connection = client.graphql(PR_DETAILS_QUERY, variables)["repository"]["pullRequests"]
        nodes = connection["nodes"]
        keep = [pr for pr in nodes
                if (not until or pr["createdAt"] < until)
                and (not window_start or pr["createdAt"] >= window_start)]
        append_jsonl(out_file, keep)

        passed_window = bool(window_start and nodes and nodes[-1]["createdAt"] < window_start)
        state["pages"] += 1
        state["next"] = connection["pageInfo"]["endCursor"]
        state["done"] = not connection["pageInfo"]["hasNextPage"] or passed_window
        checkpoints.save()
        pages_this_run += 1
        print(f"[{step}] page {state['pages']}: kept {len(keep)} of {len(nodes)} pull requests")
        if state["done"] or (max_pages and pages_this_run >= max_pages):
            break


def collect_pr_reviews_extra(client, owner, repo, raw_dir, checkpoints):
    """Step 6: fetch ALL reviews (via REST) for PRs that have more than REVIEWS_PER_PR reviews."""
    step = "pr_reviews_extra"
    state = checkpoints.get(step)
    finished = set(state.setdefault("finished_prs", []))

    needed = [
        pr["number"]
        for pr in read_jsonl(raw_dir / "pr_details.jsonl")
        if pr["reviews"]["totalCount"] > len(pr["reviews"]["nodes"])
    ]
    todo = [n for n in sorted(set(needed)) if n not in finished]
    print(f"[{step}] {len(needed)} PRs have more than {REVIEWS_PER_PR} reviews, {len(todo)} left to fetch")

    for number in todo:
        reviews = []
        for page, _ in client.get_pages(f"/repos/{owner}/{repo}/pulls/{number}/reviews", {"per_page": 100}):
            reviews.extend(page)
        for review in reviews:
            review["_pr_number"] = number  # remember which PR this review belongs to
        append_jsonl(raw_dir / "pr_reviews_extra.jsonl", reviews)
        state["finished_prs"].append(number)
        checkpoints.save()
        print(f"[{step}] PR #{number}: {len(reviews)} reviews")
    state["done"] = checkpoints.get("pr_details")["done"]
    checkpoints.save()


# ----------------------------------------------------------------------
# Manifest: a record of what was collected and when (for reproducibility)
# ----------------------------------------------------------------------
def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return None


def write_manifest(raw_dir, args, started_at, checkpoints):
    path = raw_dir / "manifest.json"
    manifest = json.loads(path.read_text()) if path.exists() else {"runs": []}
    manifest["repository"] = f"{args.owner}/{args.repo}"
    window_start, window_end = item_window(raw_dir)
    manifest["selection"] = {
        **checkpoints.data.get("selection", {}),
        "items_collected": len({i["id"] for i in read_jsonl(raw_dir / "issues.jsonl")}),
        "oldest_item_created_at": window_start,
        "newest_item_created_at": window_end,
    }
    manifest["runs"].append({
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "steps": args.steps,
        "max_pages": args.max_pages,
        "code_git_commit": git_commit(),
    })
    manifest["record_counts"] = {
        f.name: count_lines(f) for f in sorted(raw_dir.glob("*.jsonl"))
    }
    manifest["steps_complete"] = {step: checkpoints.get(step)["done"] for step in ALL_STEPS if step != "repo"}
    path.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest written to {path}")
    print(json.dumps(manifest["selection"], indent=2))
    print(json.dumps(manifest["record_counts"], indent=2))


def check_selection(checkpoints, selection):
    """Refuse to mix two different datasets in one output folder."""
    if not checkpoints.data:
        checkpoints.data["selection"] = selection
        checkpoints.save()
    elif checkpoints.data.get("selection") != selection:
        sys.exit(
            f"This output folder was collected with different settings:\n"
            f"  saved:   {checkpoints.data.get('selection')}\n"
            f"  current: {selection}\n"
            f"Use a different --out folder (or delete the old one to start over)."
        )


# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Collect raw GitHub issue/PR discussions.")
    parser.add_argument("--owner", default="huggingface")
    parser.add_argument("--repo", default="transformers")
    parser.add_argument("--out", default="data", help="output folder (default: data)")
    parser.add_argument("--max-items", type=int, default=0,
                        help="keep only the N newest issues+PRs (0 = all)")
    parser.add_argument("--until", default=None,
                        help="only items created before this date, e.g. 2026-09-01")
    parser.add_argument("--max-pages", type=int, default=0,
                        help="stop each step after this many pages (for test runs; 0 = no limit)")
    parser.add_argument("--steps", default=",".join(ALL_STEPS),
                        help="comma-separated subset of: " + ",".join(ALL_STEPS))
    args = parser.parse_args()
    args.steps = [s.strip() for s in args.steps.split(",")]
    until = f"{args.until}T00:00:00Z" if args.until else None

    load_dotenv()  # reads GITHUB_TOKEN from the .env file
    client = GitHubClient()
    if not client.token:
        print("WARNING: no GITHUB_TOKEN found. Only 60 requests/hour and no GraphQL. See docs/02_setup.md\n")

    raw_dir = Path(args.out) / "raw" / f"{args.owner}__{args.repo}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    checkpoints = Checkpoints(raw_dir / "_checkpoints.json")
    check_selection(checkpoints, {"max_items": args.max_items, "until": until, "order": "newest_first"})
    started_at = datetime.now(timezone.utc).isoformat()
    base = f"/repos/{args.owner}/{args.repo}"

    try:
        if "repo" in args.steps:
            collect_repo(client, args.owner, args.repo, raw_dir)
        if "issues" in args.steps:
            collect_items(client, base, raw_dir / "issues.jsonl", checkpoints,
                          args.max_items, until, args.max_pages)

        # The comment and PR steps only need the time window of the selected items.
        window_start = item_window(raw_dir)[0] if args.max_items else None
        if args.max_items and not checkpoints.get("issues")["done"]:
            print("WARNING: the issues step is not complete, so the item window is not final yet.")

        if "issue_comments" in args.steps:
            collect_comments(client, "issue_comments", f"{base}/issues/comments",
                             raw_dir / "issue_comments.jsonl", checkpoints, window_start, args.max_pages)
        if "review_comments" in args.steps:
            collect_comments(client, "review_comments", f"{base}/pulls/comments",
                             raw_dir / "review_comments.jsonl", checkpoints, window_start, args.max_pages)
        if "pr_details" in args.steps:
            collect_pr_details(client, args.owner, args.repo, raw_dir / "pr_details.jsonl",
                               checkpoints, args.max_pages, until, window_start)
        if "pr_reviews_extra" in args.steps:
            collect_pr_reviews_extra(client, args.owner, args.repo, raw_dir, checkpoints)
    finally:
        # Always write the manifest, even if the run was interrupted.
        write_manifest(raw_dir, args, started_at, checkpoints)


if __name__ == "__main__":
    main()
