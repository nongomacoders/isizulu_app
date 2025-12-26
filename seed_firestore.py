import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# ------------------------------------------------------------------
# INIT FIRESTORE
# ------------------------------------------------------------------
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

db = firestore.client(database_id='isizulu')

# ------------------------------------------------------------------
# DATA
# ------------------------------------------------------------------
STORY_ID = "story_demo_001"

sentences = [
    {
        "id": "0001",
        "index": 1,
        "text_zu": "Ngilinde kuze ukudla kuphekile.",
        "translation_en": "I am waiting until the food is cooked.",
        "grammar_brief": "Subjunctive clause introduced by 'kuze'."
    },
    {
        "id": "0002",
        "index": 2,
        "text_zu": "Umama upheka ekhishini.",
        "translation_en": "Mother is cooking in the kitchen.",
        "grammar_brief": "Present tense with subject concord."
    }
]

lexicon = {
    "zu_ngilinde": {
        "lemma": "ukulinda",
        "meaning": "to wait"
    },
    "zu_kuze": {
        "lemma": "kuze",
        "meaning": "until"
    },
    "zu_ukudla": {
        "lemma": "ukudla",
        "meaning": "food"
    },
    "zu_kuphekile": {
        "lemma": "ukupheka",
        "meaning": "cooked"
    }
}

# ------------------------------------------------------------------
# CREATE STORY
# ------------------------------------------------------------------
story_ref = db.collection("stories").document(STORY_ID)
story_ref.set({
    "title": "Demo isiZulu Story",
    "language": "zu",
    "level": "A1",
    "sentenceCount": len(sentences),
    "createdAt": firestore.SERVER_TIMESTAMP,
    "updatedAt": firestore.SERVER_TIMESTAMP
})

# ------------------------------------------------------------------
# CREATE SENTENCES
# ------------------------------------------------------------------
for s in sentences:
    sentence_ref = (
        db.collection("stories")
        .document(STORY_ID)
        .collection("sentences")
        .document(s["id"])
    )

    sentence_ref.set({
        "index": s["index"],
        "text_zu": s["text_zu"],
        "translation": {
            "en": s["translation_en"],
            "model": "seed",
            "createdAt": firestore.SERVER_TIMESTAMP
        },
        "grammar": {
            "brief": s["grammar_brief"],
            "model": "seed",
            "createdAt": firestore.SERVER_TIMESTAMP
        }
    })

# ------------------------------------------------------------------
# CREATE LEXICON WORDS
# ------------------------------------------------------------------
for word_id, data in lexicon.items():
    word_ref = db.collection("lexicon_words").document(word_id)
    word_ref.set({
        "language": "zu",
        "lemma": data["lemma"],
        "meaning_primary_en": data["meaning"],
        "meanings_en": [data["meaning"]],
        "frequency": 1,
        "createdAt": firestore.SERVER_TIMESTAMP
    }, merge=True)

print("Firestore seeding complete.")
