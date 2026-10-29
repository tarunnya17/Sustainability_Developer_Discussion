"""
Export the BERTopic input (the keyword-hit passages) as plain files, to run BERTopic elsewhere (e.g. Google Colab).

    python -m topics.export_input                    # ~30 s, no GPU and no torch needed
    python -m topics.export_input --dest /u2/users/scb052/bertopic_input   # elsewhere (~50 MB; home quota)

Input : <out>/tables/<owner>__<repo>/items.csv, comments.csv
        <out>/filtered/<owner>__<repo>/candidates.csv
        <out>/topics/<owner>__<repo>/embeddings_*.npy, masked/embeddings_*.npy, summary.json (if model_topics ran)
Output: <dest>/<owner>__<repo>/                    (dest: <out>/bertopic_input unless --dest)
          documents.csv          one row per passage: metadata, text (embed this), text_cut (topic words)
          embeddings_<model>.npy      embeddings of `text` (main run); row i = documents.csv row i
          embeddings_<model>_cut.npy  embeddings of `text_cut` (the --mask-keywords run)
          stopwords.txt          stop words for the topic words (sklearn English + topics/vocabulary.py)
          settings.json          settings, counts and package versions of the main run
          README.md              how to use it in Colab (copied from topics/export_readme.md)
        <dest>/<owner>__<repo>.zip                 the same folder, to upload

The passages are the ones model_topics.py uses (same build_passages and cut_concern). Embeddings are copied, not
computed: they are included only if the cache of model_topics.py was made from exactly these passages and text.
Needs requirements.txt + scikit-learn (for the stop word list).
"""

import argparse
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from topics.passages import build_passages
from topics.vocabulary import TOKEN_PATTERN, concern_patterns, cut_concern, stop_words

README = Path(__file__).with_name("export_readme.md")


def cached_embeddings(path, ids, docs, model_name):
    """The embeddings model_topics.py cached for exactly these passages and text (same key as
    model_topics.embed), with their metadata; (None, reason) otherwise."""
    meta_path = path.with_suffix(".json")
    if not (path.exists() and meta_path.exists()):
        return None, "no cache (run python -m topics.model_topics first)"
    meta = json.loads(meta_path.read_text())
    key = hashlib.sha256("\n".join(f"{i}\t{d}" for i, d in zip(ids, docs)).encode()).hexdigest()
    if meta["model"] != model_name or meta["sha256"] != key:
        return None, "cache was made from other passages or another model"
    embeddings = np.load(path)
    if len(embeddings) != len(docs):
        return None, "cache has another number of rows"
    return embeddings, meta


def main():
    parser = argparse.ArgumentParser(description="Export the BERTopic input (keyword-hit passages) for Colab.")
    parser.add_argument("--owner", default="huggingface")
    parser.add_argument("--repo", default="transformers")
    parser.add_argument("--out", default="data")
    parser.add_argument("--dest", help="folder to write to (default: <out>/bertopic_input)")
    parser.add_argument("--min-words", type=int, default=8, help="as in model_topics (must match for the embeddings)")
    parser.add_argument("--boilerplate-min", type=int, default=20, help="as in filtering (must match)")
    parser.add_argument("--embedding-model", default="sentence-transformers/all-mpnet-base-v2")
    args = parser.parse_args()

    name = f"{args.owner}__{args.repo}"
    table_dir = Path(args.out) / "tables" / name
    filtered_dir = Path(args.out) / "filtered" / name
    topics_dir = Path(args.out) / "topics" / name
    out_dir = Path(args.dest or Path(args.out) / "bertopic_input") / name
    out_dir.mkdir(parents=True, exist_ok=True)

    items = pd.read_csv(table_dir / "items.csv")
    comments = pd.read_csv(table_dir / "comments.csv", dtype={"parent_id": "Int64", "review_id": "Int64", "line": "Int64"})
    candidates = pd.read_csv(filtered_dir / "candidates.csv")

    # ---- 1. documents: the passages of model_topics.py, plus the text with the concern phrases cut out ----
    docs = build_passages(items, comments, candidates, args.min_words, args.boilerplate_min)
    patterns = concern_patterns()
    docs["text_cut"] = [cut_concern(t, patterns) for t in docs["text"]]
    docs.insert(docs.columns.get_loc("terms"), "groups", [
        ";".join(sorted(set(filter(None, s.split(";"))) | set(filter(None, w.split(";")))))
        for s, w in zip(docs["strong_groups"], docs["weak_groups"])])
    docs.to_csv(out_dir / "documents.csv", index=False)
    print(f"documents: {len(docs)} passages from {docs['item_number'].nunique()} of {len(candidates)} candidate items")

    # ---- 2. embeddings (copied from the model_topics.py caches if they match) ----
    model_short = args.embedding_model.split("/")[-1]
    embedding_info = {}
    for column, cache, suffix in [("text", topics_dir, ""), ("text_cut", topics_dir / "masked", "_cut")]:
        file = f"embeddings_{model_short}{suffix}.npy"
        embeddings, meta = cached_embeddings(cache / f"embeddings_{model_short}.npy", docs["passage_id"],
                                             docs[column], args.embedding_model)
        if embeddings is None:
            (out_dir / file).unlink(missing_ok=True)
            print(f"{file}: not included ({meta})")
            continue
        np.save(out_dir / file, embeddings)
        embedding_info[file] = {"of_column": column, "model": meta["model"], "device": meta["device"],
                                "shape": list(embeddings.shape), "dtype": str(embeddings.dtype), "normalized": True}
        print(f"{file}: {embeddings.shape[0]} x {embeddings.shape[1]} (embeddings of `{column}`)")

    # ---- 3. stop words and settings ----
    (out_dir / "stopwords.txt").write_text("\n".join(stop_words()) + "\n")
    summary_path = topics_dir / "summary.json"
    run = json.loads(summary_path.read_text()) if summary_path.exists() else None
    settings = {
        "exported": date.today().isoformat(),
        "repository": f"{args.owner}/{args.repo}",
        "documents": {"file": "documents.csv", "rows": len(docs), "items": int(docs["item_number"].nunique()),
                      "candidate_items": len(candidates), "concern_hit": int(docs["concern_hit"].sum()),
                      "rows_per_tier": docs["tier"].value_counts().to_dict(), "min_words": args.min_words},
        "embeddings": embedding_info,
        # fixed values below are hard-coded in model_topics.py; the others come from its summary.json
        "main_run": None if run is None else {
            "fit": "BERTopic.fit_transform(documents.text_cut, embeddings of documents.text)",
            "embedding_model": run["settings"]["embedding_model"],
            "umap": {"n_neighbors": run["settings"]["n_neighbors"], "n_components": run["settings"]["n_components"],
                     "min_dist": 0.0, "metric": "cosine", "random_state": run["settings"]["seed"]},
            "hdbscan": {"min_cluster_size": run["settings"]["min_cluster_size"],
                        "min_samples": run["settings"]["min_samples"], "metric": "euclidean",
                        "cluster_selection_method": "eom", "prediction_data": True},
            "vectorizer": {"stop_words": "stopwords.txt", "token_pattern": TOKEN_PATTERN, "ngram_range": [1, 2],
                           "min_df": 2},
            "ctfidf": {"reduce_frequent_words": True},
            "representation": {"MaximalMarginalRelevance": {"diversity": 0.3}},
            "top_n_words": run["settings"]["top_n_words"],
            "outliers": "reduce_outliers(strategy='embeddings') for the prevalence tables",
            "result": {"topics": run["topics"], "outlier_share": run["outlier_share"]},
            "versions": run["versions"],
        },
    }
    (out_dir / "settings.json").write_text(json.dumps(settings, indent=2))
    shutil.copyfile(README, out_dir / "README.md")

    # ---- 4. zip (one folder, to upload to Colab or Google Drive) ----
    zip_path = shutil.make_archive(str(out_dir), "zip", root_dir=out_dir.parent, base_dir=name)
    print(f"\nOutput written to {out_dir}\nZip: {zip_path} ({Path(zip_path).stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
