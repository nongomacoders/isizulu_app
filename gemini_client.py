# gemini_client.py
import json
import logging
from typing import List, Tuple, Optional

from google import genai
from models import LexiconAnalysis

logger = logging.getLogger(__name__)


SYSTEM_STYLE = """You are an expert isiZulu tutor.
Be concise and accurate.
"""

SYSTEM_JSON = """You are an expert isiZulu linguistics assistant.
Be conservative and do NOT guess.
Return strictly valid JSON only (no markdown, no extra text).
"""


def _truncate(s: str, n: int = 800) -> str:
    s = (s or "")
    if len(s) <= n:
        return s
    return s[:n] + f"... [truncated {len(s) - n} chars]"


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
        try:
            resp = self.client.models.generate_content(model=self.model, contents=prompt)
            text = (getattr(resp, "text", "") or "").strip()
        except Exception:
            logger.exception("Gemini translate_and_explain failed. model=%s sentence=%r", self.model, _truncate(sentence_zu, 200))
            raise

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
        logger.info("Gemini analyze_tokens request. model=%s n_tokens=%d", self.model, len(tokens))

        try:
            resp = self.client.models.generate_content(model=self.model, contents=prompt)
            raw = (getattr(resp, "text", "") or "").strip()
        except Exception:
            logger.exception("Gemini analyze_tokens failed. model=%s tokens=%r", self.model, tokens[:50])
            return [
                LexiconAnalysis(
                    token=t, lemma=None, pos="unknown", noun_class=None,
                    infinitive=None, notes="Gemini request failed.", confidence=None
                )
                for t in tokens
            ]

        js = _extract_json(raw)
        if not js:
            logger.error("Gemini analyze_tokens returned no JSON. model=%s raw=%r", self.model, _truncate(raw))
            return [
                LexiconAnalysis(
                    token=t, lemma=None, pos="unknown", noun_class=None,
                    infinitive=None, notes="No JSON returned.", confidence=None
                )
                for t in tokens
            ]

        try:
            arr = json.loads(js)
            if not isinstance(arr, list):
                raise ValueError("Expected a JSON array.")

            out: List[LexiconAnalysis] = []
            for i, item in enumerate(arr):
                tok = str((item or {}).get("token") or tokens[i])
                item = item or {}
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
                out.append(
                    LexiconAnalysis(
                        token=t, lemma=None, pos="unknown", noun_class=None,
                        infinitive=None, notes="Missing model row.", confidence=None
                    )
                )
            return out

        except Exception:
            logger.exception(
                "Gemini analyze_tokens JSON parse failed. model=%s extracted=%r raw=%r",
                self.model, _truncate(js), _truncate(raw)
            )
            return [
                LexiconAnalysis(
                    token=t, lemma=None, pos="unknown", noun_class=None,
                    infinitive=None, notes="JSON parse error (see logs).", confidence=None
                )
                for t in tokens
            ]

    # -----------------------------
    # Theory docs: grammar concept explanation
    # -----------------------------
    def generate_theory_doc(self, concept_id: str, context_concepts: Optional[List[str]] = None) -> dict:
        cid = (concept_id or "").strip().lower()
        context_concepts = context_concepts or []

        prompt_body = """
You are creating a theory note for an isiZulu learner application.

The learner is reading real isiZulu stories and needs clear, practical explanations.
Write in a teaching tone, not an academic one.

Concept ID: <<CID>>
Related concepts (context only): <<RELATED>>

Return ONLY valid JSON (no markdown outside JSON, no explanations) matching EXACTLY this schema:

{
  "title": "Human-readable title",
  "short": "1–2 sentence learner-friendly summary",
  "body": "Explanation written for learners using emphasis, not rigid sections.",
  "examples": [
    {"zu": "isiZulu example", "en": "English translation", "note": "Why this form is used"}
  ],
  "tags": ["searchable_tag_1", "searchable_tag_2"],
  "level": "Beginner | Intermediate | Advanced"
}

Formatting rules for the **body** field ONLY:
- Use **bold** for key ideas and important forms.
- Use *italics* for meanings, contrasts, or learner reminders.
- Use hyphen bullets only when helpful.
- Use `inline code` for prefixes, verb forms, or patterns.
- Do NOT use tables.
- Do NOT use fenced code blocks.
- Do NOT use boxed sections or rigid headings.
- Keep paragraphs short and readable.

Style and structure rules:
- Start with **what the learner should understand**, not a formal definition.
- Explain the idea in plain English, then show how isiZulu expresses it.
- Emphasize **patterns the learner will see in stories**.
- Avoid repeating the same idea in different wording.
- If a technical term is necessary (e.g. subject concord), define it briefly in simple English.

Auxiliary-specific rules (VERY IMPORTANT):
- If the concept is an auxiliary (e.g. kade, se, ya, nga, ma, ka, ye, zo):
  - Explain what the auxiliary *adds* (time, aspect, emphasis, mood).
  - Explain how it combines with the subject concord and the verb.
  - Mention common contracted forms learners actually encounter.
  - Mention when the auxiliary is **optional**, **emphatic**, or **context-driven**.

Exceptions and irregularities (REQUIRED):
- Include **common exceptions or special cases** learners are likely to encounter.
- Mention:
  - when the form is **not used** even though English would suggest it,
  - when another construction is preferred,
  - or when meaning changes subtly depending on context.
- Present exceptions gently, as *“Learners often notice that…”* or *“In stories, you may also see…”*.
- Do NOT list rare or highly technical exceptions.

Examples rules:
- Include 3–6 examples.
- Examples must sound natural and story-like.
- Prefer narrative or conversational sentences.
- Notes should explain *why* the form is used, not just translate it.

Level guidance:
- Beginner: focus on meaning and recognition.
- Intermediate: highlight patterns, contrasts, and common exceptions.
- Advanced: include nuance or stylistic usage, but keep it readable.

IMPORTANT:
- Output ONLY valid JSON.
- Do NOT include markdown fences.
- Do NOT include comments.
- Do NOT include extra keys.

""".strip()

        prompt = SYSTEM_JSON + "\n\n" + prompt_body.replace("<<CID>>", cid).replace("<<RELATED>>", ", ".join(context_concepts))

        logger.info("Gemini generate_theory_doc request. cid=%s model=%s related=%s", cid, self.model, context_concepts[:10])

        try:
            resp = self.client.models.generate_content(model=self.model, contents=prompt)
            raw = (getattr(resp, "text", "") or "").strip()
        except Exception:
            logger.exception("Gemini generate_theory_doc failed. cid=%s model=%s", cid, self.model)
            raise

        js = _extract_json(raw)
        if not js:
            logger.error("Gemini returned no JSON. cid=%s model=%s raw=%r", cid, self.model, _truncate(raw))
            raise ValueError("No JSON returned for theory doc.")

        try:
            data = json.loads(js)
        except Exception:
            logger.exception(
                "Theory JSON parse failed. cid=%s model=%s extracted=%r raw=%r",
                cid, self.model, _truncate(js), _truncate(raw)
            )
            raise

        out = {
            "title": (data.get("title") or cid.replace("_", " ").title()).strip(),
            "short": (data.get("short") or "").strip(),
            "body": (data.get("body") or "").strip(),
            "examples": data.get("examples") or [],
            "tags": data.get("tags") or [cid],
            "level": (data.get("level") or "Beginner").strip(),
        }
        return out

    # -----------------------------
    # Deep Analysis: Morphological breakdown + Cultural Context
    # -----------------------------
    def analyze_sentence_detailed(self, sentence_zu: str) -> str:
        prompt = f"""{SYSTEM_STYLE}

TASK: Provide a deep linguistic and cultural analysis of this isiZulu sentence.

SENTENCE:
{sentence_zu}

STRUCTURE YOUR RESPONSE IN MARKDOWN:
1. **Natural Translation**: A smooth, contextual English translation.
2. **Literal Translation**: A word-for-word translation to show structure.
3. **Morphological Breakdown**: Provide a breakdown for **EVERY SINGLE WORD** in the sentence.
   - List each word as a main bullet point (e.g., `- **Word**`).
   - Use indented sub-bullets for each component (prefixes, roots, suffixes), explaining their function (e.g., `  - **wa-**: Subject concord`).
   - Do not skip any words from the original sentence.
4. **Grammar & Syntax**: Explain the key grammatical choices (e.g., mood, aspect, rare prefixes).
5. **Cultural/Contextual Nuance**: Explain any idioms, social implications, or cultural context if applicable.

Guidelines:
- Use bold for isiZulu terms.
- Use nested lists for morphological breakdowns (indented sub-bullets for components).
- **Ensure EVERY word from the original sentence is listed in the breakdown section.**
- Be concise but thorough.
"""
        logger.info("Gemini analyze_sentence_detailed request. model=%s sentence=%r", self.model, _truncate(sentence_zu, 100))
        resp = self.client.models.generate_content(model=self.model, contents=prompt)
        return (getattr(resp, "text", "") or "").strip()
