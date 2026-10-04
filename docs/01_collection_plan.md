# 01 · Data collection plan: what we collect and why

## 1. How GitHub stores a discussion (the data model)

Knowing these five facts makes the rest of the design make sense.

1. **Issues and pull requests share one number sequence.** `#1234` is either an issue or a PR, never
   both. GitHub's API treats every PR as "an issue with extra PR fields", so one list endpoint
   returns both. We use the `#` number (`item_number`) as the main key.

2. **There are three different kinds of "comment"**, and they live in different places:

   | Kind | Where you see it on github.com | API | Threaded? |
   |---|---|---|---|
   | `issue_comment` | the normal conversation below an issue or PR | `/issues/comments` | No. The thread is flat, and people reply by quoting with `>` |
   | `review` | "X approved these changes", "X requested changes", plus an optional summary text | GraphQL `reviews`, REST `/pulls/{n}/reviews` | It is the container for inline comments |
   | `review_comment` | a comment attached to a line of code in "Files changed" | `/pulls/comments` | Yes, `in_reply_to_id` points to the parent |

   Trade-off negotiation often happens in **review comments**, for example *"this doubles memory
   usage, can we avoid it?"* on a specific line. That is why we collect all three kinds.

3. **The outcome is spread over several fields:**
   - issue: `state` (open/closed), `state_reason` (`completed` vs. `not_planned`), `closed_by`
   - PR: `merged`, `merged_at`, `merged_by`, `review_decision`
   - reviews: `APPROVED` / `CHANGES_REQUESTED` / `COMMENTED` / `DISMISSED`

4. **Issue ↔ PR links.** When a PR says "Fixes #123", GitHub records a *closing reference*. We get
   these from GraphQL (`closingIssuesReferences`). Informal mentions ("see #123") only exist inside
   the text, but the text is kept, so they can be parsed later.

5. **`author_association`** tells us each person's role: `OWNER`, `MEMBER` (Hugging Face staff),
   `COLLABORATOR`, `CONTRIBUTOR` (has merged code before), `FIRST_TIME_CONTRIBUTOR` or `NONE`. This
   matters for RQ3, for example when a maintainer and an outside contributor disagree.

## 2. Which items are in the dataset (selection)

The dataset contains the **10,000 newest issues and PRs created before 2026-09-01**:

```bash
python -m collector.collect --max-items 10000 --until 2026-09-01
```

Why this selection:
- **LLM era.** The newest items reach back to about mid-2025. This is when Transformers is mostly
  about LLMs (quantization, KV-cache, attention kernels, long context), which is where the
  accuracy-vs-cost trade-offs we study are discussed. The oldest items (2018–2020) are from the
  BERT era.
- **One month of "settling time".** Items opened in September 2026 are left out, so most
  discussions have had time to reach an outcome (merged, closed, or rejected). This matters for RQ3.
- **Comments are not cut off at the cutoff date.** If an August issue got replies in September, those
  replies are included. Each discussion is captured as it is on the collection day.

The exact window (oldest and newest `created_at` of the selected items) is saved in
`manifest.json` under `selection`.

## 3. Which APIs we call (the 6 steps)

| # | Step | API call | Output file | Requests (10k dataset) |
|---|---|---|---|---|
| 1 | repo | `GET /repos/huggingface/transformers` | `repo.json` | 1 |
| 2 | issues | `GET /repos/.../issues?state=all&sort=created&direction=desc&per_page=100` | `issues.jsonl` | ~110 |
| 3 | issue_comments | `GET /repos/.../issues/comments?sort=updated&direction=asc&since=<oldest item date>` | `issue_comments.jsonl` | several hundred |
| 4 | review_comments | `GET /repos/.../pulls/comments?sort=updated&direction=asc&since=<oldest item date>` | `review_comments.jsonl` | several hundred |
| 5 | pr_details | GraphQL `pullRequests(first: 50, orderBy: CREATED_AT DESC)` with merge info, size, reviews and closing issues | `pr_details.jsonl` | ~170 |
| 6 | pr_reviews_extra | `GET /repos/.../pulls/{n}/reviews` | `pr_reviews_extra.jsonl` | only PRs with more than 50 reviews |

Why this combination:

- **Steps 2–4 use repository-wide list endpoints.** Each request returns 100 records from the
  whole repo. Fetching item by item would need tens of thousands of requests.
- **Step 2 goes newest first** (`direction=desc`). It skips items created on or after `--until` and
  stops after `--max-items`.
- **Steps 3–4 use `since`.** This means "only comments updated at or after this time". A comment on one
  of our items was written after the item was created, so `since = oldest item date` gets all of
  them. It also returns some comments on older items that were active recently. `build_tables.py`
  removes those from the CSVs, and they stay in the raw files.
- **Step 5 uses GraphQL** because the PR-only fields (merged?, additions, deletions, commits,
  changed files, review verdicts) are *not* in the issue list. With REST we would need two extra
  requests per PR. GraphQL returns all of it for 50 PRs per request.
- **Step 6** is a safety net. The GraphQL query takes the first 50 reviews per PR. For the rare PR
  with more, we fetch the complete list with REST, so nothing is cut off.

## 4. GitHub pagination limits we discovered (and how the code handles them)

GitHub returns long lists in **pages** of 100. While testing we found that GitHub does not let you
page through very long lists without limits:

| Endpoint | What GitHub does | How we handle it |
|---|---|---|
| `/issues` (item list) | From page 100 on: error 422, *"Pagination with the page parameter is not supported for large datasets, please use cursor based pagination"* | We never build page numbers ourselves. We follow GitHub's own "next page" link, which contains a **cursor** (`after=...`), a bookmark that says "continue after this item". Tested past page 102. |
| `/issues/comments` | Stops at **page 300** (30,000 comments). Page 301 gives *"pagination is limited for this resource"*. Page 300 just has no "next" link, so a naive script would **think it finished** and silently miss newer comments. | **Windows** (below). |
| `/pulls/comments` | No hard stop, but very deep pages are slow (page 300 returned a server error after 8 s). | The same windows keep every query shallow. The retry logic covers occasional server errors. |

**Windows, explained.** Comments are sorted by "last updated, oldest first". We read 50 pages
(5,000 comments), note the `updated_at` of the last comment, and then start a **new** query with
`since = that time`. Each query stays far below page 300. A query that ends on its own (fewer than
50 pages) means we reached the newest comment. The few comments at the boundary between two windows
are downloaded twice, and `build_tables.py` removes the duplicates by id.

## 5. Alternatives we considered and rejected

| Option | Why not |
|---|---|
| GitHub **Search API** | Returns at most 1,000 results per query, so it cannot give "everything" |
| **PyGithub** library | Convenient, but it hides pagination and makes one request per object (slow), and it is harder to see what happens |
| **GH Archive / BigQuery** | Built for event streams across all of GitHub. Overkill here, needs a Google Cloud account, and queries can cost money |
| **Timeline API** per item | Gives every event (labels added, cross-references…), but needs one or more extra requests per item (10,000+). Can be added later for a filtered subset |
| Scraping github.com HTML | Fragile and against GitHub's terms. The API is the official route |

## 6. Reliability features

- **Token**: 5,000 REST requests/hour and 5,000 GraphQL points/hour. Without a token you get 60/hour.
- **Rate-limit waiting**: when fewer than 20 requests are left, the script sleeps until GitHub resets the limit.
- **Retries**: network errors and server errors (5xx) are retried up to 6 times with growing waits.
- **Checkpoints** (`_checkpoints.json`): after each saved page, the script records the URL (or
  GraphQL cursor) of the next page. Run the same command again and it continues from there.
- **Duplicates are harmless**: if the script stops between "save page" and "save checkpoint", that
  page is downloaded twice. `build_tables.py` removes duplicates by id.
- **Manifest** (`manifest.json`): records when each run happened, its options, how many records
  each file has, and the code version. This tells us exactly what snapshot we analysed.

## 7. Known limitations (to mention in the report)

- **Snapshot in time.** We see discussions as they are at collection time. Edited comments show only
  their latest text (`updated_at` tells us an edit happened), and deleted comments are gone.
- **Deleted users** appear as `ghost`. GitHub's issue *list* also hides some items whose author was
  deleted or flagged. In our window this hid 5 PRs (0.05 %), which are therefore not in the dataset.
  See [worklog.md](worklog.md).
- **Bots.** Accounts with `type == "Bot"` or a `[bot]` login suffix (e.g. `github-actions[bot]`) are
  flagged with `author_is_bot`. Some automated accounts are normal user accounts (e.g.
  `HuggingFaceDocBuilderDev`), so the preprocessing stage will need a manual bot list too.
- **Issue ↔ PR links** only include formal closing references. Plain `#123` mentions need text parsing.
- **Not collected:** commit messages, code diffs (only `diff_hunk` context for inline comments),
  timeline events (label changes, cross-references), and Hugging Face forum or Discord discussions.
  GitHub Discussions is disabled for this repository.
