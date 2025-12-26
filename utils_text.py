import re
from typing import List

_SENT_SPLIT_RE = re.compile(r"(?<=[\.\!\?])\s+")

def split_into_sentences(text: str) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    text = re.sub(r"\s+", " ", text).strip()
    parts = _SENT_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]

# Keep isiZulu letters; keep apostrophe and hyphen; remove other punctuation
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:['\-][A-Za-zÀ-ÖØ-öø-ÿ]+)*")

def tokenize_zu(sentence: str) -> List[str]:
    s = sentence.strip()
    tokens = _TOKEN_RE.findall(s)
    # normalize spaces; keep case for proper-noun detection
    return [t for t in tokens if t]
