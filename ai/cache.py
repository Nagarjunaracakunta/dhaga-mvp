"""SQLite cache: identical comments are classified once, ever (per model + prompt version)."""
import hashlib
import sqlite3
from pathlib import Path
from . import config


def cache_key(normalized_comment: str, model_label: str) -> str:
    return hashlib.sha256(f"{config.PROMPT_VERSION}|{model_label}|{normalized_comment}".encode()).hexdigest()


class ClassificationCache:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS c (key TEXT PRIMARY KEY, value TEXT)")

    def get_many(self, keys: list) -> dict:
        out = {}
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            q = f"SELECT key, value FROM c WHERE key IN ({','.join('?' * len(chunk))})"
            out.update(dict(self.db.execute(q, chunk).fetchall()))
        return out

    def put_many(self, rows: dict):
        self.db.executemany("INSERT OR REPLACE INTO c VALUES (?, ?)", rows.items())
        self.db.commit()
