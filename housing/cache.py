"""SQLite-backed key/value cache with TTL expiry.

Used to store Google Maps API responses so repeated pipeline runs only pay
for new or stale data.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Optional


class Cache:
    """A small persistent cache. Values are JSON-serialized."""

    def __init__(self, db_path: str = "cache/cache.db", table: str = "cache",
                 ttl_days: int = 14) -> None:
        if not table.isidentifier():
            raise ValueError(f"Invalid cache table name: {table!r}")
        self.db_path = str(db_path)
        self.table = table
        self.ttl_seconds = int(ttl_days * 24 * 60 * 60)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
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
        """Return the cached value, or None if missing, expired, or unreadable."""
        now = int(time.time())
        with self._connect() as conn:
            cur = conn.execute(
                f"SELECT value, updated_at FROM {self.table} WHERE key = ?", (key,)
            )
            row = cur.fetchone()
            if not row:
                return None
            value_json, updated_at = row
            if self.ttl_seconds > 0 and (now - int(updated_at)) > self.ttl_seconds:
                conn.execute(f"DELETE FROM {self.table} WHERE key = ?", (key,))
                conn.commit()
                return None
            try:
                return json.loads(value_json)
            except (TypeError, ValueError):
                return None

    def set(self, key: str, value: Any) -> None:
        now = int(time.time())
        value_json = json.dumps(value, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                f"REPLACE INTO {self.table} (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value_json, now),
            )
            conn.commit()
