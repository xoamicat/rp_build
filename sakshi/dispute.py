"""Stage 3: the dispute agent.

When a customer disputes, the same facts the earlier stages wrote are read back in explain
mode: what was asked, what the gate said, what a human changed, what was charged, what
settled. From those the agent recommends one of

    CONTEST         the chain shows the customer authorised exactly this; deny with evidence
    REFUND          the chain shows the agent erred (paid a blocked cart, unapproved delegated order)
    PARTIAL_REFUND  an undisclosed charge sits on top of what was promised; return that part
    ESCALATE        the evidence Sakshi holds does not decide it (delivery, quality, unlinked order)

and prices the cost of refunding: the amount, the fee and GST Razorpay keeps, and on
international payments the gap between the rate on the payment day and the rate on the
dispute day (Razorpay deducts disputes at the dispute-day rate).

The evidence pack follows the order Razorpay's representment guide asks for: transaction
details, customer authorisation and interaction, order and pricing, verification, settlement,
policies, integrity. Everything in it comes from the ledger, so every line can be traced to a
hashed event.
"""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, TYPE_CHECKING

from .checkers.base import Status
from .fx.fbil import RateRef, confidence_for
from .ledger import Event, Ledger
from .models import MerchantConfig
from .settlements.fees import FeeSchedule, refund_fee_burn

if TYPE_CHECKING:
    from .evidence import EvidenceSigner

CLAIM_TYPES = ("not_authorized", "wrong_item", "amount_differs", "not_received", "other")


@dataclass
class DisputeClaim:
    type: str  # one of CLAIM_TYPES
    text: str = ""  # the customer's words
    opened_on: Optional[date] = None
    claimed_amount_paise: Optional[int] = None

    def __post_init__(self) -> None:
        if self.type not in CLAIM_TYPES:
            self.type = "other"
        if self.opened_on is None:
            self.opened_on = date.today()


@dataclass
class ChainView:
    """The transaction as the ledger tells it."""

    txn: str
    events: list[Event]
    intent: Optional[dict] = None
    carts: list[dict] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)  # {type, payload}
    gates: list[dict] = field(default_factory=list)
    overrides: list[dict] = field(default_factory=list)
    policy_corrections: list[dict] = field(default_factory=list)
    order: Optional[dict] = None
    order_verdicts: list[dict] = field(default_factory=list)
    payment: Optional[dict] = None
    refunds: list[dict] = field(default_factory=list)
    settlement: Optional[dict] = None
    reconcile: Optional[dict] = None
    offer_lock: Optional[dict] = None
    offer_drift_checks: list[dict] = field(default_factory=list)
    rzp_calls: int = 0

    @classmethod
    def load(cls, ledger: Ledger, txn: str) -> "ChainView":
        events = ledger.chain(txn)
        v = cls(txn=txn, events=events)
        for e in events:
            t, p = e.type, e.payload
            if t == "intent.captured":
                v.intent = p
            elif t == "cart.assembled":
                v.carts.append(p)
            elif t.startswith("check."):
                v.checks.append({"type": t, **p})
            elif t == "gate.verdict":
                v.gates.append(p)
            elif t == "human.override":
                v.overrides.append(p)
            elif t == "policy.correction":
                v.policy_corrections.append(p)
            elif t == "rzp.order.created":
                v.order = p
            elif t == "order.verdict":
                v.order_verdicts.append(p)
            elif t == "rzp.payment.captured":
                v.payment = p
            elif t == "rzp.refund.created":
                v.refunds.append(p)
            elif t == "settlement.line":
                v.settlement = p
            elif t == "reconcile.verdict":
                v.reconcile = p
            elif t == "offer.locked":
                v.offer_lock = p
            elif t == "offer.drift.checked":
                v.offer_drift_checks.append(p)
            elif t.startswith("rzp.request"):
                v.rzp_calls += 1
        return v

    # --------------------------------------------------------------- helpers
    @property
    def final_cart(self) -> Optional[dict]:
        return self.carts[-1] if self.carts else None

    @property
    def final_gate(self) -> Optional[dict]:
        return self.gates[-1] if self.gates else None

    def last_check(self, name: str) -> Optional[dict]:
        hits = [c for c in self.checks if c["type"] == f"check.{name}"]
        return hits[-1] if hits else None

    @property
    def hash_rides_with_money(self) -> Optional[bool]:
        """Does the intent hash in the order notes match the intent the ledger recorded?"""
        if not self.intent or not self.order:
            return None
        notes = self.order.get("notes") or {}
        return notes.get("sakshi_intent") == self.intent.get("intent_hash")

    @property
    def paid(self) -> bool:
        return self.payment is not None

    @property
    def corrections(self) -> list[dict]:
        return self.overrides + self.policy_corrections

    @property
    def latest_offer_drift(self) -> Optional[dict]:
        return self.offer_drift_checks[-1] if self.offer_drift_checks else None


@dataclass
class DisputeResult:
    txn: str
    claim: DisputeClaim
    recommendation: str  # CONTEST | REFUND | PARTIAL_REFUND | ESCALATE
    refund_amount_paise: int
    confidence: float
    reasons: list[str]
    cost_of_refund: dict  # amount, fee_burn, fx_delta, total
    evidence_pack: list[dict]
    customer_explanation: str
    requires_human: bool
    event: Optional[Event] = None

    def as_dict(self) -> dict:
        return {
            "txn": self.txn, "claim": self.claim.__dict__ | {"opened_on": self.claim.opened_on.isoformat()},
            "recommendation": self.recommendation, "refund_amount_paise": self.refund_amount_paise,
            "confidence": self.confidence, "reasons": self.reasons, "cost_of_refund": self.cost_of_refund,
            "evidence_pack": self.evidence_pack, "customer_explanation": self.customer_explanation,
            "requires_human": self.requires_human,
        }


def _rs(paise: Optional[int]) -> str:
    return "n/a" if paise is None else f"₹{paise / 100:,.2f}"


def _ts(unix: Optional[float]) -> str:
    if not unix:
        return "n/a"
    return datetime.fromtimestamp(float(unix)).strftime("%Y-%m-%d %H:%M")


@dataclass
class DisputeAgent:
    ledger: Ledger
    merchant: MerchantConfig
    fees: FeeSchedule = field(default_factory=FeeSchedule)
    min_confidence_for_auto: float = 0.75
    signer: Optional["EvidenceSigner"] = None

    # ------------------------------------------------------------- entry point
    def decide(self, txn: str, claim: DisputeClaim, fx_now: Optional[RateRef] = None,
               record: bool = True) -> DisputeResult:
        chain = ChainView.load(self.ledger, txn)
        if record:
            self.ledger.append(txn, "dispute.opened", "customer",
                               {"type": claim.type,
                                "claim_hash": hashlib.sha256(claim.text.encode("utf-8")).hexdigest(),
                                "claimed_amount_paise": claim.claimed_amount_paise,
                                "opened_on": claim.opened_on.isoformat()})
        rec, amount, conf, reasons = self._rule(chain, claim)
        cost = self._cost_of_refund(chain, amount, claim, fx_now)
        if chain.paid:
            paid = int(chain.payment.get("base_amount", chain.payment.get("amount", 0)))
            if amount < paid:
                cost["if_full_refund"] = self._cost_of_refund(chain, paid, claim, fx_now)
        pack = self.evidence_pack(chain, claim, cost)
        explanation = self.explain(chain, claim, rec, amount, cost)
        requires_human = (conf < self.min_confidence_for_auto or amount > self.merchant.hitl_threshold_paise
                          or rec == "ESCALATE")
        ev = None
        if record:
            ev = self.ledger.append(txn, "dispute.verdict", "sakshi", {
                "recommendation": rec, "refund_amount_paise": amount, "confidence": conf,
                "reasons": reasons, "cost_of_refund": cost, "requires_human": requires_human,
            })
        return DisputeResult(txn, claim, rec, amount, conf, reasons, cost, pack, explanation, requires_human, ev)

    # --------------------------------------------------------------- the rule
    def _rule(self, c: ChainView, claim: DisputeClaim) -> tuple[str, int, float, list[str]]:
        reasons: list[str] = []
        if not c.paid:
            return "ESCALATE", 0, 0.5, ["no payment recorded for this transaction"]
        paid_amount = int(c.payment.get("base_amount", c.payment.get("amount", 0)))
        gate = (c.final_gate or {}).get("status")
        intent = c.intent
        hash_ok = c.hash_rides_with_money
        approved = any(o.get("decision") in ("approved", "corrected") for o in c.overrides)

        if self.merchant.extra.get("require_signed_evidence") and not self.signed_evidence_valid(c.txn):
            return "ESCALATE", 0, 0.4, ["merchant policy requires a valid signed evidence seal for an automated dispute decision"]

        drift = c.latest_offer_drift
        if drift and drift.get("status") in ("RECONFIRM", "ESCALATE") and claim.type in ("wrong_item", "amount_differs"):
            return "ESCALATE", 0, 0.55, [
                "a material Offer Lock drift check occurred after buyer consent",
                "do not rely on the original approval to contest this claim; obtain the later buyer confirmation or review it manually",
            ]

        if intent is None:
            return "ESCALATE", 0, 0.4, ["order was not created through the gate: no intent record to compare against"]
        if hash_ok is False:
            reasons.append("intent hash on the order does not match the ledger: treat with care")

        if claim.type == "not_authorized":
            if not intent.get("human_present") and gate in ("ASK_HUMAN", "BLOCK") and not approved:
                return "REFUND", paid_amount, 0.9, reasons + [
                    "delegated order was held or blocked by the gate and paid without a human approval on record"]
            if intent.get("human_present"):
                return "CONTEST", 0, 0.9 if hash_ok else 0.75, reasons + [
                    f"customer was present and asked for: {intent.get('playback')}",
                    "intent hash travelled on the order notes" if hash_ok else "order notes lack the intent hash"]
            if intent.get("mandate_ref"):
                return "CONTEST", 0, 0.8 if hash_ok else 0.65, reasons + [
                    f"delegated purchase under mandate {intent.get('mandate_ref')}; intent recorded: {intent.get('playback')}"]
            return "ESCALATE", 0, 0.5, reasons + ["no human presence and no mandate reference on record"]

        if claim.type == "wrong_item":
            qs = c.last_check("quantity_sku")
            cart_matched = gate in ("PASS", "FLAG") and (qs is None or qs.get("status") == "PASS" or _overridden(c, "quantity_sku"))
            if cart_matched:
                return "CONTEST", 0, 0.85 if hash_ok else 0.7, reasons + [
                    f"cart matched the stated intent ({intent.get('playback')}) before payment",
                    "gate verdict: " + str(gate)] + ([f"corrected before payment: {o.get('note')}" for o in c.corrections])
            if gate == "BLOCK":
                return "REFUND", paid_amount, 0.9, reasons + [
                    "the gate blocked this cart and it was paid anyway: agent error",
                    *[r for r in (c.final_gate or {}).get("reasons", [])]]
            return "ESCALATE", 0, 0.55, reasons + ["cart verdict inconclusive"]

        if claim.type == "amount_differs":
            po = c.last_check("promise_order")
            diff = int((po or {}).get("evidence", {}).get("diff_paise", 0)) if po else 0
            if diff > 0:
                return "PARTIAL_REFUND", diff, 0.9, reasons + [
                    f"order carried {_rs(diff)} above the total the agent stated: undisclosed charge"]
            if po is not None:
                return "CONTEST", 0, 0.85, reasons + [
                    f"charged exactly the stated total ({_rs((po.get('evidence') or {}).get('promised_paise'))})"]
            return "ESCALATE", 0, 0.5, reasons + ["no record of what total was stated"]

        if claim.type == "not_received":
            return "ESCALATE", 0, 0.5, reasons + ["delivery evidence is outside Sakshi's chain; attach logistics proof"]
        return "ESCALATE", 0, 0.5, reasons + ["claim type not decidable from the chain"]

    # ------------------------------------------------------------ cost lines
    def _cost_of_refund(self, c: ChainView, amount: int, claim: DisputeClaim, fx_now: Optional[RateRef]) -> dict:
        cost = {"refund_amount_paise": amount, "fee_burn_paise": 0, "fx_delta_paise": 0, "total_paise": amount,
                "notes": []}
        if not c.paid or amount <= 0:
            return cost
        burn = refund_fee_burn(c.payment, amount, self.fees)
        cost["fee_burn_paise"] = burn["burn_paise"]
        cost["notes"].append(f"fee and GST not returned on refund: {_rs(burn['burn_paise'])}")
        if c.payment.get("currency", "INR") != "INR" and "base_amount" in c.payment:
            applied = c.payment["base_amount"] / c.payment["amount"]
            if fx_now is not None:
                foreign_units = amount / applied
                delta = int(round((fx_now.rate - applied) * foreign_units))
                cost["fx_delta_paise"] = max(delta, 0)
                cost["notes"].append(
                    f"dispute-day rate {fx_now.rate} ({fx_now.provider}, {fx_now.published}) vs applied {applied:.4f}: "
                    f"{'+' if delta >= 0 else ''}{_rs(delta)}" + (f", reference {fx_now.stale_days} day(s) stale" if fx_now.stale_days else ""))
                cost["fx_confidence"] = confidence_for(fx_now)
            else:
                cost["notes"].append("international payment: dispute-day FX rate not supplied, exposure not priced")
        cost["total_paise"] = amount + cost["fee_burn_paise"] + cost["fx_delta_paise"]
        return cost

    # ---------------------------------------------------------- evidence pack
    def evidence_pack(self, c: ChainView, claim: DisputeClaim, cost: dict) -> list[dict]:
        ok, bad = self.ledger.verify()
        seal_present = any(event.type == "evidence.sealed" for event in c.events)
        pay, order, intent = c.payment or {}, c.order or {}, c.intent or {}
        cart = c.final_cart or {}
        return [
            {"section": "1. Transaction details", "items": {
                "order_id": order.get("id"), "payment_id": pay.get("id"), "amount": _rs(pay.get("base_amount", pay.get("amount"))),
                "currency": pay.get("currency"), "method": pay.get("method"), "paid_at": _ts(pay.get("created_at")),
                "dispute_type": claim.type, "dispute_opened": claim.opened_on.isoformat()}},
            {"section": "2. Customer authorisation", "items": {
                "playback": intent.get("playback"), "intent_hash": intent.get("intent_hash"),
                "channel": intent.get("channel"), "language": intent.get("lang"),
                "human_present": intent.get("human_present"), "mandate_ref": intent.get("mandate_ref"),
                "cap": _rs(intent.get("cap_paise")), "captured_at": _ts(intent.get("created_at")),
                "hash_on_order_notes": c.hash_rides_with_money}},
            {"section": "3. Customer interaction", "items": {
                "note": "conversation transcript held by the merchant; ledger stores playback and hashes only",
                "utterance_hash": intent.get("utterance_hash")}},
            {"section": "4. Order and pricing", "items": {
                "lines": [f"{l['qty']} x {l['name']} @ {_rs(l['unit_paise'])} ({l.get('source')})" for l in cart.get("lines", [])],
                "discount": _rs(cart.get("discount_paise")), "quoted_total": _rs(cart.get("quoted_total_paise")),
                "order_amount": _rs(order.get("amount"))}},
            {"section": "5. Verification before payment", "items": {
                "gate": (c.final_gate or {}).get("status"), "gate_reasons": (c.final_gate or {}).get("reasons"),
                "order_check": (c.order_verdicts[-1].get("status") if c.order_verdicts else None),
                "human_overrides": [f"{o.get('who')}: {o.get('decision')} ({o.get('note')})" for o in c.overrides],
                "policy_corrections": [f"{o.get('decision')} ({o.get('note')})" for o in c.policy_corrections]}},
            {"section": "6. Settlement", "items": {
                "settlement_id": (c.settlement or {}).get("settlement_id"), "settled": _rs((c.settlement or {}).get("amount")),
                "fee": _rs((c.settlement or {}).get("fee")), "tax": _rs((c.settlement or {}).get("tax")),
                "reconcile": (c.reconcile or {}).get("status"), "reconcile_reasons": (c.reconcile or {}).get("reasons")}},
            {"section": "7. Policies", "items": {
                "refund_policy": self.merchant.extra.get("refund_policy", "not on file"),
                "delivery_policy": self.merchant.extra.get("delivery_policy", "not on file")}},
            {"section": "8. Cost of refunding", "items": cost},
            {"section": "9. Integrity", "items": {
                "ledger_verified": ok, "first_bad_event": bad, "events": len(c.events),
                "signed_chain_seal_present": seal_present,
                "signed_chain_seal_verified": self.signed_evidence_valid(c.txn) if seal_present else False,
                "lock_id": (c.offer_lock or {}).get("lock_id"),
                "terms_hash": (c.offer_lock or {}).get("terms_hash"),
                "catalog_version": (c.offer_lock or {}).get("catalog_version"),
                "latest_drift_status": (c.latest_offer_drift or {}).get("status"),
                "latest_deltas": (c.latest_offer_drift or {}).get("deltas", []),
                "first_hash": c.events[0].hash if c.events else None, "last_hash": c.events[-1].hash if c.events else None,
            }},
        ]

    def signed_evidence_valid(self, txn: str) -> bool:
        return bool(self.signer and self.signer.verify_latest_seal(
            self.ledger, txn, self.signer.public_key_b64
        ))

    # ------------------------------------------------------------ explanation
    def explain(self, c: ChainView, claim: DisputeClaim, rec: str, amount: int, cost: dict) -> str:
        intent, cart, pay = c.intent or {}, c.final_cart or {}, c.payment or {}
        lines_txt = ", ".join(f"{l['qty']} x {l['name']}" for l in cart.get("lines", [])) or "nothing"
        when = _ts(intent.get("created_at"))
        if pay.get("currency", "INR") != "INR" and pay.get("amount") is not None:
            paid = f"{pay['currency']} {pay['amount'] / 100:.2f}"
        else:
            paid = _rs(pay.get("base_amount", pay.get("amount")))
        gate = (c.final_gate or {}).get("status")
        parts = [f"On {when} you asked for: {intent.get('playback') or 'an order'}.",
                 f"The assistant prepared {lines_txt}."]
        if c.corrections:
            parts.append("Before payment the order was corrected: " + "; ".join(o.get("note", "") for o in c.corrections) + ".")
        elif gate == "BLOCK":
            parts.append("Our check flagged this order before payment, but it was paid anyway.")
        parts.append(f"You were charged {paid} via {pay.get('method', 'your payment method')}.")
        if rec == "CONTEST":
            parts.append("The record shows this matches what you asked for, so we are not able to refund it, "
                         "but we have attached the full record so you can see each step.")
        elif rec == "REFUND":
            parts.append(f"This was our assistant's mistake. We are refunding {_rs(amount)}.")
        elif rec == "PARTIAL_REFUND":
            parts.append(f"A charge of {_rs(amount)} was added that the assistant did not tell you about. We are refunding that part.")
        else:
            parts.append("We need one more piece of information before we can decide, and a person will review this.")
        return " ".join(parts)


def _overridden(c: ChainView, checker: str) -> bool:
    for ch in c.checks:
        if checker in (ch.get("overrides") or []) and ch.get("status") == "PASS":
            return True
    return False


def to_json(result: DisputeResult) -> str:
    return json.dumps(result.as_dict(), ensure_ascii=False, indent=2, default=str)
