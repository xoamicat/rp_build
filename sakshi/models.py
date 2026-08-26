"""Shared data models. Money is always integer subunits (paise, cents)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CartLine:
    name: str
    qty: int
    unit_paise: int
    sku: Optional[str] = None
    source: str = "catalog"  # catalog | agent | upsell | substitution

    @property
    def total_paise(self) -> int:
        return self.qty * self.unit_paise

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "qty": self.qty,
            "unit_paise": self.unit_paise,
            "sku": self.sku,
            "source": self.source,
            "total_paise": self.total_paise,
        }


@dataclass
class Cart:
    lines: list[CartLine]
    currency: str = "INR"
    discount_paise: int = 0
    quoted_total_paise: Optional[int] = None  # what the agent SAID the total was, if it said one
    quoted_rate: Optional[float] = None  # INR per foreign unit the agent quoted, if it quoted one

    @property
    def gross_paise(self) -> int:
        return sum(line.total_paise for line in self.lines)

    @property
    def total_paise(self) -> int:
        return max(self.gross_paise - self.discount_paise, 0)

    def as_dict(self) -> dict:
        return {
            "lines": [line.as_dict() for line in self.lines],
            "currency": self.currency,
            "discount_paise": self.discount_paise,
            "gross_paise": self.gross_paise,
            "total_paise": self.total_paise,
            "quoted_total_paise": self.quoted_total_paise,
            "quoted_rate": self.quoted_rate,
        }


@dataclass
class MerchantConfig:
    """Merchant-set guardrails. These mirror what Razorpay's Agent Studio principles say
    the merchant, not the agent, decides: discount ceilings, approval thresholds, offers."""

    merchant_id: str = "merchant_demo"
    name: str = "Demo Pizza Co"
    currency: str = "INR"
    max_discount_bps: int = 1000  # 10 percent ceiling on any discount an agent may apply
    hitl_threshold_paise: int = 200_000  # above this, delegated (human-not-present) orders need approval
    fx_band_bps: int = 150  # allowed markup over the FBIL reference on quotes (used from drop 3)
    substitution_tolerance_paise: int = 0  # raised by human overrides in Stage 4
    extra: dict = field(default_factory=dict)
