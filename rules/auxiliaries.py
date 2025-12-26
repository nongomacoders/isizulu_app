from typing import Dict, Any

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
    "yo": "future-marker",  # common variant/allomorph of -zo-
}

def apply_auxiliary_override(update: Dict[str, Any]) -> Dict[str, Any]:
    lemma = (update.get("lemma") or "").strip().lower()
    if not lemma:
        return update

    aux_type = AUXILIARY_LEMMAS.get(lemma)
    if not aux_type:
        return update

    update["pos"] = "auxiliary"
    update["auxiliaryType"] = aux_type
    update.pop("infinitive", None)
    update.pop("nounClass", None)
    update.setdefault("analysisNotes", "Auxiliary detected by rule layer.")
    return update
