# gui.py
import tkinter as tk
from tkinter import ttk

from tab_create import CreateTab
from tab_learn import LearnTab


class MainGUI(tk.Tk):
    def __init__(self, service, repo):
        super().__init__()
        self.title("isiZulu Story App")
        self.geometry("1000x760")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        nb.add(CreateTab(nb, service=service), text="Create")
        nb.add(LearnTab(nb, repo=repo), text="Learn")
