# rules/auxiliary_explain.py

AUX_TYPE_EXPLANATIONS = {
    "perfective": {
        "title": "Already / now (perfective)",
        "meaning": "Shows something has already happened or is now the case.",
        "pattern": "SC + se + (main verb)  OR  SC + se + (copulative/predicate)",
        "example_zu": "Usefikile.",
        "example_en": "He/she has already arrived."
    },
    "past-perfect": {
        "title": "Had been (past perfect / experiential)",
        "meaning": "Shows an action/state had been true for some time before another past moment.",
        "pattern": "SC + ye + kade + (main verb, often in participial form)",
        "example_zu": "Wayekade engekho isikhathi eside.",
        "example_en": "He/she had been away for a long time."
    },
    "sequential-past": {
        "title": "Then / already (sequence in the past)",
        "meaning": "Often used to show sequence: 'then' / 'already' in past narration.",
        "pattern": "SC + be/se + (main verb)",
        "example_zu": "Wabe esehamba.",
        "example_en": "Then he/she left."
    },
    "present-emphatic": {
        "title": "Emphasis / habitual (present emphatic)",
        "meaning": "Adds emphasis or habitual sense; not always translated.",
        "pattern": "SC + ya + (main verb)",
        "example_zu": "Uyahamba.",
        "example_en": "He/she DOES go / He/she is going."
    },
    "potential": {
        "title": "May / might (potential mood)",
        "meaning": "Expresses possibility or permission depending on context.",
        "pattern": "SC + nga + (main verb)",
        "example_zu": "Angahamba.",
        "example_en": "He/she may go."
    },
    "hortative": {
        "title": "Let / should (hortative)",
        "meaning": "Used to suggest/encourage an action.",
        "pattern": "ma + (verb) / SC + ma + (verb)",
        "example_zu": "Makahambe.",
        "example_en": "Let him/her go."
    },
    "negative-perfect": {
        "title": "Not yet / never (negative perfect-like)",
        "meaning": "Commonly appears in negative constructions to express 'not yet'.",
        "pattern": "a-ka- + (verb)",
        "example_zu": "Akakafiki.",
        "example_en": "He/she has not arrived yet."
    },
    "past-linker": {
        "title": "Past linker (-ye-)",
        "meaning": "Links subject concord to past narration forms; often fused into verb forms.",
        "pattern": "SC + ye + (stem/auxiliary)",
        "example_zu": "Wayehamba.",
        "example_en": "He/she was walking / went (context)."
    },
    "future-marker": {
        "title": "Future marker (-zo- / -yo-)",
        "meaning": "Marks future action.",
        "pattern": "SC + zo/yo + (verb)  (yo is a common variant of zo)",
        "example_zu": "Uzohamba.",
        "example_en": "He/she will go."
    },
}


def explain_auxiliary(aux_type: str) -> str:
    info = AUX_TYPE_EXPLANATIONS.get(aux_type)
    if not info:
        return "Auxiliary: (no explanation available for this type yet.)"

    return (
        f"Auxiliary meaning: {info['title']}\n"
        f"- Meaning: {info['meaning']}\n"
        f"- Common pattern: {info['pattern']}\n"
        f"- Example: {info['example_zu']}\n"
        f"- English: {info['example_en']}"
    )
