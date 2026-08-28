"""Append-only, hash-chained event ledger.

Every event stores the hash of the previous event, so editing or deleting any
row breaks verification.  A hash chain alone is *tamper-evident*, not
tamper-proof: configure :mod:`sakshi.evidence` to cryptographically anchor an
intent and completed transaction head outside this SQLite database.

Event types used across the lifecycle (drop 1 uses the first group):

    intent.captured     what the customer asked for (playback + hash, never the raw words)
    cart.assembled      what the agent built
    check.<checker>     one verdict per checker
    gate.verdict        aggregated Stage 1 decision
    human.override      a person approved, corrected or rejected
    policy.correction   an automatic merchant policy correction (not human approval)
    rzp.request         a call the agent made to Razorpay (via the interceptor)
    rzp.response        what Razorpay (or the stub) answered
    rzp.order.created / rzp.payment.captured / rzp.refund.created
    settlement.line     a settlement recon line joined to this transaction
    dispute.opened / dispute.verdict
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Optional

GENESIS = "0" * 64


def canonical(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace. Used for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


@dataclass(frozen=True)
class Event:
    seq: int
    ts: float
    txn: str
    type: str
    actor: str
    payload: dict
    prev_hash: str
    hash: str

    def as_dict(self) -> dict:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "txn": self.txn,
            "type": self.type,
            "actor": self.actor,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }


class Ledger:
    """SQLite-backed ledger. Safe for a single process; serialise writers if you go multi-process."""

    def __init__(self, path: str = ":memory:"):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                seq       INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        REAL    NOT NULL,
                txn       TEXT    NOT NULL,
                type      TEXT    NOT NULL,
                actor     TEXT    NOT NULL,
                payload   TEXT    NOT NULL,
                prev_hash TEXT    NOT NULL,
                hash      TEXT    NOT NULL UNIQUE
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_events_txn ON events(txn)")
        self.conn.commit()

    # ------------------------------------------------------------------ hashing
    @staticmethod
    def compute_hash(prev_hash: str, ts: float, txn: str, type_: str, actor: str, payload: dict) -> str:
        body = canonical({"ts": ts, "txn": txn, "type": type_, "actor": actor, "payload": payload})
        return hashlib.sha256(f"{prev_hash}|{body}".encode("utf-8")).hexdigest()

    def _last_hash(self) -> str:
        row = self.conn.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        return row[0] if row else GENESIS

    # ------------------------------------------------------------------ writes
    def append(self, txn: str, type_: str, actor: str, payload: dict, ts: Optional[float] = None) -> Event:
        ts = time.time() if ts is None else float(ts)
        with self.conn:
            prev = self._last_hash()
            h = self.compute_hash(prev, ts, txn, type_, actor, payload)
            cur = self.conn.execute(
                "INSERT INTO events (ts, txn, type, actor, payload, prev_hash, hash) VALUES (?,?,?,?,?,?,?)",
                (ts, txn, type_, actor, canonical(payload), prev, h),
            )
            return Event(cur.lastrowid, ts, txn, type_, actor, json.loads(canonical(payload)), prev, h)

    # ------------------------------------------------------------------ reads
    def _row_to_event(self, row) -> Event:
        seq, ts, txn, type_, actor, payload, prev_hash, h = row
        return Event(seq, ts, txn, type_, actor, json.loads(payload), prev_hash, h)

    def events(self, txn: Optional[str] = None, type_: Optional[str] = None) -> list[Event]:
        sql = "SELECT seq, ts, txn, type, actor, payload, prev_hash, hash FROM events"
        clauses, args = [], []
        if txn is not None:
            clauses.append("txn = ?")
            args.append(txn)
        if type_ is not None:
            clauses.append("type = ?")
            args.append(type_)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY seq"
        return [self._row_to_event(r) for r in self.conn.execute(sql, args)]

    def chain(self, txn: str) -> list[Event]:
        """All events for one transaction, in order. This is what the dispute agent reads."""
        return self.events(txn=txn)

    def latest(self, txn: str, type_: str) -> Optional[Event]:
        rows = self.events(txn=txn, type_=type_)
        return rows[-1] if rows else None

    def verify(self) -> tuple[bool, Optional[int]]:
        """Recompute every hash. Returns (ok, first_bad_seq)."""
        prev = GENESIS
        for ev in self.events():
            if ev.prev_hash != prev:
                return False, ev.seq
            expected = self.compute_hash(prev, ev.ts, ev.txn, ev.type, ev.actor, ev.payload)
            if expected != ev.hash:
                return False, ev.seq
            prev = ev.hash
        return True, None

    def close(self) -> None:
        self.conn.close()
