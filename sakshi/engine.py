"""The engine runs checkers over a transaction and writes every step to the ledger.

Drop 1 covers Stage 1 (the gate) and the record-keeping the later stages read:
human overrides, Razorpay order and payment events. Stage 2 (settlement) and
Stage 3 (dispute, which is the same checkers in explain mode) come next.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .checkers.base import CheckContext, Checker, Status, Verdict, aggregate, total_impact
from .intent import IntentReceipt
from .ledger import Event, Ledger
from .models import Cart, MerchantConfig


@dataclass
class GateResult:
    txn: str
    status: Status
    verdicts: list[Verdict]
    impact_paise: int
    notes: dict  # ready to pass to Razorpay's Orders API
    event: Event

    @property
    def allowed(self) -> bool:
        return self.status in (Status.PASS, Status.FLAG)

    def summary(self) -> str:
        lines = [f"[{self.status.value}] txn={self.txn} impact=₹{self.impact_paise / 100:.2f}"]
        for v in self.verdicts:
            if v.status is not Status.SKIP:
                lines.append(f"  - {v.checker:<18} {v.status.value:<9} {v.reason}")
        return "\n".join(lines)


@dataclass
class Engine:
    ledger: Ledger
    merchant: MerchantConfig
    checkers: list[Checker] = field(default_factory=list)

    # ------------------------------------------------------------ stage 1
    def capture_intent(self, intent: IntentReceipt) -> Event:
        return self.ledger.append(intent.txn, "intent.captured", "customer", intent.ledger_payload())

    def gate(self, intent: IntentReceipt, cart: Cart, content: Optional[list[str]] = None) -> GateResult:
        """Compare the cart with the intent before any money moves."""
        self.ledger.append(intent.txn, "cart.assembled", "agent", cart.as_dict())
        ctx = CheckContext(merchant=self.merchant, intent=intent, cart=cart, content=content or [])
        verdicts: list[Verdict] = []
        for checker in self.checkers:
            if getattr(checker, "stage", 1) != 1:
                continue
            ctx.extras["prior_verdicts"] = list(verdicts)  # deterministic first, LLM checkers read these
            v = checker.check(ctx)
            verdicts.append(v)
            self.ledger.append(intent.txn, f"check.{checker.name}", "sakshi", v.as_dict())
        status = aggregate(verdicts)
        impact = total_impact(verdicts)
        ev = self.ledger.append(
            intent.txn, "gate.verdict", "sakshi",
            {
                "status": status.value,
                "impact_paise": impact,
                "reasons": [v.reason for v in verdicts if v.status not in (Status.PASS, Status.SKIP)],
                "intent_hash": intent.intent_hash(),
            },
        )
        return GateResult(intent.txn, status, verdicts, impact, intent.to_notes(gate_verdict=status.value), ev)

    # ------------------------------------------------------------ humans
    def record_human(self, txn: str, decision: str, note: str = "", corrected_cart: Optional[Cart] = None,
                     who: str = "merchant") -> Event:
        payload = {"decision": decision, "note": note, "who": who}
        if corrected_cart is not None:
            payload["corrected_cart"] = corrected_cart.as_dict()
        return self.ledger.append(txn, "human.override", "human", payload)

    # ------------------------------------------------------------ razorpay events
    def record_order(self, txn: str, order: dict) -> Event:
        return self.ledger.append(txn, "rzp.order.created", "razorpay", _slim(order))

    def record_payment(self, txn: str, payment: dict) -> Event:
        return self.ledger.append(txn, "rzp.payment.captured", "razorpay", _slim(payment))

    def record_refund(self, txn: str, refund: dict) -> Event:
        return self.ledger.append(txn, "rzp.refund.created", "razorpay", _slim(refund))

    def record_settlement_line(self, txn: str, line: dict) -> Event:
        return self.ledger.append(txn, "settlement.line", "bank", line)

    # ------------------------------------------------------------ explain (Stage 3 reads this)
    def explain(self, txn: str) -> list[dict]:
        """The full chain for one transaction, oldest first. Stage 3 renders this as evidence."""
        return [e.as_dict() for e in self.ledger.chain(txn)]


_KEEP = {
    "id", "entity", "amount", "amount_paid", "amount_due", "currency", "receipt", "status", "attempts",
    "notes", "created_at", "order_id", "method", "captured", "base_amount", "base_currency", "fee", "tax",
    "international", "payment_id", "speed_processed", "batch_id",
}


def _slim(entity: dict) -> dict:
    """Keep the fields the chain needs; never persist card data or contact details."""
    return {k: v for k, v in entity.items() if k in _KEEP}
