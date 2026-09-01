"""Preflight controls for a merchant's Razorpay Subscription update.

Razorpay remains the system that accepts ``PATCH /v1/subscriptions/:id``.
Atlas sits before the merchant calls that API and answers a deliberately
narrow question: can the previous buyer-visible commercial promise still be
used for this proposed mutation?  The module never calls Razorpay, performs a
charge/refund, or treats a notification flag as buyer approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .offer_lock import OfferDecision, OfferLock, OfferLockService, OfferTerms


class SubscriptionPreflightError(ValueError):
    pass


@dataclass(frozen=True)
class SubscriptionPatch:
    """A safe, minimal projection of Razorpay's subscription-update request."""

    subscription_id: str
    plan_id: str
    quantity: Optional[int] = None
    remaining_count: Optional[int] = None
    start_at: Optional[int] = None
    schedule_change_at: str = "now"
    customer_notify: bool = True
    offer_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.subscription_id.strip() or not self.plan_id.strip():
            raise SubscriptionPreflightError("subscription_id and plan_id are required")
        if self.quantity is not None and self.quantity < 1:
            raise SubscriptionPreflightError("quantity must be positive when supplied")
        if self.remaining_count is not None and self.remaining_count < 1:
            raise SubscriptionPreflightError("remaining_count must be positive when supplied")
        if self.start_at is not None and self.start_at <= 0:
            raise SubscriptionPreflightError("start_at must be a positive Unix timestamp when supplied")
        if self.schedule_change_at not in {"now", "cycle_end"}:
            raise SubscriptionPreflightError("schedule_change_at must be 'now' or 'cycle_end'")

    def as_dict(self) -> dict[str, Any]:
        return {
            "subscription_id": self.subscription_id,
            "plan_id": self.plan_id,
            "offer_id": self.offer_id,
            "quantity": self.quantity,
            "remaining_count": self.remaining_count,
            "start_at": self.start_at,
            "schedule_change_at": self.schedule_change_at,
            "customer_notify": self.customer_notify,
        }


@dataclass(frozen=True)
class SubscriptionPreflight:
    """A release receipt that the merchant stores before it invokes Razorpay."""

    lock_id: str
    patch: SubscriptionPatch
    decision: OfferDecision
    proposed_terms_hash: str

    @property
    def razorpay_patch_permitted(self) -> bool:
        """Only ALLOW can release the merchant's downstream PATCH worker."""
        return self.decision.allowed

    def as_dict(self) -> dict[str, Any]:
        return {
            "lock_id": self.lock_id,
            "patch": self.patch.as_dict(),
            "decision": self.decision.as_dict(),
            "proposed_terms_hash": self.proposed_terms_hash,
            "razorpay_patch_permitted": self.razorpay_patch_permitted,
            "next_step": (
                "Merchant worker may call Razorpay PATCH; retain this receipt with the subscription change."
                if self.razorpay_patch_permitted
                else "Do not call Razorpay PATCH. Reconfirm the exact change with the buyer or escalate to operations."
            ),
            "boundary": "Atlas does not call Razorpay, create a charge/refund, or treat customer_notify as consent.",
        }


def preflight_subscription_update(
    service: OfferLockService,
    lock: OfferLock,
    patch: SubscriptionPatch,
    proposed_terms: OfferTerms,
) -> SubscriptionPreflight:
    """Compare the proposed renewed promise, append an audit receipt and release or stop.

    ``proposed_terms`` must come from the merchant's catalog/subscription
    mapping service.  It intentionally remains typed commercial data instead
    of attempting to infer price or entitlement from a Razorpay plan id.
    """
    decision = service.check(lock, proposed_terms)
    result = SubscriptionPreflight(
        lock_id=lock.lock_id,
        patch=patch,
        decision=decision,
        proposed_terms_hash=proposed_terms.material_hash(),
    )
    if service.ledger is not None:
        service.ledger.append(lock.txn, "subscription.update.preflighted", "atlas_subscription", result.as_dict())
    return result
