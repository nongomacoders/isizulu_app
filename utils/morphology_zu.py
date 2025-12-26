# utils/morphology_zu.py

from typing import Dict, Any, List


# Very small starter lists (expand over time)
SUBJECT_BLOCKS = [
    "wawu",  # class 3 past narrative packaging
    "wabe", "babe", "yabe", "zabe", "labe", "kabe",
    "waye", "beye", "saye", "naye", "baye", "zaye",
    "wase", "base", "yase", "zase",
]

# Normal subject concords (SC)
SUBJECT_CONCORDS = [
    "ngi", "u", "si", "ni", "ba",
    "i", "li", "a", "zi", "lu", "bu", "ku",
    "wa", "sa", "ya", "za", "lwa", "bwa", "kwe",  # common fused narrative forms
]

# Relative/participial subject concords (starter set)
RELATIVE_CONCORDS = [
    "aba", "esi", "eli",  # longer first helps
    "e", "o", "a",
]

# TAM markers (stackable). Keep fused/longer forms here too.
# NOTE: include "kabi" so we don't split it into "ka" + "bi" (which would break analysis).
TAM_MARKERS = [
    "kabi",  # "not yet" / negative-perfect-like (often after ka-, e.g., akakabi..., engakabi...)
    "ya", "sa", "se", "be", "ye", "zo", "yo", "nga", "ka"
]

OBJECT_MARKERS = [
    "ngi", "ku", "m", "si", "ni", "ba", "yi", "li", "wa", "zi"
]

FINAL_VOWELS = ["a", "e", "i"]


def _strip_punct(token: str) -> str:
    t = token.strip()
    while t and t[-1] in ".,!?;:”“\"'()[]":
        t = t[:-1]
    while t and t[0] in "“\"'(":
        t = t[1:]
    return t


def breakdown_verb_token(token: str, lemma: str | None = None) -> Dict[str, Any]:
    """
    Heuristic isiZulu verb morphology breakdown.
    Not perfect, but useful for learning patterns.
    """
    raw = token
    t = _strip_punct(token).lower()

    out: Dict[str, Any] = {
        "raw": raw,
        "normalized": t,
        "prefixes": [],
        "tam": [],
        "object": None,
        "root_guess": None,
        "final_vowel": None,
        "explain": [],
    }

    if len(t) < 3:
        out["explain"].append("Too short to analyze.")
        return out

    # Final vowel guess -> define stem FIRST
    if t[-1] in FINAL_VOWELS:
        out["final_vowel"] = t[-1]
        stem = t[:-1]
    else:
        stem = t

    # Try match a fused subject block first (longest first)
    matched_subject_block = None
    for blk in sorted(SUBJECT_BLOCKS, key=len, reverse=True):
        if stem.startswith(blk):
            matched_subject_block = blk
            out["prefixes"].append(blk + "-")
            stem = stem[len(blk):]
            break

    # Relative/participial subject concords (e-, o-, etc.)
    rel_sc = None
    for cand in sorted(RELATIVE_CONCORDS, key=len, reverse=True):
        if stem.startswith(cand):
            rel_sc = cand
            out["prefixes"].append(cand + "-")
            stem = stem[len(cand):]
            out["explain"].append("Relative/participial subject concord detected.")
            break

    # Special handling for NEGATIVE RELATIVES:
    # After "e-" you often get "nga-" (relative negative/potential marker),
    # e.g.:
    #   engase-...    = e- + nga- + se- + ...
    #   engakabi-...  = e- + nga- + ka- + kabi- + ...
    #
    # Because we already stripped "e-" above, we can now just let TAM stacking pick up:
    #   nga, se, ka, kabi
    # The only thing we must ensure is that "kabi" exists (it does) and is not split.
    #
    # (So: no extra code needed here beyond having "kabi" in TAM_MARKERS.)

    # Normal subject concords (if present)
    sc = None
    for cand in sorted(SUBJECT_CONCORDS, key=len, reverse=True):
        if stem.startswith(cand):
            sc = cand
            out["prefixes"].append(cand + "-")
            stem = stem[len(cand):]
            break

    # TAM markers after SC/relative SC (stackable)
    progressed = True
    while progressed:
        progressed = False
        for m in sorted(TAM_MARKERS, key=len, reverse=True):
            if stem.startswith(m) and m != sc:
                out["tam"].append(m)
                stem = stem[len(m):]
                progressed = True
                break

    # Normalize common allomorphs/variants
    # In fast speech/orthography, future marker '-zo-' can appear as 'yo' (especially after 'se-')
    if out["tam"] and "yo" in out["tam"]:
        out["tam"] = ["zo" if x == "yo" else x for x in out["tam"]]
        out["explain"].append("Note: 'yo-' normalized to future marker 'zo-'.")

    # If we see "nga" in TAM and we're in a relative form, add a helpful note
    if rel_sc and "nga" in out["tam"]:
        out["explain"].append("Note: 'nga-' here is part of a negative/relative (e-nga-...) construction.")

    # Try object marker
    # Guard: don't strip a 1-letter OM like "m-" from a bare relative like "e- + VERB"
    # Example: e + memeza  -> remaining stem starts with "m", but that's root-initial, not an OM.
    allow_object = False

    # If we have a normal SC, or any TAM, this looks like a full verb complex -> allow OM.
    if sc is not None or out["tam"]:
        allow_object = True

    # Lemma-protection: if the remaining stem already matches the lemma stem, do NOT strip OM.
    if lemma:
        lemma_t = lemma.strip().lower()
        lemma_stem = lemma_t[:-1] if lemma_t and lemma_t[-1] in FINAL_VOWELS else lemma_t
        if stem == lemma_stem:
            allow_object = False
            out["explain"].append("Skipped object marker: stem matches lemma (likely root-initial 'm', not OM).")

    if allow_object:
        for om in sorted(OBJECT_MARKERS, key=len, reverse=True):
            if stem.startswith(om) and om != sc:
                out["object"] = om
                stem = stem[len(om):]
                break


    # Root guess (what remains)
    out["root_guess"] = stem if stem else None

    # Explanation text
    if out["prefixes"]:
        out["explain"].append(f"Subject concord/prefix: {''.join(out['prefixes'])}")
    if matched_subject_block:
        out["explain"].append(f"Subject block detected: {matched_subject_block}-")
    if out["tam"]:
        out["explain"].append(f"TAM markers: {', '.join(out['tam'])}")
    if out["object"]:
        out["explain"].append(f"Object marker: {out['object']}")
    if out["root_guess"]:
        out["explain"].append(f"Root/stem guess: {out['root_guess']}")
    if out["final_vowel"]:
        out["explain"].append(f"Final vowel: -{out['final_vowel']}")

    if lemma:
        out["explain"].append(f"Lexicon lemma (if correct): {lemma}")

    return out


def format_breakdown(b: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("Verb morphology (heuristic)")
    lines.append(f"- Token: {b.get('raw')}")
    lines.append(f"- Normalized: {b.get('normalized')}")
    if b.get("prefixes"):
        lines.append(f"- Prefix: {''.join(b['prefixes'])}")
    if b.get("tam"):
        lines.append(f"- TAM: {', '.join(b['tam'])}")
    if b.get("object"):
        lines.append(f"- Object: {b['object']}")
    if b.get("root_guess"):
        lines.append(f"- Root guess: {b['root_guess']}")
    if b.get("final_vowel"):
        lines.append(f"- Final vowel: -{b['final_vowel']}")
    if b.get("explain"):
        lines.append("")
        lines.extend([f"  {x}" for x in b["explain"]])
    return "\n".join(lines)
