# 00 · Overview

## What this stage does

The goal is to **download the 10,000 newest issue and pull request discussions from `huggingface/transformers`
(created before 2026-09-01)** and store them so that later we can:

- rebuild any discussion **episode**: the opening post, all replies in time order, who took part, and how it ended
- filter for sustainability-related discussions (keywords like *memory*, *energy*, *latency*, *FLOPs* …) **without downloading again**

This stage does **no** cleaning, no filtering and no analysis. It only collects and stores.

## The pipeline in one picture

```
GitHub API ──► collector/collect.py ──► data/raw/huggingface__transformers/*.jsonl   (exact API answers, never edited)
                                              │
                                              ▼
                     collector/build_tables.py ──► data/tables/huggingface__transformers/*.csv  (flat tables)
                                              │
                                              ▼
                     collector/show_episode.py  (print one discussion to check it)
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
├── .env.example             template for your secret GitHub token (.env is never committed)
├── collector/
│   ├── github_api.py        talks to GitHub: token, pagination, rate limits, retries
│   ├── collect.py           the 6 collection steps + checkpoints + manifest
│   ├── build_tables.py      raw JSONL -> CSV tables
│   └── show_episode.py      print one issue/PR as a timeline
├── docs/                    you are here
└── data/                    (not in git; created when you run the collector)
    ├── pilot/               first small test run (old version of the code)
    ├── collect_10k.log      log of the dataset collection
    ├── raw/huggingface__transformers/
    └── tables/huggingface__transformers/
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

See [worklog.md](worklog.md) for details.
