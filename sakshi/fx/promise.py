"""A three-date FX promise envelope for cross-border agentic commerce.

Razorpay settles an international receipt in INR at the rate on the payment
date, while an international dispute can debit the merchant at the rate on the
later dispute date.  Neither rate is an AI decision.  Atlas records the rate
shown in the buyer playback, checks the capture-day settlement against a
labelled reference, and prices the later dispute-date FX delta as a reserve.

This is an evidence and release primitive, not a foreign-exchange quote,
hedging product, regulatory calculation, or a statement of Razorpay's rate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


class FxPromiseError(ValueError):
    pass


def _rate(value: float | int | str, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise FxPromiseError(f"{field} must be numeric") from exc
    if result <= 0:
        raise FxPromiseError(f"{field} must be positive")
    return result


def _paise(amount_minor: int, minor_per_unit: int, rate: Decimal) -> int:
    """Convert a foreign amount to INR paise without binary floating-point drift."""
    return int((Decimal(amount_minor) * rate * Decimal(100) / Decimal(minor_per_unit)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    ))


def _bps(reference: Decimal, observed: Decimal) -> int:
    return int(((observed - reference) * Decimal(10_000) / reference).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _source_ref(value: str, field: str) -> str:
    """Keep an opaque source pointer, never a raw report/transcript in evidence."""
    result = " ".join(str(value or "").split())
    if not result or len(result) > 160:
        raise FxPromiseError(f"{field} must be a non-empty opaque source reference up to 160 characters")
    return result


@dataclass(frozen=True)
class FxPromiseEnvelope:
    """Buyer-visible currency playback plus payment/dispute-date risk budget."""

    buyer_currency: str
    foreign_amount_minor: int
    minor_per_unit: int
    displayed_rate: float
    reference_rate: float
    reference_provider: str
    reference_source_ref: str
    reference_date: str
    valid_through: str
    allowed_spread_bps: int = 150
    settlement_currency: str = "INR"

    def __post_init__(self) -> None:
        if len(self.buyer_currency) != 3 or len(self.settlement_currency) != 3:
            raise FxPromiseError("currencies must be ISO 4217-style three-letter codes")
        if self.buyer_currency.upper() == self.settlement_currency.upper():
            raise FxPromiseError("an FX promise needs different buyer and settlement currencies")
        if self.foreign_amount_minor <= 0 or self.minor_per_unit <= 0:
            raise FxPromiseError("foreign amount and minor-per-unit must be positive")
        if self.allowed_spread_bps < 0:
            raise FxPromiseError("allowed_spread_bps cannot be negative")
        _rate(self.displayed_rate, "displayed_rate")
        _rate(self.reference_rate, "reference_rate")
        _source_ref(self.reference_source_ref, "reference_source_ref")
        try:
            date.fromisoformat(self.reference_date)
            date.fromisoformat(self.valid_through)
        except ValueError as exc:
            raise FxPromiseError("reference_date and valid_through must use YYYY-MM-DD") from exc

    def as_dict(self) -> dict:
        return {
            "buyer_currency": self.buyer_currency.upper(),
            "foreign_amount_minor": self.foreign_amount_minor,
            "minor_per_unit": self.minor_per_unit,
            "displayed_rate": self.displayed_rate,
            "reference_rate": self.reference_rate,
            "reference_provider": self.reference_provider,
            "reference_source_ref": self.reference_source_ref,
            "reference_date": self.reference_date,
            "valid_through": self.valid_through,
            "allowed_spread_bps": self.allowed_spread_bps,
            "settlement_currency": self.settlement_currency.upper(),
        }

    def assess(self, *, payment_rate: float, payment_date: str, payment_source_ref: str,
               dispute_rate: Optional[float] = None, dispute_date: Optional[str] = None,
               dispute_source_ref: Optional[str] = None) -> "FxLifecycleAssessment":
        """Assess quote, capture and optional dispute-date exposure.

        ``payment_rate`` and ``dispute_rate`` are actual/observed rates supplied
        by the merchant's payment/recon and dispute systems.  Atlas never
        fabricates them or treats a reference rate as Razorpay's applied rate.
        """
        pay_rate = _rate(payment_rate, "payment_rate")
        payment_source = _source_ref(payment_source_ref, "payment_source_ref")
        display_rate = _rate(self.displayed_rate, "displayed_rate")
        reference_rate = _rate(self.reference_rate, "reference_rate")
        try:
            paid_on = date.fromisoformat(payment_date)
        except ValueError as exc:
            raise FxPromiseError("payment_date must use YYYY-MM-DD") from exc
        if dispute_date is not None:
            try:
                disputed_on = date.fromisoformat(dispute_date)
            except ValueError as exc:
                raise FxPromiseError("dispute_date must use YYYY-MM-DD") from exc
        else:
            disputed_on = None
        if (dispute_rate is None) != (dispute_date is None):
            raise FxPromiseError("dispute_rate and dispute_date must be supplied together")
        if dispute_rate is None and dispute_source_ref is not None:
            raise FxPromiseError("dispute_source_ref requires a dispute_rate")

        quote_spread_bps = _bps(reference_rate, display_rate)
        capture_spread_bps = _bps(reference_rate, pay_rate)
        quote_expired = paid_on > date.fromisoformat(self.valid_through)
        quote_status = "BLOCK" if quote_spread_bps > self.allowed_spread_bps else "ALLOW"
        capture_status = "FLAG" if abs(capture_spread_bps) > self.allowed_spread_bps else "PASS"
        displayed_value = _paise(self.foreign_amount_minor, self.minor_per_unit, display_rate)
        reference_value = _paise(self.foreign_amount_minor, self.minor_per_unit, reference_rate)
        payment_value = _paise(self.foreign_amount_minor, self.minor_per_unit, pay_rate)

        dispute_value = None
        dispute_delta = None
        if dispute_rate is not None:
            rate = _rate(dispute_rate, "dispute_rate")
            dispute_source = _source_ref(str(dispute_source_ref or ""), "dispute_source_ref")
            dispute_value = _paise(self.foreign_amount_minor, self.minor_per_unit, rate)
            dispute_delta = dispute_value - payment_value
        else:
            dispute_source = None

        return FxLifecycleAssessment(
            envelope=self,
            quote_status=quote_status,
            capture_status=capture_status,
            quote_expired=quote_expired,
            quote_spread_bps=quote_spread_bps,
            capture_spread_bps=capture_spread_bps,
            displayed_value_paise=displayed_value,
            reference_value_paise=reference_value,
            payment_value_paise=payment_value,
            dispute_value_paise=dispute_value,
            dispute_fx_delta_paise=dispute_delta,
            payment_date=payment_date,
            dispute_date=disputed_on.isoformat() if disputed_on else None,
            payment_source_ref=payment_source,
            dispute_source_ref=dispute_source,
        )


@dataclass(frozen=True)
class FxLifecycleAssessment:
    envelope: FxPromiseEnvelope
    quote_status: str
    capture_status: str
    quote_expired: bool
    quote_spread_bps: int
    capture_spread_bps: int
    displayed_value_paise: int
    reference_value_paise: int
    payment_value_paise: int
    dispute_value_paise: Optional[int]
    dispute_fx_delta_paise: Optional[int]
    payment_date: str
    dispute_date: Optional[str]
    payment_source_ref: str
    dispute_source_ref: Optional[str]

    @property
    def dispute_reserve_paise(self) -> Optional[int]:
        return max(self.dispute_fx_delta_paise or 0, 0) if self.dispute_value_paise is not None else None

    def as_dict(self) -> dict:
        return {
            "envelope": self.envelope.as_dict(),
            "quote_status": self.quote_status,
            "capture_status": self.capture_status,
            "quote_expired": self.quote_expired,
            "quote_spread_bps": self.quote_spread_bps,
            "capture_spread_bps": self.capture_spread_bps,
            "displayed_value_paise": self.displayed_value_paise,
            "reference_value_paise": self.reference_value_paise,
            "payment_value_paise": self.payment_value_paise,
            "dispute_value_paise": self.dispute_value_paise,
            "dispute_fx_delta_paise": self.dispute_fx_delta_paise,
            "dispute_reserve_paise": self.dispute_reserve_paise,
            "payment_date": self.payment_date,
            "dispute_date": self.dispute_date,
            "payment_source_ref": self.payment_source_ref,
            "dispute_source_ref": self.dispute_source_ref,
            "methodology": "Displayed/reference/payment/dispute rates are separate source-labelled facts; values are computed in integer INR paise.",
        }
