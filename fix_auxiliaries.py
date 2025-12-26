# fix_auxiliaries.py
from __future__ import annotations

from typing import Dict, Any, List
import firebase_admin
from firebase_admin import credentials, firestore


# ---- CONFIG ----
SERVICE_ACCOUNT_PATH = r"serviceAccountKey.json"  # <-- change this
DATABASE_ID = "isizulu"
LEXICON_COLLECTION = "lexicon_words"  # <-- change if yours is different
ANALYSIS_VERSION = "v1"
ANALYSIS_MODEL = "rule_fix"

AUXILIARY_LEMMAS: Dict[str, str] = {
    "se": "perfective",
    "kade": "past-perfect",
    "be": "sequential-past",
    "ya": "present-emphatic",
    "nga": "potential",
    "ma": "hortative",
    "ka": "negative-perfect",
    "ye": "past-linker",
    "zo": "future-marker",
}


def _normalize(s: Any) -> str:
    return (str(s).strip().lower() if s is not None else "")


def _doc_token_from_id(doc_id: str) -> str:
    # doc ids are like "zu_kade"
    if doc_id.startswith("zu_"):
        return doc_id[3:]
    return doc_id


def build_aux_fix(doc_id: str, doc: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Return an update dict if this doc should be fixed, else None.
    """
    lemma = _normalize(doc.get("lemma"))
    token = _normalize(_doc_token_from_id(doc_id))

    # If lemma missing but token itself is a known auxiliary, set lemma to token
    if not lemma and token in AUXILIARY_LEMMAS:
        lemma = token

    aux_type = AUXILIARY_LEMMAS.get(lemma)
    if not aux_type:
        return None

    # Determine if update is actually needed
    pos = _normalize(doc.get("pos"))
    has_inf = doc.get("infinitive") not in (None, "", [])
    has_nc = doc.get("nounClass") not in (None, "", [])

    if pos == "auxiliary" and doc.get("auxiliaryType") == aux_type and not has_inf and not has_nc:
        # Already correct
        return None

    # Build patch
    patch: Dict[str, Any] = {
        "lemma": lemma,  # ensure it’s populated
        "pos": "auxiliary",
        "auxiliaryType": aux_type,
        "analysisVersion": ANALYSIS_VERSION,
        "analysisModel": ANALYSIS_MODEL,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }

    # Remove misleading fields
    patch["infinitive"] = firestore.DELETE_FIELD
    patch["nounClass"] = firestore.DELETE_FIELD

    # Notes
    prev_notes = doc.get("analysisNotes")
    note_line = f"Rule fix: lemma '{lemma}' treated as auxiliary ({aux_type})."
    if isinstance(prev_notes, str) and prev_notes.strip():
        if note_line not in prev_notes:
            patch["analysisNotes"] = prev_notes.strip() + " | " + note_line
    else:
        patch["analysisNotes"] = note_line

    return patch


def main():
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)

    db = firestore.client(database_id=DATABASE_ID)
    col = db.collection(LEXICON_COLLECTION)

    print("Scanning lexicon collection:", LEXICON_COLLECTION)

    batch = db.batch()
    pending = 0
    updated = 0
    scanned = 0

    # Stream all docs (for large collections this can take time, but it's safe)
    for snap in col.stream():
        scanned += 1
        doc_id = snap.id
        doc = snap.to_dict() or {}

        patch = build_aux_fix(doc_id, doc)
        if patch is None:
            continue

        ref = col.document(doc_id)
        batch.set(ref, patch, merge=True)
        pending += 1
        updated += 1

        # Firestore batch limit is 500; keep buffer
        if pending >= 400:
            batch.commit()
            print(f"Committed 400 updates... (scanned={scanned}, updated={updated})")
            batch = db.batch()
            pending = 0

    if pending:
        batch.commit()

    print("Done.")
    print("Docs scanned:", scanned)
    print("Docs updated:", updated)


if __name__ == "__main__":
    main()
