"""Signed evidence envelopes for intent and transaction-chain proofs.

The ledger is append-only and hash chained.  That detects accidental or
unsophisticated edits, but a database administrator could otherwise rewrite a
complete chain.  This module anchors the customer-approved intent and a final
transaction-chain head to an Ed25519 key held outside the database.

The public key is carried for portability, but a verifier should *also*
allow-list its key id/public key pair.  Do not treat a self-supplied public key
as an identity assertion.
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Any, Optional

from .ledger import Ledger, canonical


class EvidenceError(RuntimeError):
    """Raised when signing material is missing or malformed."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _payload_bytes(payload: dict[str, Any]) -> bytes:
    return canonical(payload).encode("utf-8")


@dataclass(frozen=True)
class SignedEvidence:
    """A portable, canonical, Ed25519-signed evidence payload."""

    payload: dict[str, Any]
    payload_hash: str
    signature: str
    public_key: str
    key_id: str
    algorithm: str = "Ed25519"

    def as_dict(self) -> dict[str, Any]:
        return {
            "payload": self.payload,
            "payload_hash": self.payload_hash,
            "signature": self.signature,
            "public_key": self.public_key,
            "key_id": self.key_id,
            "algorithm": self.algorithm,
        }

    def note_fields(self) -> dict[str, str]:
        """Compact proof references suitable for Razorpay's ``notes`` object."""
        return {
            "sakshi_eid": self.payload_hash[:24],
            "sakshi_kid": self.key_id,
            "sakshi_sig": self.signature,
        }


class EvidenceSigner:
    """Signs only canonical, privacy-safe evidence payloads with Ed25519."""

    def __init__(self, private_key: Any, key_id: str = "sakshi-dev-1") -> None:
        self._private_key = private_key
        self.key_id = key_id

    @classmethod
    def from_private_key_b64(cls, value: str, key_id: str) -> "EvidenceSigner":
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

            return cls(Ed25519PrivateKey.from_private_bytes(_unb64(value)), key_id)
        except Exception as exc:  # pragma: no cover - exact backend error varies
            raise EvidenceError("SAKSHI_EVIDENCE_PRIVATE_KEY_B64 is not a valid Ed25519 private key") from exc

    @classmethod
    def generate_for_demo(cls, key_id: str = "sakshi-demo-1") -> "EvidenceSigner":
        """Create an ephemeral signer for tests/demos; never use this for production proof."""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

            return cls(Ed25519PrivateKey.generate(), key_id)
        except ImportError as exc:  # pragma: no cover
            raise EvidenceError("pip install cryptography to enable signed evidence") from exc

    @classmethod
    def from_env(cls, private_key_b64: str, key_id: str) -> Optional["EvidenceSigner"]:
        return cls.from_private_key_b64(private_key_b64, key_id) if private_key_b64 else None

    @property
    def public_key_b64(self) -> str:
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        return _b64(self._private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))

    def sign(self, payload: dict[str, Any]) -> SignedEvidence:
        raw = _payload_bytes(payload)
        return SignedEvidence(
            payload=payload,
            payload_hash=hashlib.sha256(raw).hexdigest(),
            signature=_b64(self._private_key.sign(raw)),
            public_key=self.public_key_b64,
            key_id=self.key_id,
        )

    def verify(self, evidence: SignedEvidence, trusted_public_key: Optional[str] = None) -> bool:
        """Verify hash + signature, optionally pinning the expected public key."""
        if evidence.algorithm != "Ed25519":
            return False
        if trusted_public_key is not None and evidence.public_key != trusted_public_key:
            return False
        raw = _payload_bytes(evidence.payload)
        if hashlib.sha256(raw).hexdigest() != evidence.payload_hash:
            return False
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            Ed25519PublicKey.from_public_bytes(_unb64(evidence.public_key)).verify(
                _unb64(evidence.signature), raw
            )
            return True
        except Exception:
            return False

    def seal_transaction(self, ledger: Ledger, txn: str) -> SignedEvidence:
        """Sign the current per-transaction head, then append the seal to the ledger."""
        events = [event for event in ledger.chain(txn) if event.type != "evidence.sealed"]
        if not events:
            raise EvidenceError(f"cannot seal empty transaction {txn}")
        payload = {
            "type": "sakshi.transaction-chain.v1",
            "txn": txn,
            "event_count": len(events),
            "first_hash": events[0].hash,
            "head": events[-1].hash,
        }
        evidence = self.sign(payload)
        ledger.append(txn, "evidence.sealed", "sakshi", evidence.as_dict())
        return evidence

    def verify_latest_seal(self, ledger: Ledger, txn: str, trusted_public_key: Optional[str] = None) -> bool:
        seals = [event for event in ledger.chain(txn) if event.type == "evidence.sealed"]
        if not seals:
            return False
        seal_event = seals[-1]
        try:
            record = SignedEvidence(**seal_event.payload)
        except (TypeError, KeyError):
            return False
        preceding = [event for event in ledger.chain(txn) if event.seq < seal_event.seq and event.type != "evidence.sealed"]
        if not preceding:
            return False
        expected = {
            "type": "sakshi.transaction-chain.v1",
            "txn": txn,
            "event_count": len(preceding),
            "first_hash": preceding[0].hash,
            "head": preceding[-1].hash,
        }
        return record.payload == expected and self.verify(record, trusted_public_key)
