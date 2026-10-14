"""
The keyword list for finding sustainability-related discussions.

This is the only file to edit when tuning the filter. See docs/06_filtering.md for why
each term is here (or was left out).

Structure:  GROUPS[group] = {"label": ..., "strong": {term: regex}, "weak": {term: regex}}
- strong: the term alone is enough evidence for the group
- weak:   the term is common in this repo for other reasons; it only counts together with other terms
- term:   the canonical name stored in keyword_hits.csv (the exact matched text is stored too)

All patterns are matched against cleaned, NFKC-normalized, lowercased text (filtering/clean_text.py),
so they are written in lowercase. There is no automatic stemming: suffixes, plurals,
separators and US/UK spellings are written into the patterns by hand.
"""

import re

SEP = r"[-_ ]?"  # "trade-off" / "trade off" / "tradeoff", "kv_cache" / "kv-cache" / "kv cache"

GROUPS = {
    "A": {
        "label": "explicit sustainability / environmental",
        "strong": {
            "sustainab*": r"\bsustainab\w*",
            "energy consumption/efficiency": rf"\benergy{SEP}(consumption|efficien\w*|usage|use|cost|aware|saving|reduction)",
            "power consumption/efficiency": rf"\bpower{SEP}(consumption|usage|efficien\w*|draw)",
            "watt / kwh / joule": r"\b(watts?|watt-hours?|kwh|joules?)\b",
            "carbon footprint/emissions": rf"\bcarbon{SEP}(footprint|emissions?|efficien\w*|intensity)",
            "co2 / ghg": r"\bco2e?\b|carbon dioxide|greenhouse|\bghg\b",
            "green ai/software/computing": r"\bgreen (ai|software|computing)\b",
            "environmental impact": r"\b(environmental(ly)?|ecological) (impact|cost|footprint|friendly)",
            "climate": r"\bclimate\b",
        },
        "weak": {
            "energy": r"\benergy\b",
            "electricity": r"\belectricity\b",
        },
    },
    "B": {
        "label": "compute / resource cost",
        "strong": {
            "compute cost": rf"\b(compute|computational){SEP}(cost|budget|resources?|efficien\w*|overhead|burden)",
            "gpu hours": rf"\bgpu{SEP}hours?\b",
            "gpu/cpu utilization": rf"\b(gpu|cpu){SEP}(utili[sz]ation|usage|consumption)",
            "resource usage/efficiency": rf"\bresources?{SEP}(cost|efficien\w*|usage|consumption|utili[sz]ation|saving|intensive|hungry)",
            "training/inference cost": rf"\b(training|inference){SEP}costs?\b",
            "flops": r"\b[gt]?flops\b",
            "wasteful": r"\bwasteful\b",
        },
        "weak": {
            "expensive/cheap": r"\b(expensive|costly|cheap|cheaper)\b",
            "training/inference time": rf"\b(training|inference){SEP}time\b",
        },
    },
    "C": {
        "label": "memory",
        "strong": {
            "memory usage/footprint": rf"\b(memory|vram){SEP}(footprint|usage|consumption|efficien\w*|overhead|savings?|reduction|requirements?|pressure|spikes?|bloat)",
            "peak memory": r"\bpeak memory\b",
            "gpu/cpu memory": r"\b(gpu|cpu) memory\b",
            "oom": r"\boom\b|\bout[- ]of[- ]memory\b",
            "vram": r"\bvram\b",
            "memory leak": r"\bmemory leaks?\b",
        },
        "weak": {
            "memory": r"\bmemory\b",
            "offload": r"\boffload\w*",
            "kv cache": rf"\bkv{SEP}cache\b",
        },
    },
    "D": {
        "label": "speed / runtime performance",
        "strong": {
            "latency": r"\blatency\b",
            "throughput": r"\bthroughput\b",
            "tokens/s": r"\btok(ens)?/s\b|\btokens per second\b",
            "speedup/slowdown": rf"\bspeed{SEP}ups?\b|\bslow{SEP}downs?\b|\b\d+(\.\d+)?x (faster|slower)\b",
            "performance regression": r"\b(perf|performance|speed) regressions?\b",
            # "maintenance overhead" belongs to group G, not here
            "overhead": r"(?<!maintenance )\boverhead\b",
            "execution time": rf"\bexecution time\b|\bwall{SEP}clock\b|\b(inference|training) speed\b|\bruntime (cost|overhead)\b",
        },
        "weak": {
            "faster/slower": r"\b(faster|slower)\b",
            "benchmark": r"\bbenchmark\w*",
        },
    },
    "E": {
        "label": "efficiency techniques",
        "strong": {},  # everyday features in transformers; never enough on their own
        "weak": {
            "quantization": r"\bquantiz\w*",
            "low-bit dtype": r"\b(int8|int4|fp8|fp4|nf4)\b",
            "mixed precision": r"\bmixed precision\b",
            "pruning": r"\bprun(e|ed|ing)\b",
            "sparsity": r"\bsparsity\b",
            "distillation": r"\bdistill\w*",
            "lora/peft": r"\blora\b|\bpeft\b|\bparameter[- ]efficient\b",
            "flash attention": rf"\bflash{SEP}att\w*",
            "gradient checkpointing": rf"\bgradient{SEP}checkpointing\b",
            "model compression": r"\bmodel compression\b",
        },
    },
    "F": {
        "label": "accuracy / quality (competing concern)",
        "strong": {
            "accuracy drop": rf"\baccuracy{SEP}(drop|loss|degradation|regression|hit)s?\b|\b(quality|performance) degradation\b",
            "perplexity": r"\bperplexity\b",
        },
        "weak": {
            "accuracy": r"\baccuracy\b",
            "quality": r"\bquality\b",
            "logits": r"\blogits\b",
            "numerical precision/stability": r"\bnumerical (precision|stability)\b",
        },
    },
    "G": {
        "label": "maintainability / development effort (competing concern; technical sustainability)",
        "strong": {
            "maintainability": r"\bmaintainab\w*",
            "maintenance burden": rf"\bmaintenance{SEP}(burden|cost|overhead)",
            "technical debt": r"\b(technical|tech) debt\b",
            "bloat": r"(?<!memory )(?<!vram )\bbloat\w*",
            "development effort": r"\b(development|implementation|engineering|developer) effort\b",
            "waste of time": r"\bwast(e|ing) (of )?(\w+ ){0,2}time\b",
        },
        "weak": {
            "maintenance": r"\bmaintenance\b",
            "complexity": r"\bcomplexity\b",
            "code duplication": r"\bcode duplication\b",
        },
    },
    "H": {
        "label": "trade-off / negotiation language",
        "strong": {
            "trade-off": rf"\btrade{SEP}offs?\b",
            "at the cost of": r"\bat the (cost|expense) of\b",
            "worth it": r"\b(not )?worth it\b",
            "cost/benefit": r"\bcost[/ -]benefit\b",
            "downside": r"\bdownsides?\b",
            "compromise": r"\bcompromis\w*",
        },
        "weak": {
            "balance between": r"\bbalance between\b",
            "prioritize": r"\bprioriti[sz]\w*",
        },
    },
}

# Sustainability concern. Group E (techniques) is recorded but never selects an item, not even
# together with other weak terms: "quantization + memory" mostly comes from ordinary bug reports.
CORE = ["A", "B", "C", "D"]
COMPETING = ["F", "G", "H"]  # competing concern or trade-off language


def compiled_terms():
    """[(group, strength, term, compiled_regex), ...] in a fixed order."""
    out = []
    for group, spec in GROUPS.items():
        for strength in ("strong", "weak"):
            for term, pattern in spec[strength].items():
                out.append((group, strength, term, re.compile(pattern)))
    return out
