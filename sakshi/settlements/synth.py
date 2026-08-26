"""Schema-faithful synthetic settlements.

Razorpay test mode never settles, so Stage 2 is developed against synthetic
settlement lines that use the exact field set of the Settlement Recon API
(``GET /v1/settlements/recon/combined``). Code written against these lines
runs unchanged on a real recon export.

The important property: ``notes`` and ``order_id`` are carried on every line,
which is how the Intent Receipt reaches the settlement and lets Stage 2 join a
settled rupee amount back to what the customer asked for.
"""
from __future__ import annotations

import random
import string
import time
from typing import Iterable, Optional

from .fees import FeeSchedule

# Field order and names as returned by the Settlement Recon API sample.
RECON_FIELDS = [
    "entity_id", "type", "debit", "credit", "amount", "currency", "fee", "tax", "on_hold", "settled",
    "created_at", "settled_at", "settlement_id", "posted_at", "credit_type", "description", "notes",
    "payment_id", "settlement_utr", "order_id", "order_receipt", "method", "card_network", "card_issuer",
    "card_type", "dispute_id",
]


def _utr() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=16))


def _settlement_id() -> str:
    return "setl_stub" + "".join(random.choices(string.ascii_letters + string.digits, k=10))


def _line(**kwargs) -> dict:
    line = {k: None for k in RECON_FIELDS}
    line.update(kwargs)
    return line


def settlement_lines(payments: Iterable[dict], refunds: Iterable[dict] = (), fees: Optional[FeeSchedule] = None,
                     settled_at: Optional[int] = None, settlement_id: Optional[str] = None,
                     utr: Optional[str] = None, orders: Optional[dict] = None) -> list[dict]:
    """Build recon lines for captured payments and processed refunds.

    ``amount`` on a settled payment is the INR amount that actually settles: ``base_amount``
    for international payments, ``amount`` for domestic ones. The original currency is kept
    in ``description`` so nothing is lost. Verify against a real recon export once you have
    live data; the sample in Razorpay's docs shows the original currency on the line.
    """
    fees = fees or FeeSchedule()
    settled_at = settled_at or int(time.time())
    settlement_id = settlement_id or _settlement_id()
    utr = utr or _utr()
    orders = orders or {}
    lines: list[dict] = []

    for p in payments:
        settled_amount = int(p.get("base_amount", p["amount"]))
        method = p.get("method", "card")
        intl = bool(p.get("international"))
        fee, tax = fees.fee_tax(settled_amount, method, intl)
        order = orders.get(p.get("order_id"), {})
        description = None
        if p.get("currency") != "INR":
            description = f"intl {p['currency']} {p['amount']} @ {p.get('applied_rate', 'bank rate')}"
        lines.append(_line(
            entity_id=p["id"], type="payment", debit=0, credit=settled_amount - fee - tax,
            amount=settled_amount, currency="INR", fee=fee, tax=tax, on_hold=False, settled=True,
            created_at=p.get("created_at"), settled_at=settled_at, settlement_id=settlement_id,
            credit_type="default", description=description, notes=dict(p.get("notes", {})),
            payment_id=None, settlement_utr=utr, order_id=p.get("order_id"),
            order_receipt=order.get("receipt"), method=method,
            card_network=p.get("card_network"), card_issuer=None if intl else p.get("card_issuer"),
            card_type=p.get("card_type"), dispute_id=p.get("dispute_id"),
        ))

    for r in refunds:
        lines.append(_line(
            entity_id=r["id"], type="refund", debit=int(r["amount"]), credit=0, amount=int(r["amount"]),
            currency="INR", fee=0, tax=0, on_hold=False, settled=True, created_at=r.get("created_at"),
            settled_at=settled_at, settlement_id=settlement_id, credit_type="default",
            description=None, notes=dict(r.get("notes", {})), payment_id=r.get("payment_id"),
            settlement_utr=utr, order_id=r.get("order_id"), order_receipt=None, method=r.get("method"),
        ))
    return lines


def join_settlement_to_intent(lines: Iterable[dict]) -> dict[str, list[dict]]:
    """Group recon lines by the Sakshi transaction carried in notes. Lines without the
    receipt land under ``unlinked``: those are the orders that were created outside the gate."""
    groups: dict[str, list[dict]] = {}
    for line in lines:
        notes = line.get("notes") or {}
        txn = notes.get("sakshi_txn") if isinstance(notes, dict) else None
        groups.setdefault(txn or "unlinked", []).append(line)
    return groups
