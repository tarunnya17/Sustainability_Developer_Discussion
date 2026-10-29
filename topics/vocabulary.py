"""
Words used to describe topics. This is the only file to edit when tuning topic words.

It changes how a topic is *described* (its c-TF-IDF words), not which passages end up together
(that comes from the embeddings, see docs/07_topics.md).

Why the concern keywords are cut out: every passage contains a keyword hit by construction, so with
them the topic words just repeat the filter (memory usage / oom / speedup). Cutting the matched
concern phrases out of the text leaves the *technical context* (kv cache, fp8 kernels, loading ...).
The concern side is not lost: each passage keeps its hit groups A-H as columns.

Only the matched phrase is cut, not every occurrence of its words: "gpu memory" is removed, but
"gpu" elsewhere in the passage stays.
"""

import re

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

from filtering.keywords import compiled_terms

# A token starts with a letter and may contain digits, "_", "-" and ".":
# keeps fp8, mxfp4, kv_cache, from_pretrained, flash-attn
TOKEN_PATTERN = r"(?u)\b[a-z][a-z0-9_\-\.]*[a-z0-9]\b"

# Groups whose matched phrases are cut out of the topic-word text.
# Group E (quantization, LoRA, flash attention ...) names techniques, i.e. context, so it stays.
CONCERN_GROUPS = ["A", "B", "C", "D", "F", "G", "H"]

# Hit terms of a concern group that name a mechanism rather than a concern; they stay too.
KEEP_AS_CONTEXT = {"kv cache", "offload", "logits"}

# Review chatter, contractions (don't -> "don") and template text that survives cleaning.
EXTRA_STOPWORDS = {
    "thanks", "thank", "thx", "lgtm", "nit", "nits", "pls", "please", "hi", "hello", "hey", "sorry",
    "review", "reviewed", "reviewing", "pr", "prs", "comment", "comments",
    "think", "just", "like", "would", "could", "should", "need", "needs", "use", "used", "using",
    "make", "sure", "let", "know", "added", "add", "yes", "ok", "okay", "maybe", "imo", "really",
    "actually", "also", "lot", "good", "great", "nice", "fine", "way", "better", "want", "did", "does",
    "don", "doesn", "didn", "isn", "wasn", "aren", "won", "couldn", "shouldn", "wouldn", "haven",
    "hasn", "ll", "ve", "e.g", "i.e", "etc",
    "contributor", "guideline", "guidelines", "discussed", "approved",
}


def stop_words():
    return sorted(ENGLISH_STOP_WORDS | EXTRA_STOPWORDS)


def concern_patterns():
    """Compiled regexes of the concern terms (from filtering/keywords.py) that are cut out."""
    return [regex for group, _, term, regex in compiled_terms()
            if group in CONCERN_GROUPS and term not in KEEP_AS_CONTEXT]


def cut_concern(text, patterns):
    """The passage with every matched concern phrase removed."""
    for regex in patterns:
        text = regex.sub(" ", text)
    return " ".join(text.split())
