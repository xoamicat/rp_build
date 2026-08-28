"""Durable, privacy-safe persistence for Offer Locks and Test Mode handoffs.

The ledger is the append-only source of evidence.  This small companion store
keeps the signed OfferLock snapshot and the non-sensitive Test Mode order
handoff addressable after a process restart.  It deliberately stores no raw
buyer utterance, checkout response body, payment credential or webhook secret.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from .evidence import SignedEvidence
from .offer_lock import BuyerApproval, OfferLine, OfferLock, OfferTerms


class DurableOfferStore:
    """SQLite persistence enabled only for a configured production evidence key."""

    def __init__(self, path: str) -> None:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        self.path = str(file_path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS atlas_offer_locks (
                lock_id TEXT PRIMARY KEY,
                txn TEXT NOT NULL,
                terms_json TEXT NOT NULL,
                approval_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_atlas_offer_locks_txn ON atlas_offer_locks(txn)")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS atlas_test_mode_orders (
                order_id TEXT PRIMARY KEY,
                lock_id TEXT NOT NULL,
                txn TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_atlas_test_orders_lock ON atlas_test_mode_orders(lock_id)")
        self.conn.commit()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def put_lock(self, lock: OfferLock) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO atlas_offer_locks(lock_id,txn,terms_json,approval_json,evidence_json,created_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(lock_id) DO UPDATE SET txn=excluded.txn, terms_json=excluded.terms_json,
                   approval_json=excluded.approval_json, evidence_json=excluded.evidence_json""",
                (
                    lock.lock_id, lock.txn, self._json(lock.terms.as_dict()), self._json(lock.approval.as_dict()),
                    self._json(lock.evidence.as_dict()), time.time(),
                ),
            )

    def get_lock(self, lock_id: str) -> Optional[OfferLock]:
        row = self.conn.execute(
            "SELECT txn,terms_json,approval_json,evidence_json FROM atlas_offer_locks WHERE lock_id=?", (lock_id,)
        ).fetchone()
        if row is None:
            return None
        txn, terms_raw, approval_raw, evidence_raw = row
        terms = json.loads(terms_raw)
        approval = json.loads(approval_raw)
        return OfferLock(
            txn=txn,
            terms=OfferTerms(
                merchant_id=terms["merchant_id"], offer_id=terms["offer_id"],
                catalog_version=terms["catalog_version"],
                lines=tuple(OfferLine(
                    sku=line["sku"], name=line["name"], qty=int(line["qty"]), unit_paise=int(line["unit_paise"])
                ) for line in terms["lines"]),
                currency=terms.get("currency", "INR"), shipping_paise=int(terms.get("shipping_paise", 0)),
                tax_paise=int(terms.get("tax_paise", 0)), delivery_by=terms.get("delivery_by"),
                return_policy_version=terms.get("return_policy_version"),
                substitution_policy=terms.get("substitution_policy", "no_substitution"),
                renewal_summary=terms.get("renewal_summary"),
            ),
            approval=BuyerApproval(
                approval_ref=approval["approval_ref"], playback=approval["playback"],
                channel=approval.get("channel", "agent"), principal_ref=approval.get("principal_ref"),
            ),
            evidence=SignedEvidence(**json.loads(evidence_raw)),
        )

    def find_lock_by_prefix(self, prefix: str) -> Optional[OfferLock]:
        """Resolve legacy short evidence-session URLs only when unambiguous."""
        rows = self.conn.execute(
            "SELECT lock_id FROM atlas_offer_locks WHERE lock_id LIKE ? LIMIT 2", (prefix + "%",)
        ).fetchall()
        return self.get_lock(rows[0][0]) if len(rows) == 1 else None

    def put_test_order(self, order_id: str, state: dict[str, Any]) -> None:
        safe_state = dict(state)
        safe_state.pop("razorpay_signature", None)
        safe_state.pop("payment_id", None)
        with self.conn:
            self.conn.execute(
                """INSERT INTO atlas_test_mode_orders(order_id,lock_id,txn,state_json,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(order_id) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at""",
                (order_id, str(safe_state["lock_id"]), str(safe_state["txn"]), self._json(safe_state), time.time()),
            )

    def get_test_order(self, order_id: str) -> Optional[dict[str, Any]]:
        row = self.conn.execute("SELECT state_json FROM atlas_test_mode_orders WHERE order_id=?", (order_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def find_test_order_for_lock(self, lock_id: str) -> Optional[dict[str, Any]]:
        row = self.conn.execute(
            "SELECT state_json FROM atlas_test_mode_orders WHERE lock_id=? ORDER BY updated_at DESC LIMIT 1", (lock_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None
