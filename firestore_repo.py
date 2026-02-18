from typing import List, Dict, Any, Optional
import hashlib
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore

from google.api_core.exceptions import NotFound


class FirestoreRepo:
    """
    Firestore repository for:
      - stories
      - lexicon
      - theory docs

    Adds a fast 'theory catalog' index stored at:
      meta/theory_catalog
    with fields:
      - idMap: { "<concept_id>": true or {title, level, updatedAt} }
      - updatedAt: server timestamp
    """

    def __init__(
        self,
        service_account_path: str,
        stories_collection: str,
        lexicon_collection: str,
        theory_collection: str,
        sentence_analysis_collection: str,
    ):
        if not firebase_admin._apps:
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)

        self.db = firestore.client(database_id="isizulu")
        self.stories_collection = stories_collection
        self.lexicon_collection = lexicon_collection
        self.theory_collection = theory_collection
        self.sentence_analysis_collection = sentence_analysis_collection

        # Catalog location
        self._meta_collection = "meta"
        self._theory_catalog_doc = "theory_catalog"

    # -----------------------------
    # WRITE METHODS
    # -----------------------------

    def update_word_learning(self, word_id: str, learning_patch: dict) -> None:
        """Updates selected fields inside `learning` without overwriting the whole map.

        NOTE: The previous implementation used `set({'learning': patch}, merge=True)` which
        replaces the entire `learning` object. That breaks spaced repetition fields.
        """
        if not isinstance(learning_patch, dict) or not learning_patch:
            return

        ref = self.db.collection(self.lexicon_collection).document(word_id)
        payload: Dict[str, Any] = {f"learning.{k}": v for k, v in learning_patch.items()}
        payload["updatedAt"] = firestore.SERVER_TIMESTAMP

        try:
            ref.update(payload)
        except NotFound:
            # If the doc doesn't exist yet, fall back to creating it.
            ref.set(
                {
                    "learning": learning_patch,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                    "createdAt": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )

    # -----------------------------
    # REVISION / ACTIVE RECALL
    # -----------------------------

    def list_due_words(self, limit: int = 25, scan_limit: int = 250) -> List[Dict[str, Any]]:
        """Returns lexicon words that are due for review.

        This intentionally uses a bounded scan to avoid requiring Firestore composite indexes.
        A word is considered due if:
          - learning.known == True AND
          - learning.nextReviewAt is missing/None OR <= now
        """
        limit = max(1, int(limit))
        scan_limit = max(limit, int(scan_limit))

        now = datetime.now(timezone.utc)
        qs = (
            self.db.collection(self.lexicon_collection)
            .where("learning.known", "==", True)
            .limit(scan_limit)
            .stream()
        )

        due: List[Dict[str, Any]] = []
        for snap in qs:
            if not snap.exists:
                continue
            d = snap.to_dict() or {}
            learning = d.get("learning") or {}
            if not isinstance(learning, dict):
                learning = {}

            next_at = learning.get("nextReviewAt")
            is_due = (next_at is None) or (next_at <= now)
            if not is_due:
                continue

            d["id"] = snap.id
            due.append(d)

        def _sort_key(item: Dict[str, Any]):
            lr = (item.get("learning") or {})
            nxt = lr.get("nextReviewAt")
            return (nxt is not None, nxt or now)

        due.sort(key=_sort_key)
        return due[:limit]

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

    def delete_story(self, story_id: str, batch_size: int = 400) -> int:
        """Deletes a story and all its sentence docs.

        Firestore does not automatically delete subcollections when deleting a parent doc.
        Returns the number of sentence docs deleted.
        """
        sid = (story_id or "").strip()
        if not sid:
            return 0

        batch_size = max(1, min(int(batch_size), 450))

        story_ref = self.db.collection(self.stories_collection).document(sid)
        sentences_ref = story_ref.collection("sentences")

        deleted = 0
        batch = self.db.batch()
        pending = 0

        for snap in sentences_ref.stream():
            if not snap.exists:
                continue
            batch.delete(snap.reference)
            pending += 1
            deleted += 1
            if pending >= batch_size:
                batch.commit()
                batch = self.db.batch()
                pending = 0

        if pending:
            batch.commit()

        # Delete the parent story doc last.
        story_ref.delete()
        return deleted

    def update_sentence_learning(self, story_id: str, sentence_id: str, learning_patch: dict) -> None:
        """Updates selected fields inside a sentence's `learning` map."""
        if not story_id or not sentence_id:
            return
        if not isinstance(learning_patch, dict) or not learning_patch:
            return

        ref = (
            self.db.collection(self.stories_collection)
            .document(story_id)
            .collection("sentences")
            .document(sentence_id)
        )

        payload: Dict[str, Any] = {f"learning.{k}": v for k, v in learning_patch.items()}
        payload["updatedAt"] = firestore.SERVER_TIMESTAMP

        try:
            ref.update(payload)
        except NotFound:
            ref.set(
                {
                    "learning": learning_patch,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )

    def list_due_sentences(self, story_id: str, limit: int = 10, scan_limit: int = 250) -> List[Dict[str, Any]]:
        """Returns sentences due for review for a specific story.

        A sentence is due if learning.known == True and nextReviewAt is missing/None or <= now.
        Uses a bounded scan to avoid index requirements.
        """
        if not story_id:
            return []

        limit = max(1, int(limit))
        scan_limit = max(limit, int(scan_limit))

        now = datetime.now(timezone.utc)
        qs = (
            self.db.collection(self.stories_collection)
            .document(story_id)
            .collection("sentences")
            .order_by("index")
            .limit(scan_limit)
            .stream()
        )

        due: List[Dict[str, Any]] = []
        for snap in qs:
            if not snap.exists:
                continue
            d = snap.to_dict() or {}
            learning = d.get("learning") or {}
            if not isinstance(learning, dict):
                learning = {}

            if learning.get("known") is not True:
                continue
            next_at = learning.get("nextReviewAt")
            is_due = (next_at is None) or (next_at <= now)
            if not is_due:
                continue

            d["id"] = snap.id
            due.append(d)

        def _sort_key(item: Dict[str, Any]):
            lr = (item.get("learning") or {})
            nxt = lr.get("nextReviewAt")
            return (nxt is not None, nxt or now)

        due.sort(key=_sort_key)
        return due[:limit]

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
    # THEORY CATALOG (FAST INDEX)
    # -----------------------------

    def _catalog_ref(self):
        return self.db.collection(self._meta_collection).document(self._theory_catalog_doc)

    def ensure_theory_catalog(self) -> None:
        """
        Creates the catalog doc if it doesn't exist.
        Safe to call anytime.
        """
        ref = self._catalog_ref()
        snap = ref.get()
        if snap.exists:
            return
        ref.set(
            {
                "idMap": {},
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

    def get_theory_catalog_map(self) -> Dict[str, Any]:
        """
        Returns the catalog idMap, e.g.
          {"pluperfect_tense": True, "auxiliary_kade": {"title":..., "level":...}}

        One Firestore read.
        """
        ref = self._catalog_ref()
        snap = ref.get()
        if not snap.exists:
            return {}
        d = snap.to_dict() or {}
        id_map = d.get("idMap") or {}
        if not isinstance(id_map, dict):
            return {}
        # normalize keys to lowercase
        out = {}
        for k, v in id_map.items():
            if not k:
                continue
            out[str(k).strip().lower()] = v
        return out

    def update_theory_catalog(self, concept_id: str, title: Optional[str] = None, level: Optional[str] = None) -> None:
        """
        Adds/updates a concept id in the catalog.
        Uses merge=True so it only touches that key.
        """
        cid = (concept_id or "").strip().lower()
        if not cid:
            return

        ref = self._catalog_ref()

        # Keep it simple: store either True, or store small metadata if available.
        if title or level:
            payload_value: Any = {
                "title": (title or "").strip(),
                "level": (level or "").strip(),
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
        else:
            payload_value = True

        ref.set(
            {
                "idMap": {cid: payload_value},
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

    def rebuild_theory_catalog(self, limit: int = 2000) -> int:
        """
        Admin helper: scans theory docs and rebuilds the catalog.
        Returns number of theory docs indexed.

        Use if you manually edited/deleted theory docs outside the app.
        """
        qs = self.db.collection(self.theory_collection).limit(limit).stream()

        id_map: Dict[str, Any] = {}
        count = 0
        for snap in qs:
            if not snap.exists:
                continue
            d = snap.to_dict() or {}
            cid = (d.get("conceptId") or snap.id or "").strip().lower()
            if not cid:
                continue
            title = (d.get("title") or "").strip()
            level = (d.get("level") or "").strip()
            if title or level:
                id_map[cid] = {"title": title, "level": level}
            else:
                id_map[cid] = True
            count += 1

        self._catalog_ref().set(
            {
                "idMap": id_map,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=False,
        )
        return count

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

    # -----------------------------
    # THEORY READS
    # -----------------------------

    def search_theory(self, query: str, limit: int = 50):
        q = (query or "").strip().lower()
        out = []

        # 1) Exact doc id match
        doc = self.db.collection(self.theory_collection).document(q).get()
        if doc.exists:
            d = doc.to_dict() or {}
            d["id"] = doc.id
            d.setdefault("conceptId", doc.id)
            return [d]

        # 2) Tag match
        qs = (
            self.db.collection(self.theory_collection)
            .where("tags", "array_contains", q)
            .limit(limit)
            .stream()
        )
        for snap in qs:
            d = snap.to_dict() or {}
            d["id"] = snap.id
            d.setdefault("conceptId", snap.id)
            out.append(d)

        return out

    def get_theory_by_concepts(self, concepts: list[str], limit: int = 50):
        # Multi-concept best effort:
        # - fetch exact ids where possible
        # - otherwise tag search per concept (dedup)
        found = {}
        concepts_norm = [(c or "").strip().lower() for c in concepts if (c or "").strip()]
        if not concepts_norm:
            return []

        # exact id fetch (still okay for small lists, but not used for "missing" anymore)
        for c in concepts_norm:
            snap = self.db.collection(self.theory_collection).document(c).get()
            if snap.exists:
                d = snap.to_dict() or {}
                d["id"] = snap.id
                d.setdefault("conceptId", snap.id)
                found[snap.id] = d

        # tag search
        if len(found) < limit:
            for c in concepts_norm:
                qs = (
                    self.db.collection(self.theory_collection)
                    .where("tags", "array_contains", c)
                    .limit(limit)
                    .stream()
                )
                for snap in qs:
                    if snap.id in found:
                        continue
                    d = snap.to_dict() or {}
                    d["id"] = snap.id
                    d.setdefault("conceptId", snap.id)
                    found[snap.id] = d
                    if len(found) >= limit:
                        break
                if len(found) >= limit:
                    break

        return list(found.values())

    def create_or_update_theory_doc(self, concept_id: str, data: dict) -> None:
        """
        Writes theory/{concept_id} and updates meta/theory_catalog.
        """
        cid = (concept_id or "").strip().lower()
        if not cid:
            raise ValueError("concept_id is empty")

        ref = self.db.collection(self.theory_collection).document(cid)
        payload = dict(data)
        payload["conceptId"] = cid
        payload.setdefault("createdAt", firestore.SERVER_TIMESTAMP)
        payload["updatedAt"] = firestore.SERVER_TIMESTAMP
        ref.set(payload, merge=True)

        # Update fast index catalog (1 extra write)
        title = (payload.get("title") or "").strip()
        level = (payload.get("level") or "").strip()
        self.update_theory_catalog(cid, title=title or None, level=level or None)

    def theory_exists(self, concept_id: str) -> bool:
        cid = (concept_id or "").strip().lower()
        if not cid:
            return False
        snap = self.db.collection(self.theory_collection).document(cid).get()
        return bool(snap.exists)

    def list_theory_docs(self, limit: int = 200):
        qs = (
            self.db.collection(self.theory_collection)
            .order_by("conceptId")
            .limit(limit)
            .stream()
        )
        out = []
        for snap in qs:
            d = snap.to_dict() or {}
            d["id"] = snap.id
            d.setdefault("conceptId", snap.id)
            out.append(d)
        return out

    # -----------------------------
    # SENTENCE ANALYSIS CACHE
    # -----------------------------

    def _sentence_hash(self, text: str) -> str:
        """Helper to create a stable document ID for a sentence."""
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    def get_sentence_analysis(self, sentence_zu: str) -> Optional[str]:
        """Returns cached analysis from Firestore if it exists and is valid."""
        sid = self._sentence_hash(sentence_zu)
        ref = self.db.collection(self.sentence_analysis_collection).document(sid).get()
        if ref.exists:
            analysis = ref.to_dict().get("analysis")
            if analysis == "Failed to get detailed analysis from Gemini.":
                return None
            return analysis
        return None

    def save_sentence_analysis(self, sentence_zu: str, analysis: str) -> None:
        """Saves analysis to Firestore for future reuse."""
        sid = self._sentence_hash(sentence_zu)
        self.db.collection(self.sentence_analysis_collection).document(sid).set({
            "sentence": sentence_zu.strip(),
            "analysis": analysis,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        })
