# 06 · Filtering sustainability-related discussions

This stage selects the discussions that talk about sustainability-related concerns, using keywords.
It reads the tables from the collection stage and never changes them.

```bash
python -m filtering.filter_discussions          # ~25 s
python -m collector.show_episode 40073          # read one of the selected discussions
```

| File | Role |
|---|---|
| `filtering/keywords.py` | the keyword list (**the only file to edit when tuning**) |
| `filtering/clean_text.py` | text cleaning before matching |
| `filtering/filter_discussions.py` | matching, scoring, tiers, outputs |

## 1. What "sustainability-related" means here

The project studies trade-offs between sustainability and competing goals (README, RQ1–3). The keywords
are grouped as follows. Groups A–D are the **sustainability concern**, E covers **efficiency techniques**, and F–H are the
**other side of a trade-off**:

| Group | Meaning |
|---|---|
| A | explicit sustainability / environmental (energy, carbon, power, climate …) |
| B | compute / resource cost |
| C | memory |
| D | speed / runtime performance |
| E | efficiency techniques (quantization, LoRA, flash attention …) |
| F | accuracy / quality (competing concern) |
| G | maintainability / development effort (competing concern; also "technical sustainability") |
| H | trade-off / negotiation language |

Each group has **strong** terms (enough evidence on their own) and **weak** terms (common in this repository
for other reasons, so they count only together with other evidence).

## 2. The keywords

`*` = any word ending, `[-_ ]` = optional separator. The exact regexes are in `filtering/keywords.py`.

| Group | Strong | Weak |
|---|---|---|
| A | sustainab*, energy consumption/efficien*/usage/use/cost/aware/saving/reduction, power consumption/usage/efficien*/draw, watt(s)/watt-hour/kWh/joule(s), carbon footprint/emission(s)/efficien*/intensity, CO2(e)/carbon dioxide/greenhouse/GHG, green AI/software/computing, environmental(ly)/ecological impact/cost/footprint/friendly, climate | energy, electricity |
| B | compute/computational cost/budget/resource(s)/efficien*/overhead/burden, GPU hour(s), GPU/CPU utili[sz]ation/usage/consumption, resource(s) cost/efficien*/usage/consumption/utili[sz]ation/saving/intensive/hungry, training/inference cost(s), (G/T)FLOPs, wasteful | expensive, costly, cheap(er), training/inference time |
| C | memory/VRAM footprint/usage/consumption/efficien*/overhead/saving(s)/reduction/requirement(s)/pressure/spike(s)/bloat, peak memory, GPU/CPU memory, OOM, out of memory, VRAM, memory leak(s) | memory, offload*, KV cache |
| D | latency, throughput, tok/s, tokens/s, tokens per second, speedup(s), slowdown(s), "N x faster/slower", perf/performance/speed regression(s), overhead (not "maintenance overhead"), execution time, wall-clock, inference/training speed, runtime cost/overhead | faster, slower, benchmark* |
| E | none | quantiz*, int8/int4/fp8/fp4/nf4, mixed precision, prune/pruned/pruning, sparsity, distill*, LoRA, PEFT, parameter-efficient, flash attention*, gradient checkpointing, model compression |
| F | accuracy drop/loss/degradation/regression/hit, quality/performance degradation, perplexity | accuracy, quality, logits, numerical precision/stability |
| G | maintainab*, maintenance burden/cost/overhead, technical/tech debt, bloat* (not "memory bloat"), development/implementation/engineering/developer effort, waste (of) … time | maintenance, complexity, code duplication |
| H | trade-off/tradeoff/trade off(s), at the cost/expense of, (not) worth it, cost/benefit, downside(s), compromis* | balance between, prioriti[sz]* |

### Where the list came from
We merged two candidate lists (one drafted with ChatGPT, one of our own), then **measured every term on the
cleaned data** and read random snippets for the unclear ones. Terms were removed or made weak when most matches
were unrelated:

| Term(s) | Decision | Why (what the data showed) |
|---|---|---|
| but, however, although, instead, alternative, vs/versus, balance, benefit | dropped | in 500–4,400 items each; ordinary English |
| bare *power* | dropped | mostly "power-of-two", "power users" |
| bare *runtime* | dropped | mostly "runtime error", tracebacks |
| bare *waste* | replaced by *wasteful* (B) and *waste of … time* (G) | mostly "waste of (maintainer) time" |
| dependency/dependencies, duplication, recall, F1 | dropped | "list any dependencies" is template text; "duplicate" = duplicate issue/code |
| sparse, compression, checkpointing, fp16/bf16 | dropped | dtype settings and model checkpoints, not efficiency talk |
| CI time, build time | dropped | mostly CI badge text |
| accuracy, quality, precision, maintenance, complexity | kept as weak | common, but useful next to a strong term |
| all group E | weak only | everyday library features in transformers |

## 3. Keyword processing (normalization, no stemming)

- **Unicode NFKC + lowercase** on all text, so that e.g. non-breaking hyphens ("trade‑off") and full-width
  characters match their plain forms.
- **Separator variants** come from one pattern: `trade[-_ ]?off` matches *trade-off*, *trade off* and *tradeoff*.
  `kv[-_ ]?cache` matches *kv_cache*, *kv-cache* and *kv cache*.
- **No automatic stemming or lemmatization** (Porter/Snowball/spaCy). Instead, word endings are written into the patterns by
  hand: `quantiz\w*` (quantize, quantized, quantization), `distill\w*`, `maintainab\w*`, `prun(e|ed|ing)`,
  plurals with `s?`, and US/UK spellings `utili[sz]ation`, `prioriti[sz]e`.
  Why: stemmers break technical tokens (*bf16*, *tok/s*, *OOM*, *FLOPs*) and multi-word phrases, and they merge
  unrelated words (e.g. *prune* and *prunus*). Hand-written patterns are predictable and need no extra package.
- **Word boundaries** (`\b`), so *oom* does not match *room*/*zoom* and *lora* does not match *flora*.
- **No double counting:** a weak hit inside a strong hit's span is dropped (*memory* inside *memory usage*).
- Each pattern has a **canonical term name**. A hit stores both that name and the exact matched text.

## 4. Text cleaning (before matching)

Done on a copy in memory. `tables/` is not changed.

1. **Bots are skipped**: 202 bot-authored items (only their title/body; human comments on them are kept) and
   16,854 bot comments. A bot is either `author_is_bot` or listed in `KNOWN_BOTS`. That list only has
   `HuggingFaceDocBuilderDev` (5,202 identical "The docs for this PR live here" comments), which GitHub does not
   mark as a bot. It was the only account with ≥ 50 comments that were mostly identical.
2. **Removed:** HTML comments, the `ci-dashboard-badge` block, badges and images, fenced code blocks, `<details>`
   blocks (usually logs), the issue template's `### System Info` section, quoted reply lines (`> …`, so quoted
   text is not counted twice), inline code, URLs, @mentions, traceback lines, HTML tags.
3. **Boilerplate lines:** any line that appears in **≥ 20 different texts** is removed (603 lines: the PR and
   issue templates, reviewer tag lists like `- quantization: @SunMarc`, bot footers). This is data-driven, so it
   needs no hand-written template list. None of the removed lines contains a keyword except template lines.
4. **Kept:** markdown tables (benchmark tables with *speedup* / *tok/s* are real evidence).

Effect: 34.4 M characters → 14.9 M. Before cleaning, *quantiz* matched 1,793 items, most of them only through the PR template.

## 5. Selection rule

The unit is the discussion **episode**: title + opening post + all human comments. Each item gets at most one tier,
taken in this order:

| Tier | Rule | Items | Use |
|---|---|---|---|
| `tradeoff` | strong A–D term **and** strong F, G or H term | 99 | main set for RQ1–3 |
| `resource` | strong A–D term | 685 | sustainability concern without an explicit counter-concern |
| `resource_weak` | no strong A–D term, but weak terms from ≥ 2 of A–D, or weak A–D + strong H | 72 | low confidence |
| `technical` | strong G term (maintainability/effort), none of the above | 142 | "technical sustainability"; kept as a separate tier by decision, easy to drop |

`is_candidate` = any tier. **Candidates: 998 of 10,000 items** (703 PRs, 295 issues).
`explicit_green` is a separate flag (strong group-A term): only **7 items**.

Group E never selects an item, not even together with other weak terms. In a check, every one of 10 random items
selected only through E + another weak term (e.g. *quantization + memory*) was an ordinary bug report or a
feature PR.

## 6. Results to keep in mind

- **Explicit environmental vocabulary is almost absent.** After cleaning, there are zero hits for climate, carbon, CO2,
  electricity, environmental impact or GPU-hours. Of the 7 `explicit_green` items:
  three (#39208, #41723, #46851) use *sustainable* to mean "maintainable" ("not a sustainable approach"). #41861
  reports GPU power draw in watts for a Windows slowdown. Two (#45145, #45151) are near-identical "N6 Arithmetic
  energy reduction" posts that look like spam. #44407 (energy-efficiency docs for bitsandbytes quantization) is the
  only clearly environmental discussion.
  Developers here talk about sustainability through **resource proxies** (memory, speed, compute) and not through
  environmental terms. This is a finding in itself.
- Strong terms are mostly precise in snippet checks. Typical noise: *OOM* in plain bug reports, *bloat* used for
  docstrings, *compromise* meaning "break correctness".

## 7. Outputs (`data/filtered/huggingface__transformers/`)

| File | One row per | Main columns |
|---|---|---|
| `keyword_hits.csv` | keyword hit | item_number, source (title/body/comment), comment_id, comment_kind, author, group, strength, term, matched_text, snippet (±80 chars) |
| `items_scored.csv` | item (all 10,000) | `<group>_strong` / `<group>_weak` counts, groups, strong_groups, n_hits, top_terms, explicit_green, tier, is_candidate |
| `candidates.csv` | candidate item | item metadata + tier, groups, top_terms (sorted by tier, then number of hits) |
| `candidate_comments.csv` | human comment of a candidate | all comment columns + has_hit, hit_terms, tier |
| `review_sample.csv` | sampled item | 25 per tier + 50 non-candidates (seed 42), example snippets, empty `label` / `notes` |
| `summary.json` | — | counts per tier, group and term, cleaning statistics |

## 8. Validation (to do by hand)

Fill in `label` (yes/no: is this a sustainability-related discussion?) in `review_sample.csv`. Then:
- **precision per tier** = share of "yes" in that tier
- **missed discussions** = "yes" among the 50 non-candidates (this estimates recall)

If a tier turns out noisy, change the terms in `filtering/keywords.py` (or drop the tier) and re-run.
