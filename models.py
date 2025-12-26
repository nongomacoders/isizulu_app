# models.py
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


# -----------------------------
# Sentence-level AI output
# -----------------------------

@dataclass
class SentenceAI:
    index: int
    text_zu: str
    translation_en: str
    grammar_brief: str
    concepts: List[str]

    def to_firestore(self, model_name: str) -> Dict[str, Any]:
        return {
            "index": self.index,
            "text_zu": self.text_zu,
            "translation": {
                "en": self.translation_en,
                "model": model_name,
            },
            "grammar": {
                "brief": self.grammar_brief,
                "concepts": self.concepts,
                "model": model_name,
            },
        }


# -----------------------------
# Story creation
# -----------------------------

@dataclass
class StoryCreateRequest:
    title: str
    level: str
    text_zu: str


@dataclass
class StoryCreateResult:
    story_id: str
    sentence_count: int


# -----------------------------
# Lexicon enrichment (THIS WAS MISSING)
# -----------------------------

@dataclass
class LexiconAnalysis:
    token: str
    lemma: Optional[str]
    pos: Optional[str]
    noun_class: Optional[str]   # e.g. "1/2", "7/8"
    infinitive: Optional[str]   # verbs: e.g. "ukulinda"
    notes: Optional[str]
    confidence: Optional[float]

    def to_upsert(self) -> Dict[str, Any]:
        """
        Convert analysis to Firestore update fields.
        """
        out: Dict[str, Any] = {}

        if self.lemma:
            out["lemma"] = self.lemma
        if self.pos:
            out["pos"] = self.pos
        if self.noun_class:
            out["nounClass"] = self.noun_class
        if self.infinitive:
            out["infinitive"] = self.infinitive
        if self.notes:
            out["analysisNotes"] = self.notes
        if self.confidence is not None:
            out["analysisConfidence"] = float(self.confidence)

        return out
