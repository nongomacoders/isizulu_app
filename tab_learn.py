# tab_learn.py
# Minimal "Learn" tab:
# - Choose a story
# - Navigate sentence-by-sentence
# - Hide/Show English
# - Hint button cycles: (1) concepts only -> (2) grammar brief + concepts -> (3) off
# - Click a word to view dictionary (lemma, POS, noun class, infinitive, etc.)
# - NEW: "Understood" button marks all words in sentence as learning.known=True

import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Dict, Any, Optional

from utils_text import tokenize_zu
from story_service import normalize_word_id


class LearnTab(ttk.Frame):
    def __init__(self, parent, repo):
        super().__init__(parent)
        self.repo = repo

        self.stories: List[Dict[str, Any]] = []
        self.sentences: List[Dict[str, Any]] = []
        self.story_id: Optional[str] = None
        self.idx: int = 0

        # English visibility + hint cycling
        self.show_english = tk.BooleanVar(value=True)
        self.hint_state = 0  # 0=off, 1=concepts only, 2=brief+concepts

        # Cache for the displayed sentence
        self._full_cache = ""       # English + grammar
        self._hint1_cache = ""      # concepts only
        self._hint2_cache = ""      # brief + concepts

        self._build()
        self._refresh_stories()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # Top row: story chooser
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="we", padx=10, pady=10)
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Story").grid(row=0, column=0, sticky="w")
        self.story_var = tk.StringVar(value="")
        self.story_combo = ttk.Combobox(top, textvariable=self.story_var, state="readonly")
        self.story_combo.grid(row=0, column=1, sticky="we", padx=(8, 8))
        self.story_combo.bind("<<ComboboxSelected>>", lambda e: self._load_selected_story())

        ttk.Button(top, text="Refresh", command=self._refresh_stories).grid(row=0, column=2, sticky="e")

        # Nav row: previous/next + hide/show + hint + understood
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

        # Main area
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
        ttk.Label(main, text="Dictionary").grid(row=2, column=1, sticky="w", pady=(10, 0))

        self.info_txt = tk.Text(main, height=10, wrap="word", state="disabled")
        self.info_txt.grid(row=3, column=0, sticky="nsew", padx=(0, 10), pady=(4, 0))

        self.word_txt = tk.Text(main, height=10, wrap="word", state="disabled")
        self.word_txt.grid(row=3, column=1, sticky="nsew", pady=(4, 0))

    # -----------------------------
    # Story loading
    # -----------------------------

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

    # -----------------------------
    # Navigation
    # -----------------------------

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

    # -----------------------------
    # Hide/show English and hints
    # -----------------------------

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

    # -----------------------------
    # Learning action
    # -----------------------------

    def _current_sentence_tokens(self) -> List[str]:
        if not self.sentences:
            return []
        s = self.sentences[self.idx]
        toks = s.get("tokens")
        if isinstance(toks, list) and toks:
            return [str(t).strip() for t in toks if str(t).strip()]

        # Fallback for older sentences that don't store tokens
        zu = (s.get("text_zu") or "").strip()
        return tokenize_zu(zu)

    def _mark_sentence_understood(self):
        if not self.sentences:
            return

        toks = self._current_sentence_tokens()
        if not toks:
            messagebox.showwarning("No tokens", "No words found for this sentence.")
            return

        # Normalize and de-duplicate
        word_ids = sorted({normalize_word_id(t) for t in toks})

        try:
            for wid in word_ids:
                # Minimal: mark known. (You can later expand to SM-2 scheduling.)
                self.repo.update_word_learning(wid, {"known": True})
        except Exception as e:
            messagebox.showerror("Error", f"Failed to mark words as known:\n{e}")
            return

        messagebox.showinfo("Saved", f"Marked {len(word_ids)} word(s) as known.")

    # -----------------------------
    # Rendering
    # -----------------------------

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

        # Hint caches
        self._hint1_cache = (f"Concepts: {concepts_str}" if concepts_str else "Concepts: (none)").strip()
        if brief and concepts_str:
            self._hint2_cache = f"{brief}\n\nConcepts: {concepts_str}".strip()
        elif brief:
            self._hint2_cache = brief
        elif concepts_str:
            self._hint2_cache = f"Concepts: {concepts_str}"
        else:
            self._hint2_cache = "(No grammar saved for this sentence.)"

        # Full cache
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

    # -----------------------------
    # Dictionary lookup
    # -----------------------------

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

        lines = [f"Token: {token}", f"Word ID: {wid}"]

        # Learning state (optional display)
        learning = w.get("learning") or {}
        if isinstance(learning, dict) and learning:
            known = learning.get("known")
            if known is not None:
                lines.append(f"Known: {known}")

        if w.get("lemma"):
            lines.append(f"Lemma: {w.get('lemma')}")
        if w.get("pos"):
            lines.append(f"POS: {w.get('pos')}")
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

        self._set_text(self.word_txt, "\n".join(lines))

    # -----------------------------
    # Utility
    # -----------------------------

    def _set_text(self, widget: tk.Text, text: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text or "")
        widget.configure(state="disabled")
