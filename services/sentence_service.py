from __future__ import annotations

import traceback
from typing import Callable, Dict, Any, List

from models import SentenceAI
from utils_text import tokenize_zu
from utils.logger import log

def sentence_id_from_index(index_1_based: int) -> str:
    return f"{index_1_based:04d}"

class SentenceService:
    def __init__(self, repo, gemini):
        self.repo = repo
        self.gemini = gemini

    def build_sentence_doc(self, idx: int, text_zu: str, build_tokens: bool = True) -> Dict[str, Any]:
        tokens: List[str] = tokenize_zu(text_zu) if build_tokens else []

        translation = ""
        grammar_brief = ""
        concepts: List[str] = []

        try:
            translation, grammar_brief, concepts = self.gemini.translate_and_explain(text_zu)
        except Exception:
            translation = ""
            grammar_brief = "Gemini error: translation/grammar unavailable for this sentence."
            concepts = ["gemini_error"]

        sent_ai = SentenceAI(
            index=idx,
            text_zu=text_zu,
            translation_en=translation,
            grammar_brief=grammar_brief,
            concepts=concepts,
        )
        data = sent_ai.to_firestore(model_name=self.gemini.model)
        data["tokens"] = tokens
        return {"sentence_id": sentence_id_from_index(idx), "data": data}

    def save_sentences_incremental(
        self,
        story_id: str,
        sentence_docs: List[Dict[str, Any]],
        flush_every: int,
        progress: Callable[[str], None],
    ) -> None:
        if not sentence_docs:
            return
        flush_every = max(1, int(flush_every))

        remaining = len(sentence_docs) % flush_every
        # Flush complete chunks
        for i in range(0, len(sentence_docs) - remaining, flush_every):
            chunk = sentence_docs[i:i + flush_every]
            try:
                log(progress, "INFO", f"Flushing {len(chunk)} sentence(s) to Firestore...")
                self.repo.write_sentences_batch(story_id, chunk)
            except Exception as e:
                log(progress, "ERROR", "Failed to flush sentence batch to Firestore.")
                log(progress, "ERROR", str(e))
                log(progress, "ERROR", traceback.format_exc())

        # Flush remaining
        if remaining:
            chunk = sentence_docs[-remaining:]
            try:
                log(progress, "INFO", f"Flushing remaining {len(chunk)} sentence(s) to Firestore...")
                self.repo.write_sentences_batch(story_id, chunk)
            except Exception as e:
                log(progress, "ERROR", "Failed to flush remaining sentences to Firestore.")
                log(progress, "ERROR", str(e))
                log(progress, "ERROR", traceback.format_exc())
