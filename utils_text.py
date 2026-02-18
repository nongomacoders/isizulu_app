import re
from typing import List

_SENT_SPLIT_RE = re.compile(r"(?<=[\.\!\?])\s+")
_LINE_SPLIT_RE = re.compile(r"\n+")

def split_into_sentences(text: str) -> List[str]:
    """Splits user-pasted text into sentence-like units.

    Important behavior for this app:
    - Do NOT collapse newlines into spaces. Lyrics/poems often rely on line breaks.
    - Still split prose on end-of-sentence punctuation (. ! ?).
    """
    text = (text or "").strip()
    if not text:
        return []

    # Normalize Windows/Mac line endings first.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Treat each non-empty line (or paragraph) as a boundary, then split further by .!? inside it.
    chunks = [c.strip() for c in _LINE_SPLIT_RE.split(text) if c.strip()]

    sentences: List[str] = []
    for chunk in chunks:
        # Collapse spaces/tabs inside a line, but keep the newline boundaries handled above.
        chunk = re.sub(r"[\t\f\v ]+", " ", chunk).strip()
        parts = _SENT_SPLIT_RE.split(chunk)
        for p in parts:
            p = p.strip()
            if p:
                sentences.append(p)

    return sentences

# Keep isiZulu letters; keep apostrophe and hyphen; remove other punctuation
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:['\-][A-Za-zÀ-ÖØ-öø-ÿ]+)*")

def tokenize_zu(sentence: str) -> List[str]:
    s = sentence.strip()
    tokens = _TOKEN_RE.findall(s)
    # normalize spaces; keep case for proper-noun detection
    return [t for t in tokens if t]
