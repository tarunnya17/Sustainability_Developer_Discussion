# 03 · Data schema

There are two layers:

1. **Raw files** in `data/raw/huggingface__transformers/`. These are the exact GitHub API answers,
   one JSON object per line (JSONL). They are never edited.
2. **Tables** in `data/tables/huggingface__transformers/`. These are flat CSVs built from the raw files by
   `collector/build_tables.py`, and they can be rebuilt at any time.

The "Example" columns below show what the values look like. Some are illustrative.
Real rows copied from the pilot run are in [05_sample_data.md](05_sample_data.md).

## How the tables connect

```
repository.csv (1 row)

items.csv  ── item_number ──<  comments.csv      (one item has many comments, reviews, inline comments)
   │
   └── item_number ──<  links.csv  >── item_number    (PR "closes" issue)
```

The **key** is `item_number`, the `#` number you see on GitHub. Issues and PRs share one number
sequence, so it is unique within a repository. When we add DeepSpeed and Megatron-LM later, the key
becomes `(repo_name, item_number)`.

**Rebuilding an episode** works like this:
1. Take the `items` row for the item (title, description, author, outcome).
2. Take all `comments` rows with the same `item_number` and sort them by `created_at`.
3. The participants are `items.author` plus the distinct `comments.author` values.

`python -m collector.show_episode <number>` does exactly this.

---

## repository.csv

| Column | Meaning | Example |
|---|---|---|
| repo_owner | account that owns the repo | `huggingface` |
| repo_name | repository name | `transformers` |
| repo_full_name | owner/name | `huggingface/transformers` |
| repo_url | web link | `https://github.com/huggingface/transformers` |
| description | repo description | `🤗 Transformers: the model-definition framework…` |
| stars, forks | popularity at collection time | `166876`, `34735` |
| created_at | when the repo was created | `2018-10-29T13:56:00Z` |
| default_branch | main branch name | `main` |
| collected_at | when we downloaded the metadata (UTC) | `2026-10-01T04:12:10Z` |

## items.csv (one row per issue or pull request)

| Column | Meaning | Source (raw field) | Example |
|---|---|---|---|
| repo_name | repository | — | `transformers` |
| item_number | the `#` number (**key**) | `issues.number` | `32` |
| item_id | GitHub's internal id | `issues.id` | `382297829` |
| item_type | `issue` or `pull_request` | does `issues.pull_request` exist? | `pull_request` |
| title | title | `title` | `Fix ineffective no_decay bug…` |
| body | opening post (Markdown, unchanged) | `body` | `With the original code, all parameters…` |
| author | GitHub login of the opener | `user.login` | `xiaoda99` |
| author_association | role of the author in the repo | `author_association` | `CONTRIBUTOR` |
| author_is_bot | bot account? | `user.type == "Bot"` or login ends with `[bot]` | `False` |
| state | `open` / `closed` | `state` | `closed` |
| state_reason | why it was closed (issues): `completed`, `not_planned`, `reopened` | `state_reason` | `completed` |
| labels | labels, separated by `;` | `labels[].name` | `bug;Good First Issue` |
| assignees | assigned people, separated by `;` | `assignees[].login` | `ArthurZucker` |
| milestone | milestone title | `milestone.title` | `v4.40.0` |
| locked | conversation locked? | `locked` | `False` |
| comments_count | number of main-thread comments according to GitHub | `comments` | `3` |
| reactions_total | 👍❤️🎉… reactions on the opening post | `reactions.total_count` | `5` |
| created_at / updated_at / closed_at | timestamps in UTC (ISO 8601) | same names | `2018-11-18T08:21:37Z` |
| closed_by | who closed it | `closed_by.login` | `thomwolf` |
| url | web link | `html_url` | `https://github.com/huggingface/transformers/pull/32` |
| **PR only:** | (empty for issues) | GraphQL `pr_details` | |
| is_draft | draft PR? | `isDraft` | `False` |
| merged | was it merged? | `merged` | `True` |
| merged_at, merged_by | when and by whom | `mergedAt`, `mergedBy.login` | `2018-11-20T09:11:47Z`, `thomwolf` |
| merge_commit_sha | the resulting commit | `mergeCommit.oid` | `a1b2c3…` |
| commits | number of commits in the PR | `commits.totalCount` | `2` |
| changed_files, additions, deletions | size of the change | same names | `1`, `4`, `2` |
| review_decision | overall review result | `reviewDecision` | `APPROVED` / `CHANGES_REQUESTED` / `REVIEW_REQUIRED` |
| base_ref, head_ref | target branch and source branch | `baseRefName`, `headRefName` | `main`, `fix-memory-leak` |
| linked_issue_numbers | issues this PR closes (`;`) | `closingIssuesReferences` | `28120;28131` |
| **Issue only:** | | | |
| linked_pr_numbers | PRs that close this issue (`;`) | reverse of the above | `28145` |

## comments.csv (one row per comment, review or inline comment)

All three kinds of GitHub "comments" are in **one table**, so a whole discussion can be read in
time order. `comment_kind` tells you which kind a row is (see [01_collection_plan.md](01_collection_plan.md)).

| Column | Meaning | Applies to | Example |
|---|---|---|---|
| comment_id | GitHub id of the comment/review | all | `436051908` |
| comment_kind | `issue_comment`, `review` or `review_comment` | all | `review_comment` |
| repo_name | repository | all | `transformers` |
| item_number | which issue/PR it belongs to (**joins to items**) | all | `32` |
| author, author_association, author_is_bot | who wrote it and their role | all | `thomwolf`, `MEMBER`, `False` |
| body | text (Markdown, unchanged; may be empty for reviews) | all | `I think all(nd not in n …) would be clearer` |
| created_at, updated_at | timestamps (for reviews: submitted time) | all | `2018-11-19T09:17:01Z` |
| url | web link | all | `https://github.com/.../pull/32#discussion_r…` |
| reactions_total | reactions on this comment | issue_comment, review_comment | `2` |
| parent_id | the comment this one replies to | review_comment | `240097619` |
| review_id | the review this inline comment belongs to | review_comment | `176329123` |
| review_state | `APPROVED`, `CHANGES_REQUESTED`, `COMMENTED`, `DISMISSED` | review | `CHANGES_REQUESTED` |
| file_path, line | code location being discussed | review_comment | `examples/run_classifier.py`, `506` |

Notes:
- Main-thread (`issue_comment`) replies are **not** linked by GitHub. People reply by quoting
  (`> text`) or mentioning (`@user`). This can be detected from the text later.
- Many `review` rows have an **empty body** with state `COMMENTED`. They are the "envelope" around
  a batch of inline comments. We keep them because they mark *when* a reviewer engaged.

## links.csv

| Column | Meaning | Example |
|---|---|---|
| pr_number | the PR | `28145` |
| issue_number | the issue it closes | `28120` |
| issue_repo | repo of that issue (it can be in another repo) | `huggingface/transformers` |
| same_repo | is the issue in this repo? | `True` |
| link_type | always `closes` for now | `closes` |

## Raw-only fields (in JSONL, not in the tables)

These are kept in case later stages need them:
- `diff_hunk` on review comments: the code snippet being discussed
- `reactions` broken down by type (👍, 👎, 😄, 🎉, 😕, ❤️, 🚀, 👀). A 👎 count may signal disagreement
- full user objects, `node_id`s, `commit_id` of review comments, `start_line`/`side`, `type` (issue type)
