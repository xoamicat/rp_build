"""Razorpay access with two backends.

StubGateway  : in-memory, Razorpay-shaped entities, no network. Tests and the demo use it.
LiveGateway  : the official ``razorpay`` SDK against test mode, when keys are in the env.

Both write the Intent Receipt into ``notes`` on order creation.
"""
from __future__ import annotations

import random
import string
import time
from typing import Optional

from .config import Settings
from .intent import validate_notes

_ALPHABET = string.ascii_letters + string.digits


def _rid(prefix: str) -> str:
    return prefix + "".join(random.choices(_ALPHABET, k=14))


def _now() -> int:
    return int(time.time())


class StubGateway:
    """Mimics the shape of Razorpay Orders / Payments / Refunds entities closely enough
    for the ledger, the settlement synthesiser and the tests."""

    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}
        self.payments: dict[str, dict] = {}
        self.refunds: dict[str, dict] = {}

    # ---------------------------------------------------------------- orders
    def create_order(self, amount: int, currency: str = "INR", receipt: Optional[str] = None,
                     notes: Optional[dict] = None) -> dict:
        notes = notes or {}
        validate_notes(notes)
        if amount < 100:
            raise ValueError("Razorpay minimum order amount is 100 subunits")
        order = {
            "id": _rid("order_stub"),
            "entity": "order",
            "amount": int(amount),
            "amount_paid": 0,
            "amount_due": int(amount),
            "currency": currency,
            "receipt": receipt,
            "offer_id": None,
            "status": "created",
            "attempts": 0,
            "notes": dict(notes),
            "created_at": _now(),
        }
        self.orders[order["id"]] = order
        return order

    def fetch_order(self, order_id: str) -> dict:
        return self.orders[order_id]

    def update_order_notes(self, order_id: str, notes: dict) -> dict:
        validate_notes(notes)
        self.orders[order_id]["notes"] = dict(notes)
        return self.orders[order_id]

    # -------------------------------------------------------------- payments
    def simulate_capture(self, order_id: str, method: str = "upi", rate: Optional[float] = None,
                         card_network: Optional[str] = None, international: bool = False) -> dict:
        """Pretend the customer paid. For non-INR orders pass ``rate`` (INR per unit of the
        foreign currency) and ``base_amount`` is derived the way Razorpay does: converted at
        the processing bank's rate on the payment date."""
        order = self.orders[order_id]
        payment = {
            "id": _rid("pay_stub"),
            "entity": "payment",
            "amount": order["amount"],
            "currency": order["currency"],
            "status": "captured",
            "order_id": order_id,
            "method": method,
            "captured": True,
            "international": international or order["currency"] != "INR",
            "notes": dict(order["notes"]),
            "created_at": _now(),
        }
        if card_network:
            payment["card_network"] = card_network
        if order["currency"] != "INR":
            if rate is None:
                raise ValueError("rate (INR per foreign unit) required for non-INR capture")
            payment["base_amount"] = int(round(order["amount"] * rate))
            payment["base_currency"] = "INR"
            payment["applied_rate"] = rate  # stub-only field; live payments expose base_amount/amount
        order["status"] = "paid"
        order["amount_paid"] = order["amount"]
        order["amount_due"] = 0
        order["attempts"] += 1
        self.payments[payment["id"]] = payment
        return payment

    def fetch_payment(self, payment_id: str) -> dict:
        return self.payments[payment_id]

    # --------------------------------------------------------------- refunds
    def create_refund(self, payment_id: str, amount: Optional[int] = None, notes: Optional[dict] = None) -> dict:
        payment = self.payments[payment_id]
        amt = payment["amount"] if amount is None else int(amount)
        refund = {
            "id": _rid("rfnd_stub"),
            "entity": "refund",
            "amount": amt,
            "currency": payment["currency"],
            "payment_id": payment_id,
            "notes": dict(notes or payment.get("notes", {})),
            "status": "processed",
            "speed_processed": "normal",
            "created_at": _now(),
        }
        self.refunds[refund["id"]] = refund
        return refund


class LiveGateway:
    """Thin wrapper over the official SDK. Only constructed when keys exist."""

    def __init__(self, settings: Settings):
        try:
            import razorpay  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pip install razorpay to use LiveGateway") from exc
        self.client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))

    def create_order(self, amount: int, currency: str = "INR", receipt: Optional[str] = None,
                     notes: Optional[dict] = None) -> dict:
        notes = notes or {}
        validate_notes(notes)
        data = {"amount": int(amount), "currency": currency, "notes": notes}
        if receipt:
            data["receipt"] = receipt
        return self.client.order.create(data=data)

    def fetch_order(self, order_id: str) -> dict:
        return self.client.order.fetch(order_id)

    def update_order_notes(self, order_id: str, notes: dict) -> dict:
        validate_notes(notes)
        return self.client.order.edit(order_id, {"notes": notes})

    def fetch_payment(self, payment_id: str) -> dict:
        return self.client.payment.fetch(payment_id)

    def create_refund(self, payment_id: str, amount: Optional[int] = None, notes: Optional[dict] = None) -> dict:
        data: dict = {}
        if amount is not None:
            data["amount"] = int(amount)
        if notes:
            validate_notes(notes)
            data["notes"] = notes
        return self.client.payment.refund(payment_id, data)


def gateway_from_env(settings: Optional[Settings] = None):
    settings = settings or Settings.from_env()
    return LiveGateway(settings) if settings.has_razorpay_keys else StubGateway()
