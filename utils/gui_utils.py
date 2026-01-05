import tkinter as tk
import re

MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
MD_CODE_RE = re.compile(r"`([^`]+)`")

def configure_markdown_tags(text: tk.Text):
    """Configures tags for markdown rendering in a tk.Text widget."""
    text.tag_configure("h1", font=("Segoe UI", 16, "bold"), spacing1=10, spacing3=10)
    text.tag_configure("h2", font=("Segoe UI", 14, "bold"), spacing1=8, spacing3=8)
    text.tag_configure("h3", font=("Segoe UI", 15, "bold"), foreground="#D35400", spacing1=6, spacing3=6)
    text.tag_configure("bold", font=("Segoe UI", 14, "bold"))
    # Inline `code` appears as monospace but without a border; use bold+italic for emphasis.
    text.tag_configure("code", font=("Consolas", 14, "bold", "italic"))
    text.tag_configure("bullet", lmargin1=18, lmargin2=40, spacing1=2)
    text.tag_configure("subbullet", lmargin1=48, lmargin2=70, spacing1=2)
    text.tag_configure("mono", font=("Consolas", 14))

def insert_inline_md(text: tk.Text, s: str):
    """Inserts text into a tk.Text widget, applying bold and code tags."""
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
    """Renders basic markdown (H1, H2, bullets, bold, code) into a tk.Text widget."""
    text.configure(state="normal")
    text.delete("1.0", "end")

    lines = (md or "").splitlines()
    for raw in lines:
        line = raw.rstrip("\n")

        if not line.strip():
            text.insert("end", "\n")
            continue

        if line.startswith("### "):
            text.insert("end", line[4:].strip() + "\n", ("h3",))
            continue

        if line.startswith("## "):
            text.insert("end", line[3:].strip() + "\n", ("h2",))
            continue

        if line.startswith("# "):
            text.insert("end", line[2:].strip() + "\n", ("h1",))
            continue

        stripped = line.lstrip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            indent = len(line) - len(stripped)
            content = stripped[2:].strip()
            
            # If indented by 2 or more spaces, treat as sub-bullet
            if indent >= 2:
                text.insert("end", "◦ ", ("subbullet",))
                insert_inline_md(text, content)
                text.insert("end", "\n", ("subbullet",))
            else:
                text.insert("end", "• ", ("bullet",))
                insert_inline_md(text, content)
                text.insert("end", "\n", ("bullet",))
            continue

        insert_inline_md(text, line)
        text.insert("end", "\n")

    text.configure(state="disabled")
