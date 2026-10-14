"""
Clean issue/PR/comment text before keyword matching.

The goal is to keep only what people actually wrote in prose. Removed:
- the PR / issue template and other repeated boilerplate (reviewer tag lists, CI badges)
- code: fenced blocks, inline code, tracebacks, <details> blocks (logs), the "### System Info" section
- quoted replies ("> ..."), so text quoted from an earlier comment is not counted twice
- URLs, @mentions, HTML tags and comments

The original text in tables/ is never changed; this works on a copy.
"""

import re
import unicodedata
from collections import Counter

BADGE_BLOCK = re.compile(r"<!--\s*ci-dashboard-badge:start\s*-->.*?<!--\s*ci-dashboard-badge:end\s*-->", re.S)
HTML_COMMENT = re.compile(r"<!--.*?(-->|$)", re.S)
FENCED_CODE = re.compile(r"```.*?(```|$)|~~~.*?(~~~|$)", re.S)
DETAILS = re.compile(r"<details>.*?(</details>|$)", re.S | re.I)
SYSTEM_INFO = re.compile(r"^#+\s*system info.*?(?=^#+\s|\Z)", re.S | re.I | re.M)
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")           # ![alt](src), also the inside of badge links
EMPTY_LINK = re.compile(r"\[\s*\]\([^)]*\)")          # what is left of [![badge](...)](link)
INLINE_CODE = re.compile(r"`[^`\n]*`")
URL = re.compile(r"https?://\S+|www\.\S+")
MENTION = re.compile(r"(?<![\w.])@[\w-]+")
HTML_TAG = re.compile(r"</?[a-z][^>]*>", re.I)
TRACEBACK_LINE = re.compile(r"traceback \(most recent call last\)|file \"[^\"]*\", line \d+|^\s*\w*(error|exception):", re.I)
SPACES = re.compile(r"[ \t]+")


def normalize(text):
    """Unicode NFKC + lowercase. NFKC turns e.g. non-breaking hyphens/spaces and full-width letters into plain ones."""
    return unicodedata.normalize("NFKC", text).lower()


def norm_line(line):
    return SPACES.sub(" ", normalize(line).strip())


def find_boilerplate(texts, min_count=20):
    """Lines that appear in at least `min_count` different texts (templates, tag lists, bot footers)."""
    counts = Counter()
    for text in texts:
        if not isinstance(text, str):
            continue
        counts.update({norm_line(line) for line in text.split("\n")})
    return {line for line, n in counts.items() if n >= min_count and len(line) > 3}


def clean(text, boilerplate=frozenset()):
    if not isinstance(text, str) or not text:
        return ""
    for pattern in (BADGE_BLOCK, HTML_COMMENT, FENCED_CODE, DETAILS, SYSTEM_INFO):
        text = pattern.sub(" ", text)
    kept = []
    for line in text.split("\n"):
        if line.lstrip().startswith(">"):
            continue
        if norm_line(line) in boilerplate or TRACEBACK_LINE.search(line):
            continue
        kept.append(line)
    text = "\n".join(kept)
    for pattern in (IMAGE, EMPTY_LINK, INLINE_CODE, URL, MENTION, HTML_TAG):
        text = pattern.sub(" ", text)
    return SPACES.sub(" ", normalize(text)).strip()
