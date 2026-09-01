from sakshi.evidence import EvidenceSigner
from sakshi.ledger import Ledger
from sakshi.offer_lock import BuyerApproval, OfferLine, OfferLockService, OfferTerms
from sakshi.subscriptions import SubscriptionPatch, SubscriptionPreflightError, preflight_subscription_update


def _terms(*, renewal_summary=None, price=32_000):
    return OfferTerms(
        merchant_id="pizza-demo", offer_id="pizza-monthly", catalog_version="menu-v1",
        lines=(OfferLine("PZ-MARG", "Margherita", 2, price),), shipping_paise=4_000,
        delivery_by="2026-09-01", return_policy_version="returns-v1", renewal_summary=renewal_summary,
    )


def test_subscription_preflight_withholds_patch_when_new_renewal_promise_differs():
    ledger = Ledger()
    service = OfferLockService(EvidenceSigner.generate_for_demo("subscription-key"), ledger)
    lock = service.lock("txn_subscription_001", _terms(), BuyerApproval("approval-1", "Two pizzas for ₹680."))
    patch = SubscriptionPatch(
        subscription_id="sub_001", plan_id="plan_monthly_v2", quantity=2, remaining_count=12,
        schedule_change_at="cycle_end", customer_notify=False,
    )

    result = preflight_subscription_update(
        service, lock, patch, _terms(renewal_summary="Renews monthly at ₹680 including delivery."),
    )

    assert result.decision.status == "RECONFIRM"
    assert result.razorpay_patch_permitted is False
    assert result.patch.customer_notify is False
    assert ledger.latest(lock.txn, "subscription.update.preflighted") is not None


def test_subscription_preflight_allows_identical_terms_but_rejects_invalid_patch_shape():
    service = OfferLockService(EvidenceSigner.generate_for_demo("subscription-key"), Ledger())
    lock = service.lock("txn_subscription_002", _terms(), BuyerApproval("approval-2", "Two pizzas for ₹680."))
    result = preflight_subscription_update(
        service, lock, SubscriptionPatch(subscription_id="sub_002", plan_id="plan_v1"), _terms(),
    )

    assert result.decision.status == "ALLOW"
    assert result.razorpay_patch_permitted is True

    try:
        SubscriptionPatch(subscription_id="sub_002", plan_id="plan_v1", schedule_change_at="later")
    except SubscriptionPreflightError:
        pass
    else:  # pragma: no cover - a readable assertion for invalid release schedule
        raise AssertionError("invalid Razorpay schedule should be rejected")
