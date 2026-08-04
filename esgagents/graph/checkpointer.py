from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from langgraph.checkpoint.sqlite import SqliteSaver


def safe_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "unknown"


def thread_id(company_id: str, year: int, run_id: str) -> str:
    raw = f"{company_id.upper()}:{year}:{run_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@contextmanager
def get_checkpointer(cache_dir: str | Path, company_id: str) -> Generator[SqliteSaver, None, None]:
    cp_dir = Path(cache_dir) / "checkpoints"
    cp_dir.mkdir(parents=True, exist_ok=True)
    db_path = cp_dir / f"{safe_component(company_id).upper()}.db"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        saver.setup()
        yield saver
    finally:
        conn.close()
