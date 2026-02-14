# tab_learn.py

import tkinter as tk
from tkinter import ttk, messagebox
import threading
from typing import List, Dict, Any, Optional
from utils.gui_utils import configure_markdown_tags, render_markdown
from datetime import datetime, timezone

from utils_text import tokenize_zu
from services.lexicon_service import normalize_word_id
from utils.morphology_zu import breakdown_verb_token, format_breakdown
from rules.auxiliary_explain import explain_auxiliary
from utils.revision import sm2_update


class LearnTab(ttk.Frame):
    def __init__(self, parent, repo, gemini=None):
        super().__init__(parent)
        self.repo = repo
        self.gemini = gemini

        self.stories: List[Dict[str, Any]] = []
        self.sentences: List[Dict[str, Any]] = []
        self.story_id: Optional[str] = None
        self.idx: int = 0

        self.show_english = tk.BooleanVar(value=True)
        self.hint_state = 0  # 0=off, 1=concepts only, 2=brief+concepts

        self._full_cache = ""
        self._hint1_cache = ""
        self._hint2_cache = ""

        self._build()
        self._refresh_stories()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="we", padx=10, pady=10)
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Story").grid(row=0, column=0, sticky="w")
        self.story_var = tk.StringVar(value="")
        self.story_combo = ttk.Combobox(top, textvariable=self.story_var, state="readonly")
        self.story_combo.grid(row=0, column=1, sticky="we", padx=(8, 8))
        self.story_combo.bind("<<ComboboxSelected>>", lambda e: self._load_selected_story())
        ttk.Button(top, text="Refresh", command=self._refresh_stories).grid(row=0, column=2, sticky="e")

        nav = ttk.Frame(self)
        nav.grid(row=1, column=0, sticky="we", padx=10)
        nav.columnconfigure(1, weight=1)

        self.prev_btn = ttk.Button(nav, text="◀", command=self._prev)
        self.prev_btn.grid(row=0, column=0, sticky="w")

        self.pos_lbl = ttk.Label(nav, text="0 / 0")
        self.pos_lbl.grid(row=0, column=1)

        self.next_btn = ttk.Button(nav, text="▶", command=self._next)
        self.next_btn.grid(row=0, column=2, sticky="e")

        self.toggle_btn = ttk.Button(nav, text="Hide English", command=self._toggle_english)
        self.toggle_btn.grid(row=0, column=3, sticky="e", padx=(8, 0))

        self.hint_btn = ttk.Button(nav, text="Hint", command=self._cycle_hint)
        self.hint_btn.grid(row=0, column=4, sticky="e", padx=(8, 0))

        self.understood_btn = ttk.Button(nav, text="Understood", command=self._mark_sentence_understood)
        self.understood_btn.grid(row=0, column=5, sticky="e", padx=(8, 0))

        self.revision_btn = ttk.Button(nav, text="Revision", command=self._open_revision)
        self.revision_btn.grid(row=0, column=6, sticky="e", padx=(8, 0))

        self.sent_revision_btn = ttk.Button(nav, text="Sentence Revision", command=self._open_sentence_revision)
        self.sent_revision_btn.grid(row=0, column=7, sticky="e", padx=(8, 0))

        self.theory_btn = ttk.Button(nav, text="Theory", command=self._open_theory_for_sentence)
        self.theory_btn.grid(row=0, column=8, sticky="e", padx=(8, 0))

        self.ai_btn = ttk.Button(nav, text="Sentence AI", command=self._open_sentence_ai)
        self.ai_btn.grid(row=0, column=9, sticky="e", padx=(8, 0))

        main = ttk.Frame(self)
        main.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        main.columnconfigure(0, weight=2)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(1, weight=1)
        main.rowconfigure(3, weight=1)

        ttk.Label(main, text="isiZulu").grid(row=0, column=0, sticky="w")
        ttk.Label(main, text="Words").grid(row=0, column=1, sticky="w")

        self.zu_txt = tk.Text(main, height=5, wrap="word", state="disabled")
        self.zu_txt.grid(row=1, column=0, sticky="nsew", padx=(0, 10))

        self.tokens = tk.Listbox(main)
        self.tokens.grid(row=1, column=1, sticky="nsew")
        self.tokens.bind("<<ListboxSelect>>", lambda e: self._show_word())

        ttk.Label(main, text="English / Grammar / Hint").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Label(main, text="Dictionary / Analysis").grid(row=2, column=1, sticky="w", pady=(10, 0))

        self.info_txt = tk.Text(main, height=10, wrap="word", state="disabled")
        self.info_txt.grid(row=3, column=0, sticky="nsew", padx=(0, 10), pady=(4, 0))

        self.word_txt = tk.Text(main, height=10, wrap="word", state="disabled")
        self.word_txt.grid(row=3, column=1, sticky="nsew", pady=(4, 0))
    
    def _open_theory_for_sentence(self):
        if not self.sentences:
            return
        s = self.sentences[self.idx]
        concepts = (s.get("grammar") or {}).get("concepts") or []
        if not isinstance(concepts, list) or not concepts:
            messagebox.showinfo("Theory", "No concepts for this sentence.")
            return

        if hasattr(self, "_theory_tab") and hasattr(self, "_notebook"):
            self._theory_tab.load_concepts(concepts)
            self._notebook.select(self._theory_tab)
        else:
            messagebox.showerror("Theory", "Theory tab not connected.")


    def set_theory_tab(self, theory_tab, notebook):
        self._theory_tab = theory_tab
        self._notebook = notebook

    def _open_sentence_ai(self):
        if not self.sentences:
            return
        if not self.gemini:
            messagebox.showerror("Error", "Gemini client not connected.")
            return

        s = self.sentences[self.idx]
        zu = (s.get("text_zu") or "").strip()
        if not zu:
            return

        # Show a simple loading state or just launch
        
        def _fetch(win_to_update, force=False):
            try:
                if not force:
                    # 1) Check Firestore Cache first
                    cached = self.repo.get_sentence_analysis(zu)
                    if cached:
                        self.after(0, lambda: win_to_update.set_analysis(cached))
                        return
                else:
                    self.after(0, lambda: win_to_update.reset_loading())

                # 2) If not cached or forced, call Gemini
                analysis = self.gemini.analyze_sentence_detailed(zu)
                
                # 3) Save to cache
                self.repo.save_sentence_analysis(zu, analysis)
                
                self.after(0, lambda: win_to_update.set_analysis(analysis))
            except Exception as e:
                self.after(0, lambda: win_to_update.set_analysis(f"Error: {e}"))

        # Create window with re-analyze callback
        win = SentenceAIWindow(
            self, 
            zu, 
            on_reanalyze=lambda: threading.Thread(target=_fetch, args=(win, True), daemon=True).start()
        )
        
        threading.Thread(target=_fetch, args=(win,), daemon=True).start()

    def _refresh_stories(self):
        try:
            self.stories = self.repo.list_stories(limit=100)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to list stories:\n{e}")
            return

        self._display_to_id = {}
        values = []
        for s in self.stories:
            sid = s["id"]
            title = (s.get("title") or "Untitled").strip()
            n = s.get("sentenceCount", "")
            label = f"{title} ({sid}) [{n}]"
            values.append(label)
            self._display_to_id[label] = sid

        self.story_combo["values"] = values
        if values:
            self.story_var.set(values[0])
            self._load_selected_story()
        else:
            self.story_var.set("")
            self.sentences = []
            self.idx = 0
            self._render()

    def _load_selected_story(self):
        label = self.story_var.get()
        sid = self._display_to_id.get(label)
        if not sid:
            return

        self.story_id = sid
        try:
            self.sentences = self.repo.list_sentences(sid)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load sentences:\n{e}")
            self.sentences = []
            return

        self.idx = 0
        self.show_english.set(True)
        self.hint_state = 0
        self.toggle_btn.configure(text="Hide English")
        self._render()

    def _prev(self):
        if self.idx > 0:
            self.idx -= 1
            self.hint_state = 0
            self._render()

    def _next(self):
        if self.idx < len(self.sentences) - 1:
            self.idx += 1
            self.hint_state = 0
            self._render()

    def _toggle_english(self):
        self.show_english.set(not self.show_english.get())
        if self.show_english.get():
            self.toggle_btn.configure(text="Hide English")
            self.hint_state = 0
        else:
            self.toggle_btn.configure(text="Show English")
            self.hint_state = 0
        self._render_info_only()

    def _cycle_hint(self):
        if self.show_english.get():
            return
        self.hint_state = (self.hint_state + 1) % 3
        self._render_info_only()

    def _render_info_only(self):
        if self.show_english.get():
            self._set_text(self.info_txt, self._full_cache)
            return
        if self.hint_state == 1:
            self._set_text(self.info_txt, self._hint1_cache)
        elif self.hint_state == 2:
            self._set_text(self.info_txt, self._hint2_cache)
        else:
            self._set_text(self.info_txt, "")

    def _current_sentence_tokens(self) -> List[str]:
        if not self.sentences:
            return []
        s = self.sentences[self.idx]
        toks = s.get("tokens")
        if isinstance(toks, list) and toks:
            return [str(t).strip() for t in toks if str(t).strip()]
        zu = (s.get("text_zu") or "").strip()
        return tokenize_zu(zu)

    def _mark_sentence_understood(self):
        if not self.sentences:
            return
        toks = self._current_sentence_tokens()
        if not toks:
            messagebox.showwarning("No tokens", "No words found for this sentence.")
            return
        word_ids = sorted({normalize_word_id(t) for t in toks})
        try:
            now = datetime.now(timezone.utc)

            # 1) Mark the sentence itself as reviewable (spaced repetition)
            if self.story_id:
                s = self.sentences[self.idx]
                sid = (s.get("id") or "").strip()
                if sid:
                    self.repo.update_sentence_learning(
                        self.story_id,
                        sid,
                        {"known": True, "nextReviewAt": now},
                    )

            # 2) Mark words as known and due now
            for wid in word_ids:
                # Mark known AND ensure it becomes reviewable in Revision.
                self.repo.update_word_learning(wid, {"known": True, "nextReviewAt": now})
        except Exception as e:
            messagebox.showerror("Error", f"Failed to mark words as known:\n{e}")
            return
        messagebox.showinfo("Saved", f"Marked {len(word_ids)} word(s) as known.")

    def _open_revision(self):
        WordRevisionWindow(self, repo=self.repo)

    def _open_sentence_revision(self):
        if not self.story_id:
            messagebox.showinfo("Sentence Revision", "Pick a story first.")
            return
        SentenceRevisionWindow(self, repo=self.repo, story_id=self.story_id)

    def _render(self):
        total = len(self.sentences)
        if total == 0:
            self._set_text(self.zu_txt, "")
            self._set_text(self.info_txt, "")
            self.tokens.delete(0, "end")
            self._set_text(self.word_txt, "")
            self.pos_lbl.configure(text="0 / 0")
            self.prev_btn.configure(state="disabled")
            self.next_btn.configure(state="disabled")
            self.understood_btn.configure(state="disabled")
            return

        self.idx = max(0, min(self.idx, total - 1))
        s = self.sentences[self.idx]

        zu = (s.get("text_zu") or "").strip()
        en = ((s.get("translation") or {}).get("en") or "").strip()

        g = s.get("grammar") or {}
        brief = (g.get("brief") or "").strip()

        concepts = g.get("concepts") or []
        if isinstance(concepts, list):
            concepts_str = ", ".join([str(c).strip() for c in concepts if str(c).strip()])
        else:
            concepts_str = str(concepts).strip()

        self._hint1_cache = (f"Concepts: {concepts_str}" if concepts_str else "Concepts: (none)").strip()
        if brief and concepts_str:
            self._hint2_cache = f"{brief}\n\nConcepts: {concepts_str}".strip()
        elif brief:
            self._hint2_cache = brief
        elif concepts_str:
            self._hint2_cache = f"Concepts: {concepts_str}"
        else:
            self._hint2_cache = "(No grammar saved for this sentence.)"

        if en and brief and concepts_str:
            self._full_cache = f"{en}\n\n{brief}\n\nConcepts: {concepts_str}".strip()
        elif en and brief:
            self._full_cache = f"{en}\n\n{brief}".strip()
        elif en and concepts_str:
            self._full_cache = f"{en}\n\nConcepts: {concepts_str}".strip()
        else:
            self._full_cache = en or brief or (f"Concepts: {concepts_str}" if concepts_str else "")

        self._set_text(self.zu_txt, zu)
        self._render_info_only()

        toks = self._current_sentence_tokens()
        self.tokens.delete(0, "end")
        for t in toks:
            self.tokens.insert("end", t)

        self._set_text(self.word_txt, "")
        self.pos_lbl.configure(text=f"{self.idx + 1} / {total}")

        self.prev_btn.configure(state=("disabled" if self.idx == 0 else "normal"))
        self.next_btn.configure(state=("disabled" if self.idx == total - 1 else "normal"))
        self.understood_btn.configure(state="normal")

    def _show_word(self):
        sel = self.tokens.curselection()
        if not sel:
            return
        token = self.tokens.get(sel[0])
        wid = normalize_word_id(token)

        try:
            w = self.repo.get_word(wid)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load word:\n{e}")
            return

        if not w:
            self._set_text(self.word_txt, f"{token}\n\nNo entry yet.\n(wordId: {wid})")
            return

        lemma = w.get("lemma")
        pos = (w.get("pos") or "").strip().lower()

        lines = [f"Token: {token}", f"Word ID: {wid}"]

        learning = w.get("learning") or {}
        if isinstance(learning, dict) and learning:
            known = learning.get("known")
            if known is not None:
                lines.append(f"Known: {known}")

        if lemma:
            lines.append(f"Lemma: {lemma}")
        if w.get("pos"):
            lines.append(f"POS: {w.get('pos')}")
        if w.get("auxiliaryType"):
            lines.append(f"Aux type: {w.get('auxiliaryType')}")
        if w.get("nounClass"):
            lines.append(f"Noun class: {w.get('nounClass')}")
        if w.get("infinitive"):
            lines.append(f"Infinitive: {w.get('infinitive')}")
        if w.get("analysisConfidence") is not None:
            lines.append(f"Confidence: {w.get('analysisConfidence')}")
        if w.get("analysisNotes"):
            lines.append(f"Notes: {w.get('analysisNotes')}")

        lines.append("")
        lines.append(f"Frequency: {w.get('frequency', 0)}")
        sf = w.get("surfaceForms") or []
        if sf:
            lines.append("Surface forms: " + ", ".join(sf[:25]))

        # -----------------------------
        # NEW: Auxiliary-specific explanation
        # -----------------------------
        if pos == "auxiliary":
            aux_type = (w.get("auxiliaryType") or "").strip()
            lines.append("")
            lines.append("Auxiliary explanation")
            lines.append(explain_auxiliary(aux_type))

        # -----------------------------
        # NEW: Verb morphology breakdown (heuristic)
        # -----------------------------
        if pos == "verb":
            b = breakdown_verb_token(token, lemma=lemma)
            lines.append("")
            lines.append(format_breakdown(b))

        self._set_text(self.word_txt, "\n".join(lines))

    def _set_text(self, widget: tk.Text, text: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text or "")
        widget.configure(state="disabled")


class SentenceAIWindow(tk.Toplevel):
    def __init__(self, parent, sentence_zu: str, on_reanalyze=None):
        super().__init__(parent)
        self.title("Sentence AI Analysis")
        
        # Use a large window but not absolute full screen to avoid taskbar overlap
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        # Set to approx 90% of screen size, centered
        w = int(sw * 0.9)
        h = int(sh * 0.85)
        x = (sw - w) // 2
        y = (sh - h) // 2 - 30 # Offset slightly up
        self.geometry(f"{w}x{h}+{x}+{y}")
            
        self.transient(parent)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="we", padx=20, pady=20)
        
        ttk.Label(header, text="isiZulu Sentence:", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        # Larger font for the isiZulu sentence
        lbl = ttk.Label(header, text=sentence_zu, wraplength=1000, font=("Segoe UI", 16))
        lbl.pack(anchor="w", pady=(5, 10))

        ttk.Separator(self, orient="horizontal").grid(row=1, column=0, sticky="we")

        # Container for text and scrollbar
        container = ttk.Frame(self)
        container.grid(row=2, column=0, sticky="nsew", padx=20, pady=20)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        self.txt = tk.Text(container, wrap="word", padx=20, pady=20, state="disabled", font=("Segoe UI", 14))
        self.txt.grid(row=0, column=0, sticky="nsew")
        
        sb = ttk.Scrollbar(container, orient="vertical", command=self.txt.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.txt.configure(yscrollcommand=sb.set)

        configure_markdown_tags(self.txt)
        
        self.txt.configure(state="normal")
        self.txt.insert("end", "Consulting Gemini 3 Flash Preview for detailed analysis...\n\nPlease wait.")
        self.txt.configure(state="disabled")
        self.loading_text = "Consulting Gemini 3 Flash Preview for detailed analysis...\n\nPlease wait."

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=3, column=0, sticky="e", padx=20, pady=(0, 20))
        
        if on_reanalyze:
            self.btn_reanalyze = ttk.Button(btn_frame, text="Re-analyze (Bypass Cache)", command=on_reanalyze)
            self.btn_reanalyze.pack(side="left", padx=5)
            
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side="left")

    def reset_loading(self):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("end", self.loading_text)
        self.txt.configure(state="disabled")
        if hasattr(self, "btn_reanalyze"):
            self.btn_reanalyze.configure(state="disabled")

    def set_analysis(self, text: str):
        render_markdown(self.txt, text)
        if hasattr(self, "btn_reanalyze"):
            self.btn_reanalyze.configure(state="normal")


class WordRevisionWindow(tk.Toplevel):
    def __init__(self, parent, repo):
        super().__init__(parent)
        self.title("Revision (Words)")
        self.repo = repo

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(900, int(sw * 0.8))
        h = min(650, int(sh * 0.75))
        x = (sw - w) // 2
        y = (sh - h) // 2 - 30
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.transient(parent)

        self._cards: List[Dict[str, Any]] = []
        self._idx = 0
        self._revealed = False
        self._reviewed = 0

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="we", padx=12, pady=12)
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Word revision (active recall)").grid(row=0, column=0, sticky="w")
        self.stats_lbl = ttk.Label(header, text="Loading…")
        self.stats_lbl.grid(row=0, column=1, sticky="e")

        ttk.Separator(self, orient="horizontal").grid(row=1, column=0, sticky="we")

        body = ttk.Frame(self)
        body.grid(row=2, column=0, sticky="nsew", padx=12, pady=12)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        self.prompt_lbl = ttk.Label(body, text="", font=("Segoe UI", 18, "bold"), wraplength=w - 60)
        self.prompt_lbl.grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.front_lbl = ttk.Label(body, text="Recall the meaning (then reveal).", wraplength=w - 60)
        self.front_lbl.grid(row=1, column=0, sticky="w", pady=(0, 10))

        self.answer_txt = tk.Text(body, wrap="word", state="disabled")
        self.answer_txt.grid(row=2, column=0, sticky="nsew")

        btns = ttk.Frame(self)
        btns.grid(row=3, column=0, sticky="we", padx=12, pady=(0, 12))

        self.btn_show = ttk.Button(btns, text="Show answer", command=self._reveal)
        self.btn_show.pack(side="left")

        self.btn_again = ttk.Button(btns, text="Again", command=lambda: self._grade("again"), state="disabled")
        self.btn_hard = ttk.Button(btns, text="Hard", command=lambda: self._grade("hard"), state="disabled")
        self.btn_good = ttk.Button(btns, text="Good", command=lambda: self._grade("good"), state="disabled")
        self.btn_easy = ttk.Button(btns, text="Easy", command=lambda: self._grade("easy"), state="disabled")

        for b in [self.btn_again, self.btn_hard, self.btn_good, self.btn_easy]:
            b.pack(side="left", padx=(8, 0))

        ttk.Separator(btns, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Button(btns, text="Skip", command=self._skip).pack(side="left")
        ttk.Button(btns, text="Refresh", command=self._refresh).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Close", command=self.destroy).pack(side="right")

        self._refresh()

    def _set_answer(self, text: str):
        self.answer_txt.configure(state="normal")
        self.answer_txt.delete("1.0", "end")
        self.answer_txt.insert("1.0", text or "")
        self.answer_txt.configure(state="disabled")

    def _refresh(self):
        self._set_answer("")
        self.prompt_lbl.configure(text="Loading…")
        self.front_lbl.configure(text="")
        self._disable_grades()
        self._revealed = False
        self._idx = 0

        def _fetch():
            try:
                cards = self.repo.list_due_words(limit=25)
            except Exception as e:
                cards = []
                err = str(e)
                self.after(0, lambda: messagebox.showerror("Revision", f"Failed to load due words:\n{err}"))
            self.after(0, lambda: self._set_cards(cards))

        threading.Thread(target=_fetch, daemon=True).start()

    def _set_cards(self, cards: List[Dict[str, Any]]):
        self._cards = cards or []
        self._revealed = False
        self._idx = 0
        self._render()

    def _disable_grades(self):
        for b in [self.btn_again, self.btn_hard, self.btn_good, self.btn_easy]:
            b.configure(state="disabled")

    def _enable_grades(self):
        for b in [self.btn_again, self.btn_hard, self.btn_good, self.btn_easy]:
            b.configure(state="normal")

    def _current_card(self) -> Optional[Dict[str, Any]]:
        if not self._cards:
            return None
        self._idx = max(0, min(self._idx, len(self._cards) - 1))
        return self._cards[self._idx]

    def _display_token(self, w: Dict[str, Any]) -> str:
        sf = w.get("surfaceForms") or []
        if isinstance(sf, list) and sf:
            t = str(sf[0]).strip()
            if t:
                return t
        wid = (w.get("id") or "").strip()
        return wid.replace("zu_", "") if wid else "(unknown)"

    def _render(self):
        total = len(self._cards)
        if total == 0:
            self.stats_lbl.configure(text=f"Due: 0 | Reviewed: {self._reviewed}")
            self.prompt_lbl.configure(text="No due words right now.")
            self.front_lbl.configure(text="Tip: click 'Understood' on a sentence to add its words to revision.")
            self._set_answer("")
            self.btn_show.configure(state="disabled")
            self._disable_grades()
            return

        self.btn_show.configure(state="normal")
        self.stats_lbl.configure(text=f"Due: {total} | Reviewed: {self._reviewed} | {self._idx + 1}/{total}")

        w = self._current_card() or {}
        token = self._display_token(w)
        self.prompt_lbl.configure(text=token)
        self.front_lbl.configure(text="Recall the meaning. Then click 'Show answer'.")

        if not self._revealed:
            self._set_answer("")
            self._disable_grades()
        else:
            self._set_answer(self._format_answer(w))
            self._enable_grades()

    def _format_answer(self, w: Dict[str, Any]) -> str:
        lines = []
        mp = (w.get("meaning_primary_en") or "").strip()
        if mp:
            lines.append(f"Meaning: {mp}")

        lemma = (w.get("lemma") or "").strip()
        if lemma:
            lines.append(f"Lemma: {lemma}")

        pos = (w.get("pos") or "").strip()
        if pos:
            lines.append(f"POS: {pos}")

        if (w.get("nounClass") or "").strip():
            lines.append(f"Noun class: {w.get('nounClass')}")

        if (w.get("infinitive") or "").strip():
            lines.append(f"Infinitive: {w.get('infinitive')}")

        notes = (w.get("analysisNotes") or "").strip()
        if notes:
            lines.append("")
            lines.append(f"Notes: {notes}")

        learning = w.get("learning") or {}
        if isinstance(learning, dict):
            ease = learning.get("ease")
            interval = learning.get("intervalDays")
            reps = learning.get("repetitions")
            nxt = learning.get("nextReviewAt")
            parts = []
            if ease is not None:
                parts.append(f"ease={ease}")
            if interval is not None:
                parts.append(f"intervalDays={interval}")
            if reps is not None:
                parts.append(f"repetitions={reps}")
            if nxt is not None:
                parts.append(f"nextReviewAt={nxt}")
            if parts:
                lines.append("")
                lines.append("Schedule: " + ", ".join(parts))

        return "\n".join(lines).strip() or "(No answer data available for this word.)"

    def _reveal(self):
        if not self._cards:
            return
        self._revealed = True
        self._render()

    def _skip(self):
        if not self._cards:
            return
        self._revealed = False
        self._idx = (self._idx + 1) % len(self._cards)
        self._render()

    def _grade(self, rating: str):
        w = self._current_card()
        if not w:
            return
        wid = (w.get("id") or "").strip()
        if not wid:
            return

        patch = sm2_update(w.get("learning") or {}, rating, now=datetime.now(timezone.utc))

        def _save():
            try:
                self.repo.update_word_learning(wid, patch)
            except Exception as e:
                err = str(e)
                self.after(0, lambda: messagebox.showerror("Revision", f"Failed to save review:\n{err}"))
                return

            def _advance():
                self._reviewed += 1
                if self._cards:
                    self._cards.pop(self._idx)
                self._revealed = False
                if self._idx >= len(self._cards):
                    self._idx = 0
                self._render()

            self.after(0, _advance)

        threading.Thread(target=_save, daemon=True).start()


class SentenceRevisionWindow(tk.Toplevel):
    def __init__(self, parent, repo, story_id: str):
        super().__init__(parent)
        self.title("Revision (Sentences)")
        self.repo = repo
        self.story_id = story_id

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(1000, int(sw * 0.85))
        h = min(720, int(sh * 0.80))
        x = (sw - w) // 2
        y = (sh - h) // 2 - 30
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.transient(parent)

        self._cards: List[Dict[str, Any]] = []
        self._idx = 0
        self._revealed = False
        self._reviewed = 0

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="we", padx=12, pady=12)
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Sentence revision (English → isiZulu)").grid(row=0, column=0, sticky="w")
        self.stats_lbl = ttk.Label(header, text="Loading…")
        self.stats_lbl.grid(row=0, column=1, sticky="e")

        ttk.Separator(self, orient="horizontal").grid(row=1, column=0, sticky="we")

        body = ttk.Frame(self)
        body.grid(row=2, column=0, sticky="nsew", padx=12, pady=12)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        self.prompt_lbl = ttk.Label(body, text="", font=("Segoe UI", 16, "bold"), wraplength=w - 60)
        self.prompt_lbl.grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.front_lbl = ttk.Label(body, text="Recall the isiZulu sentence (then reveal).", wraplength=w - 60)
        self.front_lbl.grid(row=1, column=0, sticky="w", pady=(0, 10))

        self.answer_txt = tk.Text(body, wrap="word", state="disabled")
        self.answer_txt.grid(row=2, column=0, sticky="nsew")

        btns = ttk.Frame(self)
        btns.grid(row=3, column=0, sticky="we", padx=12, pady=(0, 12))

        self.btn_show = ttk.Button(btns, text="Show answer", command=self._reveal)
        self.btn_show.pack(side="left")

        self.btn_again = ttk.Button(btns, text="Again", command=lambda: self._grade("again"), state="disabled")
        self.btn_hard = ttk.Button(btns, text="Hard", command=lambda: self._grade("hard"), state="disabled")
        self.btn_good = ttk.Button(btns, text="Good", command=lambda: self._grade("good"), state="disabled")
        self.btn_easy = ttk.Button(btns, text="Easy", command=lambda: self._grade("easy"), state="disabled")

        for b in [self.btn_again, self.btn_hard, self.btn_good, self.btn_easy]:
            b.pack(side="left", padx=(8, 0))

        ttk.Separator(btns, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Button(btns, text="Skip", command=self._skip).pack(side="left")
        ttk.Button(btns, text="Refresh", command=self._refresh).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Close", command=self.destroy).pack(side="right")

        self._refresh()

    def _set_answer(self, text: str):
        self.answer_txt.configure(state="normal")
        self.answer_txt.delete("1.0", "end")
        self.answer_txt.insert("1.0", text or "")
        self.answer_txt.configure(state="disabled")

    def _disable_grades(self):
        for b in [self.btn_again, self.btn_hard, self.btn_good, self.btn_easy]:
            b.configure(state="disabled")

    def _enable_grades(self):
        for b in [self.btn_again, self.btn_hard, self.btn_good, self.btn_easy]:
            b.configure(state="normal")

    def _current_card(self) -> Optional[Dict[str, Any]]:
        if not self._cards:
            return None
        self._idx = max(0, min(self._idx, len(self._cards) - 1))
        return self._cards[self._idx]

    def _refresh(self):
        self._set_answer("")
        self.prompt_lbl.configure(text="Loading…")
        self.front_lbl.configure(text="")
        self._disable_grades()
        self._revealed = False
        self._idx = 0

        def _fetch():
            try:
                cards = self.repo.list_due_sentences(self.story_id, limit=15)
            except Exception as e:
                cards = []
                err = str(e)
                self.after(0, lambda: messagebox.showerror("Sentence Revision", f"Failed to load due sentences:\n{err}"))
            self.after(0, lambda: self._set_cards(cards))

        threading.Thread(target=_fetch, daemon=True).start()

    def _set_cards(self, cards: List[Dict[str, Any]]):
        self._cards = cards or []
        self._revealed = False
        self._idx = 0
        self._render()

    def _render(self):
        total = len(self._cards)
        if total == 0:
            self.stats_lbl.configure(text=f"Due: 0 | Reviewed: {self._reviewed}")
            self.prompt_lbl.configure(text="No due sentences right now.")
            self.front_lbl.configure(text="Tip: in Learn, click 'Understood' on a sentence to add it to revision.")
            self._set_answer("")
            self.btn_show.configure(state="disabled")
            self._disable_grades()
            return

        self.btn_show.configure(state="normal")
        self.stats_lbl.configure(text=f"Due: {total} | Reviewed: {self._reviewed} | {self._idx + 1}/{total}")

        s = self._current_card() or {}
        en = ((s.get("translation") or {}).get("en") or "").strip()
        if not en:
            en = "(No English translation saved.)"
        self.prompt_lbl.configure(text=en)
        self.front_lbl.configure(text="Say/type the isiZulu sentence to yourself, then reveal.")

        if not self._revealed:
            self._set_answer("")
            self._disable_grades()
        else:
            self._set_answer(self._format_answer(s))
            self._enable_grades()

    def _format_answer(self, s: Dict[str, Any]) -> str:
        zu = (s.get("text_zu") or "").strip()
        g = s.get("grammar") or {}
        brief = (g.get("brief") or "").strip()
        concepts = g.get("concepts") or []
        if isinstance(concepts, list):
            concepts_str = ", ".join([str(c).strip() for c in concepts if str(c).strip()])
        else:
            concepts_str = str(concepts).strip()

        lines = []
        if zu:
            lines.append("isiZulu:")
            lines.append(zu)

        if brief:
            lines.append("")
            lines.append("Grammar:")
            lines.append(brief)

        if concepts_str:
            lines.append("")
            lines.append(f"Concepts: {concepts_str}")

        return "\n".join(lines).strip() or "(No isiZulu text saved for this sentence.)"

    def _reveal(self):
        if not self._cards:
            return
        self._revealed = True
        self._render()

    def _skip(self):
        if not self._cards:
            return
        self._revealed = False
        self._idx = (self._idx + 1) % len(self._cards)
        self._render()

    def _grade(self, rating: str):
        s = self._current_card()
        if not s:
            return
        sid = (s.get("id") or "").strip()
        if not sid:
            return

        patch = sm2_update(s.get("learning") or {}, rating, now=datetime.now(timezone.utc))

        def _save():
            try:
                self.repo.update_sentence_learning(self.story_id, sid, patch)
            except Exception as e:
                err = str(e)
                self.after(0, lambda: messagebox.showerror("Sentence Revision", f"Failed to save review:\n{err}"))
                return

            def _advance():
                self._reviewed += 1
                if self._cards:
                    self._cards.pop(self._idx)
                self._revealed = False
                if self._idx >= len(self._cards):
                    self._idx = 0
                self._render()

            self.after(0, _advance)

        threading.Thread(target=_save, daemon=True).start()
