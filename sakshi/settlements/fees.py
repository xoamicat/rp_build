"""Fee arithmetic for settlements.

Rates are per merchant plan. The defaults below are placeholders: set them from
your own Razorpay pricing page in ``MerchantConfig.extra["fees"]`` or when you
construct a FeeSchedule. GST on the fee is 18 percent.

Refund fee burn: Razorpay does not reverse the fee (and GST on it) charged at
capture when a payment is refunded. Every refund an agent grants therefore has
a cost even when the goods come back. Stage 2 prices it; Stage 3 weighs it.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FeeSchedule:
    mdr_bps: dict = field(default_factory=lambda: {
        "upi": 0,          # set per your plan; zero-MDR rules apply to some UPI merchant flows
        "card": 200,       # domestic cards, 2.00 percent placeholder
        "intl_card": 300,  # international cards, 3.00 percent placeholder
        "netbanking": 200,
        "wallet": 200,
        "emandate": 200,
    })
    gst_bps: int = 1800
    default_bps: int = 200

    def rate_bps(self, method: str, international: bool = False) -> int:
        if international and method == "card":
            return self.mdr_bps.get("intl_card", self.default_bps)
        return self.mdr_bps.get(method, self.default_bps)

    def fee_tax(self, amount_paise: int, method: str, international: bool = False) -> tuple[int, int]:
        """Returns (fee, tax) in paise, rounded half-up the way invoices usually are."""
        bps = self.rate_bps(method, international)
        fee = (amount_paise * bps + 5_000) // 10_000
        tax = (fee * self.gst_bps + 5_000) // 10_000
        return fee, tax

    def net(self, amount_paise: int, method: str, international: bool = False) -> int:
        fee, tax = self.fee_tax(amount_paise, method, international)
        return amount_paise - fee - tax


def refund_fee_burn(payment: dict, refund_amount_paise: int, fees: FeeSchedule) -> dict:
    """Cost of a refund to the merchant: fee and GST on the refunded portion are not returned."""
    settled_amount = payment.get("base_amount", payment["amount"])
    fee, tax = fees.fee_tax(settled_amount, payment.get("method", "card"), bool(payment.get("international")))
    share = min(max(refund_amount_paise / max(settled_amount, 1), 0.0), 1.0)
    burned = int(round((fee + tax) * share))
    return {
        "payment_id": payment.get("id"),
        "refund_amount_paise": refund_amount_paise,
        "fee_paise": fee,
        "tax_paise": tax,
        "burn_paise": burned,
        "share_refunded": round(share, 4),
    }
