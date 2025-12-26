from __future__ import annotations

import traceback
from typing import Callable, Dict, Any, List, Tuple, Optional
from utils.logger import log
from rules.auxiliaries import apply_auxiliary_override
from models import LexiconAnalysis

CURRENT_ANALYSIS_VERSION = "v1"

def normalize_word_id(token: str) -> str:
    base = token.lower().strip()
    base = base.replace("'", "")
    base = base.replace("-", "_")
    return "zu_" + base

def looks_like_proper_noun(token: str) -> bool:
    return any(ch.isupper() for ch in token[1:])

def chunk_list(items: List[str], size: int) -> List[List[str]]:
    size = max(1, int(size))
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

    # auxiliaries OK without infinitive
    return False

class LexiconService:
    def __init__(self, repo, gemini):
        self.repo = repo
        self.gemini = gemini

    def add_tokens_to_base(
        self,
        tokens: List[str],
        lexicon_updates: Dict[str, Dict[str, Any]],
        all_unique_tokens: Dict[str, str],
    ) -> None:
        for tok in tokens:
            wid = normalize_word_id(tok)
            all_unique_tokens[wid] = tok
            lexicon_updates[wid] = merge_lexicon_base(lexicon_updates.get(wid, {}), tok)

    def upsert_base(
        self,
        lexicon_updates: Dict[str, Dict[str, Any]],
        progress: Callable[[str], None],
    ) -> None:
        if not lexicon_updates:
            return
        for data in lexicon_updates.values():
            ensure_learning_defaults(data, self.gemini.model)

        log(progress, "INFO", f"Upserting {len(lexicon_updates)} lexicon word(s) (base fields)...")
        self.repo.upsert_lexicon_words_batch(
            [{"word_id": wid, "data": data} for wid, data in lexicon_updates.items()]
        )

    def enrich_missing(
        self,
        all_unique_tokens: Dict[str, str],
        lexicon_updates: Dict[str, Dict[str, Any]],
        batch_size: int,
        progress: Callable[[str], None],
    ) -> None:
        if not all_unique_tokens:
            return

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
            return

        word_ids = [wid for wid, _ in filtered]
        toks = [tok for _, tok in filtered]

        enriched_updates: Dict[str, Dict[str, Any]] = {}
        batches = chunk_list(toks, max(5, int(batch_size)))

        offset = 0
        for bi, btoks in enumerate(batches, start=1):
            log(progress, "INFO", f"Lexicon batch {bi}/{len(batches)} ({len(btoks)} tokens)...")
            try:
                analyses: List[LexiconAnalysis] = self.gemini.analyze_tokens(btoks)
            except Exception as e:
                log(progress, "ERROR", f"Lexicon Gemini batch {bi} failed. Skipping.")
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
                    upd = apply_auxiliary_override(upd)
                    upd["analysisVersion"] = CURRENT_ANALYSIS_VERSION
                    upd["analysisModel"] = self.gemini.model
                    enriched_updates[wid] = upd

            offset += len(btoks)

        if enriched_updates:
            log(progress, "INFO", f"Writing {len(enriched_updates)} enriched lexicon update(s)...")
            self.repo.upsert_lexicon_words_batch(
                [{"word_id": wid, "data": data} for wid, data in enriched_updates.items()]
            )
