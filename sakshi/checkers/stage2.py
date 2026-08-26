"""Stage 2 checkers (after payment) plus the Stage 1 FX quote checker.

Stage 2 verdicts are FLAG or PASS: the money has moved, so the job is to find and price
variance, not to stop anything. The one exception is PromiseOrderChecker, which the engine
also runs before payment (``prepayment=True``) where a drift between what the agent said and
what it is about to charge can still be blocked.

All four are arithmetic. Their inputs come from the ledger (what was promised), Razorpay
entities (order, payment, refund) and settlement recon lines. FX references come from
``sakshi.fx`` and carry their own staleness, which lowers the checker's confidence.
"""
from __future__ import annotations

from typing import Optional

from ..fx.fbil import RateRef, confidence_for
from ..settlements.fees import FeeSchedule, refund_fee_burn
from .base import CheckContext, Status, Verdict


def _spread_bps(reference: float, applied: float) -> int:
    """Positive when the merchant received fewer rupees per unit than the reference."""
    return int(round((reference - applied) / reference * 10_000))


# ------------------------------------------------------------------ stage 1
class FxQuoteChecker:
    """The agent quoted a foreign customer a rate (or a converted price). Compare to FBIL."""

    name = "fx_quote"
    stage = 1

    def check(self, ctx: CheckContext) -> Verdict:
        cart = ctx.cart
        ref: Optional[RateRef] = ctx.extras.get("fx")
        if cart is None or getattr(cart, "quoted_rate", None) is None:
            return Verdict(self.name, self.stage, Status.SKIP, "no FX quote to check")
        if ref is None:
            return Verdict(self.name, self.stage, Status.FLAG, "FX quote made but no reference rate available",
                           confidence=0.0, evidence={"quoted_rate": cart.quoted_rate})
        quoted = float(cart.quoted_rate)
        markup_bps = int(round((quoted - ref.rate) / ref.rate * 10_000))
        band = ctx.merchant.fx_band_bps
        # foreign amount in the foreign currency's subunits; rupee impact of the mis-quote
        foreign_units = cart.gross_paise  # for non-INR carts, unit_paise holds foreign subunits
        impact = int(round(abs(quoted - ref.rate) * foreign_units))
        evidence = {"quoted_rate": quoted, "reference": ref.as_dict(), "markup_bps": markup_bps, "band_bps": band}
        conf = confidence_for(ref)
        if markup_bps > band:
            return Verdict(self.name, self.stage, Status.BLOCK,
                           f"quoted rate {quoted} is {markup_bps / 100:.2f}% over {ref.provider} {ref.rate} (band {band / 100:.2f}%): drip-pricing risk",
                           impact_paise=impact, confidence=conf, evidence=evidence, basis="fx_quote")
        if markup_bps < -band:
            return Verdict(self.name, self.stage, Status.FLAG,
                           f"quoted rate {quoted} is {-markup_bps / 100:.2f}% under {ref.provider} {ref.rate}: merchant absorbs the gap",
                           impact_paise=impact, confidence=conf, evidence=evidence, basis="fx_quote")
        return Verdict(self.name, self.stage, Status.PASS, f"quote within {band / 100:.2f}% of {ref.provider} reference",
                       confidence=conf, evidence=evidence)


# ------------------------------------------------------------------ stage 2
class PromiseOrderChecker:
    """What the agent said the total was, versus the amount on the Razorpay order."""

    name = "promise_order"
    stage = 2

    def check(self, ctx: CheckContext) -> Verdict:
        if ctx.cart is None or ctx.order is None or ctx.cart.quoted_total_paise is None:
            return Verdict(self.name, self.stage, Status.SKIP, "no quoted total or no order")
        promised, charged = int(ctx.cart.quoted_total_paise), int(ctx.order.get("amount", 0))
        diff = charged - promised
        evidence = {"promised_paise": promised, "order_paise": charged, "diff_paise": diff}
        if diff == 0:
            return Verdict(self.name, self.stage, Status.PASS, "order amount matches what the agent promised", evidence=evidence)
        prepay = bool(ctx.extras.get("prepayment"))
        if diff > 0:
            reason = f"order is {diff} above the promised total: undisclosed charge (drip pricing) and dispute risk"
            status = Status.BLOCK if prepay else Status.FLAG
        else:
            reason = f"order is {-diff} below the promised total: merchant undercharged"
            status = Status.FLAG
        return Verdict(self.name, self.stage, status, reason, impact_paise=abs(diff), evidence=evidence, basis="promise_order")


class SettlementFeeChecker:
    """Settlement line versus payment: settled amount, fee and tax against the merchant's schedule."""

    name = "settlement_fee"
    stage = 2

    def check(self, ctx: CheckContext) -> Verdict:
        line, payment = ctx.settlement, ctx.payment
        if line is None or payment is None:
            return Verdict(self.name, self.stage, Status.SKIP, "no settlement line or payment")
        fees: FeeSchedule = ctx.extras.get("fees") or FeeSchedule()
        settled_amount = int(payment.get("base_amount", payment["amount"]))
        exp_fee, exp_tax = fees.fee_tax(settled_amount, payment.get("method", "card"), bool(payment.get("international")))
        problems, impact = [], 0
        if int(line.get("amount", 0)) != settled_amount:
            d = settled_amount - int(line.get("amount", 0))
            problems.append(f"settled amount {line.get('amount')} differs from payment {settled_amount}")
            impact += abs(d)
        if int(line.get("fee", 0)) != exp_fee or int(line.get("tax", 0)) != exp_tax:
            excess = (int(line.get("fee", 0)) + int(line.get("tax", 0))) - (exp_fee + exp_tax)
            problems.append(f"fee+tax {line.get('fee')}+{line.get('tax')} vs schedule {exp_fee}+{exp_tax} ({'+' if excess >= 0 else ''}{excess})")
            impact += max(excess, 0)
        expected_credit = int(line.get("amount", 0)) - int(line.get("fee", 0)) - int(line.get("tax", 0))
        if int(line.get("credit", 0)) != expected_credit:
            problems.append(f"credit {line.get('credit')} is not amount-fee-tax ({expected_credit})")
            impact += abs(expected_credit - int(line.get("credit", 0)))
        evidence = {"settlement_id": line.get("settlement_id"), "expected_fee": exp_fee, "expected_tax": exp_tax}
        if not problems:
            return Verdict(self.name, self.stage, Status.PASS, "settlement matches payment and fee schedule", evidence=evidence)
        return Verdict(self.name, self.stage, Status.FLAG, "; ".join(problems), impact_paise=impact,
                       evidence=dict(evidence, problems=problems), basis="settlement")


class FxRateChecker:
    """Applied conversion rate on an international payment versus the FBIL reference for that day."""

    name = "fx_rate"
    stage = 2

    def check(self, ctx: CheckContext) -> Verdict:
        payment = ctx.payment
        if payment is None or payment.get("currency", "INR") == "INR" or "base_amount" not in payment:
            return Verdict(self.name, self.stage, Status.SKIP, "domestic payment or no base_amount")
        ref: Optional[RateRef] = ctx.extras.get("fx")
        if ref is None:
            return Verdict(self.name, self.stage, Status.FLAG, "international payment but no reference rate available",
                           confidence=0.0)
        applied = payment["base_amount"] / payment["amount"]
        spread = _spread_bps(ref.rate, applied)
        band = ctx.merchant.fx_band_bps
        impact = max(int(round(ref.rate * payment["amount"])) - int(payment["base_amount"]), 0)
        conf = confidence_for(ref)
        evidence = {"applied_rate": round(applied, 4), "reference": ref.as_dict(), "spread_bps": spread, "band_bps": band}
        if spread > band:
            return Verdict(self.name, self.stage, Status.FLAG,
                           f"applied {applied:.4f} is {spread / 100:.2f}% under {ref.provider} {ref.rate} (band {band / 100:.2f}%)"
                           + (f"; reference is {ref.stale_days} day(s) stale" if ref.stale_days else ""),
                           impact_paise=impact, confidence=conf, evidence=evidence, basis="fx_rate")
        return Verdict(self.name, self.stage, Status.PASS,
                       f"applied rate within {band / 100:.2f}% of {ref.provider} reference"
                       + (f" ({ref.stale_days} day(s) stale)" if ref.stale_days else ""),
                       confidence=conf, evidence=evidence)


class RefundBurnChecker:
    """Fees and GST on a refunded payment are not returned. Price the burn."""

    name = "refund_burn"
    stage = 2

    def check(self, ctx: CheckContext) -> Verdict:
        payment = ctx.payment
        refunds = ctx.extras.get("refunds") or []
        if payment is None or not refunds:
            return Verdict(self.name, self.stage, Status.SKIP, "no refunds")
        fees: FeeSchedule = ctx.extras.get("fees") or FeeSchedule()
        total_burn, detail = 0, []
        for r in refunds:
            burn = refund_fee_burn(payment, int(r["amount"]), fees)
            total_burn += burn["burn_paise"]
            detail.append({"refund_id": r.get("id"), **burn})
        return Verdict(self.name, self.stage, Status.FLAG,
                       f"{len(refunds)} refund(s): {total_burn} paise of fee and GST not returned",
                       impact_paise=total_burn, evidence={"refunds": detail}, basis="refund_burn")


def default_stage2() -> list:
    return [PromiseOrderChecker(), SettlementFeeChecker(), FxRateChecker(), RefundBurnChecker()]
