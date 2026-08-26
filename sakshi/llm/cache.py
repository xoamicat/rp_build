"""LLM response cache.

Every completion is keyed by (provider, model, system, prompt, json_mode). A repeated call
returns the stored answer without touching the network, so re-running a Kasauti batch,
re-judging transcripts, or re-running a demo never spends free-tier quota twice.
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from typing import Optional

from .provider import Provider


class LlmCache:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_cache (
                key        TEXT PRIMARY KEY,
                provider   TEXT NOT NULL,
                model      TEXT NOT NULL,
                response   TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        self.conn.commit()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key_for(provider: str, model: str, prompt: str, system: Optional[str], json_mode: bool) -> str:
        raw = "\x1f".join([provider, model, system or "", prompt, "json" if json_mode else "text"])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[str]:
        row = self.conn.execute("SELECT response FROM llm_cache WHERE key = ?", (key,)).fetchone()
        if row:
            self.hits += 1
            return row[0]
        self.misses += 1
        return None

    def put(self, key: str, provider: str, model: str, response: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO llm_cache (key, provider, model, response, created_at) VALUES (?,?,?,?,?)",
                (key, provider, model, response, time.time()),
            )

    def __len__(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0]


class CachedProvider:
    """Wraps any Provider. Identical requests are served from the cache."""

    def __init__(self, inner: Provider, cache: LlmCache):
        self.inner = inner
        self.cache = cache
        self.name = f"cached:{inner.name}"

    @property
    def model(self) -> str:
        return getattr(self.inner, "model", self.inner.name)

    def complete(self, prompt: str, system: Optional[str] = None, json_mode: bool = False) -> str:
        key = LlmCache.key_for(self.inner.name, self.model, prompt, system, json_mode)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        response = self.inner.complete(prompt, system=system, json_mode=json_mode)
        self.cache.put(key, self.inner.name, self.model, response)
        return response
