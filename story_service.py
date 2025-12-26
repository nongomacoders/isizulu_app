# story_service.py
# Robust story ingestion service with:
# - incremental sentence saving (prevents "story shell" with 0 sentences)
# - structured progress logging (INFO/WARN/ERROR with timestamps)
# - safe Gemini error handling per sentence and per lexicon batch
# - lexicon base upsert (frequency + surface forms)
# - lexicon enrichment (lemma/POS/noun class/infinitive) ONLY when missing (avoids re-sending whole lexicon)

from __future__ import annotations

from datetime import datetime
import traceback
from typing import Callable, Dict, Any, List, Tuple, Optional

from models import StoryCreateRequest, StoryCreateResult, SentenceAI, LexiconAnalysis
from utils_text import split_into_sentences, tokenize_zu
from gemini_client import GeminiClient
from firestore_repo import FirestoreRepo


# -----------------------------
# Versioning (bump when you change Gemini prompts/logic)
# -----------------------------
CURRENT_ANALYSIS_VERSION = "v1"


# -----------------------------
# Logging
# -----------------------------
def log(progress: Callable[[str], None], level: str, msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    progress(f"[{level}] {ts} - {msg}")


# -----------------------------
# Helpers
# -----------------------------
def sentence_id_from_index(index_1_based: int) -> str:
    return f"{index_1_based:04d}"


def normalize_word_id(token: str) -> str:
    base = token.lower().strip()
    base = base.replace("'", "")
    base = base.replace("-", "_")
    return "zu_" + base


def looks_like_proper_noun(token: str) -> bool:
    # Proper nouns often appear as uThapelo, kwaSithole etc. (internal capitals)
    return any(ch.isupper() for ch in token[1:])


def chunk_list(items: List[str], size: int) -> List[List[str]]:
    if size <= 0:
        return [items]
    return [items[i:i + size] for i in range(0, len(items), size)]


def merge_lexicon_base(existing: Dict[str, Any], token_surface: str) -> Dict[str, Any]:
    doc = dict(existing) if existing else {}
    doc.setdefault("language", "zu")
    doc.setdefault("surfaceForms", [])
    doc.setdefault("frequency", 0)
    doc.setdefault("meaning_primary_en", "")
    doc.setdefault("meanings_en", [])
    doc.setdefault("isProperNoun", False)

    if token_surface not in doc["surfaceForms"]:
        doc["surfaceForms"].append(token_surface)

    doc["frequency"] = int(doc.get("frequency", 0)) + 1

    if looks_like_proper_noun(token_surface):
        doc["isProperNoun"] = True

    return doc


def ensure_learning_defaults(doc: Dict[str, Any], model_name: str) -> None:
    """
    Ensure learning + analysis metadata exist on every lexicon word (without overwriting existing progress).
    """
    doc.setdefault("learning", {
        "known": False,
        "ease": 2.5,
        "intervalDays": 0,
        "repetitions": 0,
        "lastReviewedAt": None,
        "nextReviewAt": None,
    })
    doc.setdefault("analysisVersion", CURRENT_ANALYSIS_VERSION)
    doc.setdefault("analysisModel", model_name)


def analysis_to_firestore_update(a: LexiconAnalysis) -> Dict[str, Any]:
    upd: Dict[str, Any] = {}
    if a.lemma:
        upd["lemma"] = a.lemma
    if a.pos:
        upd["pos"] = a.pos
    if a.noun_class:
        upd["nounClass"] = a.noun_class
    if a.infinitive:
        upd["infinitive"] = a.infinitive
    if a.notes:
        upd["analysisNotes"] = a.notes
    if a.confidence is not None:
        try:
            upd["analysisConfidence"] = float(a.confidence)
        except Exception:
            pass
    return upd


def needs_enrichment(doc: Optional[Dict[str, Any]]) -> bool:
    """
    Only send to Gemini if:
    - doc doesn't exist OR
    - analysisVersion changed OR
    - lemma/pos missing OR
    - noun missing nounClass OR
    - verb missing infinitive
    """
    if not doc:
        return True

    if doc.get("analysisVersion") != CURRENT_ANALYSIS_VERSION:
        return True

    pos = (doc.get("pos") or "").strip()
    lemma = (doc.get("lemma") or "").strip()
    if not pos or not lemma:
        return True

    if pos == "noun" and not (doc.get("nounClass") or "").strip():
        return True

    if pos == "verb" and not (doc.get("infinitive") or "").strip():
        return True

    return False


# -----------------------------
# Service
# -----------------------------
class StoryService:
    def __init__(self, gemini: GeminiClient, repo: FirestoreRepo):
        self.gemini = gemini
        self.repo = repo

    def create_story_from_text(
        self,
        req: StoryCreateRequest,
        progress: Callable[[str], None] = lambda _: None,
        build_lexicon: bool = True,
        lexicon_enrich_with_gemini: bool = True,
        lexicon_batch_size: int = 40,
        flush_every_sentences: int = 5,
    ) -> StoryCreateResult:
        """
        Workflow:
        1) Split story into sentences
        2) Create story doc
        3) For each sentence:
           - tokenize (for lexicon base)
           - Gemini translate + grammar
           - store sentence with tokens
           - flush incrementally
        4) Upsert base lexicon updates (with learning defaults)
        5) Optional lexicon enrichment with Gemini only when needed
        """

        title = (req.title or "").strip() or "Untitled"
        level = (req.level or "").strip() or "Unknown"
        story_text = (req.text_zu or "").strip()

        sentences = split_into_sentences(story_text)
        if not sentences:
            raise ValueError("No sentences found. Paste a story with at least one sentence.")

        log(progress, "INFO", f"Split into {len(sentences)} sentence(s). Creating story...")
        story_id = self.repo.create_story(
            title=title,
            level=level,
            language="zu",
            sentence_count=len(sentences),
        )
        log(progress, "INFO", f"Story created: {story_id}")

        sentence_docs: List[Dict[str, Any]] = []

        lexicon_updates: Dict[str, Dict[str, Any]] = {}
        all_unique_tokens: Dict[str, str] = {}

        log(progress, "INFO", "Generating translations + grammar (Gemini)...")

        for idx, s in enumerate(sentences, start=1):
            s_clean = (s or "").strip()
            if not s_clean:
                log(progress, "WARN", f"Skipping empty sentence at index {idx}")
                continue

            # Tokenize first (used for sentence tokens + lexicon base)
            tokens: List[str] = []
            if build_lexicon:
                try:
                    tokens = tokenize_zu(s_clean)
                except Exception as e:
                    log(progress, "WARN", f"Tokenization failed on sentence {idx}: {e}")
                    tokens = []

                for tok in tokens:
                    wid = normalize_word_id(tok)
                    all_unique_tokens[wid] = tok
                    lexicon_updates[wid] = merge_lexicon_base(lexicon_updates.get(wid, {}), tok)

            # Gemini per-sentence (safe)
            translation = ""
            grammar_brief = ""
            concepts: List[str] = []
            try:
                translation, grammar_brief, concepts = self.gemini.translate_and_explain(s_clean)
            except Exception as e:
                log(progress, "ERROR", f"Gemini failed on sentence {idx}. Saving sentence with empty translation.")
                log(progress, "ERROR", f"Sentence: {s_clean[:200]}")
                log(progress, "ERROR", str(e))
                log(progress, "ERROR", traceback.format_exc())
                translation = ""
                grammar_brief = "Gemini error: translation/grammar unavailable for this sentence."
                concepts = ["gemini_error"]

            sent_ai = SentenceAI(
                index=idx,
                text_zu=s_clean,
                translation_en=translation,
                grammar_brief=grammar_brief,
                concepts=concepts,
            )

            data = sent_ai.to_firestore(model_name=self.gemini.model)
            data["tokens"] = tokens  # <-- store tokens on sentence doc (review/gaps become cheap)

            sid = sentence_id_from_index(idx)
            sentence_docs.append({"sentence_id": sid, "data": data})

            if idx % 5 == 0 or idx == len(sentences):
                log(progress, "INFO", f"Processed {idx}/{len(sentences)} sentence(s)")

            # Incremental flush to Firestore
            if len(sentence_docs) % max(1, int(flush_every_sentences)) == 0:
                try:
                    chunk = sentence_docs[-max(1, int(flush_every_sentences)):]
                    log(progress, "INFO", f"Flushing {len(chunk)} sentence(s) to Firestore...")
                    self.repo.write_sentences_batch(story_id, chunk)
                except Exception as e:
                    log(progress, "ERROR", "Failed to flush sentence batch to Firestore.")
                    log(progress, "ERROR", str(e))
                    log(progress, "ERROR", traceback.format_exc())

        # Flush remaining
        remaining = len(sentence_docs) % max(1, int(flush_every_sentences))
        if remaining:
            try:
                chunk = sentence_docs[-remaining:]
                log(progress, "INFO", f"Flushing remaining {len(chunk)} sentence(s) to Firestore...")
                self.repo.write_sentences_batch(story_id, chunk)
            except Exception as e:
                log(progress, "ERROR", "Failed to flush remaining sentences to Firestore.")
                log(progress, "ERROR", str(e))
                log(progress, "ERROR", traceback.format_exc())

        log(progress, "INFO", f"Total sentence docs prepared: {len(sentence_docs)}")

        # Upsert base lexicon (IMPORTANT: set defaults BEFORE upsert)
        if build_lexicon and lexicon_updates:
            try:
                for data in lexicon_updates.values():
                    ensure_learning_defaults(data, self.gemini.model)

                log(progress, "INFO", f"Upserting {len(lexicon_updates)} lexicon word(s) (base fields)...")
                self.repo.upsert_lexicon_words_batch(
                    [{"word_id": wid, "data": data} for wid, data in lexicon_updates.items()]
                )
            except Exception as e:
                log(progress, "ERROR", "Failed to upsert base lexicon words.")
                log(progress, "ERROR", str(e))
                log(progress, "ERROR", traceback.format_exc())

        # Enrich lexicon with Gemini only when needed
        if build_lexicon and lexicon_enrich_with_gemini and all_unique_tokens:
            try:
                # NOTE: you MUST add this helper in FirestoreRepo:
                # def get_words_batch(self, word_ids: List[str]) -> Dict[str, Dict[str, Any]]: ...
                existing_docs = self.repo.get_words_batch(list(all_unique_tokens.keys()))

                items = sorted(all_unique_tokens.items(), key=lambda x: x[0])  # (wordId, token)
                filtered: List[Tuple[str, str]] = []
                for wid, tok in items:
                    if lexicon_updates.get(wid, {}).get("isProperNoun", False):
                        continue
                    if needs_enrichment(existing_docs.get(wid)):
                        filtered.append((wid, tok))

                log(progress, "INFO", f"Lexicon enrichment candidates: {len(filtered)}")
                if not filtered:
                    log(progress, "INFO", "Lexicon enrichment skipped: nothing needs enrichment.")
                else:
                    word_ids = [wid for wid, _ in filtered]
                    tokens = [tok for _, tok in filtered]

                    enriched_updates: Dict[str, Dict[str, Any]] = {}

                    batch_size = max(5, int(lexicon_batch_size))
                    batches = chunk_list(tokens, batch_size)

                    offset = 0
                    for bi, btoks in enumerate(batches, start=1):
                        log(progress, "INFO", f"Lexicon batch {bi}/{len(batches)} ({len(btoks)} tokens)...")
                        try:
                            analyses: List[LexiconAnalysis] = self.gemini.analyze_tokens(btoks)
                        except Exception as e:
                            log(progress, "ERROR", f"Lexicon Gemini batch {bi} failed. Skipping this batch.")
                            log(progress, "ERROR", str(e))
                            log(progress, "ERROR", traceback.format_exc())
                            offset += len(btoks)
                            continue

                        for j, a in enumerate(analyses):
                            k = offset + j
                            if k >= len(word_ids):
                                continue

                            wid = word_ids[k]
                            upd = analysis_to_firestore_update(a)
                            if upd:
                                upd["analysisVersion"] = CURRENT_ANALYSIS_VERSION
                                upd["analysisModel"] = self.gemini.model
                                enriched_updates[wid] = upd

                        offset += len(btoks)

                    if enriched_updates:
                        log(progress, "INFO", f"Writing {len(enriched_updates)} enriched lexicon update(s)...")
                        self.repo.upsert_lexicon_words_batch(
                            [{"word_id": wid, "data": data} for wid, data in enriched_updates.items()]
                        )
                    else:
                        log(progress, "WARN", "No lexicon enrichment updates produced.")
            except Exception as e:
                log(progress, "ERROR", "Unexpected failure during lexicon enrichment.")
                log(progress, "ERROR", str(e))
                log(progress, "ERROR", traceback.format_exc())

        log(progress, "INFO", "Story import completed.")
        log(progress, "INFO", f"Story ID: {story_id}")
        log(progress, "INFO", f"Sentences saved (attempted): {len(sentence_docs)}")
        log(progress, "INFO", f"Lexicon words processed: {len(lexicon_updates)}")

        return StoryCreateResult(story_id=story_id, sentence_count=len(sentence_docs))
