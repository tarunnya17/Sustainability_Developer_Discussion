# 00 · Overview

## What this stage does

The goal is to **download every issue and pull request discussion from `huggingface/transformers`**
and store it so that later we can:

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
    ├── pilot/               small test run
    ├── raw/huggingface__transformers/
    └── tables/huggingface__transformers/
```

## Status

| Step | Status |
|---|---|
| Plan and data model research | done |
| Collector code | done |
| Smoke test (REST, no token) | done |
| Pilot run with token (incl. GraphQL) | waiting for a GitHub token |
| Full collection | not started |

See [worklog.md](worklog.md) for details.
