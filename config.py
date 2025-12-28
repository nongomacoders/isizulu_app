import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class AppConfig:
    gemini_api_key: str
    gemini_model: str
    firebase_service_account_path: str
    stories_collection: str
    lexicon_collection: str
    theory_collection: str

def load_config() -> AppConfig:
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment/.env")

    firebase_sa = os.getenv("FIREBASE_SERVICE_ACCOUNT", "").strip()
    if not firebase_sa:
        raise RuntimeError("Missing FIREBASE_SERVICE_ACCOUNT in environment/.env")

    return AppConfig(
        gemini_api_key=gemini_api_key,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
        firebase_service_account_path=firebase_sa,
        stories_collection=os.getenv("FIRESTORE_DB_COLLECTION_STORIES", "stories").strip(),
        lexicon_collection=os.getenv("FIRESTORE_DB_COLLECTION_LEXICON", "lexicon_words").strip(),
        theory_collection=os.getenv("FIRESTORE_DB_COLLECTION_THEORY", "theory").strip(),
    )
