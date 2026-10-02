# 04 · Running the collection

Always start in the project folder with the environment activated:

```bash
cd ~/Projects/sustainability-developer-discussion
source .venv/bin/activate
```

## Step A: pilot run (a few minutes)

This collects only 2 pages per step (about 200 items, 200 comments and 100 PRs of details) into a
separate folder, so you can check that everything works:

```bash
python -m collector.collect --max-pages 2 --out data/pilot
python -m collector.build_tables --out data/pilot
python -m collector.show_episode 32 --out data/pilot
```

## Step B: full run (a few hours)

```bash
nohup python -m collector.collect > collect.log 2>&1 &     # runs in background, survives logout
tail -f collect.log                                         # watch progress (Ctrl+C stops watching, not the job)
```

`tmux` works as well if you prefer it. When it finishes, build the tables:

```bash
python -m collector.build_tables
```

**Expected time and size** (full history, with a token): this is about 5,000–8,000 requests, so
roughly **1–3 hours**. The raw JSONL is about 1–3 GB and the CSV tables are a few hundred MB.

## Stopping and resuming

You can stop at any time (Ctrl+C, `kill`, network failure). Then run **the same command again**:

```
[issues] already complete, skipping
[issue_comments] resuming at page 812
```

Progress is stored in `data/raw/huggingface__transformers/_checkpoints.json`. To start from scratch,
delete the whole `data/raw/huggingface__transformers/` folder.

## Running only some steps

```bash
python -m collector.collect --steps pr_details,pr_reviews_extra
```

Step names are `repo`, `issues`, `issue_comments`, `review_comments`, `pr_details` and `pr_reviews_extra`.

## Checking the result

1. Open `data/raw/huggingface__transformers/manifest.json`:
   - `steps_complete` should be `true` for every step
   - `record_counts.issues.jsonl` should be about the number of issues plus PRs on GitHub
     (~48,400 in Sept 2026)
2. Check the tables quickly in Python:
   ```python
   import pandas as pd
   items = pd.read_csv("data/tables/huggingface__transformers/items.csv")
   print(items.item_type.value_counts())          # ~19.5k issues, ~28.9k PRs
   print(items.item_number.is_unique)             # True
   print(items[items.item_type == "pull_request"].merged.isna().sum())  # should be 0
   ```
3. Look at a few discussions with `python -m collector.show_episode <number>` and compare them
   with the page on github.com.

## Other repositories (later)

The same code works for any repository:

```bash
python -m collector.collect --owner microsoft --repo DeepSpeed
python -m collector.collect --owner NVIDIA --repo Megatron-LM
```
