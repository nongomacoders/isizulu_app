from datetime import datetime
from typing import Callable

def log(progress: Callable[[str], None], level: str, msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    progress(f"[{level}] {ts} - {msg}")
