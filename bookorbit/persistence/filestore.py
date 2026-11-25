"""FileStore - the only class that reads or writes data files (SRS 4.4).

Each table is data/<table>.txt holding one JSON object per line (JSON Lines).
Appends are a single write under a lock; full rewrites go to a temp file that
os.replace() swaps in atomically, so a crash never leaves a half-written table.
"""
import json
import os
import threading
from pathlib import Path

# Primary-key field of each table (SRS Table 9). Used by next_id().
PRIMARY_KEYS = {
    "users": "user_id",
    "biometrics": "template_id",
    "login_attempts": "attempt_id",
    "books": "book_id",
    "transactions": "txn_id",
    "purchases": "purchase_id",
    "reviews": "review_id",
    "warnings": "warning_id",
    "taboo_words": "word",
    "browse_history": "event_id",
    "chat_log": "msg_id",
    "reading_progress": "progress_id",
    "status_changes": "change_id",
    "admin_actions": "action_id",
    "rag_chunks": "chunk_id",
}


class FileStore:
    def __init__(self, data_dir: str | Path):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        # RLock: update() calls save_all() while already holding the lock.
        self.lock = threading.RLock()

    def resolve(self, rel_path: str | None) -> Path | None:
        """Files referenced by records (covers, .npy templates) are stored relative
        to the data folder so the project can be moved; this turns them into real paths."""
        return None if not rel_path else self.dir / rel_path

    def _path(self, table: str) -> Path:
        return self.dir / f"{table}.txt"

    def load(self, table: str) -> list[dict]:
        path = self._path(table)
        if not path.exists():
            return []
        records = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    records.append(json.loads(line))
        return records

    def append(self, table: str, record: dict) -> dict:
        with self.lock:
            with self._path(table).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def save_all(self, table: str, records: list[dict]) -> None:
        path = self._path(table)
        tmp = path.with_suffix(".txt.tmp")
        with self.lock:
            with tmp.open("w", encoding="utf-8") as fh:
                for r in records:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            os.replace(tmp, path)  # atomic swap

    def update(self, table: str, key: str, value, changes: dict) -> dict:
        with self.lock:  # read-modify-write must not interleave with another writer
            records = self.load(table)
            hit = None
            for r in records:
                if r.get(key) == value:
                    r.update(changes)
                    hit = r
            if hit is None:
                raise KeyError((table, key, value))
            self.save_all(table, records)
            return hit

    def find(self, table: str, key: str, value) -> dict | None:
        for r in self.load(table):
            if r.get(key) == value:
                return r
        return None

    def next_id(self, table: str, prefix: str) -> str:
        """New id such as R-0013: highest existing number + 1, zero-padded to 4."""
        pk = PRIMARY_KEYS[table]
        nums = []
        for r in self.load(table):
            tail = str(r.get(pk, "")).rsplit("-", 1)[-1]
            if tail.isdigit():
                nums.append(int(tail))
        n = max(nums) + 1 if nums else 1
        return f"{prefix}-{n:04d}"
