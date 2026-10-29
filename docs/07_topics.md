# 07 · Topic modeling of keyword-hit passages (BERTopic)

This stage groups the passages where sustainability keywords occur into **topics**. It gives an exploratory
map of *where* (in which technical areas) sustainability concerns come up and *which* concerns (keyword
groups A–H) come up there. This mainly serves RQ1, and the topics serve as strata for sampling discussions to code by hand.
It reads `tables/` and `filtered/` and never changes them.

```bash
python -m topics.model_topics --stability       # main run + stability check (~3 min; embeddings on the GPU)
python -m topics.model_topics --mask-keywords   # sensitivity check, written to .../masked/
```

| File | Role |
|---|---|
| `topics/vocabulary.py` | words used to describe topics (**the only file to edit when tuning topic words**) |
| `topics/passages.py` | builds the passages (paragraphs with a keyword hit) |
| `topics/model_topics.py` | embeddings, BERTopic, tables, pictures |

**Status: provisional.** The keyword filter's precision is not validated yet (`review_sample.csv` is unlabelled,
see [06_filtering.md](06_filtering.md) §8), and topics built on candidates inherit its noise. The `topic × tier`
table helps to spot noisy tiers.

## 0. Setup (extra packages)

The stage needs BERTopic, sentence-transformers and torch (several GB), listed separately in
`requirements-topics.txt`. On our server the home folder has a quota (it was full), so the environment and caches
live on the local data disk `/u2/users/scb052/`:

```bash
export UV_CACHE_DIR=/u2/users/scb052/.cache/uv            # uv download cache (not in the home quota)
export HF_HOME=/u2/users/scb052/.cache/huggingface        # embedding model download (~420 MB)
V=/u2/users/scb052/venvs/sustainability-topics
~/.local/bin/uv venv -p 3.11 $V
# torch for CUDA 12.6 first: the default PyPI build is for CUDA 13 and needs a newer driver (580+) than ours (565)
~/.local/bin/uv pip install -p $V "torch==2.14.1+cu126" --index-url https://download.pytorch.org/whl/cu126
~/.local/bin/uv pip install -p $V -r requirements.txt -r requirements-topics.txt
source $V/bin/activate                                    # instead of .venv, for this stage
```

On a machine without a quota problem, the same two installs into `.venv` work. Without a GPU, skip the first
install. Everything then runs on CPU (~5 min instead of ~3).

**GPU.** `--device` defaults to `cuda` when torch sees a GPU (`cuda:2` picks a specific one; `--device cpu` forces
CPU). Only the embedding model uses the GPU: 3,789 passages take 14 s on one A100 vs. ~90 s on 64 CPU cores.
UMAP and HDBSCAN run on CPU (~30 s per UMAP fit). The GPU versions (RAPIDS cuML) give different results and are
not needed at this size. The A100s are shared, so check `nvidia-smi` first. The model needs < 2 GB of GPU memory.

## 1. The unit: a paragraph that contains a keyword hit

| Unit | Count | Median length | Why (not) |
|---|---|---|---|
| Whole episode | 998 | 396 words (p90 1,589) | longer than an embedding model reads (384 tokens); one episode mixes many things |
| Single comment | 26,818 | 10 words, 49 % under 10 | too short and mostly "LGTM", nits |
| **Paragraph with a keyword hit** | **3,789** | **33 words** | one thought, about the concern, and it fits the model |

A **passage** is one blank-line separated paragraph of a cleaned title, opening post or human comment of one of
the 998 candidates that
- contains **at least one keyword hit** (any group, strong or weak). This is a decision: it gives the most coverage,
- has **at least 8 words** (`--min-words`).

Text is cleaned exactly as in the filter (the shared function `filtering.filter_discussions.build_texts`), and hits
are found with the same `find_hits`. Markdown table rows are removed from a paragraph, because they are numbers, not prose (9 paragraphs).
All four tiers are included, and `tier` is a column.

`concern_hit` marks passages with a strong hit or a weak hit in A–D (2,799 passages). The other ~1,000 passages only
mention a technique (E: *quantization*, *LoRA*) or a weak accuracy/maintenance word (*logits*, *quality*, *complexity*).
They are kept, but the analysis can drop them without refitting.

## 2. Topic words without the filter keywords (the circularity problem)

Every passage contains a keyword by construction. If the keywords are left in, the topic words just repeat the
filter (*memory usage*, *oom*, *speedup*). This happened in a first NMF pilot. So:
- **Topic words** are computed on the passage text with every **matched concern phrase cut out**: groups A–D and F–H
  of `filtering/keywords.py`, using the same regexes. Only the matched phrase is cut. *gpu memory* disappears,
  but *gpu* elsewhere stays.
- **Kept as context** (`KEEP_AS_CONTEXT` + all of group E): *kv cache*, *offload*, *logits*, *quantization*, *fp8*,
  *LoRA*, *flash attention*, *gradient checkpointing* … These name *where* something happens.
- The **concern side is not lost**: each passage keeps its hit groups A–H, so the tables show which concerns each
  topic carries.
- Also removed from topic words: English stop words, review chatter (*thanks, lgtm, nit, pls*), contractions (*don*),
  and leftover template words (*contributor guideline*).

This only changes how a topic is **described**. Which passages end up together comes from the embeddings
of the **natural text**. As a check, `--mask-keywords` cuts the concern phrases out before embedding too (§6).

## 3. Model and settings

BERTopic runs four steps. Each step and its setting:

| Step | Setting | Why |
|---|---|---|
| Embedding | `sentence-transformers/all-mpnet-base-v2`, normalized, on the GPU | strong general sentence model; reads 384 tokens, enough for all but 20 passages (their end is cut off) |
| Dimension reduction | UMAP: 15 neighbours, 5 dimensions, `min_dist=0`, cosine, **seed 42** | BERTopic defaults; the seed makes runs reproducible |
| Clustering | HDBSCAN: `min_cluster_size=15`, `min_samples=5`, `eom` | finds the number of topics itself; passages that fit no topic become **outliers (-1)** instead of being forced in |
| Topic words | CountVectorizer (1–2 word phrases, `min_df=2`, token pattern keeps *fp8*, *kv_cache*) → class-based TF-IDF (`reduce_frequent_words`) → MMR (`diversity=0.3`) | words typical for a topic compared to the others; MMR avoids near-duplicates (*flash*, *flash attention*) |

**Outliers.** `topic` keeps HDBSCAN's answer (-1 = outlier). Use it to read and label topics.
`topic_assigned` gives every outlier the topic whose centre is most similar (`reduce_outliers`, embedding strategy).
Use it for prevalence tables. Topic words come from the clean clusters only.

**Representative passages** are the 8 passages closest to a topic's centre (cosine similarity), not BERTopic's
default 3.

Embeddings are cached in `embeddings_all-mpnet-base-v2.npy` and reused only if the model, **device**, passages and
text are the same. With the cache and the fixed seed, a second run gives exactly the same topics (checked:
identical `passage_topics.csv`). The device counts because GPU and CPU embeddings differ in the last digits, and
that is enough to move UMAP. The CPU and GPU runs agreed only as much as two seeds do (ARI 0.60, §6).

**Thread clash (fixed in the code).** UMAP's numba would pick an OpenMP thread pool that clashes with torch's.
After UMAP, every small torch call (MMR embeds the topic words) became ~185× slower, and the first run stalled for
15+ minutes. `model_topics.py` therefore sets `NUMBA_THREADING_LAYER=workqueue`. UMAP runs single-threaded anyway
because of the fixed seed, so nothing is lost.

## 4. Outputs (`data/topics/huggingface__transformers/`)

| File | One row per | Main columns |
|---|---|---|
| `passages.csv` | passage | passage_id (`item:source:comment_id:paragraph`), item_number, source, author, author_association, tier, item_type, created_at, url, n_words, strong_groups, weak_groups, terms, concern_hit, text |
| `passage_topics.csv` | passage | topic (-1 = outlier), probability (HDBSCAN membership), topic_name, topic_assigned, topic_assigned_name |
| `topic_info.csv` | topic | size, size_assigned, n_items, top_words, share_concern_hit, share per tier, main_groups (groups in ≥ 20 % of its passages) |
| `topic_crosstabs.csv` | topic × value | dimension (group, tier, source, author_association, item_type, concern_hit), value, n, share_of_topic, share_of_value. Uses `topic_assigned`. For `group`, a passage counts once per group it has a hit in |
| `item_topics.csv` | candidate item | n_passages, dominant_topic, topics (`id (count)`), from `topic_assigned` |
| `topic_labels.csv` | topic | top_words, example_1…8 (text + passage id + link), empty **label / description / keep / notes** |
| `stability.csv` | run | seed, min_cluster_size, n_topics, outlier_share, ari, nmi, ari_clustered |
| `topics_barchart.html`, `topics_map.html` | — | top words per topic; 2-D map of all passages (hover shows the text; needs internet for plotly) |
| `model/` | — | the fitted BERTopic model (safetensors) |
| `summary.json` | — | settings, package versions, counts, outlier share, stability means, runtime |
| `masked/` | — | the same files for the `--mask-keywords` run, with `compared_to_main_run` in its summary |

## 5. Labelling the topics (to do by hand)

Open `topic_labels.csv` (or `topics_map.html` to browse). For each topic, read the examples and fill in:
- `label`: a short name for the technical area or concern (e.g. "KV cache memory during generation")
- `description`: one sentence on what the passages have in common
- `keep`: `yes` (coherent), `no` (mixed or noise), or `merge` (name the other topic in `notes`)

Then follow 2–3 topics to whole discussions with `python -m collector.show_episode <item_number>`.
Topic-word quality scores (coherence) are not used. They agree poorly with human judgment, so the reading is the check.

## 6. Results of the first run (2026-10-20)

| | |
|---|---|
| Passages | 3,789 from 980 of 998 candidates (18 candidates have no paragraph of ≥ 8 words with a hit); 2,799 with `concern_hit` |
| Topics | **58**, plus 1,342 outliers (**35 %**). The largest has 159 passages, the smallest 15 |
| Runtime | ~3 min with `--stability` (embeddings 14 s on one A100; the 7 UMAP fits on CPU) |
| Topic words | contain no concern keyword; context terms (*kv cache*, *fp8*, *quantization*, *offloading*, *lora*, *flash*) do appear |

**What the topics look like.** This is a first reading of the top words and examples; the topics are not labelled
by hand yet. The themes of the NMF pilot come back:
- KV cache (6), fp8/mxfp4 quantization (13), quantizers (19), KV-cache quantization (11), GGUF / llama.cpp (40)
- CUDA graphs and GPU sync (12), `torch.compile` (10), token generation speed (17), benchmark scripts (1)
- CPU/disk offloading (52, 55), continuous batching (53), speculative decoding (39), flash attention / SDPA (3, 8)
- RAM limits of CI runners (4), CUDA out-of-memory reports (30), failing GPU tests (42)
- Import time and lazy loading (46, 56)
- Modular code and new model classes (0, mostly group G maintainability)
- **Code agents / AI-generated PRs (38)**, e.g. *"code agent PRs are often correct! but … we're bottlenecked on
  reviews and verification now, not on writing code"*. Group G (maintainer effort) is the concern here, not a
  resource.

**Things to watch when labelling**
- **Six topics are about a technique, not a concern** (`share_concern_hit` < 0.3): 2 (training logs), 3 (flash
  attention), 5 (PEFT/LoRA), 13 (fp8), 19 (quantizers), 49 (router logits). They come from passages that only mention
  *quantization*, *logits* etc. Drop them with `concern_hit`, or mark them `keep = no`.
- **Two topics are one long thread, not a theme**: 44 (22 passages from 2 items) and 57 (15 passages from 1 item).
  Always look at `n_items`.
- **Trade-offs concentrate in quantization.** Of all passages, 21 % come from `tradeoff`-tier items. In topics 13,
  19 and 11 it is 43–46 %, and in 46 (lazy loading) and 50 (long-context generation) 47–48 %. This is provisional:
  topic 11 is only 8 items.

**Stability** (`stability.csv`)

| Change | Topics | ARI | NMI | ARI (clustered in both) |
|---|---|---|---|---|
| UMAP seed 1–4 instead of 42 | 50–59 | 0.59 (mean) | 0.80 | 0.88 |
| `min_cluster_size` 10 / 25 instead of 15 | 83 / 38 | 0.78 / 0.69 | 0.91 / 0.89 | 0.96 / 0.87 |
| CPU instead of GPU embeddings | 62 | 0.60 | — | — |

The *themes* are stable: passages that are clustered in both runs mostly stay together (0.88). The exact
boundaries, the outliers and the number of topics are not. So report topics as themes, with labels from reading,
not as a fixed count. Before quoting a share, check it in another seed.

**Sensitivity: concern keywords hidden from the embeddings** (`masked/`). 63 topics, 35 % outliers, ARI 0.27 vs. the
main run (NMI 0.59; 0.68 on passages clustered in both). That is more different than a seed change. In the main run,
10 of 58 topics have ≥ 90 % of their passages in one concern group (C memory or D speed). In the masked run it is 2 of 63.
So with natural text, the topics partly split an area by concern ("KV cache memory" vs. "decode speed"). Masked,
they group by area only. Both are valid. The main run fits RQ1 (*which* concerns in *which* area). The masked run
shows the areas alone.

## 7. Next steps

1. Label `review_sample.csv` (filter precision), then decide whether to keep all tiers / all passages.
2. Label `topic_labels.csv` (label, description, keep) and merge near-duplicate topics by hand.
3. Use `item_topics.csv` to sample discussions per topic for qualitative coding (RQ1–3). Code the 99 `tradeoff`
   episodes in full.
4. Later: DeepSpeed and Megatron-LM in one model with transformers, so their topics can be compared.
