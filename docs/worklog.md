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

## 2026-10-04: dataset = 10,000 newest issues/PRs (created before 2026-09-01)

**Request:** a dataset of 10,000 issues/PRs instead of the full history.

**Decision:** the **10,000 newest items created before 2026-09-01**, chosen together.
- Why the newest: they come from the LLM era (back to about mid-2025). The oldest 10,000 would be from 2018–2020.
- Why stop at 2026-09-01: discussions get one month to reach an outcome (important for RQ3).
- Checked with the Search API: about 10,350 items were created between 2025-05-01 and 2026-08-31, so 10,000 newest reach back to about June 2025.

**Problems discovered while probing the API**. These would also have broken the original full-history plan:
1. `/issues` with `page=100` or more gives error 422 ("use cursor based pagination"). Following GitHub's own
   next link (which contains an `after=` cursor) works. Tested to page 102.
2. `/issues/comments` stops at **page 300** with no warning (no next link on page 300; page 301 says
   "pagination is limited for this resource"). The old code would have silently missed newer comments.
3. `/pulls/comments` deep pages are slow (page 300 returned a 500 error after 8 s).

**Code changes**
- `collect.py`:
  - New options `--max-items` and `--until`.
  - Items are now listed newest first (cursor pagination).
  - Comments are read with `since=<oldest item date>`, sorted by update time, in **windows of 50 pages**
    (each new window starts at the last `updated_at` seen).
  - GraphQL PR details are now newest first, with a date-window filter.
  - The first run saves its selection settings, and a different selection on the same folder is refused.
  - `manifest.json` now has a `selection` block.
- `build_tables.py`: keeps only comments, PR details and links of the selected items (raw keeps everything).
- Docs updated: 00, 01 (new sections 2 and 4), 03, 04, README.

**Test run (300 newest items, scratch folder)**
- Exactly 300 unique items (2026-08-19 to 2026-08-31), none on or after 2026-09-01.
- Comment windows rolled over correctly. One PR had 77 reviews, and step 6 fetched all of them.
- All 234 PRs got PR details. 64 PR→issue links were found.
- **For all 300 items, the main-thread comment count matched GitHub's `comments_count`.**

**Full collection: done** (`data/`, log in `data/collect_10k.log`)
- Run time: 2026-10-04, 18:18 to 19:00 UTC (41 min) in one run with no restarts. 3 temporary GitHub 502 errors were retried
  automatically, and one short "secondary rate limit" pause (60 s) happened during GraphQL.
- Selection: 10,000 items created **2025-05-21 → 2026-08-31** (7,837 PRs, 2,163 issues).
- Raw: 10,000 items · 45,491 main comments · 42,927 inline review comments · 7,842 PR details ·
  5,078 extra reviews for the 54 PRs with more than 50 reviews (the largest had 215). Total 672 MB.
- Tables: `items.csv` 10,000 rows · `comments.csv` 102,783 rows · `links.csv` 1,619 rows (65 MB).
  10,507 comments on items outside the selection were left out of the CSVs (they stay in raw).

**Verification**
- All 6 steps report `steps_complete: true`. The 10,000 `item_number`s are unique, and none was created on or after 2026-09-01.
- All 7,837 PRs have PR details (`merged` is never empty). There are no duplicate comment ids.
- Main-thread comment count equals GitHub's `comments_count` for 9,967 of 10,000 items. Spot-checks of the
  27 items with a lower count showed that GitHub's per-item comment API also returns exactly what we have:
  the counter includes deleted or hidden comments. The 6 items where we have more received new comments during collection.
- **Gap check.** Item numbers are given out in order, so I checked every number from #38254 to #48443 that is
  not in the dataset (190 numbers). Fetching each one directly gave:
  - 175 → 404: deleted, most likely spam
  - 9 → 301: transferred to another repository
  - 1 → 410: gone
  - **5 PRs (#40389, #40848, #42007, #42360, #44449) exist but are hidden from GitHub's issue *list*.**
    Their authors' accounts were deleted (shown as `ghost`) or are flagged. GraphQL still returned
    them, which is why `pr_details.jsonl` has 7,842 rows for 7,837 PRs. They are left out of the
    tables, so the dataset is "the 10,000 newest items that GitHub's issue list returns". This is a
    0.05 % gap, listed in [01_collection_plan.md](01_collection_plan.md) §7.
- `show_episode 48341` reconstructs a full memory-related PR episode. See [05_sample_data.md](05_sample_data.md).

**Next (later stages, not done yet)**
- Preprocessing: bot list (e.g. `HuggingFaceDocBuilderDev`), strip CI badges and templates from bodies.
- Sustainability keyword filtering, then qualitative analysis.
- Same collection for DeepSpeed and Megatron-LM.
