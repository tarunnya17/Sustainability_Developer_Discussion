# BERTopic input: keyword-hit passages

Made by `python -m topics.export_input` (see `docs/07_topics.md` §8 in the project). These are the same documents,
embeddings and stop words that `topics/model_topics.py` used for the main run (58 topics). Counts, settings and
package versions are in `settings.json`.

| File | What it is |
|---|---|
| `documents.csv` | one row per passage (a paragraph with a sustainability keyword hit), with metadata |
| `embeddings_all-mpnet-base-v2.npy` | embeddings of `text`, float32, normalized; **row i = row i of documents.csv** |
| `embeddings_all-mpnet-base-v2_cut.npy` | embeddings of `text_cut` (keyword-masked sensitivity run) |
| `stopwords.txt` | stop words for the topic words: sklearn English + review chatter (`topics/vocabulary.py`) |
| `settings.json` | settings and result of the main run, package versions |

## Two texts per passage

| Column | Use it for | Why |
|---|---|---|
| `text` | **embeddings** (clustering) | the cleaned natural paragraph |
| `text_cut` | **topic words** (the `docs` passed to `fit_transform`) | `text` with the matched concern phrases (*memory usage*, *oom*, *speedup* …) cut out. Every passage has a keyword by construction, so with them the topic words only repeat the filter. Techniques (*quantization*, *kv cache*, *offload* …) stay |

BERTopic clusters on the embeddings you pass and builds the topic words from the `docs`. So
`fit_transform(text_cut, embeddings_of_text)` = natural-text clusters, described without the filter words.

## Columns of documents.csv

| Column | Meaning |
|---|---|
| `passage_id` | `item:source:comment_id:paragraph`, unique |
| `item_number` | issue/PR number; link `https://github.com/huggingface/transformers/issues/<n>` |
| `source` | `title`, `body`, `issue_comment`, `review_comment`, `review` |
| `comment_id`, `para_idx` | comment id (empty for title/body), paragraph index in that text |
| `author`, `author_association` | GitHub login and role (`MEMBER`, `CONTRIBUTOR`, `NONE` …) |
| `tier` | filter tier of the item: `tradeoff`, `resource`, `resource_weak`, `technical` |
| `item_type` | `issue` or `pull_request` |
| `created_at`, `url` | time (UTC, ISO) and link of the comment (title/body: of the item) |
| `n_words` | words in `text` |
| `strong_groups`, `weak_groups`, `groups` | keyword groups hit (`;`-separated, may be empty): A accuracy, B energy/carbon, C memory, D speed, E techniques, F cost, G maintainability, H trade-off words |
| `terms` | the keyword terms found |
| `concern_hit` | `True` = strong hit, or weak hit in A–D. `False` = only a technique (E) or a weak word like *logits*, *quality* |
| `text`, `text_cut` | see above |

## In Colab

Upload the zip (Files pane, or Google Drive). No GPU is needed with the included embeddings.

```python
!unzip -q huggingface__transformers.zip      # from Drive: !unzip -q /content/drive/MyDrive/<path>/huggingface__transformers.zip
!pip install -q bertopic==0.17.4

import numpy as np
import pandas as pd
from bertopic import BERTopic
from bertopic.representation import MaximalMarginalRelevance
from bertopic.vectorizers import ClassTfidfTransformer
from hdbscan import HDBSCAN
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import CountVectorizer
from umap import UMAP

d = "huggingface__transformers"
df = pd.read_csv(f"{d}/documents.csv")
emb = np.load(f"{d}/embeddings_all-mpnet-base-v2.npy")
stop_words = open(f"{d}/stopwords.txt").read().split()
docs = df["text_cut"].tolist()

# the main run's settings (settings.json); change what you like
topic_model = BERTopic(
    embedding_model=SentenceTransformer("sentence-transformers/all-mpnet-base-v2"),  # used by MMR (topic words)
    umap_model=UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine", random_state=42),
    hdbscan_model=HDBSCAN(min_cluster_size=15, min_samples=5, metric="euclidean",
                          cluster_selection_method="eom", prediction_data=True),
    vectorizer_model=CountVectorizer(stop_words=stop_words, token_pattern=r"(?u)\b[a-z][a-z0-9_\-\.]*[a-z0-9]\b",
                                     ngram_range=(1, 2), min_df=2),
    ctfidf_model=ClassTfidfTransformer(reduce_frequent_words=True),
    representation_model=MaximalMarginalRelevance(diversity=0.3),
    top_n_words=10,
)
topics, probs = topic_model.fit_transform(docs, emb)
topic_model.get_topic_info()
```

Variations:

```python
# only passages about a concern (drops ~1,000 technique-only passages): filter docs AND embeddings with the same mask
m = df["concern_hit"].to_numpy()
topics, probs = topic_model.fit_transform(df.loc[m, "text_cut"].tolist(), emb[m])

# keyword-masked run: same docs, embeddings of text_cut
emb = np.load(f"{d}/embeddings_all-mpnet-base-v2_cut.npy")

# another embedding model (use a GPU runtime): embed `text`, not `text_cut`
emb = SentenceTransformer("<model>").encode(df["text"].tolist(), normalize_embeddings=True, show_progress_bar=True)

# outliers -> nearest topic (as topic_assigned in the main run)
assigned = topic_model.reduce_outliers(docs, topics, strategy="embeddings", embeddings=emb)

# topics per tier / over time
topic_model.topics_per_class(docs, classes=df["tier"].tolist())
topic_model.topics_over_time(docs, pd.to_datetime(df["created_at"]).tolist(), nr_bins=12)
```

## Good to know

- Keep rows aligned: whenever you filter `df`, filter the embeddings with the same mask (`emb[m]`).
- Same settings + same embeddings give topics close to the main run, but not guaranteed identical (other library
  versions and machine). Topic ids and counts differ between runs anyway (UMAP seeds: ARI ≈ 0.6). Compare themes, not ids.
- 20 passages are longer than the model's 384 tokens. Their embeddings only cover the beginning.
- `strong_groups`, `weak_groups`, `groups` are empty for some rows: pandas reads them as NaN (`.fillna("")`).
