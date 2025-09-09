import sqlite3
import os
import json
import time
from typing import Any, Optional


class Cache:
    def __init__(self, db_path: str = 'cache/cache.db', table: str = 'cache', ttl_days: int = 14) -> None:
        self.db_path = db_path
        self.table = table
        self.ttl_seconds = int(ttl_days * 24 * 60 * 60)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    def get(self, key: str) -> Optional[Any]:
        now = int(time.time())
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT value, updated_at FROM {self.table} WHERE key = ?", (key,))
            row = cur.fetchone()
            if not row:
                return None
            value_json, updated_at = row
            if self.ttl_seconds > 0 and (now - int(updated_at)) > self.ttl_seconds:
                try:
                    cur.execute(f"DELETE FROM {self.table} WHERE key = ?", (key,))
                    conn.commit()
                except Exception:
                    pass
                return None
            try:
                return json.loads(value_json)
            except Exception:
                return None

    def set(self, key: str, value: Any) -> None:
        now = int(time.time())
        value_json = json.dumps(value, ensure_ascii=False)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"REPLACE INTO {self.table} (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value_json, now)
            )
            conn.commit()



