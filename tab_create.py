# tab_create.py
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from models import StoryCreateRequest


class CreateTab(ttk.Frame):
    def __init__(self, parent, service):
        super().__init__(parent)
        self.service = service
        self._build()

    def _build(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)

        # Title
        ttk.Label(self, text="Title").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        self.title_var = tk.StringVar(value="Untitled")
        ttk.Entry(self, textvariable=self.title_var).grid(
            row=0, column=1, sticky="we", padx=10, pady=(10, 0)
        )

        # Level
        ttk.Label(self, text="Level").grid(row=1, column=0, sticky="w", padx=10, pady=(10, 0))
        self.level_var = tk.StringVar(value="A1")
        ttk.Combobox(
            self,
            textvariable=self.level_var,
            state="readonly",
            values=["A1", "A2", "B1", "B2", "C1", "C2", "Unknown"],
            width=10,
        ).grid(row=1, column=1, sticky="w", padx=10, pady=(10, 0))

        # Options
        self.lexicon_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="Build lexicon_words", variable=self.lexicon_var).grid(
            row=2, column=0, sticky="w", padx=10, pady=(10, 0)
        )

        self.enrich_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self,
            text="Enrich lexicon (lemma / POS / noun class) with Gemini",
            variable=self.enrich_var,
        ).grid(row=2, column=1, sticky="w", padx=10, pady=(10, 0))

        # Story text
        ttk.Label(self, text="Paste isiZulu story").grid(
            row=3, column=0, sticky="nw", padx=10, pady=(10, 0)
        )
        self.text = tk.Text(self, wrap="word")
        self.text.grid(row=3, column=1, sticky="nsew", padx=10, pady=(10, 0))

        # Buttons
        btns = ttk.Frame(self)
        btns.grid(row=4, column=0, columnspan=2, sticky="we", padx=10, pady=10)

        self.save_btn = ttk.Button(btns, text="Generate + Save", command=self._on_save)
        self.save_btn.pack(side="left")

        ttk.Button(btns, text="Clear", command=lambda: self.text.delete("1.0", "end")).pack(
            side="left", padx=8
        )

        # Log
        self.log = tk.Text(self, height=8, wrap="word", state="disabled")
        self.log.grid(row=5, column=0, columnspan=2, sticky="we", padx=10, pady=(0, 10))

    def _set_busy(self, busy: bool):
        self.save_btn.configure(state=("disabled" if busy else "normal"))

    def _append_log(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _on_save(self):
        title = self.title_var.get().strip()
        level = self.level_var.get().strip()
        text_zu = self.text.get("1.0", "end").strip()

        if not text_zu:
            messagebox.showwarning("Missing text", "Paste a story first.")
            return

        build_lexicon = bool(self.lexicon_var.get())
        enrich = bool(self.enrich_var.get())

        self._set_busy(True)
        self._append_log("Starting...")

        def progress(msg: str):
            self.after(0, lambda: self._append_log(msg))

        def worker():
            try:
                req = StoryCreateRequest(title=title, level=level, text_zu=text_zu)
                res = self.service.create_story_from_text(
                    req,
                    progress=progress,
                    build_lexicon=build_lexicon,
                    lexicon_enrich_with_gemini=enrich,
                )
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Saved",
                        f"Story saved.\nStory ID: {res.story_id}\nSentences: {res.sentence_count}",
                    ),
                )
            except Exception as e:
                err = str(e)
                self.after(0, lambda err=err: messagebox.showerror("Error", err))

            finally:
                self.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()
