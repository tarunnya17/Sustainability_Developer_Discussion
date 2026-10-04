"""
Turn the raw JSONL files into simple, flat CSV tables.

    python -m collector.build_tables --owner huggingface --repo transformers
    python -m collector.build_tables --owner huggingface --repo transformers --out data/pilot

Input : <out>/raw/<owner>__<repo>/*.jsonl
Output: <out>/tables/<owner>__<repo>/
          repository.csv   one row: the repository
          items.csv        one row per issue or pull request
          comments.csv     one row per comment / review / inline review comment
          links.csv        one row per "PR closes issue" link

This is NOT preprocessing: no text is cleaned, nothing is filtered out.
It only flattens and joins the raw data so it is easy to open in pandas/Excel.
Duplicates (e.g. a page saved twice after an interrupted run) are removed by id.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from collector.collect import read_jsonl


def is_bot(user):
    """GitHub marks app accounts as type 'Bot'; their logins usually end with '[bot]'."""
    if not user:
        return False
    return user.get("type") == "Bot" or user.get("login", "").endswith("[bot]")


def login(user):
    # Deleted accounts come back as null; GitHub shows them as "ghost".
    return user["login"] if user else "ghost"


def dedupe(records, key):
    """Keep the last record for every key (later downloads are more up to date)."""
    return list({r[key]: r for r in records}.values())


def number_from_url(url):
    """'https://api.github.com/repos/o/r/issues/123' -> 123"""
    return int(url.rstrip("/").split("/")[-1])


def reactions_total(record):
    return (record.get("reactions") or {}).get("total_count")


# ----------------------------------------------------------------------
def build_repository(raw_dir):
    repo = json.loads((raw_dir / "repo.json").read_text())
    collected_at = datetime.fromtimestamp((raw_dir / "repo.json").stat().st_mtime, timezone.utc).isoformat()
    return pd.DataFrame([{
        "repo_owner": repo["owner"]["login"],
        "repo_name": repo["name"],
        "repo_full_name": repo["full_name"],
        "repo_url": repo["html_url"],
        "description": repo["description"],
        "stars": repo["stargazers_count"],
        "forks": repo["forks_count"],
        "created_at": repo["created_at"],
        "default_branch": repo["default_branch"],
        "collected_at": collected_at,
    }])


def build_links(pr_details, repo_full_name):
    rows = []
    for pr in pr_details:
        for issue in pr["closingIssuesReferences"]["nodes"]:
            rows.append({
                "pr_number": pr["number"],
                "issue_number": issue["number"],
                "issue_repo": issue["repository"]["nameWithOwner"],
                "same_repo": issue["repository"]["nameWithOwner"].lower() == repo_full_name.lower(),
                "link_type": "closes",
            })
    return pd.DataFrame(rows, columns=["pr_number", "issue_number", "issue_repo", "same_repo", "link_type"])


def build_items(issues, pr_details, links, repo_name):
    details_by_number = {pr["number"]: pr for pr in pr_details}

    same_repo_links = links[links["same_repo"]] if len(links) else links
    issues_of_pr, prs_of_issue = {}, {}
    for _, link in same_repo_links.iterrows():
        issues_of_pr.setdefault(link["pr_number"], []).append(str(link["issue_number"]))
        prs_of_issue.setdefault(link["issue_number"], []).append(str(link["pr_number"]))

    rows = []
    for item in issues:
        number = item["number"]
        is_pr = "pull_request" in item
        pr = details_by_number.get(number, {}) if is_pr else {}
        rows.append({
            "repo_name": repo_name,
            "item_number": number,
            "item_id": item["id"],
            "item_type": "pull_request" if is_pr else "issue",
            "title": item["title"],
            "body": item["body"],
            "author": login(item["user"]),
            "author_association": item.get("author_association"),
            "author_is_bot": is_bot(item["user"]),
            "state": item["state"],
            "state_reason": item.get("state_reason"),
            "labels": ";".join(label["name"] for label in item.get("labels", [])),
            "assignees": ";".join(login(a) for a in item.get("assignees") or []),
            "milestone": (item.get("milestone") or {}).get("title"),
            "locked": item.get("locked"),
            "comments_count": item.get("comments"),
            "reactions_total": reactions_total(item),
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
            "closed_at": item["closed_at"],
            "closed_by": (item.get("closed_by") or {}).get("login"),
            "url": item["html_url"],
            # --- pull request only (empty for issues, or if pr_details is missing) ---
            "is_draft": pr.get("isDraft"),
            "merged": pr.get("merged"),
            "merged_at": pr.get("mergedAt"),
            "merged_by": (pr.get("mergedBy") or {}).get("login"),
            "merge_commit_sha": (pr.get("mergeCommit") or {}).get("oid"),
            "commits": (pr.get("commits") or {}).get("totalCount"),
            "changed_files": pr.get("changedFiles"),
            "additions": pr.get("additions"),
            "deletions": pr.get("deletions"),
            "review_decision": pr.get("reviewDecision"),
            "base_ref": pr.get("baseRefName"),
            "head_ref": pr.get("headRefName"),
            "linked_issue_numbers": ";".join(issues_of_pr.get(number, [])) if is_pr else None,
            # --- issue only ---
            "linked_pr_numbers": None if is_pr else ";".join(prs_of_issue.get(number, [])),
        })

    df = pd.DataFrame(rows).sort_values("item_number")
    for col in ["commits", "changed_files", "additions", "deletions", "comments_count", "reactions_total"]:
        df[col] = df[col].astype("Int64")  # keep whole numbers even when some rows are empty
    return df


def build_comments(issue_comments, review_comments, pr_details, extra_reviews, repo_name):
    rows = []

    # 1) Main conversation comments (issues and PRs share this kind)
    for c in issue_comments:
        rows.append({
            "comment_id": c["id"],
            "comment_kind": "issue_comment",
            "item_number": number_from_url(c["issue_url"]),
            "author": login(c["user"]),
            "author_association": c.get("author_association"),
            "author_is_bot": is_bot(c["user"]),
            "body": c["body"],
            "created_at": c["created_at"],
            "updated_at": c["updated_at"],
            "url": c["html_url"],
            "reactions_total": reactions_total(c),
        })

    # 2) Reviews (the "Approve / Request changes / Comment" verdict + summary text)
    reviews = {}
    for pr in pr_details:
        for r in pr["reviews"]["nodes"]:
            author = r.get("author") or {}
            reviews[r["databaseId"]] = {
                "comment_id": r["databaseId"],
                "comment_kind": "review",
                "item_number": pr["number"],
                "author": author.get("login", "ghost"),
                "author_association": r.get("authorAssociation"),
                "author_is_bot": author.get("__typename") == "Bot",
                "body": r["body"],
                "created_at": r.get("submittedAt") or r.get("createdAt"),
                "updated_at": r.get("updatedAt"),
                "url": r.get("url"),
                "review_state": r["state"],
            }
    for r in extra_reviews:  # REST format, only for PRs with many reviews
        reviews[r["id"]] = {
            "comment_id": r["id"],
            "comment_kind": "review",
            "item_number": r["_pr_number"],
            "author": login(r["user"]),
            "author_association": r.get("author_association"),
            "author_is_bot": is_bot(r["user"]),
            "body": r["body"],
            "created_at": r.get("submitted_at"),
            "updated_at": None,
            "url": r.get("html_url"),
            "review_state": r["state"],
        }
    rows.extend(reviews.values())

    # 3) Inline review comments (attached to a line of code; can reply to each other)
    for c in review_comments:
        rows.append({
            "comment_id": c["id"],
            "comment_kind": "review_comment",
            "item_number": number_from_url(c["pull_request_url"]),
            "author": login(c["user"]),
            "author_association": c.get("author_association"),
            "author_is_bot": is_bot(c["user"]),
            "body": c["body"],
            "created_at": c["created_at"],
            "updated_at": c["updated_at"],
            "url": c["html_url"],
            "reactions_total": reactions_total(c),
            "parent_id": c.get("in_reply_to_id"),
            "review_id": c.get("pull_request_review_id"),
            "file_path": c.get("path"),
            "line": c.get("line") or c.get("original_line"),
        })

    columns = ["comment_id", "comment_kind", "repo_name", "item_number", "author", "author_association",
               "author_is_bot", "body", "created_at", "updated_at", "url", "reactions_total",
               "parent_id", "review_id", "review_state", "file_path", "line"]
    df = pd.DataFrame(rows).reindex(columns=columns)
    df["repo_name"] = repo_name
    for col in ["parent_id", "review_id", "line", "reactions_total"]:
        df[col] = df[col].astype("Int64")
    return df.sort_values(["item_number", "created_at"])


# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Build CSV tables from raw JSONL files.")
    parser.add_argument("--owner", default="huggingface")
    parser.add_argument("--repo", default="transformers")
    parser.add_argument("--out", default="data")
    args = parser.parse_args()

    raw_dir = Path(args.out) / "raw" / f"{args.owner}__{args.repo}"
    table_dir = Path(args.out) / "tables" / f"{args.owner}__{args.repo}"
    table_dir.mkdir(parents=True, exist_ok=True)

    issues = dedupe(read_jsonl(raw_dir / "issues.jsonl"), "id")
    issue_comments = dedupe(read_jsonl(raw_dir / "issue_comments.jsonl"), "id")
    review_comments = dedupe(read_jsonl(raw_dir / "review_comments.jsonl"), "id")
    pr_details = dedupe(read_jsonl(raw_dir / "pr_details.jsonl"), "number")
    extra_reviews = dedupe(read_jsonl(raw_dir / "pr_reviews_extra.jsonl"), "id")

    repository = build_repository(raw_dir)
    repo_name = repository.loc[0, "repo_name"]

    # The comment lists also contain comments on OLDER items that were active
    # recently. Keep only what belongs to the selected items (raw files keep everything).
    numbers = {item["number"] for item in issues}
    pr_details = [pr for pr in pr_details if pr["number"] in numbers]
    extra_reviews = [r for r in extra_reviews if r["_pr_number"] in numbers]

    links = build_links(pr_details, repository.loc[0, "repo_full_name"])
    items = build_items(issues, pr_details, links, repo_name)
    comments = build_comments(issue_comments, review_comments, pr_details, extra_reviews, repo_name)
    outside = ~comments["item_number"].isin(numbers)
    print(f"dropped {outside.sum()} comments that belong to items outside the selection")
    comments = comments[~outside]

    for name, df in [("repository", repository), ("items", items), ("comments", comments), ("links", links)]:
        df.to_csv(table_dir / f"{name}.csv", index=False)
        print(f"{name + '.csv':16} {len(df):>8} rows")
    print(f"\nTables written to {table_dir}")


if __name__ == "__main__":
    main()
