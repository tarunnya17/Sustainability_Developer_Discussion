"""
Print one issue or pull request as a chronological "discussion episode".

    python -m collector.show_episode 1234
    python -m collector.show_episode 1234 --out data/pilot --full

This is a quick way to check that the collected data really lets us reconstruct
a discussion: the opening post, every comment/review in time order,
the participants, and the outcome.
"""

import argparse
from pathlib import Path

import pandas as pd


def short(text, full, limit=300):
    text = "" if pd.isna(text) else str(text).strip()
    if full or len(text) <= limit:
        return text
    return text[:limit] + " [...]"


def main():
    parser = argparse.ArgumentParser(description="Show one issue/PR discussion in time order.")
    parser.add_argument("number", type=int, help="issue or PR number, e.g. 1234")
    parser.add_argument("--owner", default="huggingface")
    parser.add_argument("--repo", default="transformers")
    parser.add_argument("--out", default="data")
    parser.add_argument("--full", action="store_true", help="print full texts instead of the first 300 characters")
    args = parser.parse_args()

    table_dir = Path(args.out) / "tables" / f"{args.owner}__{args.repo}"
    items = pd.read_csv(table_dir / "items.csv")
    comments = pd.read_csv(table_dir / "comments.csv", dtype={"parent_id": "Int64", "review_id": "Int64", "line": "Int64"})

    match = items[items["item_number"] == args.number]
    if match.empty:
        print(f"#{args.number} is not in {table_dir / 'items.csv'}")
        return
    item = match.iloc[0]
    thread = comments[comments["item_number"] == args.number].sort_values("created_at")

    print("=" * 80)
    print(f"#{item['item_number']} [{item['item_type']}] {item['title']}")
    print(f"{item['url']}")
    print(f"opened by {item['author']} ({item['author_association']}) at {item['created_at']}")
    print(f"labels: {item['labels'] if pd.notna(item['labels']) else '-'}")
    print("-" * 80)
    print(short(item["body"], args.full))

    for _, c in thread.iterrows():
        print("-" * 80)
        extra = ""
        if c["comment_kind"] == "review":
            extra = f" verdict={c['review_state']}"
        elif c["comment_kind"] == "review_comment":
            extra = f" on {c['file_path']}:{c['line']}"
            if pd.notna(c["parent_id"]):
                extra += f" (reply to {c['parent_id']})"
        print(f"{c['created_at']}  {c['author']} ({c['author_association']})  [{c['comment_kind']}{extra}]")
        body = short(c["body"], args.full)
        if body:
            print(body)

    print("=" * 80)
    participants = sorted(set([item["author"]]) | set(thread["author"]))
    print(f"participants ({len(participants)}): {', '.join(participants)}")
    print(f"comments: {len(thread)}  ->  {thread['comment_kind'].value_counts().to_dict()}")
    outcome = f"state={item['state']}"
    if item["item_type"] == "pull_request":
        outcome += f", merged={item['merged']}, review_decision={item['review_decision']}"
        if pd.notna(item.get("linked_issue_numbers")):
            outcome += f", closes issues: {item['linked_issue_numbers']}"
    else:
        outcome += f", state_reason={item['state_reason']}"
        if pd.notna(item.get("linked_pr_numbers")):
            outcome += f", closed by PRs: {item['linked_pr_numbers']}"
    print(f"outcome: {outcome}, closed_at={item['closed_at']}, closed_by={item['closed_by']}")


if __name__ == "__main__":
    main()
