"""Stage 4: correction memory.

Every human correction is stored once and applied to later runs, so the system's accuracy
improves without retraining anything. Three kinds of correction exist today:

    substitution_tolerance  "substitutions within ₹50 are fine for this merchant" -> raises
                            MerchantConfig.substitution_tolerance_paise, so the semantic
                            substitution judge stops flagging small price differences
    judge_override          "that transcript is fine, the judge was wrong" -> a pattern the
                            judge found on a transcript hash is suppressed next time (and the
                            reverse: a pattern a human added is noted for calibration)
    dispute_policy          "always refund delivery-fee disputes" -> a claim type maps to a
                            fixed recommendation for this merchant

Memory is per merchant and keyed by a stable id, never by free text. It records who corrected
and why, because a correction is itself evidence in a later dispute.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Optional

from .models import MerchantConfig

KINDS = ("substitution_tolerance", "judge_override", "dispute_policy")


class CorrectionMemory:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                merchant TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL,
                value TEXT NOT NULL, note TEXT, who TEXT, created_at REAL NOT NULL
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_corr ON corrections(merchant, kind, key)")
        self.conn.commit()

    # ----------------------------------------------------------------- write
    def learn(self, merchant: str, kind: str, key: str, value, note: str = "", who: str = "merchant") -> int:
        if kind not in KINDS:
            raise ValueError(f"unknown correction kind {kind}")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO corrections (merchant, kind, key, value, note, who, created_at) VALUES (?,?,?,?,?,?,?)",
                (merchant, kind, key, json.dumps(value), note, who, time.time()),
            )
            return cur.lastrowid

    # ------------------------------------------------------------------ read
    def latest(self, merchant: str, kind: str, key: str):
        row = self.conn.execute(
            "SELECT value FROM corrections WHERE merchant=? AND kind=? AND key=? ORDER BY id DESC LIMIT 1",
            (merchant, kind, key),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def all(self, merchant: Optional[str] = None) -> list[dict]:
        sql = "SELECT merchant, kind, key, value, note, who, created_at FROM corrections"
        args: tuple = ()
        if merchant:
            sql += " WHERE merchant=?"
            args = (merchant,)
        return [{"merchant": m, "kind": k, "key": key, "value": json.loads(v), "note": n, "who": w, "created_at": c}
                for m, k, key, v, n, w, c in self.conn.execute(sql + " ORDER BY id", args)]

    def __len__(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]

    # ------------------------------------------------------------ application
    def apply_to_merchant(self, merchant: MerchantConfig) -> MerchantConfig:
        tol = self.latest(merchant.merchant_id, "substitution_tolerance", "default")
        if tol is not None:
            merchant.substitution_tolerance_paise = int(tol)
        return merchant

    def rejected_patterns(self, merchant: str, transcript_hash: str) -> set[str]:
        """Patterns a human said were NOT present on this exact conversation."""
        out: set[str] = set()
        for c in self.all(merchant):
            if c["kind"] == "judge_override" and c["key"] == transcript_hash:
                for p in c["value"].get("rejected", []):
                    out.add(p)
        return out

    def dispute_policy(self, merchant: str, claim_type: str) -> Optional[str]:
        return self.latest(merchant, "dispute_policy", claim_type)

    # ---------------------------------------------------------- from labels
    def learn_from_labels(self, merchant: str, results: list[dict], labels: dict, who: str = "labeler") -> int:
        """Turn hand labels into judge overrides. ``results`` are run rows (dicts with transcript_hash and
        patterns); ``labels`` maps transcript_hash -> list of patterns a human saw. A pattern the judge
        found that the human did not is recorded as rejected for that conversation."""
        learned = 0
        by_hash: dict[str, set] = {}
        for r in results:
            by_hash.setdefault(r["transcript_hash"], set()).update(r.get("patterns", []))
        for h, found in by_hash.items():
            if h not in labels:
                continue
            human = set(labels[h])
            rejected = sorted(found - human)
            added = sorted(human - found)
            if rejected or added:
                self.learn(merchant, "judge_override", h, {"rejected": rejected, "added": added},
                           note="from hand labels", who=who)
                learned += 1
        return learned
