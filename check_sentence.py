from firestore_repo import FirestoreRepo
from config import load_config

cfg = load_config()

repo = FirestoreRepo(
    service_account_path=cfg.firebase_service_account_path,
    stories_collection=cfg.stories_collection,
    lexicon_collection=cfg.lexicon_collection,
)

stories = repo.list_stories(limit=1)

if not stories:
    print("No stories found.")
    raise SystemExit

story = stories[0]
print("Latest story ID:", story["id"])
print("Title:", story.get("title"))
print("Sentence count (story field):", story.get("sentenceCount"))

sentences = repo.list_sentences(story["id"])
print("Sentence docs found:", len(sentences))

if sentences:
    print("First sentence text:", sentences[0].get("text_zu"))
