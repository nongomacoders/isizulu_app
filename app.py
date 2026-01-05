# app.py
from config import load_config
from gemini_client import GeminiClient
from firestore_repo import FirestoreRepo
from services.story_service import StoryService
from gui import MainGUI
import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    fh = RotatingFileHandler("app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

setup_logging()


def main():
    cfg = load_config()

    gemini = GeminiClient(api_key=cfg.gemini_api_key, model=cfg.gemini_model)
    repo = FirestoreRepo(
        service_account_path=cfg.firebase_service_account_path,
        stories_collection=cfg.stories_collection,
        lexicon_collection=cfg.lexicon_collection,
        theory_collection=cfg.theory_collection,
        sentence_analysis_collection=cfg.sentence_analysis_collection,
    )
    service = StoryService(gemini=gemini, repo=repo)

    try:
        app = MainGUI(service=service, repo=repo)
        app.mainloop()
    finally:
        gemini.close()


if __name__ == "__main__":
    main()
