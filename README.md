# Accuracy vs. Sustainability: How Developers Negotiate Green Trade-offs

Social Computing course project. We study how developers in open-source LLM repositories
discuss and negotiate sustainability-related trade-offs (accuracy, performance, compute/resource
cost, maintainability, development effort).

- **RQ1:** What types of sustainability-related trade-offs emerge in open-source LLM development discussions?
- **RQ2:** How do developers justify prioritizing sustainability or competing goals?
- **RQ3:** How are disagreements about sustainability-related trade-offs discussed and resolved?

**Current stage:** raw data collection. The dataset holds the **10,000 newest issues and PRs of
`huggingface/transformers` created before 2026-09-01**, with all their comments and reviews. Preprocessing,
filtering, analysis, DeepSpeed and Megatron-LM come later.

## Quickstart

```bash
# 1. one-time setup (details: docs/02_setup.md)
~/.local/bin/uv venv .venv && ~/.local/bin/uv pip install -p .venv -r requirements.txt
cp .env.example .env          # then paste your GitHub token into .env
source .venv/bin/activate

# 2. small test run (1-2 minutes)
python -m collector.collect --max-items 300 --until 2026-09-01 --out data/test300
python -m collector.build_tables --out data/test300

# 3. the dataset: 10,000 newest items before 2026-09-01 (~40 min; safe to stop and restart)
python -m collector.collect --max-items 10000 --until 2026-09-01
python -m collector.build_tables

# 4. look at one discussion
python -m collector.show_episode 1234
```

## Documentation

| File | What it explains |
|---|---|
| [docs/00_overview.md](docs/00_overview.md) | Big picture, folder map, status |
| [docs/01_collection_plan.md](docs/01_collection_plan.md) | GitHub data model, which APIs we use and why, limitations |
| [docs/02_setup.md](docs/02_setup.md) | Python environment + creating a GitHub token |
| [docs/03_schema.md](docs/03_schema.md) | Every table and column |
| [docs/04_running.md](docs/04_running.md) | How to run, resume, check the collection |
| [docs/05_sample_data.md](docs/05_sample_data.md) | Real sample rows and a reconstructed discussion |
| [docs/worklog.md](docs/worklog.md) | Dated log of what was done |
