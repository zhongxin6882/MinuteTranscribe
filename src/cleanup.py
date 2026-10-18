from __future__ import annotations

import re

FILLER_PATTERNS = (
    r"\b嗯+\b",
    r"\b呃+\b",
    r"\b啊+\b",
    r"\b这个\b",
    r"\b那个\b",
)


def clean_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"([，。！？、,.!?])\1+", r"\1", cleaned)
    for pattern in FILLER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    return cleaned.strip()

