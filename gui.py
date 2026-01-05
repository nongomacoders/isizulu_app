import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

from tab_create import CreateTab
from tab_learn import LearnTab
from tab_theory import TheoryTab


class MainGUI(tk.Tk):
    def __init__(self, service, repo):
        super().__init__()
        self._configure_global_fonts()
        self.title("isiZulu Story App")
        self.geometry("1000x760")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        # Create tabs (ONLY ONCE each)
        self.create_tab = CreateTab(self.notebook, service=service)
        self.learn_tab = LearnTab(self.notebook, repo=repo, gemini=service.gemini)
        self.theory_tab = TheoryTab(self.notebook, repo=repo, gemini=service.gemini)

        # Add tabs
        self.notebook.add(self.create_tab, text="Create")
        self.notebook.add(self.learn_tab, text="Learn")
        self.notebook.add(self.theory_tab, text="Theory")

        # Allow Learn tab to open Theory tab cleanly
        self.learn_tab.set_theory_tab(self.theory_tab, self.notebook)

    def _configure_global_fonts(self) -> None:
        """Applies a consistent 14pt font across the entire GUI (Tk + ttk)."""
        family = "Segoe UI"
        size = 14

        # Update Tk named fonts so classic Tk widgets (Text/Listbox/etc.) inherit 14pt.
        for name in [
            "TkDefaultFont",
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
            "TkSmallCaptionFont",
            "TkIconFont",
            "TkTooltipFont",
        ]:
            try:
                f = tkfont.nametofont(name)
                f.configure(family=family, size=size)
            except Exception:
                pass

        # Keep fixed-width family, but ensure size is 14.
        try:
            fixed = tkfont.nametofont("TkFixedFont")
            fixed.configure(family="Consolas", size=size)
        except Exception:
            pass

        # Ensure ttk widgets pick up 14pt as well.
        style = ttk.Style(self)
        style.configure(".", font=(family, size))
        style.configure("TNotebook.Tab", font=(family, size))
        style.configure("TLabelframe.Label", font=(family, size))
        style.configure("Treeview", font=(family, size))
        style.configure("Treeview.Heading", font=(family, size, "bold"))
