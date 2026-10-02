# 05 · Sample data

All examples below are **real data** from `huggingface/transformers`, collected by the smoke test on
2026-09-30. The PR-details part (merged, additions, reviews) needs a token and will be added after
the pilot run.

## A raw record (`review_comments.jsonl`, shortened)

Each line in a `.jsonl` file is one JSON object, exactly as GitHub returned it (~25 fields; the
important ones are shown here):

```json
{
  "id": 234541128,
  "pull_request_url": "https://api.github.com/repos/huggingface/transformers/pulls/32",
  "path": "examples/run_classifier.py",
  "line": 506,
  "author_association": "NONE",
  "created_at": "2018-11-19T09:17:01Z",
  "body": "I think `all(nd not in n for nd in no_decay)` would be clearer",
  "diff_hunk": "@@ -503,8 +503,8 @@ def main():\n         param_optimizer = list(model.named_parameters())\n     no_decay = ['bias', 'gamma', 'beta']\n ..."
}
```

`diff_hunk` (the code being discussed) is kept only in the raw file. It is too long for the CSV but
useful for later qualitative reading.

## A row of `items.csv` (issue #5)

| Column | Value |
|---|---|
| item_number | 5 |
| item_id | 377698378 |
| item_type | issue |
| title | MRPC hyperparameters question |
| body | When describing how you reproduced the MRPC results, you say: "Our test ran on a few seeds with the original implementation hyper-parameters gave evaluation results between 82 and 87." … |
| author | ethanjperez |
| author_association | CONTRIBUTOR |
| state / state_reason | closed / completed |
| comments_count | 5 |
| created_at | 2018-11-06T05:30:36Z |
| closed_at / closed_by | 2018-11-07T23:42:51Z / thomwolf |
| url | https://github.com/huggingface/transformers/issues/5 |

## A reconstructed episode (`python -m collector.show_episode 32`)

```
================================================================================
#32 [pull_request] Fix ineffective no_decay bug when using BERTAdam
https://github.com/huggingface/transformers/pull/32
opened by xiaoda99 (CONTRIBUTOR) at 2018-11-18T08:21:37Z
labels: -
--------------------------------------------------------------------------------
With the original code, all parameters are decayed because the condition "parameter_name in no_decay" will never be satisfied.
--------------------------------------------------------------------------------
2018-11-19T09:17:01Z  artemisart (NONE)  [review_comment on examples/run_classifier.py:506]
I think `all(nd not in n for nd in no_decay)` would be clearer
--------------------------------------------------------------------------------
2018-11-20T09:11:51Z  thomwolf (MEMBER)  [issue_comment]
thanks!
================================================================================
participants (3): artemisart, thomwolf, xiaoda99
comments: 2  ->  {'review_comment': 1, 'issue_comment': 1}
outcome: state=closed, merged=nan, review_decision=nan, closed_at=2018-11-20T09:11:47Z, closed_by=thomwolf
```

This small example already has the full shape of an episode:
- a **description** (the bug)
- an **inline code suggestion** from an outside user (`NONE`) about *maintainability/readability*
- a **maintainer response** (`MEMBER`)
- an **outcome** (closed by the maintainer)

`merged=nan` appears only because the smoke test had no token, so the PR details step (GraphQL) did not run.

## Coming after the pilot run
- PR row with `merged`, `additions`, `deletions`, `review_decision`
- `review` rows with verdicts (`APPROVED` / `CHANGES_REQUESTED`)
- a `links.csv` example (PR closes issue)
