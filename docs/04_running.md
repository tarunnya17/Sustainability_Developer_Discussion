# 04 · Running the collection

Always start in the project folder with the environment activated:

```bash
cd ~/Projects/sustainability-developer-discussion
source .venv/bin/activate
```

## Step A: small test run (1–2 minutes)

This collects the 300 newest items into a separate folder, so you can check that everything works:

```bash
python -m collector.collect --max-items 300 --until 2026-09-01 --out data/test300
python -m collector.build_tables --out data/test300
python -m collector.show_episode <some PR number from items.csv> --out data/test300
```

## Step B: the dataset (10,000 newest items before 2026-09-01; ~40 min)

```bash
nohup python -u -m collector.collect --max-items 10000 --until 2026-09-01 > data/collect_10k.log 2>&1 &
tail -f data/collect_10k.log      # watch progress (Ctrl+C stops watching, not the job)
```

When it finishes, build the tables:

```bash
python -m collector.build_tables
```

The output is:
- `data/raw/huggingface__transformers/`: exact API data
- `data/tables/huggingface__transformers/`: CSV tables

`nohup … &` keeps the job running after you close the terminal. `-u` makes Python write the log
immediately instead of buffering it.

## What the log means

```
[issues] page 33: kept 100 of 100, total 2459         <- items saved so far (stops at 10000)
[issue_comments] window 2, page 17: +100 (up to 2025-11-02T10:41:12Z)
                                                       <- comments, read in windows of 50 pages
[pr_details] page 14: kept 25 of 50 pull requests      <- PRs outside the date window are skipped
```

## Stopping and resuming

You can stop at any time (Ctrl+C, `kill`, network failure). Then run **the same command again**:

```
[issues] already complete, skipping
[issue_comments] window 3, page 12: ...
```

Progress is stored in `data/raw/huggingface__transformers/_checkpoints.json`.

**Selection guard:** the first run saves its settings (`--max-items`, `--until`) in the checkpoint
file. If you later run the same `--out` folder with *different* settings, the script refuses:

```
This output folder was collected with different settings: ...
Use a different --out folder (or delete the old one to start over).
```

This prevents two different datasets from being mixed in one folder. To collect something
different (e.g. the full history), use another folder: `--out data/full`.

## Running only some steps

```bash
python -m collector.collect --max-items 10000 --until 2026-09-01 --steps pr_details,pr_reviews_extra
```

Step names are `repo`, `issues`, `issue_comments`, `review_comments`, `pr_details` and `pr_reviews_extra`.

## Checking the result

1. `data/raw/huggingface__transformers/manifest.json`:
   - `selection.items_collected` should be `10000`
   - `steps_complete` should be `true` for every step
2. Quick checks in Python:
   ```python
   import pandas as pd
   items = pd.read_csv("data/tables/huggingface__transformers/items.csv")
   comments = pd.read_csv("data/tables/huggingface__transformers/comments.csv")
   print(len(items), items.item_number.is_unique)                       # 10000 True
   print(items.created_at.max() < "2026-09-01")                         # True
   print(items[items.item_type == "pull_request"].merged.isna().sum())  # 0
   # comment completeness: GitHub's own count vs what we collected
   got = comments[comments.comment_kind == "issue_comment"].groupby("item_number").size()
   diff = items.set_index("item_number").comments_count - got.reindex(items.item_number).fillna(0).values
   print((diff != 0).sum())   # ~0 (small differences = comments deleted/added during collection)
   ```
3. Look at a few discussions with `python -m collector.show_episode <number>` and compare them
   with the page on github.com.

## Other repositories (later)

The same code works for any repository:

```bash
python -m collector.collect --owner microsoft --repo DeepSpeed --max-items 10000 --until 2026-09-01 --out data
python -m collector.collect --owner NVIDIA --repo Megatron-LM --until 2026-09-01 --out data
```

Each repository gets its own folder (`data/raw/<owner>__<repo>/`), so they don't conflict.
