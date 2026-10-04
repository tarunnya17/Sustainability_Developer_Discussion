# 05 · Sample data

All examples are **real data** from the 10k dataset (collected 2026-10-04), in
`data/tables/huggingface__transformers/`.

## Dataset at a glance

| | |
|---|---|
| Items | **10,000**: 7,837 pull requests + 2,163 issues |
| Created between | 2025-05-21 and 2026-08-31 |
| Comment rows (`comments.csv`) | **102,783**: 39,268 main-thread comments, 24,949 reviews, 38,566 inline review comments |
| PR outcomes | 4,764 merged · `review_decision`: 4,195 APPROVED, 3,565 REVIEW_REQUIRED, 18 CHANGES_REQUESTED |
| Issue outcomes (`state_reason`) | 1,902 completed · 103 not_planned · 6 duplicate · 147 still open |
| Review verdicts | 19,189 COMMENTED · 5,663 APPROVED · 79 CHANGES_REQUESTED · 18 DISMISSED |
| PR → issue links (`links.csv`) | 1,619 |
| Rows written by bot accounts | 11,652 (only the ones GitHub marks as bots, see below) |
| Median participants per discussion | 3 |
| Size on disk | raw 672 MB · tables 65 MB |

## A reconstructed episode (`python -m collector.show_episode 48341`)

This is a **resource-related** PR (memory exhaustion when loading large models on Windows). Long bot
messages are shortened here with `[...]`.

```
#48341 [pull_request] Fix `safe_open` mmap memory exhaustion on Windows by using `pread` backend
https://github.com/huggingface/transformers/pull/48341
opened by eryk-roch (CONTRIBUTOR) at 2026-08-26T13:07:17Z
--------------------------------------------------------------------------------
2026-08-26T13:48:51Z  kaixuanliu (CONTRIBUTOR)  [review verdict=COMMENTED]
2026-08-26T13:48:51Z  kaixuanliu (CONTRIBUTOR)  [review_comment on src/transformers/modeling_layers.py:610]
Better to put this line before the loop
2026-08-26T13:54:02Z  kaixuanliu (CONTRIBUTOR)  [review_comment on tests/utils/test_modeling_utils.py:3833]
Here patch("transformers.modeling_utils.sys.platform", "win32") to patch only the attribute should be better IMO, ...
2026-08-26T13:54:39Z  kaixuanliu (CONTRIBUTOR)  [issue_comment]
Basically LGTM. Just 2 small nits above.
2026-08-26T14:00:59Z  SunMarc (MEMBER)  [review_comment on tests/utils/test_modeling_utils.py:3831]
it's fine to not have test for windows as we don't test on it.
2026-08-26T14:04:25Z  SunMarc (MEMBER)  [review_comment on src/transformers/modeling_layers.py:611]
we should also do the fix for mps
2026-08-26T14:04:32Z  SunMarc (MEMBER)  [review verdict=COMMENTED]
Thanks, just a nit
2026-08-26T18:36:01Z  github-actions[bot] (CONTRIBUTOR)  [issue_comment]
## CI Security Gate — automatic approval blocked [...]
2026-08-26T18:38:00Z  eryk-roch (CONTRIBUTOR)  [issue_comment]
Addressed all review comments:
- Hoisted `backend` selection before the loop in `modeling_layers.py`
- Added MPS handling to `MtpModel` loading path (matching `modeling_utils.py` pattern)
- Removed Windows-specific tests per @SunMarc, kept Linux backend test with targeted `sys.platform` patch per [...]
2026-08-26T19:22:07Z  matthewdouglas (MEMBER)  [review verdict=APPROVED]
2026-08-26T20:13:16Z  SunMarc (MEMBER)  [review_comment on tests/utils/test_modeling_utils.py:3826]
It's fine we can remove this test also
2026-08-27T01:15:09Z  kaixuanliu (CONTRIBUTOR)  [review verdict=APPROVED]
2026-08-27T09:24:30Z  eryk-roch (CONTRIBUTOR)  [issue_comment]
@SunMarc  Removed the last test as suggested ... Could you or @matthewdouglas merge this when ready? I don't have write access to the repo.
2026-08-27T09:32:21Z  github-actions[bot] (CONTRIBUTOR)  [issue_comment]
### CI recap [...]
2026-08-27T12:52:40Z  HuggingFaceDocBuilderDev (NONE)  [issue_comment]
The docs for this PR live [here](...). [...]
================================================================================
participants (6): HuggingFaceDocBuilderDev, SunMarc, eryk-roch, github-actions[bot], kaixuanliu, matthewdouglas
comments: 17  ->  {'review': 6, 'issue_comment': 6, 'review_comment': 5}
outcome: state=closed, merged=True, review_decision=APPROVED, closes issues: 48285, closed_at=2026-08-27T13:00:11Z, closed_by=SunMarc
```

This one episode shows everything the RQs need:
- **Trade-off topic:** a memory/resource problem (RQ1).
- **Justification:** "it's fine to not have test for windows as we don't test on it" weighs test
  effort against coverage (RQ2).
- **Negotiation and resolution:** a reviewer suggests something, the author makes the change, and a
  maintainer approves and merges it (RQ3).
- **Roles:** `MEMBER` (Hugging Face staff) vs. `CONTRIBUTOR` (outside contributor without write access).

## The same PR as a row of `items.csv`

| Column | Value |
|---|---|
| item_number | 48341 |
| item_type | pull_request |
| title | Fix `safe_open` mmap memory exhaustion on Windows by using `pread` backend |
| author / author_association | eryk-roch / CONTRIBUTOR |
| state | closed |
| created_at → closed_at | 2026-08-26T13:07:17Z → 2026-08-27T13:00:11Z |
| closed_by | SunMarc |
| is_draft | False |
| merged / merged_at / merged_by | True / 2026-08-27T13:00:11Z / SunMarc |
| merge_commit_sha | 8631167e310d56baa87f5213f524fdb5f47c4ff9 |
| commits / changed_files / additions / deletions | 3 / 2 / 15 / 2 |
| review_decision | APPROVED |
| base_ref → head_ref | main ← fix-windows-mmap-pread |
| linked_issue_numbers | 48285 |

## Its `review` rows in `comments.csv`

| comment_id | author | author_association | review_state | created_at | body |
|---|---|---|---|---|---|
| 5031188625 | kaixuanliu | CONTRIBUTOR | COMMENTED | 2026-08-26T13:48:51Z | *(empty; envelope for an inline comment)* |
| 5031325647 | SunMarc | MEMBER | COMMENTED | 2026-08-26T14:04:32Z | Thanks, just a nit |
| 5034269438 | matthewdouglas | MEMBER | **APPROVED** | 2026-08-26T19:22:07Z | |
| 5036408342 | kaixuanliu | CONTRIBUTOR | **APPROVED** | 2026-08-27T01:15:09Z | |

## The issue it closes (`links.csv` and the issue row)

`links.csv`:

| pr_number | issue_number | issue_repo | same_repo | link_type |
|---|---|---|---|---|
| 48341 | 48285 | huggingface/transformers | True | closes |

Issue #48285 in `items.csv`:
- title: "`from_pretrained` with safetensors mmap crashes on Windows for large multi-shard checkpoints (copy-on-write commit charge exhausts memory)"
- state: closed, with state_reason `completed`
- closed_by: SunMarc
- linked_pr_numbers: `48341`

So the **issue → PR → merge** story can be followed in both directions.

## A raw record (`review_comments.jsonl`, shortened)

Each line in a `.jsonl` file is one JSON object, exactly as GitHub returned it (~25 fields). This
one comes from an early test run (PR #32 from 2018):

```json
{
  "id": 234541128,
  "pull_request_url": "https://api.github.com/repos/huggingface/transformers/pulls/32",
  "path": "examples/run_classifier.py",
  "line": 506,
  "author_association": "NONE",
  "created_at": "2018-11-19T09:17:01Z",
  "body": "I think `all(nd not in n for nd in no_decay)` would be clearer",
  "diff_hunk": "@@ -503,8 +503,8 @@ def main():\n         param_optimizer = list(model.named_parameters())\n ..."
}
```

`diff_hunk` (the code being discussed) is kept only in the raw files.

## Things the preprocessing stage should handle (noticed in the data)

- **Bots.** `github-actions[bot]` is flagged as a bot. `HuggingFaceDocBuilderDev` is a normal
  account (`author_is_bot = False`, association `NONE`) that posts automated doc-preview messages,
  so it needs a manual bot list.
- **Machine-generated text inside human posts.** Many PR descriptions start with a CI badge block
  (`<!-- ci-dashboard-badge:start --> ...`). PR templates and HTML comments should be stripped
  before keyword filtering.
- **Empty review bodies.** Most `COMMENTED` reviews have no text. Their content is in the
  `review_comment` rows that share their `review_id`.
- **`comments_count` vs. collected comments.** For 9,967 of 10,000 items they match exactly. In 27
  items GitHub's counter is higher by one, but GitHub's own per-item comment API returns exactly
  the comments we have (the counter includes deleted or hidden comments). In 6 items we have
  more, because comments were added after the item list was saved.
