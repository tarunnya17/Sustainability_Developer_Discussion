# 00 · Overview

## What this stage does

The goal is to **download the 10,000 newest issue and pull request discussions from `huggingface/transformers`
(created before 2026-09-01)** and store them so that later we can:

- rebuild any discussion **episode**: the opening post, all replies in time order, who took part, and how it ended
- filter for sustainability-related discussions (keywords like *memory*, *energy*, *latency*, *FLOPs* …) **without downloading again**

The collection stage does no cleaning, no filtering and no analysis. It only collects and stores.
The filtering stage ([06_filtering.md](06_filtering.md)) reads the tables and writes `data/filtered/`.
The topic stage ([07_topics.md](07_topics.md)) groups the keyword-hit passages of the candidates into topics
and writes `data/topics/`.

## The pipeline in one picture

```
GitHub API ──► collector/collect.py ──► data/raw/huggingface__transformers/*.jsonl   (exact API answers, never edited)
                                              │
                                              ▼
                     collector/build_tables.py ──► data/tables/huggingface__transformers/*.csv  (flat tables)
                                              │
                                              ▼
                     collector/show_episode.py  (print one discussion to check it)
                                              │
                                              ▼
                     filtering/filter_discussions.py ──► data/filtered/huggingface__transformers/*.csv
                                              │          (keyword hits, tiers, candidate discussions)
                                              ▼
                     topics/model_topics.py ──► data/topics/huggingface__transformers/
                                                (passages, topics, topic x tier/group tables, labelling sheet)
```

There are two layers on purpose:
- **raw/** is the "evidence". It holds exactly what GitHub returned. If we later need a field we did
  not put in the tables, it is still here.
- **tables/** is the "working copy". It is easy to open with pandas or Excel, and it can always be
  rebuilt from raw/ in seconds.

## Folder map

```
.
├── README.md
├── requirements.txt         Python packages (requests, pandas, python-dotenv)
├── requirements-topics.txt  extra packages for topics/ (BERTopic, sentence-transformers, torch …)
├── .env.example             template for your secret GitHub token (.env is never committed)
├── collector/
│   ├── github_api.py        talks to GitHub: token, pagination, rate limits, retries
│   ├── collect.py           the 6 collection steps + checkpoints + manifest
│   ├── build_tables.py      raw JSONL -> CSV tables
│   └── show_episode.py      print one issue/PR as a timeline
├── filtering/
│   ├── keywords.py          the sustainability keyword list (edit this to tune)
│   ├── clean_text.py        strip templates, code, quotes, badges before matching
│   └── filter_discussions.py  match, score, assign tiers, write data/filtered/
├── topics/                  (extra packages: requirements-topics.txt)
│   ├── vocabulary.py        words used to describe topics (edit this to tune)
│   ├── passages.py          paragraphs of candidate discussions that contain a keyword hit
│   └── model_topics.py      embeddings + BERTopic + tables, write data/topics/
├── docs/                    you are here
└── data/                    (not in git; created when you run the collector)
    ├── pilot/               first small test run (old version of the code)
    ├── collect_10k.log      log of the dataset collection
    ├── raw/huggingface__transformers/
    ├── tables/huggingface__transformers/
    ├── filtered/huggingface__transformers/
    └── topics/huggingface__transformers/
```

## Status

| Step | Status |
|---|---|
| Plan and data model research | done |
| Collector code | done |
| Smoke test (REST, no token) | done |
| Pilot run with token (incl. GraphQL) | done (`data/pilot/`) |
| Selection "10,000 newest before 2026-09-01" + fixes for GitHub pagination limits | done |
| 10k dataset collection (10,000 items, 102,783 comment rows) | done, verified |
| Keyword filter (998 candidate discussions, 99 in the `tradeoff` tier) | done; manual validation pending |
| Topic model (BERTopic) on 3,789 keyword-hit passages: 58 topics, 35 % outliers | done (provisional); topic labelling pending |

See [worklog.md](worklog.md) for details.
