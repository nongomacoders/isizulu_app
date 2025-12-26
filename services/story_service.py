from __future__ import annotations

from typing import Callable, Dict, Any, List

from models import StoryCreateRequest, StoryCreateResult
from utils_text import split_into_sentences, tokenize_zu
from utils.logger import log
from services.sentence_service import SentenceService
from services.lexicon_service import LexiconService

class StoryService:
    def __init__(self, gemini, repo):
        self.repo = repo
        self.gemini = gemini
        self.sentence_svc = SentenceService(repo=repo, gemini=gemini)
        self.lexicon_svc = LexiconService(repo=repo, gemini=gemini)

    def create_story_from_text(
        self,
        req: StoryCreateRequest,
        progress: Callable[[str], None] = lambda _: None,
        build_lexicon: bool = True,
        lexicon_enrich_with_gemini: bool = True,
        lexicon_batch_size: int = 40,
        flush_every_sentences: int = 5,
    ) -> StoryCreateResult:

        title = (req.title or "").strip() or "Untitled"
        level = (req.level or "").strip() or "Unknown"
        story_text = (req.text_zu or "").strip()

        sentences = split_into_sentences(story_text)
        if not sentences:
            raise ValueError("No sentences found. Paste a story with at least one sentence.")

        log(progress, "INFO", f"Split into {len(sentences)} sentence(s). Creating story...")
        story_id = self.repo.create_story(
            title=title,
            level=level,
            language="zu",
            sentence_count=len(sentences),
        )
        log(progress, "INFO", f"Story created: {story_id}")

        sentence_docs: List[Dict[str, Any]] = []
        lexicon_updates: Dict[str, Dict[str, Any]] = {}
        all_unique_tokens: Dict[str, str] = {}

        log(progress, "INFO", "Processing sentences...")
        for idx, s in enumerate(sentences, start=1):
            s_clean = (s or "").strip()
            if not s_clean:
                continue

            tokens = tokenize_zu(s_clean) if build_lexicon else []
            if build_lexicon and tokens:
                self.lexicon_svc.add_tokens_to_base(tokens, lexicon_updates, all_unique_tokens)

            sentence_docs.append(self.sentence_svc.build_sentence_doc(idx, s_clean, build_tokens=True))

            if idx % 5 == 0 or idx == len(sentences):
                log(progress, "INFO", f"Built {idx}/{len(sentences)} sentence(s)")

            # flush incrementally to prevent shell stories
            if len(sentence_docs) % max(1, int(flush_every_sentences)) == 0:
                self.sentence_svc.save_sentences_incremental(
                    story_id=story_id,
                    sentence_docs=sentence_docs[-max(1, int(flush_every_sentences)):],
                    flush_every=max(1, int(flush_every_sentences)),
                    progress=progress,
                )

        # flush any remaining
        self.sentence_svc.save_sentences_incremental(
            story_id=story_id,
            sentence_docs=sentence_docs,
            flush_every=max(1, int(flush_every_sentences)),
            progress=progress,
        )

        if build_lexicon:
            self.lexicon_svc.upsert_base(lexicon_updates, progress=progress)
            if lexicon_enrich_with_gemini:
                self.lexicon_svc.enrich_missing(
                    all_unique_tokens=all_unique_tokens,
                    lexicon_updates=lexicon_updates,
                    batch_size=lexicon_batch_size,
                    progress=progress,
                )

        log(progress, "INFO", "Story import completed.")
        log(progress, "INFO", f"Story ID: {story_id}")
        log(progress, "INFO", f"Sentences saved (attempted): {len(sentence_docs)}")
        log(progress, "INFO", f"Lexicon words processed: {len(lexicon_updates)}")

        return StoryCreateResult(story_id=story_id, sentence_count=len(sentence_docs))
