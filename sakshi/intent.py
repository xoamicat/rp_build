"""The Intent Receipt.

Razorpay entities carry a ``notes`` object: at most 15 key-value pairs, each
value at most 256 characters. The settlement recon report returns ``notes``
and ``order_id`` on every settled line. So if the intent is written into the
order's notes at creation time, it travels with the money: into the payment,
into the settlement report, into the dispute. No new fields, no side database.

Privacy rule: the raw customer utterance never goes into notes or the ledger.
Only the agent's playback (a short restatement) and a hash of the utterance do.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional

from .ledger import canonical

NOTES_MAX_KEYS = 15
NOTES_MAX_LEN = 256
RECEIPT_VERSION = "ir0.1"


class NotesError(ValueError):
    pass


def validate_notes(notes: dict) -> None:
    """Enforce Razorpay's documented notes limits before we ever call the API."""
    if len(notes) > NOTES_MAX_KEYS:
        raise NotesError(f"notes has {len(notes)} keys; Razorpay allows {NOTES_MAX_KEYS}")
    for k, v in notes.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise NotesError(f"notes keys and values must be strings: {k!r}={v!r}")
        if len(k) > NOTES_MAX_LEN or len(v) > NOTES_MAX_LEN:
            raise NotesError(f"notes entry too long (> {NOTES_MAX_LEN} chars): {k!r}")


def truncate(text: str, limit: int = NOTES_MAX_LEN) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class IntentItem:
    name: str
    qty: int
    sku: Optional[str] = None

    def as_dict(self) -> dict:
        return {"name": self.name, "qty": self.qty, "sku": self.sku}


@dataclass
class IntentReceipt:
    txn: str
    utterance: str  # raw words (Hinglish welcome). Hashed, never stored in clear.
    playback: str  # agent's restatement, what the customer will see on the receipt
    items: list[IntentItem]
    cap_paise: Optional[int] = None
    currency: str = "INR"
    channel: str = "chat"  # chat | voice | whatsapp | app | llm
    lang: str = "en"
    mandate_ref: Optional[str] = None  # Reserve Pay / UPI Circle mandate, when delegated
    human_present: bool = True
    created_at: float = field(default_factory=time.time)

    # ------------------------------------------------------------- derived
    def utterance_hash(self) -> str:
        return hashlib.sha256(self.utterance.strip().encode("utf-8")).hexdigest()

    def intent_hash(self) -> str:
        body = canonical(
            {
                "txn": self.txn,
                "playback": self.playback,
                "items": [i.as_dict() for i in self.items],
                "cap_paise": self.cap_paise,
                "currency": self.currency,
                "mandate_ref": self.mandate_ref,
                "human_present": self.human_present,
                "created_at": round(self.created_at, 3),
                "utterance_hash": self.utterance_hash(),
            }
        )
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def ledger_payload(self) -> dict:
        """What goes into the ledger. Playback and hashes, never the raw words."""
        return {
            "intent_hash": self.intent_hash(),
            "utterance_hash": self.utterance_hash(),
            "playback": self.playback,
            "items": [i.as_dict() for i in self.items],
            "cap_paise": self.cap_paise,
            "currency": self.currency,
            "channel": self.channel,
            "lang": self.lang,
            "mandate_ref": self.mandate_ref,
            "human_present": self.human_present,
            "created_at": self.created_at,
        }

    def to_notes(self, gate_verdict: Optional[str] = None, extra: Optional[dict] = None) -> dict:
        """Razorpay-safe notes. Keys are prefixed so they never collide with the merchant's own."""
        notes = {
            "sakshi_v": RECEIPT_VERSION,
            "sakshi_txn": self.txn,
            "sakshi_intent": self.intent_hash(),
            "sakshi_playback": truncate(self.playback),
            "sakshi_cap": "" if self.cap_paise is None else str(self.cap_paise),
            "sakshi_ccy": self.currency,
            "sakshi_hp": "1" if self.human_present else "0",
            "sakshi_mandate": self.mandate_ref or "",
            "sakshi_gate": gate_verdict or "",
        }
        if extra:
            for k, v in extra.items():
                notes[str(k)] = truncate(str(v))
        validate_notes(notes)
        return notes


def make_txn_id(prefix: str = "txn") -> str:
    """Opaque transaction id. Not a Razorpay id; it links conversation, order, payment and settlement."""
    stamp = int(time.time() * 1000)
    return f"{prefix}_{stamp:x}"
