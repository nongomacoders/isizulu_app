from typing import List, Dict, Any, Optional
import firebase_admin
from firebase_admin import credentials, firestore


class FirestoreRepo:
    def __init__(self, service_account_path: str, stories_collection: str, lexicon_collection: str):
        if not firebase_admin._apps:
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)

        self.db = firestore.client(database_id="isizulu")
        self.stories_collection = stories_collection
        self.lexicon_collection = lexicon_collection

    # -----------------------------
    # WRITE METHODS
    # -----------------------------

    def update_word_learning(self, word_id: str, learning_patch: dict) -> None:
        self.db.collection(self.lexicon_collection).document(word_id).set(
            {
                "learning": learning_patch,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

    def create_story(self, title: str, level: str, language: str, sentence_count: int) -> str:
        doc_ref = self.db.collection(self.stories_collection).document()
        doc_ref.set(
            {
                "title": title,
                "language": language,
                "level": level,
                "sentenceCount": sentence_count,
                "createdAt": firestore.SERVER_TIMESTAMP,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
        )
        return doc_ref.id

    def write_sentences_batch(self, story_id: str, sentence_docs: List[Dict[str, Any]]) -> None:
        batch = self.db.batch()
        for doc in sentence_docs:
            sentence_id = doc["sentence_id"]
            data = doc["data"]
            ref = (
                self.db.collection(self.stories_collection)
                .document(story_id)
                .collection("sentences")
                .document(sentence_id)
            )
            batch.set(ref, data, merge=True)
        batch.commit()

    def upsert_lexicon_words_batch(self, word_entries: List[Dict[str, Any]]) -> None:
        if not word_entries:
            return

        batch = self.db.batch()
        for w in word_entries:
            ref = self.db.collection(self.lexicon_collection).document(w["word_id"])
            data = dict(w["data"])
            data["updatedAt"] = firestore.SERVER_TIMESTAMP
            data.setdefault("createdAt", firestore.SERVER_TIMESTAMP)
            batch.set(ref, data, merge=True)
        batch.commit()

    # -----------------------------
    # READ METHODS
    # -----------------------------

    def list_stories(self, limit: int = 50) -> List[Dict[str, Any]]:
        qs = (
            self.db.collection(self.stories_collection)
            .order_by("createdAt", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )

        out = []
        for doc in qs:
            d = doc.to_dict() or {}
            d["id"] = doc.id
            out.append(d)
        return out

    def get_story(self, story_id: str) -> Optional[Dict[str, Any]]:
        ref = self.db.collection(self.stories_collection).document(story_id).get()
        if not ref.exists:
            return None
        d = ref.to_dict() or {}
        d["id"] = story_id
        return d

    def list_sentences(self, story_id: str) -> List[Dict[str, Any]]:
        qs = (
            self.db.collection(self.stories_collection)
            .document(story_id)
            .collection("sentences")
            .order_by("index")
            .stream()
        )

        out = []
        for doc in qs:
            d = doc.to_dict() or {}
            d["id"] = doc.id
            out.append(d)
        return out

    def get_word(self, word_id: str) -> Optional[Dict[str, Any]]:
        ref = self.db.collection(self.lexicon_collection).document(word_id).get()
        if not ref.exists:
            return None
        d = ref.to_dict() or {}
        d["id"] = word_id
        return d

    # -----------------------------
    # BATCH HELPERS
    # -----------------------------

    def get_words_batch(self, word_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch existing lexicon docs in one round-trip.
        Returns {word_id: doc_dict} for docs that exist.
        """
        if not word_ids:
            return {}

        refs = [self.db.collection(self.lexicon_collection).document(wid) for wid in word_ids]
        snaps = self.db.get_all(refs)

        out: Dict[str, Dict[str, Any]] = {}
        for snap in snaps:
            if snap.exists:
                out[snap.id] = snap.to_dict() or {}
        return out
