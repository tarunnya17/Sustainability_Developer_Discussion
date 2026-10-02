"""
Collect raw issue / pull request discussion data from one GitHub repository.

Example (small test run, 2 pages per step):
    python -m collector.collect --owner huggingface --repo transformers --max-pages 2 --out data/pilot

Example (full run):
    python -m collector.collect --owner huggingface --repo transformers

The script runs six steps. Each step saves the exact API responses as JSON Lines
(one JSON object per line) in  <out>/raw/<owner>__<repo>/ :

    1. repo              -> repo.json                (repository metadata)
    2. issues            -> issues.jsonl             (all issues AND pull requests)
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
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from collector.github_api import GitHubClient

ALL_STEPS = ["repo", "issues", "issue_comments", "review_comments", "pr_details", "pr_reviews_extra"]

# Reviews fetched per PR inside the GraphQL query. PRs with more get step 6.
REVIEWS_PER_PR = 50

PR_DETAILS_QUERY = """
query($owner: String!, $repo: String!, $cursor: String, $pageSize: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequests(first: $pageSize, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        databaseId
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


# ----------------------------------------------------------------------
# Steps
# ----------------------------------------------------------------------
def collect_repo(client, owner, repo, raw_dir):
    data = client.get_json(f"/repos/{owner}/{repo}")
    (raw_dir / "repo.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"[repo] saved metadata for {data['full_name']}")


def collect_rest_list(client, step, start_url, params, out_file, checkpoints, max_pages):
    """Generic loop for the REST list endpoints (steps 2, 3, 4)."""
    state = checkpoints.get(step)
    if state["done"]:
        print(f"[{step}] already complete, skipping")
        return

    # Resume from the saved "next page" URL, or start from the beginning.
    if state["next"]:
        url, params = state["next"], None
        print(f"[{step}] resuming at page {state['pages'] + 1}")
    else:
        url = start_url

    pages_this_run = 0
    for items, next_url in client.get_pages(url, params):
        append_jsonl(out_file, items)
        state["pages"] += 1
        state["next"] = next_url
        state["done"] = next_url is None
        checkpoints.save()  # save AFTER writing, so no page is ever skipped
        pages_this_run += 1
        print(f"[{step}] page {state['pages']}: +{len(items)} records")
        if max_pages and pages_this_run >= max_pages:
            print(f"[{step}] stopped after {max_pages} pages (--max-pages)")
            break


def collect_pr_details(client, owner, repo, out_file, checkpoints, max_pages, page_size=50):
    """Step 5: one GraphQL query returns details for `page_size` pull requests."""
    step = "pr_details"
    state = checkpoints.get(step)
    if state["done"]:
        print(f"[{step}] already complete, skipping")
        return

    pages_this_run = 0
    while True:
        variables = {"owner": owner, "repo": repo, "cursor": state["next"], "pageSize": page_size}
        connection = client.graphql(PR_DETAILS_QUERY, variables)["repository"]["pullRequests"]
        append_jsonl(out_file, connection["nodes"])
        state["pages"] += 1
        state["next"] = connection["pageInfo"]["endCursor"]
        state["done"] = not connection["pageInfo"]["hasNextPage"]
        checkpoints.save()
        pages_this_run += 1
        print(f"[{step}] page {state['pages']}: +{len(connection['nodes'])} pull requests")
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
    print(json.dumps(manifest["record_counts"], indent=2))


# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Collect raw GitHub issue/PR discussions.")
    parser.add_argument("--owner", default="huggingface")
    parser.add_argument("--repo", default="transformers")
    parser.add_argument("--out", default="data", help="output folder (default: data)")
    parser.add_argument("--max-pages", type=int, default=0,
                        help="stop each step after this many pages (for test runs; 0 = no limit)")
    parser.add_argument("--steps", default=",".join(ALL_STEPS),
                        help="comma-separated subset of: " + ",".join(ALL_STEPS))
    args = parser.parse_args()
    args.steps = [s.strip() for s in args.steps.split(",")]

    load_dotenv()  # reads GITHUB_TOKEN from the .env file
    client = GitHubClient()
    if not client.token:
        print("WARNING: no GITHUB_TOKEN found. Only 60 requests/hour and no GraphQL. See docs/02_setup.md\n")

    raw_dir = Path(args.out) / "raw" / f"{args.owner}__{args.repo}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    checkpoints = Checkpoints(raw_dir / "_checkpoints.json")
    started_at = datetime.now(timezone.utc).isoformat()
    base = f"/repos/{args.owner}/{args.repo}"
    oldest_first = {"per_page": 100, "sort": "created", "direction": "asc"}

    try:
        if "repo" in args.steps:
            collect_repo(client, args.owner, args.repo, raw_dir)
        if "issues" in args.steps:
            collect_rest_list(client, "issues", f"{base}/issues", {**oldest_first, "state": "all"},
                              raw_dir / "issues.jsonl", checkpoints, args.max_pages)
        if "issue_comments" in args.steps:
            collect_rest_list(client, "issue_comments", f"{base}/issues/comments", oldest_first,
                              raw_dir / "issue_comments.jsonl", checkpoints, args.max_pages)
        if "review_comments" in args.steps:
            collect_rest_list(client, "review_comments", f"{base}/pulls/comments", oldest_first,
                              raw_dir / "review_comments.jsonl", checkpoints, args.max_pages)
        if "pr_details" in args.steps:
            collect_pr_details(client, args.owner, args.repo, raw_dir / "pr_details.jsonl",
                               checkpoints, args.max_pages)
        if "pr_reviews_extra" in args.steps:
            collect_pr_reviews_extra(client, args.owner, args.repo, raw_dir, checkpoints)
    finally:
        # Always write the manifest, even if the run was interrupted.
        write_manifest(raw_dir, args, started_at, checkpoints)


if __name__ == "__main__":
    main()
