"""
Build the documents for topic modeling: paragraphs of the candidate discussions that contain a keyword hit.

A passage is one paragraph (blank-line separated) of a cleaned title, opening post or human comment of a
candidate item (data/filtered/.../candidates.csv) that
- has at least `min_words` words, and
- contains at least one keyword hit (any group, strong or weak).

Text is cleaned exactly like in the filtering stage (filtering.filter_discussions.build_texts), and hits are
found with the same function (find_hits), so a passage's hits match keyword_hits.csv.
"""

import re

import pandas as pd

from filtering.filter_discussions import build_texts, find_hits
from filtering.keywords import CORE, compiled_terms

PARAGRAPH = re.compile(r"\n\s*\n")
TABLE_ROW = re.compile(r"^\s*\|.*$", re.M)  # markdown table rows: numbers, not prose


def build_passages(items, comments, candidates, min_words=8, boilerplate_min=20):
    texts, _ = build_texts(items, comments, boilerplate_min)
    texts = texts[texts["item_number"].isin(candidates["item_number"])]
    terms = compiled_terms()

    rows = []
    for t in texts.itertuples(index=False):
        source = t.comment_kind if t.source == "comment" else t.source
        comment_id = int(t.comment_id) if pd.notna(t.comment_id) else 0
        for i, para in enumerate(PARAGRAPH.split(t.text)):
            para = TABLE_ROW.sub("", para).strip()
            n_words = len(para.split())
            if n_words < min_words:
                continue
            hits = find_hits(para, terms)
            if not hits:
                continue
            strong = {h["group"] for h in hits if h["strength"] == "strong"}
            weak = {h["group"] for h in hits if h["strength"] == "weak"}
            rows.append({
                "passage_id": f"{t.item_number}:{source}:{comment_id}:{i}",
                "item_number": t.item_number, "source": source,
                "comment_id": comment_id if comment_id else pd.NA, "para_idx": i, "author": t.author,
                "n_words": n_words,
                "strong_groups": ";".join(sorted(strong)), "weak_groups": ";".join(sorted(weak)),
                "terms": "; ".join(sorted({h["term"] for h in hits})),
                # strong hit, or weak hit of a sustainability concern (A-D); False = only techniques (E)
                # or weak accuracy/maintenance words (logits, quality, complexity ...)
                "concern_hit": bool(strong) or bool(weak & set(CORE)),
                "text": " ".join(para.split()),
            })
    passages = pd.DataFrame(rows)
    passages["comment_id"] = passages["comment_id"].astype("Int64")

    # metadata: role, time and link of the comment (for title/body: of the item), tier and type of the item
    item_meta = items.set_index("item_number")[["author_association", "created_at", "url"]]
    comment_meta = comments.set_index("comment_id")[["author_association", "created_at", "url"]]
    is_comment = passages["comment_id"].notna()
    for col in ["author_association", "created_at", "url"]:
        passages[col] = passages["item_number"].map(item_meta[col])
        passages.loc[is_comment, col] = passages.loc[is_comment, "comment_id"].map(comment_meta[col])
    cand = candidates.set_index("item_number")
    passages["tier"] = passages["item_number"].map(cand["tier"])
    passages["item_type"] = passages["item_number"].map(cand["item_type"])

    return passages[["passage_id", "item_number", "source", "comment_id", "para_idx", "author", "author_association",
                     "tier", "item_type", "created_at", "url", "n_words", "strong_groups", "weak_groups", "terms",
                     "concern_hit", "text"]]
