"""
Find sustainability-related discussions with the keyword list in filtering/keywords.py.

    python -m filtering.filter_discussions
    python -m filtering.filter_discussions --owner huggingface --repo transformers --out data

Input : <out>/tables/<owner>__<repo>/items.csv, comments.csv
Output: <out>/filtered/<owner>__<repo>/
          keyword_hits.csv        one row per keyword hit (with a text snippet)
          items_scored.csv        every item with per-group counts and its tier
          candidates.csv          only the selected items, with metadata
          candidate_comments.csv  all human comments of the selected items
          review_sample.csv       random sample per tier + non-candidates, to label by hand
          summary.json            counts per tier, group and term

A discussion "episode" (title + opening post + all human comments) is the unit that gets a tier.
See docs/06_filtering.md for the rules.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from filtering.clean_text import clean, find_boilerplate
from filtering.keywords import COMPETING, CORE, GROUPS, compiled_terms

TIERS = ["tradeoff", "resource", "resource_weak", "technical"]
SNIPPET = 80  # characters of context on each side of a hit
# Bot accounts that GitHub does not mark as bots (checked: the only account with >= 50 comments
# whose comments are mostly identical; it posts "The docs for this PR live here")
KNOWN_BOTS = {"HuggingFaceDocBuilderDev"}


def is_bot(df):
    return df["author_is_bot"].astype(str).eq("True") | df["author"].isin(KNOWN_BOTS)


def find_hits(text, terms):
    """All keyword hits in one cleaned text. Weak hits inside a strong hit's span are dropped
    (e.g. 'memory' inside 'memory usage'), so a phrase is not counted twice."""
    hits = []
    for group, strength, term, regex in terms:
        for m in regex.finditer(text):
            hits.append((group, strength, term, m.start(), m.end(), m.group(0)))
    strong_spans = [(s, e) for g, st, t, s, e, _ in hits if st == "strong"]
    out = []
    for group, strength, term, start, end, matched in hits:
        if strength == "weak" and any(s < end and start < e for s, e in strong_spans):
            continue
        snippet = text[max(0, start - SNIPPET):end + SNIPPET].replace("\n", " ")
        out.append({"group": group, "strength": strength, "term": term, "matched_text": matched, "snippet": snippet})
    return out


def build_texts(items, comments, boilerplate_min=20):
    """One row per human text: item title, item body, each comment (bots skipped), with a cleaned copy.
    Returns (texts, boilerplate). Also used by topics/, so both stages see exactly the same text."""
    human_items = items[~is_bot(items)]
    human_comments = comments[~is_bot(comments)]
    texts = pd.concat([
        pd.DataFrame({"item_number": human_items["item_number"], "source": "title", "comment_id": pd.NA,
                      "comment_kind": pd.NA, "author": human_items["author"], "raw": human_items["title"]}),
        pd.DataFrame({"item_number": human_items["item_number"], "source": "body", "comment_id": pd.NA,
                      "comment_kind": pd.NA, "author": human_items["author"], "raw": human_items["body"]}),
        pd.DataFrame({"item_number": human_comments["item_number"], "source": "comment",
                      "comment_id": human_comments["comment_id"], "comment_kind": human_comments["comment_kind"],
                      "author": human_comments["author"], "raw": human_comments["body"]}),
    ], ignore_index=True)
    boilerplate = find_boilerplate(texts["raw"], boilerplate_min)
    texts["text"] = [clean(t, boilerplate) for t in texts["raw"]]
    return texts, boilerplate


def assign_tier(strong, weak):
    """strong / weak: sets of groups that have at least one strong / weak hit in the episode."""
    has_core_strong = bool(strong & set(CORE))
    has_competing_strong = bool(strong & set(COMPETING))
    weak_core_groups = weak & set(CORE)
    if has_core_strong and has_competing_strong:
        return "tradeoff"
    if has_core_strong:
        return "resource"
    if len(weak_core_groups) >= 2 or (weak_core_groups and "H" in strong):
        return "resource_weak"
    if "G" in strong:
        return "technical"
    return None


def main():
    parser = argparse.ArgumentParser(description="Keyword filter for sustainability-related discussions.")
    parser.add_argument("--owner", default="huggingface")
    parser.add_argument("--repo", default="transformers")
    parser.add_argument("--out", default="data")
    parser.add_argument("--boilerplate-min", type=int, default=20,
                        help="a line that appears in this many different texts counts as boilerplate")
    parser.add_argument("--per-tier", type=int, default=25, help="review sample size per tier")
    parser.add_argument("--non-candidates", type=int, default=50, help="review sample size of non-candidates")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    table_dir = Path(args.out) / "tables" / f"{args.owner}__{args.repo}"
    out_dir = Path(args.out) / "filtered" / f"{args.owner}__{args.repo}"
    out_dir.mkdir(parents=True, exist_ok=True)

    items = pd.read_csv(table_dir / "items.csv")
    comments = pd.read_csv(table_dir / "comments.csv", dtype={"parent_id": "Int64", "review_id": "Int64", "line": "Int64"})

    # ---- 1-2. one row per text to search (title, body, each comment; humans only), cleaned ----
    texts, boilerplate = build_texts(items, comments, args.boilerplate_min)
    human_items = items[~is_bot(items)]
    human_comments = comments[~is_bot(comments)]
    print(f"texts: {len(texts)} ({len(items) - len(human_items)} bot items and "
          f"{len(comments) - len(human_comments)} bot comments skipped)")
    print(f"boilerplate lines removed: {len(boilerplate)}")
    raw_chars = int(texts["raw"].fillna("").str.len().sum())
    clean_chars = int(texts["text"].str.len().sum())
    print(f"characters: {raw_chars:,} raw -> {clean_chars:,} after cleaning")

    # ---- 3. match ----
    terms = compiled_terms()
    hit_rows = []
    for row in texts.itertuples(index=False):
        if not row.text:
            continue
        for hit in find_hits(row.text, terms):
            hit_rows.append({"item_number": row.item_number, "source": row.source, "comment_id": row.comment_id,
                             "comment_kind": row.comment_kind, "author": row.author, **hit})
    hits = pd.DataFrame(hit_rows, columns=["item_number", "source", "comment_id", "comment_kind", "author",
                                           "group", "strength", "term", "matched_text", "snippet"])
    hits["comment_id"] = hits["comment_id"].astype("Int64")
    hits.to_csv(out_dir / "keyword_hits.csv", index=False)

    # ---- 4. score each episode ----
    by_item = defaultdict(lambda: {"strong": set(), "weak": set(), "counts": Counter(), "terms": Counter()})
    for h in hits.itertuples(index=False):
        rec = by_item[h.item_number]
        rec[h.strength].add(h.group)
        rec["counts"][f"{h.group}_{h.strength}"] += 1
        rec["terms"][h.term] += 1
    hit_comment_ids = set(hits["comment_id"].dropna())

    score_rows = []
    for number in items["item_number"]:
        rec = by_item.get(number)
        row = {"item_number": number}
        for group in GROUPS:
            for strength in ("strong", "weak"):
                row[f"{group}_{strength}"] = rec["counts"][f"{group}_{strength}"] if rec else 0
        row["groups"] = ";".join(sorted(rec["strong"] | rec["weak"])) if rec else ""
        row["strong_groups"] = ";".join(sorted(rec["strong"])) if rec else ""
        row["n_hits"] = sum(rec["terms"].values()) if rec else 0
        row["top_terms"] = "; ".join(f"{t} ({n})" for t, n in rec["terms"].most_common(5)) if rec else ""
        row["explicit_green"] = bool(rec and "A" in rec["strong"])
        row["tier"] = assign_tier(rec["strong"], rec["weak"]) if rec else None
        row["is_candidate"] = row["tier"] is not None
        score_rows.append(row)
    scored = pd.DataFrame(score_rows)
    scored.to_csv(out_dir / "items_scored.csv", index=False)

    # ---- 5. candidates + their comments ----
    meta_cols = ["item_number", "item_type", "title", "url", "author", "author_is_bot", "state", "state_reason",
                 "merged", "labels", "comments_count", "created_at", "closed_at"]
    candidates = (scored[scored["is_candidate"]]
                  .merge(items[meta_cols], on="item_number")
                  [meta_cols[:3] + ["tier", "explicit_green", "strong_groups", "groups", "n_hits", "top_terms"] + meta_cols[3:]])
    candidates["tier"] = pd.Categorical(candidates["tier"], TIERS, ordered=True)
    candidates = candidates.sort_values(["tier", "n_hits"], ascending=[True, False])
    candidates.to_csv(out_dir / "candidates.csv", index=False)

    terms_by_comment = hits.dropna(subset=["comment_id"]).groupby("comment_id")["term"].apply(
        lambda s: "; ".join(sorted(set(s))))
    cand_comments = human_comments[human_comments["item_number"].isin(candidates["item_number"])].copy()
    cand_comments["has_hit"] = cand_comments["comment_id"].isin(hit_comment_ids)
    cand_comments["hit_terms"] = cand_comments["comment_id"].map(terms_by_comment)
    cand_comments = cand_comments.merge(candidates[["item_number", "tier"]], on="item_number")
    cand_comments.to_csv(out_dir / "candidate_comments.csv", index=False)

    # ---- 6. review sample for manual checking (precision per tier, misses among non-candidates) ----
    snippets = hits.groupby("item_number")["snippet"].apply(lambda s: " ||| ".join(s.head(3)))
    parts = []
    for tier in TIERS:
        pool = candidates[candidates["tier"] == tier]
        parts.append(pool.sample(min(args.per_tier, len(pool)), random_state=args.seed))
    non = scored[~scored["is_candidate"]].merge(items[meta_cols], on="item_number")
    non_sample = non.sample(min(args.non_candidates, len(non)), random_state=args.seed).assign(tier="none")
    sample = pd.concat(parts + [non_sample], ignore_index=True)
    sample["example_snippets"] = sample["item_number"].map(snippets)
    sample["label"] = ""   # fill in: yes / no (is this a sustainability-related discussion?)
    sample["notes"] = ""
    sample = sample[["tier", "item_number", "item_type", "title", "url", "top_terms", "example_snippets", "label", "notes"]]
    sample.to_csv(out_dir / "review_sample.csv", index=False)

    # ---- 7. summary ----
    item_terms = hits.drop_duplicates(["item_number", "term"])
    summary = {
        "settings": {"boilerplate_min": args.boilerplate_min, "seed": args.seed},
        "input": {"items": len(items), "comments": len(comments), "bot_items_skipped": len(items) - len(human_items),
                  "bot_comments_skipped": len(comments) - len(human_comments), "texts_searched": len(texts)},
        "cleaning": {"boilerplate_lines": len(boilerplate), "raw_chars": raw_chars, "clean_chars": clean_chars},
        "hits": len(hits),
        "candidates": int(scored["is_candidate"].sum()),
        "tiers": {t: int((scored["tier"] == t).sum()) for t in TIERS},
        "explicit_green_items": int(scored["explicit_green"].sum()),
        "candidates_by_type": candidates["item_type"].value_counts().to_dict(),
        "items_per_group": {f"{g}_{s}": int((scored[f"{g}_{s}"] > 0).sum()) for g in GROUPS for s in ("strong", "weak")},
        "items_per_term": {f"{g}/{s}/{t}": int(n) for (g, s, t), n in
                           item_terms.groupby(["group", "strength", "term"]).size().sort_values(ascending=False).items()},
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"keyword hits: {len(hits)}")
    print(f"candidates: {summary['candidates']} of {len(items)} items")
    for tier in TIERS:
        print(f"  {tier:14} {summary['tiers'][tier]:>5}")
    print(f"  explicit_green {summary['explicit_green_items']:>5}  (has a strong group-A term; overlaps the tiers)")
    print(f"\nOutput written to {out_dir}")


if __name__ == "__main__":
    main()
