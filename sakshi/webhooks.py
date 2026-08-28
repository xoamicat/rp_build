"""Verified Razorpay webhook ingestion.

Webhooks are the source of truth after an order leaves an agent.  This module
verifies the exact raw request body before recording a minimal, privacy-safe
event in Sakshi's ledger.  It deliberately does not trust a transaction id
from the request URL or from a client-side caller.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from .ledger import Ledger


class WebhookSignatureError(ValueError):
    pass


def verify_webhook_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    """Validate Razorpay's HMAC-SHA256 signature using constant-time comparison."""
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


_KEEP = {
    "id", "entity", "amount", "amount_paid", "amount_due", "currency", "status", "order_id", "payment_id",
    "method", "captured", "notes", "created_at", "base_amount", "base_currency", "fee", "tax", "settlement_id",
}


def _slim(value: Any) -> dict[str, Any]:
    entity = value if isinstance(value, dict) else {}
    return {key: entity[key] for key in _KEEP if key in entity}


def _entity_and_txn(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    body = payload.get("payload") or {}
    for key in ("payment", "refund", "order", "dispute", "settlement"):
        candidate = body.get(key)
        entity = candidate.get("entity") if isinstance(candidate, dict) else None
        if isinstance(entity, dict):
            notes = entity.get("notes") or {}
            txn = str(notes.get("sakshi_txn", "unlinked")) if isinstance(notes, dict) else "unlinked"
            return entity, txn
    return {}, "unlinked"


@dataclass(frozen=True)
class WebhookReceipt:
    accepted: bool
    duplicate: bool
    txn: str
    event: str
    ledger_event_type: str
    fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class RazorpayWebhookIngestor:
    """Idempotently maps verified payment lifecycle events into the evidence ledger."""

    def __init__(self, ledger: Ledger, secret: str):
        self.ledger = ledger
        self.secret = secret

    def ingest(self, raw_body: bytes, signature: str | None, event_id: str | None = None) -> WebhookReceipt:
        if not verify_webhook_signature(raw_body, signature, self.secret):
            raise WebhookSignatureError("invalid Razorpay webhook signature")
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ValueError("verified webhook body is not JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("verified webhook body must be an object")

        fingerprint = hashlib.sha256(raw_body).hexdigest()
        event_name = str(data.get("event", "unknown"))
        entity, txn = _entity_and_txn(data)
        duplicate = any(
            (event_id and event.payload.get("webhook_event_id") == event_id)
            or event.payload.get("webhook_fingerprint") == fingerprint
            for event in self.ledger.events()
        )
        if duplicate:
            return WebhookReceipt(True, True, txn, event_name, "rzp.webhook.accepted", fingerprint)

        mapping = {
            "payment.captured": "rzp.payment.captured",
            "refund.created": "rzp.refund.created",
            "refund.processed": "rzp.refund.created",
            "payment.dispute.created": "rzp.dispute.created",
            "payment.dispute.won": "rzp.dispute.won",
            "payment.dispute.lost": "rzp.dispute.lost",
        }
        ledger_type = mapping.get(event_name, "rzp.webhook.accepted")
        event_payload = _slim(entity) | {
            "webhook_fingerprint": fingerprint,
            "webhook_event_id": event_id,
            "event": event_name,
        }
        self.ledger.append(txn, ledger_type, "razorpay_webhook", event_payload)
        return WebhookReceipt(True, False, txn, event_name, ledger_type, fingerprint)
