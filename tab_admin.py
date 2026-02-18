# tab_admin.py

import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Dict, List, Optional


class AdminTab(ttk.Frame):
    def __init__(self, parent, repo):
        super().__init__(parent)
        self.repo = repo

        self.stories: List[Dict[str, Any]] = []
        self._id_by_iid: Dict[str, str] = {}

        self._busy = False

        self._build()
        self._refresh()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="we", padx=10, pady=10)
        top.columnconfigure(0, weight=1)

        self.refresh_btn = ttk.Button(top, text="Refresh", command=self._refresh)
        self.refresh_btn.grid(row=0, column=1, sticky="e")

        self.delete_btn = ttk.Button(top, text="Delete Selected", command=self._delete_selected)
        self.delete_btn.grid(row=0, column=2, sticky="e", padx=(8, 0))

        body = ttk.Frame(self)
        body.grid(row=1, column=0, sticky="nsew", padx=10)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        cols = ("title", "sentenceCount")
        self.tree = ttk.Treeview(body, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("title", text="Title")
        self.tree.heading("sentenceCount", text="Sentences")
        self.tree.column("title", width=720, anchor="w")
        self.tree.column("sentenceCount", width=120, anchor="e")
        self.tree.grid(row=0, column=0, sticky="nsew")

        sb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)

        self.log = tk.Text(self, height=8, wrap="word", state="disabled")
        self.log.grid(row=2, column=0, sticky="we", padx=10, pady=(10, 10))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.refresh_btn.configure(state=state)
        self.delete_btn.configure(state=state)

    def _append_log(self, msg: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _selected_story_id(self) -> Optional[str]:
        sel = self.tree.selection()
        if not sel:
            return None
        return self._id_by_iid.get(sel[0])

    def _refresh(self) -> None:
        if self._busy:
            return

        self._set_busy(True)
        self._append_log("Refreshing stories...")

        def worker():
            try:
                stories = self.repo.list_stories(limit=250)
                self.after(0, lambda: self._render_stories(stories))
            except Exception as e:
                err = str(e)
                self.after(0, lambda err=err: messagebox.showerror("Admin", f"Failed to list stories:\n{err}"))
            finally:
                self.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _render_stories(self, stories: List[Dict[str, Any]]) -> None:
        self.stories = stories or []
        self._id_by_iid.clear()

        for iid in self.tree.get_children():
            self.tree.delete(iid)

        for s in self.stories:
            sid = (s.get("id") or "").strip()
            title = (s.get("title") or "Untitled").strip()
            count = s.get("sentenceCount")
            count_str = "" if count is None else str(count)

            iid = self.tree.insert("", "end", values=(f"{title} ({sid})", count_str))
            self._id_by_iid[iid] = sid

        self._append_log(f"Loaded {len(self.stories)} storie(s).")

    def _delete_selected(self) -> None:
        if self._busy:
            return

        sid = self._selected_story_id()
        if not sid:
            messagebox.showinfo("Admin", "Select a story first.")
            return

        confirm = messagebox.askyesno(
            "Confirm Delete",
            "Delete this story/song and all its sentences?\n\nThis cannot be undone.",
        )
        if not confirm:
            return

        self._set_busy(True)
        self._append_log(f"Deleting story: {sid} ...")

        def worker():
            try:
                deleted = self.repo.delete_story(sid)
                self.after(0, lambda: self._append_log(f"Deleted story {sid}. Sentences deleted: {deleted}"))
                self.after(0, self._refresh)
            except Exception as e:
                err = str(e)
                self.after(0, lambda err=err: messagebox.showerror("Admin", f"Failed to delete story:\n{err}"))
            finally:
                self.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()
