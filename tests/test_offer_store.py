from sakshi.evidence import EvidenceSigner
from sakshi.offer_lock import BuyerApproval, OfferLine, OfferLockService, OfferTerms
from sakshi.offer_store import DurableOfferStore


def test_durable_offer_store_round_trips_signed_lock_and_safe_test_order(tmp_path):
    signer = EvidenceSigner.generate_for_demo("atlas-persist-test")
    lock = OfferLockService(signer).lock(
        "txn_persist_1",
        OfferTerms(
            merchant_id="m1", offer_id="o1", catalog_version="v1",
            lines=(OfferLine("SKU-1", "Widget", 1, 12300),), shipping_paise=500,
            delivery_by="2026-09-01", return_policy_version="returns-v1",
        ),
        BuyerApproval("opaque-a1", "One Widget for ₹128. Buyer reviewed.", principal_ref="opaque-user"),
    )
    store = DurableOfferStore(str(tmp_path / "atlas.db"))
    store.put_lock(lock)

    restored = store.get_lock(lock.lock_id)
    assert restored is not None
    assert restored.lock_id == lock.lock_id
    assert restored.terms.total_paise == 12_800
    assert signer.verify(restored.evidence, signer.public_key_b64)
    assert store.find_lock_by_prefix(lock.lock_id[:12]).lock_id == lock.lock_id

    store.put_test_order("order_test_1", {
        "lock_id": lock.lock_id, "txn": lock.txn, "client_returned": False,
        "order": {"id": "order_test_1", "amount": 12_800, "currency": "INR"},
        "payment_id": "must-not-persist", "razorpay_signature": "must-not-persist",
    })
    state = store.get_test_order("order_test_1")
    assert state["order"]["id"] == "order_test_1"
    assert "payment_id" not in state
    assert "razorpay_signature" not in state
