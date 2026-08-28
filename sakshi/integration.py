"""One production-shaped boundary for agentic checkout integrations.

Agents call this sidecar before creating an order.  The sidecar binds an
intent receipt to the order's Razorpay ``notes`` only after the gate passes,
then records the order response.  Payments and refunds arrive through
verified webhooks, not from an agent's assertion.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol

from .engine import Engine, GateResult
from .intent import IntentReceipt
from .models import Cart
from .offer_lock import OfferLock, OfferLockError, merge_offer_notes


class Gateway(Protocol):
    def create_order(self, amount: int, currency: str = "INR", receipt: Optional[str] = None,
                     notes: Optional[dict] = None) -> dict[str, Any]: ...


class CheckoutBlocked(PermissionError):
    def __init__(self, gate: GateResult):
        super().__init__(f"checkout blocked by Sakshi: {gate.status.value}")
        self.gate = gate


class EvidenceRequired(RuntimeError):
    """Raised when merchant policy requires signed proof but signing is not configured."""


@dataclass(frozen=True)
class GuardedOrder:
    intent: IntentReceipt
    gate: GateResult
    order: dict[str, Any]


@dataclass
class SakshiCheckout:
    engine: Engine
    gateway: Gateway

    def create_order(self, intent: IntentReceipt, cart: Cart, *, receipt: Optional[str] = None,
                     content: Optional[list[str]] = None, offer_lock: Optional[OfferLock] = None) -> GuardedOrder:
        require_signed = bool(self.engine.merchant.extra.get("require_signed_evidence"))
        if require_signed and self.engine.signer is None:
            raise EvidenceRequired("merchant requires signed evidence but no EvidenceSigner is configured")
        if not self.engine.ledger.latest(intent.txn, "intent.captured"):
            self.engine.capture_intent(intent)
        gate = self.engine.gate(intent, cart, content=content)
        if not gate.allowed:
            raise CheckoutBlocked(gate)
        if require_signed and not {"sakshi_eid", "sakshi_kid", "sakshi_sig"}.issubset(gate.notes):
            raise EvidenceRequired("merchant requires signed evidence but the order notes lack a proof reference")
        notes = gate.notes
        if offer_lock is not None:
            if offer_lock.txn != intent.txn:
                raise OfferLockError("offer lock must use the same transaction id as the guarded checkout")
            if self.engine.signer is None or not self.engine.signer.verify(
                offer_lock.evidence, self.engine.signer.public_key_b64
            ):
                raise EvidenceRequired("checkout requires an OfferLock signed by the configured trusted evidence key")
            notes = merge_offer_notes(notes, offer_lock)
        order = self.gateway.create_order(
            amount=cart.total_paise,
            currency=cart.currency,
            receipt=receipt or intent.txn,
            notes=notes,
        )
        self.engine.record_order(intent.txn, order)
        return GuardedOrder(intent, gate, order)
