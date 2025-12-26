# gemini_client.py
import json
from typing import List, Tuple
from google import genai
from models import LexiconAnalysis

SYSTEM_STYLE = """You are an expert isiZulu tutor.
Be concise and accurate.
"""

SYSTEM_JSON = """You are an expert isiZulu linguistics assistant.
Be conservative and do NOT guess.
Return strictly valid JSON only (no markdown, no extra text).
"""


def _extract_json(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    if (t.startswith("[") and t.endswith("]")) or (t.startswith("{") and t.endswith("}")):
        return t
    start_candidates = [i for i in [t.find("["), t.find("{")] if i != -1]
    if not start_candidates:
        return ""
    start = min(start_candidates)
    end = max(t.rfind("]"), t.rfind("}"))
    if end == -1 or end <= start:
        return ""
    return t[start:end + 1]


class GeminiClient:
    def __init__(self, api_key: str, model: str):
        self.model = model
        self.client = genai.Client(api_key=api_key)

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass

    # -----------------------------
    # Sentence: translation + grammar
    # -----------------------------
    def translate_and_explain(self, sentence_zu: str) -> Tuple[str, str, List[str]]:
        prompt = f"""{SYSTEM_STYLE}

Given this isiZulu sentence:
{sentence_zu}

Output exactly 3 lines:
1) ENGLISH TRANSLATION: <one natural English sentence>
2) GRAMMAR BRIEF: <1-2 lines explaining key grammar used>
3) CONCEPTS: <comma-separated keywords, e.g. subjunctive, object concord, negative past>

No extra text.
"""
        resp = self.client.models.generate_content(model=self.model, contents=prompt)
        text = (getattr(resp, "text", "") or "").strip()

        translation = ""
        grammar = ""
        concepts: List[str] = []

        for line in text.splitlines():
            line = line.strip()
            if line.lower().startswith("1)"):
                translation = line.split(":", 1)[-1].strip()
            elif line.lower().startswith("2)"):
                grammar = line.split(":", 1)[-1].strip()
            elif line.lower().startswith("3)"):
                raw = line.split(":", 1)[-1].strip()
                concepts = [c.strip() for c in raw.split(",") if c.strip()]

        if not translation:
            translation = text[:300].strip()
        if not grammar:
            grammar = "Grammar explanation unavailable."

        return translation, grammar, concepts

    # -----------------------------
    # Lexicon: lemma + POS + noun class
    # -----------------------------
    def analyze_tokens(self, tokens: List[str]) -> List[LexiconAnalysis]:
        tokens = [t.strip() for t in tokens if t.strip()]
        if not tokens:
            return []

        payload = {"language": "zu", "tokens": tokens}

        prompt = f"""{SYSTEM_JSON}

TASK: Build dictionary metadata for isiZulu tokens.

Return a JSON array of objects in the SAME ORDER as input tokens.
Each object must have EXACT keys:
token, lemma, pos, noun_class, infinitive, notes, confidence

Allowed pos values:
- noun
- verb
- adjective
- adverb
- pronoun
- conjunction
- particle
- preposition
- numeral
- interjection
- ideophone
- proper_noun
- unknown

Rules:
- If token is a NAME (e.g., uThapelo, uRefilwe, uBless), set pos="proper_noun", lemma=null, noun_class=null, infinitive=null.
- If noun: lemma should be the basic noun form; noun_class like "1/2", "3/4", "5/6", "7/8", "9/10", "11/10", "14", "15" only if confident.
- If verb: infinitive should be "uku..." form if confident; else null.
- If unsure about anything, put null and pos="unknown" (or more general).
- Confidence: 0..1 or null.

INPUT:
{json.dumps(payload, ensure_ascii=False)}
"""
        resp = self.client.models.generate_content(model=self.model, contents=prompt)
        raw = (getattr(resp, "text", "") or "").strip()
        js = _extract_json(raw)

        if not js:
            return [
                LexiconAnalysis(token=t, lemma=None, pos="unknown", noun_class=None,
                               infinitive=None, notes="No JSON returned.", confidence=None)
                for t in tokens
            ]

        try:
            arr = json.loads(js)
            out: List[LexiconAnalysis] = []
            if not isinstance(arr, list):
                raise ValueError("Expected a JSON array.")

            for i, item in enumerate(arr):
                tok = str(item.get("token") or tokens[i])
                out.append(
                    LexiconAnalysis(
                        token=tok,
                        lemma=item.get("lemma"),
                        pos=item.get("pos"),
                        noun_class=item.get("noun_class"),
                        infinitive=item.get("infinitive"),
                        notes=item.get("notes"),
                        confidence=item.get("confidence"),
                    )
                )

            while len(out) < len(tokens):
                t = tokens[len(out)]
                out.append(LexiconAnalysis(token=t, lemma=None, pos="unknown", noun_class=None,
                                           infinitive=None, notes="Missing model row.", confidence=None))
            return out

        except Exception as e:
            return [
                LexiconAnalysis(token=t, lemma=None, pos="unknown", noun_class=None,
                               infinitive=None, notes=f"JSON parse error: {e}", confidence=None)
                for t in tokens
            ]
