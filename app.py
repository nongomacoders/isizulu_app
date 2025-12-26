# app.py
from config import load_config
from gemini_client import GeminiClient
from firestore_repo import FirestoreRepo
from story_service import StoryService
from gui import MainGUI


def main():
    cfg = load_config()

    gemini = GeminiClient(api_key=cfg.gemini_api_key, model=cfg.gemini_model)
    repo = FirestoreRepo(
        service_account_path=cfg.firebase_service_account_path,
        stories_collection=cfg.stories_collection,
        lexicon_collection=cfg.lexicon_collection,
    )
    service = StoryService(gemini=gemini, repo=repo)

    try:
        app = MainGUI(service=service, repo=repo)
        app.mainloop()
    finally:
        gemini.close()


if __name__ == "__main__":
    main()
