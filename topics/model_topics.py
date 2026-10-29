"""
Topic modeling (BERTopic) on the keyword-hit passages of the candidate discussions.

    python -m topics.model_topics                    # main run (on the GPU if one is visible; ~3 min)
    python -m topics.model_topics --stability        # + refits with other seeds / cluster sizes
    python -m topics.model_topics --mask-keywords    # sensitivity check, written to .../masked/

Input : <out>/tables/<owner>__<repo>/items.csv, comments.csv
        <out>/filtered/<owner>__<repo>/candidates.csv
Output: <out>/topics/<owner>__<repo>/
          passages.csv          one row per passage (paragraph with a keyword hit) with metadata and hit groups
          passage_topics.csv    topic of each passage (topic = -1: outlier; topic_assigned: nearest topic)
          topic_info.csv        one row per topic: size, words, share per tier and per keyword group
          topic_crosstabs.csv   topic x (group, tier, source, author_association, item_type), from topic_assigned
          item_topics.csv       one row per candidate item: its topics (to sample episodes for coding)
          topic_labels.csv      top words + representative passages per topic, with empty label columns
          stability.csv         (--stability) number of topics, outliers and agreement with the main run
          topics_map.html, topics_barchart.html, model/, embeddings_*.npy, summary.json

See docs/07_topics.md for the reasons behind every setting.
"""

import argparse
import hashlib
import json
import os
import time
from importlib.metadata import version
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")  # silence the warning after HDBSCAN forks
# Numba (used by UMAP) would otherwise pick its OpenMP layer, which clashes with torch's OpenMP threads:
# after UMAP every small torch call (MMR embeds the topic words) got ~185x slower (0.04 s -> 7.4 s), and
# the run stalled for 15+ min. UMAP runs single-threaded here anyway (fixed seed), so nothing is lost.
os.environ.setdefault("NUMBA_THREADING_LAYER", "workqueue")

import numpy as np
import pandas as pd
import torch
from bertopic import BERTopic
from bertopic.representation import MaximalMarginalRelevance
from bertopic.vectorizers import ClassTfidfTransformer
from hdbscan import HDBSCAN
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
from umap import UMAP

from filtering.filter_discussions import TIERS
from filtering.keywords import GROUPS
from topics.passages import build_passages
from topics.vocabulary import TOKEN_PATTERN, concern_patterns, cut_concern, stop_words

STABILITY_SEEDS = [42, 1, 2, 3, 4]
STABILITY_MIN_CLUSTER_SIZES = [10, 15, 25]
PACKAGES = ["bertopic", "sentence-transformers", "umap-learn", "hdbscan", "scikit-learn", "torch"]


def make_umap(args, seed, n_components=None):
    # random_state makes UMAP reproducible (it then runs single-threaded, which is fine for ~4k passages)
    return UMAP(n_neighbors=args.n_neighbors, n_components=n_components or args.n_components, min_dist=0.0,
                metric="cosine", random_state=seed)


def make_hdbscan(min_cluster_size, min_samples):
    return HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples, metric="euclidean",
                   cluster_selection_method="eom", prediction_data=True)


def embed(docs, ids, model, model_name, device, cache):
    """Sentence embeddings, cached; the cache is reused only for the same model, device, passages and text.
    (GPU and CPU embeddings differ in the last digits, which can be enough to move UMAP, so the device counts.)"""
    key = hashlib.sha256("\n".join(f"{i}\t{d}" for i, d in zip(ids, docs)).encode()).hexdigest()
    meta = {"model": model_name, "device": device, "sha256": key}
    meta_path = cache.with_suffix(".json")
    if cache.exists() and meta_path.exists() and json.loads(meta_path.read_text()) == meta:
        print(f"embeddings: reusing {cache.name}")
        return np.load(cache), True
    started = time.time()
    embeddings = model.encode(docs, batch_size=64, show_progress_bar=True, normalize_embeddings=True)
    print(f"embeddings: {len(docs)} passages on {device} in {time.time() - started:.0f} s")
    np.save(cache, embeddings)
    meta_path.write_text(json.dumps(meta))
    return embeddings, False


def agreement(labels, main):
    """Number of topics, outlier share and agreement (ARI / NMI) of one clustering with the main run.
    ari_clustered only uses passages that are not outliers in either run."""
    labels, main = np.asarray(labels), np.asarray(main)
    both = (labels != -1) & (main != -1)
    return {"n_topics": len(set(labels) - {-1}), "outlier_share": round(float((labels == -1).mean()), 3),
            "ari": round(adjusted_rand_score(main, labels), 3), "nmi": round(normalized_mutual_info_score(main, labels), 3),
            "ari_clustered": round(adjusted_rand_score(main[both], labels[both]), 3)}


def representatives(embeddings, topics, n):
    """Per topic, the n passages closest to the topic's centroid (embeddings are normalized: dot = cosine)."""
    out = {}
    for t in sorted(set(topics) - {-1}):
        idx = np.where(topics == t)[0]
        centroid = embeddings[idx].mean(axis=0)
        out[t] = idx[np.argsort(-(embeddings[idx] @ (centroid / np.linalg.norm(centroid))))[:n]]
    return out


def group_sets(df):
    return [set(filter(None, s.split(";"))) | set(filter(None, w.split(";")))
            for s, w in zip(df["strong_groups"].fillna(""), df["weak_groups"].fillna(""))]


def topic_table(df, model):
    """One row per topic (members only, i.e. the `topic` column; -1 = outliers)."""
    groups = pd.Series(group_sets(df), index=df.index)
    rows = []
    for t, g in df.groupby("topic"):
        row = {"topic": t, "name": model.topic_labels_[t], "size": len(g),
               "size_assigned": int((df["topic_assigned"] == t).sum()) if t != -1 else 0,
               "n_items": g["item_number"].nunique(),
               "top_words": ", ".join(w for w, _ in model.get_topic(t)),
               "share_concern_hit": round(g["concern_hit"].mean(), 2)}
        for tier in TIERS:
            row[f"share_{tier}"] = round((g["tier"] == tier).mean(), 2)
        shares = {grp: groups[g.index].apply(lambda s: grp in s).mean() for grp in GROUPS}
        row["main_groups"] = "; ".join(f"{grp} {v:.2f}" for grp, v in sorted(shares.items(), key=lambda x: -x[1]) if v >= 0.2)
        rows.append(row)
    return pd.DataFrame(rows)


def crosstabs(df):
    """Long table: for each dimension value and topic (topic_assigned), n, share of the topic, share of the value.
    For `group` a passage counts once for every keyword group it has a hit in."""
    long = [df.assign(dimension=dim, value=df[dim].astype(str))[["topic_assigned", "dimension", "value"]]
            for dim in ["tier", "source", "author_association", "item_type", "concern_hit"]]
    g = df[["topic_assigned"]].assign(value=group_sets(df)).explode("value").dropna()
    long.append(g.assign(dimension="group"))
    long = pd.concat(long, ignore_index=True)
    out = long.groupby(["dimension", "value", "topic_assigned"]).size().rename("n").reset_index()
    out["share_of_topic"] = (out["n"] / out["topic_assigned"].map(df["topic_assigned"].value_counts())).round(3)
    value_total = long.groupby(["dimension", "value"]).size().rename("value_total").reset_index()
    out = out.merge(value_total, on=["dimension", "value"])
    out["share_of_value"] = (out["n"] / out.pop("value_total")).round(3)
    return out.rename(columns={"topic_assigned": "topic"})


def item_table(df, candidates):
    def summarize(s):
        counts = s.value_counts().sort_index().sort_values(ascending=False, kind="stable")  # ties: lower topic id
        return pd.Series({"n_passages": len(s), "dominant_topic": counts.index[0],
                          "topics": "; ".join(f"{t} ({n})" for t, n in counts.items())})
    per_item = df.groupby("item_number")["topic_assigned"].apply(summarize).unstack()
    out = candidates[["item_number", "tier", "item_type", "title", "url"]].merge(
        per_item, left_on="item_number", right_index=True, how="left")
    out["n_passages"] = out["n_passages"].fillna(0).astype(int)
    out["dominant_topic"] = out["dominant_topic"].astype("Int64")
    return out


def labels_sheet(info, df, reps, n):
    rows = []
    for row in info[info["topic"] != -1].itertuples(index=False):
        sheet = {"topic": row.topic, "name": row.name, "size": row.size, "top_words": row.top_words}
        for k, i in enumerate(reps[row.topic], start=1):
            sheet[f"example_{k}"] = f"{df.at[i, 'text']}\n[{df.at[i, 'passage_id']}] {df.at[i, 'url']}"
        for k in range(len(reps[row.topic]) + 1, n + 1):
            sheet[f"example_{k}"] = ""
        sheet.update({"label": "", "description": "", "keep": "", "notes": ""})  # fill in: keep = yes / no / merge
        rows.append(sheet)
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="BERTopic on the keyword-hit passages of the candidate discussions.")
    parser.add_argument("--owner", default="huggingface")
    parser.add_argument("--repo", default="transformers")
    parser.add_argument("--out", default="data")
    parser.add_argument("--min-words", type=int, default=8, help="shorter paragraphs are not used")
    parser.add_argument("--boilerplate-min", type=int, default=20, help="as in filtering (must match)")
    parser.add_argument("--embedding-model", default="sentence-transformers/all-mpnet-base-v2")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu",
                        help="cuda (default when a GPU is visible; cuda:1 picks GPU 1) or cpu")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-neighbors", type=int, default=15)
    parser.add_argument("--n-components", type=int, default=5)
    parser.add_argument("--min-cluster-size", type=int, default=15)
    parser.add_argument("--min-samples", type=int, default=5)
    parser.add_argument("--top-n-words", type=int, default=10)
    parser.add_argument("--n-representative", type=int, default=8)
    parser.add_argument("--mask-keywords", action="store_true",
                        help="cut the concern keywords out before embedding too (sensitivity check)")
    parser.add_argument("--stability", action="store_true", help="refit with other seeds and cluster sizes")
    args = parser.parse_args()
    started = time.time()

    table_dir = Path(args.out) / "tables" / f"{args.owner}__{args.repo}"
    filtered_dir = Path(args.out) / "filtered" / f"{args.owner}__{args.repo}"
    main_dir = Path(args.out) / "topics" / f"{args.owner}__{args.repo}"
    out_dir = main_dir / "masked" if args.mask_keywords else main_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    items = pd.read_csv(table_dir / "items.csv")
    comments = pd.read_csv(table_dir / "comments.csv", dtype={"parent_id": "Int64", "review_id": "Int64", "line": "Int64"})
    candidates = pd.read_csv(filtered_dir / "candidates.csv")

    # ---- 1. passages ----
    passages = build_passages(items, comments, candidates, args.min_words, args.boilerplate_min)
    passages.to_csv(out_dir / "passages.csv", index=False)
    print(f"passages: {len(passages)} from {passages['item_number'].nunique()} of {len(candidates)} candidate items")

    # topic words are always computed with the concern keywords cut out (topics/vocabulary.py);
    # the embeddings use the natural text unless --mask-keywords
    patterns = concern_patterns()
    docs_cut = [cut_concern(t, patterns) for t in passages["text"]]
    docs_embed = docs_cut if args.mask_keywords else passages["text"].tolist()

    # ---- 2. embeddings ----
    embedder = SentenceTransformer(args.embedding_model, device=args.device)
    n_tokens = [len(x) for x in embedder.tokenizer(docs_embed)["input_ids"]]
    too_long = sum(n > embedder.max_seq_length for n in n_tokens)
    print(f"passages longer than the model's {embedder.max_seq_length} tokens (cut off at the end): {too_long}")
    cache = out_dir / f"embeddings_{args.embedding_model.split('/')[-1]}.npy"
    embeddings, cached = embed(docs_embed, passages["passage_id"], embedder, args.embedding_model, args.device, cache)

    # ---- 3. BERTopic ----
    topic_model = BERTopic(
        embedding_model=embedder,
        umap_model=make_umap(args, args.seed),
        hdbscan_model=make_hdbscan(args.min_cluster_size, args.min_samples),
        vectorizer_model=CountVectorizer(stop_words=stop_words(), token_pattern=TOKEN_PATTERN, ngram_range=(1, 2), min_df=2),
        ctfidf_model=ClassTfidfTransformer(reduce_frequent_words=True),
        representation_model=MaximalMarginalRelevance(diversity=0.3),
        top_n_words=args.top_n_words,
    )
    topics, probs = topic_model.fit_transform(docs_cut, embeddings)
    topics = np.asarray(topics)
    # outliers -> nearest topic by embedding similarity; topic words stay those of the clean clusters
    assigned = np.asarray(topic_model.reduce_outliers(docs_cut, topics.tolist(), strategy="embeddings", embeddings=embeddings))
    n_topics = len(set(topics) - {-1})
    print(f"topics: {n_topics}, outliers: {(topics == -1).sum()} ({(topics == -1).mean():.0%})")

    df = passages.assign(topic=topics, probability=np.round(probs, 3), topic_assigned=assigned)
    df["topic_name"] = df["topic"].map(topic_model.topic_labels_)
    df["topic_assigned_name"] = df["topic_assigned"].map(topic_model.topic_labels_)
    df[["passage_id", "item_number", "topic", "probability", "topic_name", "topic_assigned", "topic_assigned_name"]].to_csv(
        out_dir / "passage_topics.csv", index=False)

    # ---- 4. tables ----
    info = topic_table(df, topic_model)
    info.to_csv(out_dir / "topic_info.csv", index=False)
    crosstabs(df).to_csv(out_dir / "topic_crosstabs.csv", index=False)
    item_table(df, candidates).to_csv(out_dir / "item_topics.csv", index=False)
    reps = representatives(embeddings, topics, args.n_representative)
    labels_sheet(info, df, reps, args.n_representative).to_csv(out_dir / "topic_labels.csv", index=False)

    # ---- 5. stability: other UMAP seeds (same cluster size) and other cluster sizes (same UMAP result) ----
    stability = None
    if args.stability:
        rows = [{"seed": args.seed, "min_cluster_size": args.min_cluster_size, **agreement(topics, topics)}]
        for seed in STABILITY_SEEDS:
            if seed != args.seed:
                reduced = make_umap(args, seed).fit_transform(embeddings)
                labels = make_hdbscan(args.min_cluster_size, args.min_samples).fit_predict(reduced)
                rows.append({"seed": seed, "min_cluster_size": args.min_cluster_size, **agreement(labels, topics)})
        for size in STABILITY_MIN_CLUSTER_SIZES:
            if size != args.min_cluster_size:
                labels = make_hdbscan(size, args.min_samples).fit_predict(topic_model.umap_model.embedding_)
                rows.append({"seed": args.seed, "min_cluster_size": size, **agreement(labels, topics)})
        stability = pd.DataFrame(rows)
        stability.to_csv(out_dir / "stability.csv", index=False)
        print(stability.to_string(index=False))

    # ---- 6. pictures and model ----
    topic_model.visualize_barchart(top_n_topics=n_topics, n_words=8).write_html(
        out_dir / "topics_barchart.html", include_plotlyjs="cdn")
    reduced_2d = make_umap(args, args.seed, n_components=2).fit_transform(embeddings)
    hover = [t[:200] for t in passages["text"]]
    topic_model.visualize_documents(hover, reduced_embeddings=reduced_2d).write_html(
        out_dir / "topics_map.html", include_plotlyjs="cdn")
    topic_model.save(out_dir / "model", serialization="safetensors", save_ctfidf=True,
                     save_embedding_model=args.embedding_model)

    # ---- 7. summary ----
    summary = {
        "settings": {k: v for k, v in vars(args).items() if k not in ("owner", "repo", "out")},
        "versions": {p: version(p) for p in PACKAGES},
        "gpu": torch.cuda.get_device_name(torch.device(args.device)) if args.device.startswith("cuda") else None,
        "passages": len(passages), "items_covered": int(passages["item_number"].nunique()),
        "passages_per_tier": passages["tier"].value_counts().to_dict(),
        "passages_concern_hit": int(passages["concern_hit"].sum()),
        "passages_over_max_tokens": too_long, "embeddings_from_cache": cached,
        "topics": n_topics, "outliers": int((topics == -1).sum()),
        "outlier_share": round(float((topics == -1).mean()), 3),
        "topic_sizes": {int(t): int(n) for t, n in pd.Series(topics).value_counts().sort_index().items()},
    }
    if stability is not None:
        others = stability.iloc[1:]
        seeds = others[others["min_cluster_size"] == args.min_cluster_size]
        summary["stability"] = {"ari_other_seeds_mean": round(seeds["ari"].mean(), 3),
                                "ari_clustered_other_seeds_mean": round(seeds["ari_clustered"].mean(), 3),
                                "n_topics_other_seeds": seeds["n_topics"].tolist()}
    if args.mask_keywords and (main_dir / "passage_topics.csv").exists():
        main_topics = pd.read_csv(main_dir / "passage_topics.csv").set_index("passage_id")["topic"]
        summary["compared_to_main_run"] = agreement(topics, main_topics.reindex(df["passage_id"]).to_numpy())
        print(f"agreement with the main run: {summary['compared_to_main_run']}")
    summary["runtime_seconds"] = round(time.time() - started)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=int))

    print(f"\nOutput written to {out_dir} ({summary['runtime_seconds']} s)")


if __name__ == "__main__":
    main()
