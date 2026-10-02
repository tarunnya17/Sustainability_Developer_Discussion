# Worklog

## 2026-09-30: data collection stage set up

**Decisions (agreed before coding)**
- Repository: `huggingface/transformers` only. DeepSpeed and Megatron-LM come later with the same code.
- Time range: **full history** (repo created 2018-10-29). About 19.5k issues and 28.9k PRs as of today.
  Why: raw data is cheap to store, and narrowing the dates later needs no new collection.
- Storage: **raw JSONL + CSV tables.** Why: raw keeps every field (nothing lost); CSV is easy for beginners.
- Include **PR reviews and inline review comments.** Why: much of the trade-off negotiation happens on code lines.
- Tools: plain `requests` + GitHub REST/GraphQL. See [01_collection_plan.md](01_collection_plan.md) for why not PyGithub, Search API or GH Archive.

**Done**
- Created the project scaffold: `requirements.txt`, `.env.example`, `.gitignore`, `.venv` (via `uv`).
- Wrote `collector/github_api.py`, `collect.py`, `build_tables.py` and `show_episode.py`.
- Smoke test **without a token** (REST steps only, 1–2 pages each):
  - 200 items (issues and PRs), 100 main comments and 100 inline review comments were collected correctly.
  - Resume works: the second run printed `[issues] resuming at page 2`.
  - Found that the issue list also gives `closed_by` (who closed the item). Added it to `items.csv` because it is useful for RQ3.
  - `show_episode 32` reconstructed PR #32 correctly (description → inline review → maintainer comment → outcome).
- Wrote docs 00–04.

**Next**
- Create a GitHub token ([02_setup.md](02_setup.md)) → pilot run with GraphQL → fill [05_sample_data.md](05_sample_data.md).
- Full collection.
