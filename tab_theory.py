# tab_theory.py
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Dict, Any, Optional
import re
import time
import threading
import logging
logger = logging.getLogger(__name__)



def normalize_concept_id(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
MD_CODE_RE = re.compile(r"`([^`]+)`")


def _clear_and_enable(text: tk.Text):
    text.configure(state="normal")
    text.delete("1.0", "end")


def _disable(text: tk.Text):
    text.configure(state="disabled")


def configure_markdown_tags(text: tk.Text):
    text.tag_configure("h1", font=("Segoe UI", 14, "bold"), spacing1=6, spacing3=6)
    text.tag_configure("h2", font=("Segoe UI", 14, "bold"), spacing1=4, spacing3=4)
    text.tag_configure("bold", font=("Segoe UI", 14, "bold"))
    # Inline `code` appears as monospace but without a border; use bold+italic for emphasis.
    text.tag_configure("code", font=("Consolas", 14, "bold", "italic"))
    text.tag_configure("bullet", lmargin1=18, lmargin2=36)
    text.tag_configure("mono", font=("Consolas", 14))


def insert_inline_md(text: tk.Text, s: str):
    i = 0
    while i < len(s):
        bold_m = MD_BOLD_RE.search(s, i)
        code_m = MD_CODE_RE.search(s, i)

        candidates = [m for m in [bold_m, code_m] if m is not None]
        if not candidates:
            text.insert("end", s[i:])
            return

        m = min(candidates, key=lambda m: m.start())
        if m.start() > i:
            text.insert("end", s[i:m.start()])

        if m.re is MD_BOLD_RE:
            text.insert("end", m.group(1), ("bold",))
        else:
            text.insert("end", m.group(1), ("code",))

        i = m.end()


def render_markdown(text: tk.Text, md: str):
    _clear_and_enable(text)

    lines = (md or "").splitlines()
    for raw in lines:
        line = raw.rstrip("\n")

        if not line.strip():
            text.insert("end", "\n")
            continue

        if line.startswith("## "):
            text.insert("end", line[3:].strip() + "\n", ("h2",))
            continue

        if line.startswith("# "):
            text.insert("end", line[2:].strip() + "\n", ("h1",))
            continue

        if line.lstrip().startswith("- "):
            content = line.lstrip()[2:].strip()
            text.insert("end", "• ", ("bullet",))
            insert_inline_md(text, content)
            text.insert("end", "\n", ("bullet",))
            continue

        insert_inline_md(text, line)
        text.insert("end", "\n")

    _disable(text)


class TheoryTab(ttk.Frame):
    def __init__(self, parent, repo, gemini):
        super().__init__(parent)
        self.repo = repo
        self.gemini = gemini

        self._ui_font = ("Segoe UI", 14)
        self._ui_font_bold = ("Segoe UI", 14, "bold")

        self.current_docs: List[Dict[str, Any]] = []
        self.selected_doc: Optional[Dict[str, Any]] = None

        self._missing_concepts: List[str] = []
        self._last_concepts: List[str] = []
        self._is_generating = False
                # Theory catalog cache (fast missing detection)
        self._theory_catalog_keys: set[str] = set()
        self._theory_catalog_loaded = False


        self._build()

    def _configure_theory_styles(self) -> None:
        """Local ttk styles for this tab only (avoid changing the whole app)."""
        style = ttk.Style(self)
        style.configure("Theory14.TLabel", font=self._ui_font)
        style.configure("Theory14.Title.TLabel", font=self._ui_font_bold)
        style.configure("Theory14.TButton", font=self._ui_font)
        style.configure("Theory14.TEntry", font=self._ui_font)
        # Listbox/Text are classic Tk widgets and are configured directly.

    def _build(self):
        self._configure_theory_styles()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="we", padx=10, pady=10)
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Search / Concept", style="Theory14.TLabel").grid(row=0, column=0, sticky="w")

        self.query_var = tk.StringVar(value="")
        self.query_entry = ttk.Entry(top, textvariable=self.query_var, style="Theory14.TEntry")
        self.query_entry.grid(row=0, column=1, sticky="we", padx=(8, 8))
        self.query_entry.bind("<Return>", lambda e: self._search())

        ttk.Button(top, text="Search", command=self._search, style="Theory14.TButton").grid(row=0, column=2, sticky="e")

        ttk.Button(top, text="Show all theory", command=self._show_all, style="Theory14.TButton").grid(
            row=0, column=3, sticky="e", padx=(8, 0)
        )

        self.create_btn = ttk.Button(top, text="Generate with Gemini", command=self._generate_missing, style="Theory14.TButton")
        self.create_btn.grid(row=0, column=4, sticky="e", padx=(8, 0))
        self.create_btn.configure(state="disabled")

        self.generate_all_btn = ttk.Button(top, text="Generate all missing", command=self._generate_all_missing, style="Theory14.TButton")
        self.generate_all_btn.grid(row=0, column=5, sticky="e", padx=(8, 0))
        self.generate_all_btn.configure(state="disabled")

        ttk.Button(top, text="Clear", command=self._clear, style="Theory14.TButton").grid(row=0, column=6, sticky="e", padx=(8, 0))

        main = ttk.Frame(self)
        main.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)

        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        ttk.Label(left, text="Theory topics", style="Theory14.TLabel").grid(row=0, column=0, sticky="w")

        self.listbox = tk.Listbox(left, height=12, font=self._ui_font)
        self.listbox.grid(row=1, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._select())

        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self.title_lbl = ttk.Label(right, text="(select a topic)", style="Theory14.Title.TLabel")
        self.title_lbl.grid(row=0, column=0, sticky="w")

        self.text = tk.Text(right, wrap="word", state="disabled", font=self._ui_font)
        self.text.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        configure_markdown_tags(self.text)

    # -----------------------------
    # Public hook from Learn tab
    # -----------------------------
    def load_concepts(self, concepts: List[str]) -> None:
        if not concepts:
            messagebox.showinfo("Theory", "No concepts for this sentence.")
            return

        self._last_concepts = list(concepts)

        concepts_norm = [normalize_concept_id(c) for c in concepts if (c or "").strip()]
        concepts_norm = [c for c in concepts_norm if c]
        if not concepts_norm:
            messagebox.showinfo("Theory", "No usable concepts for this sentence.")
            return

        self.query_var.set(concepts_norm[0])

        try:
            docs = self.repo.get_theory_by_concepts(concepts_norm, limit=50)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load theory:\n{e}")
            return

        self._set_results(docs)

                # Fast missing detection using catalog (ONE read)
        existing_keys = self._load_theory_catalog_keys(force=False)
        missing = [cid for cid in concepts_norm if cid not in existing_keys]
        self._missing_concepts = missing


        if docs:
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(0)
            self._select()

        if missing and not self._is_generating:
            self.create_btn.configure(state="normal")
            self.generate_all_btn.configure(state="normal")
            msg = "Missing theory docs:\n- " + "\n- ".join(missing[:12])
            if len(missing) > 12:
                msg += "\n- ..."
            self._append_block(msg + "\n\nTip: Click 'Generate all missing' to create them in one go.")
        elif not missing and not self._is_generating:
            self.create_btn.configure(state="disabled")
            self.generate_all_btn.configure(state="disabled")

    # -----------------------------
    # Buttons
    # -----------------------------
    def _show_all(self):
        try:
            docs = self.repo.list_theory_docs(limit=200)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load all theory docs:\n{e}")
            return

        self._set_results(docs)
        self._missing_concepts = []
        if not self._is_generating:
            self.create_btn.configure(state="disabled")
            self.generate_all_btn.configure(state="disabled")

        if docs:
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(0)
            self._select()
        else:
            self._set_text("(No theory docs in the database yet.)")

    def _clear(self):
        if self._is_generating:
            messagebox.showinfo("Busy", "Generation is still running.")
            return

        self.query_var.set("")
        self.current_docs = []
        self.selected_doc = None
        self._missing_concepts = []
        self._last_concepts = []
        self.listbox.delete(0, "end")
        self.title_lbl.configure(text="(select a topic)")
        self._set_text("")
        self.create_btn.configure(state="disabled")
        self.generate_all_btn.configure(state="disabled")

    def _search(self):
        if self._is_generating:
            messagebox.showinfo("Busy", "Generation is still running.")
            return

        q = (self.query_var.get() or "").strip()
        if not q:
            messagebox.showinfo("Search", "Type a concept id (e.g. subject_concords).")
            return

        cid = normalize_concept_id(q)

        try:
            docs = self.repo.search_theory(cid, limit=50)
        except Exception as e:
            messagebox.showerror("Error", f"Search failed:\n{e}")
            return

        self._set_results(docs)

        if docs:
            self._missing_concepts = []
            self.create_btn.configure(state="disabled")
            self.generate_all_btn.configure(state="disabled")
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(0)
            self._select()
        else:
            self._missing_concepts = [cid]
            self.create_btn.configure(state="normal")
            self.generate_all_btn.configure(state="disabled")
            self._set_text("(No theory doc found. Click 'Generate with Gemini'.)")

    def _generate_missing(self):
        cid = normalize_concept_id(self.query_var.get())
        if not cid:
            messagebox.showinfo("Generate", "Type a concept id first.")
            return

        self._missing_concepts = [cid]
        self._generate_all_missing()

    def _generate_all_missing(self):
        if self._is_generating:
            return

        missing = [normalize_concept_id(c) for c in (self._missing_concepts or []) if (c or "").strip()]
        missing = [c for c in missing if c]
        if not missing:
            messagebox.showinfo("Generate", "No missing concepts to generate.")
            return

        self._is_generating = True
        self.create_btn.configure(state="disabled")
        self.generate_all_btn.configure(state="disabled")
        self._set_text(f"Generating {len(missing)} theory docs with Gemini...\n\n")

        def worker(missing_list: List[str]):
            created = 0
            failed: List[str] = []

            def ui_append(s: str):
                self.after(0, lambda: self._append_text(s))

            try:
                for i, cid in enumerate(missing_list, start=1):
                    try:
                        if self.repo.theory_exists(cid):
                            ui_append(f"[{i}/{len(missing_list)}] Exists (skip): {cid}\n")
                            continue

                        ui_append(f"[{i}/{len(missing_list)}] Generating: {cid}...\n")
                        doc = self.gemini.generate_theory_doc(cid, context_concepts=[cid])
                        self.repo.create_or_update_theory_doc(cid, doc)
                        created += 1
                        ui_append(f"    Saved: {cid}\n")

                        time.sleep(0.25)

                    except Exception as e:
                        failed.append(cid)
                        logger.exception("Theory generation failed. cid=%s", cid)
                        ui_append(f"    FAILED {cid}: {e}\n")

            finally:
                def finish_ui():
                    self._append_text(f"\nDone. Created: {created}, Failed: {len(failed)}\n")

                    self._is_generating = False
                    # Catalog has changed (new docs). Force reload for accurate missing list.
                    self._invalidate_theory_catalog()

                    # Refresh LEFT PANEL to show newly created docs
                    if self._last_concepts:
                        self.load_concepts(self._last_concepts)
                    else:
                        self._show_all()

                    if failed:
                        messagebox.showwarning("Theory generation", f"Some concepts failed:\n- " + "\n- ".join(failed[:10]))
                    else:
                        messagebox.showinfo("Theory generation", f"Created {created} theory docs.")

                self.after(0, finish_ui)

        threading.Thread(target=worker, args=(missing,), daemon=True).start()

    # -----------------------------
    # UI helpers
    # -----------------------------
    def _append_text(self, extra: str):
        self.text.configure(state="normal")
        self.text.insert("end", extra)
        self.text.see("end")
        self.text.configure(state="disabled")

    def _append_block(self, extra: str):
        current = self.text.get("1.0", "end").strip()
        if current:
            current = current + "\n\n" + extra
        else:
            current = extra
        self._set_text(current)

    def _set_results(self, docs: List[Dict[str, Any]]):
        self.current_docs = docs or []
        self.listbox.delete(0, "end")

        for d in self.current_docs:
            cid = d.get("conceptId") or d.get("id") or ""
            title = (d.get("title") or cid or "(untitled)").strip()
            level = (d.get("level") or "").strip()
            label = f"{title}" + (f" [{level}]" if level else "")
            self.listbox.insert("end", label)

        self.title_lbl.configure(text="(select a topic)")
        self._set_text("")

    def _select(self):
        sel = self.listbox.curselection()
        if not sel:
            return

        idx = sel[0]
        if idx < 0 or idx >= len(self.current_docs):
            return

        d = self.current_docs[idx]
        self.selected_doc = d

        title = (d.get("title") or d.get("conceptId") or d.get("id") or "(untitled)").strip()
        self.title_lbl.configure(text=title)
        self._set_text(self._format_doc(d))

    def _format_doc(self, d: Dict[str, Any]) -> str:
        lines: List[str] = []

        cid = d.get("conceptId") or d.get("id") or ""
        short = (d.get("short") or "").strip()
        body = (d.get("body") or "").strip()
        level = (d.get("level") or "").strip()

        if cid:
            lines.append(f"Concept ID: {cid}")
        if level:
            lines.append(f"Level: {level}")
        if short:
            lines.append("")
            lines.append(short)

        if body:
            lines.append("")
            lines.append(body)

        examples = d.get("examples") or []
        if isinstance(examples, list) and examples:
            lines.append("")
            lines.append("## Examples")
            for ex in examples[:12]:
                if not isinstance(ex, dict):
                    continue
                zu = (ex.get("zu") or "").strip()
                en = (ex.get("en") or "").strip()
                note = (ex.get("note") or "").strip()
                if zu:
                    lines.append(f"- **ZU:** {zu}")
                if en:
                    lines.append(f"  **EN:** {en}")
                if note:
                    lines.append(f"  Note: {note}")

        tags = d.get("tags") or []
        if isinstance(tags, list) and tags:
            lines.append("")
            lines.append("Tags: " + ", ".join([str(t) for t in tags[:25]]))

        return "\n".join(lines).strip() or "(empty doc)"

    def _set_text(self, text: str):
        render_markdown(self.text, text or "")
    
    def _load_theory_catalog_keys(self, force: bool = False) -> set[str]:
        """
        Loads meta/theory_catalog once and caches keys locally.
        This avoids N Firestore reads when detecting missing concepts.
        """
        if self._theory_catalog_loaded and not force:
            return self._theory_catalog_keys

        try:
            m = self.repo.get_theory_catalog_map()  # one Firestore read
            self._theory_catalog_keys = set((k or "").strip().lower() for k in m.keys() if k)
            self._theory_catalog_loaded = True
        except Exception:
            # If catalog fails, keep existing cache (or empty) and fall back gracefully.
            logger.exception("Failed to load theory catalog map")
            self._theory_catalog_keys = set()
            self._theory_catalog_loaded = True

        return self._theory_catalog_keys

    def _invalidate_theory_catalog(self) -> None:
        # Call this after creating theory docs so missing detection reflects new docs.
        self._theory_catalog_loaded = False

