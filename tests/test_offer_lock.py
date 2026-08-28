from sakshi.checkers import default_stage1
from sakshi.engine import Engine
from sakshi.evidence import EvidenceSigner
from sakshi.gateway import StubGateway
from sakshi.integration import SakshiCheckout
from sakshi.dispute import DisputeAgent, DisputeClaim
from sakshi.models import Cart, CartLine
from sakshi.offer_lock import (
    BuyerApproval,
    OfferLine,
    OfferLockService,
    OfferTerms,
    compare_offer,
    merge_offer_notes,
)


def _terms(**overrides):
    base = {
        "merchant_id": "pizza-demo",
        "offer_id": "offer_42",
        "catalog_version": "menu-2026-08-28.1",
        "lines": (OfferLine("PZ-MARG", "Margherita Pizza", 2, 32_000),),
        "currency": "INR",
        "shipping_paise": 4_000,
        "delivery_by": "2026-08-30",
        "return_policy_version": "returns-v4",
        "substitution_policy": "no_substitution",
        "renewal_summary": None,
    }
    base.update(overrides)
    return OfferTerms(**base)


def _approval():
    return BuyerApproval(
        approval_ref="approval_abc",
        playback="2 Margherita Pizzas for ₹680, delivery by 30 August; no substitutions.",
        channel="chatgpt_app",
        principal_ref="buyer_session_opaque",
    )


def test_offer_lock_requires_reconfirmation_for_added_item_price_and_delivery_drift(ledger):
    signer = EvidenceSigner.generate_for_demo("merchant-key-1")
    service = OfferLockService(signer, ledger)
    lock = service.lock("txn_offer", _terms(), _approval())
    changed = _terms(
        catalog_version="menu-2026-08-29.2",
        lines=(
            OfferLine("PZ-MARG", "Margherita Pizza", 2, 35_000),
            OfferLine("SD-GARL", "Garlic Bread", 1, 19_000),
        ),
        delivery_by="2026-09-02",
    )

    decision = service.check(lock, changed)

    assert decision.status == "RECONFIRM"
    assert {delta.field for delta in decision.deltas} >= {
        "line.PZ-MARG.unit_paise", "line.SD-GARL", "delivery_by"
    }
    assert ledger.latest("txn_offer", "offer.locked")
    assert ledger.latest("txn_offer", "offer.drift.checked").payload["status"] == "RECONFIRM"


def test_offer_lock_allows_buyer_friendly_price_drop_but_escalates_identity_change():
    signer = EvidenceSigner.generate_for_demo()
    lock = OfferLockService(signer).lock("txn_offer", _terms(), _approval())
    cheaper = _terms(lines=(OfferLine("PZ-MARG", "Margherita Pizza", 2, 30_000),))
    assert compare_offer(lock, cheaper).status == "ALLOW"
    assert compare_offer(lock, _terms(merchant_id="another-merchant")).status == "ESCALATE"


def test_offer_lock_uses_remaining_notes_capacity_when_combined_with_signed_intent(ledger, merchant, intent, good_cart):
    signer = EvidenceSigner.generate_for_demo("shared-key-1")
    engine = Engine(ledger, merchant, default_stage1(), signer=signer)
    service = OfferLockService(signer, ledger)
    lock = service.lock(intent.txn, _terms(), _approval())

    result = SakshiCheckout(engine, StubGateway()).create_order(intent, good_cart, offer_lock=lock)

    assert len(result.order["notes"]) == 15
    assert result.order["notes"]["atlas_lock"] == lock.lock_id[:24]
    assert result.order["notes"]["atlas_sig"] == lock.evidence.signature
    assert "atlas_kid" not in result.order["notes"]  # the existing signed intent key is reused


def test_offer_lock_note_merge_is_standalone_when_no_intent_notes_exist():
    signer = EvidenceSigner.generate_for_demo("offer-key-1")
    lock = OfferLockService(signer).lock("txn_offer", _terms(), _approval())

    notes = merge_offer_notes({}, lock)

    assert notes["atlas_kid"] == "offer-key-1"
    assert len(notes) == 4


def test_a_material_offer_drift_prevents_an_automatic_dispute_contest(ledger, merchant, intent, good_cart):
    signer = EvidenceSigner.generate_for_demo("shared-key-2")
    engine = Engine(ledger, merchant, default_stage1(), signer=signer)
    service = OfferLockService(signer, ledger)
    lock = service.lock(intent.txn, _terms(), _approval())
    gateway = StubGateway()
    order = SakshiCheckout(engine, gateway).create_order(intent, good_cart, offer_lock=lock).order
    engine.record_payment(intent.txn, gateway.simulate_capture(order["id"]))
    service.check(lock, _terms(lines=(
        OfferLine("PZ-MARG", "Margherita Pizza", 2, 35_000),
        OfferLine("SD-GARL", "Garlic Bread", 1, 19_000),
    )))

    decision = DisputeAgent(ledger, merchant, signer=signer).decide(
        intent.txn, DisputeClaim("wrong_item", "I did not approve garlic bread"), record=False
    )

    assert decision.recommendation == "ESCALATE"
    assert "material Offer Lock drift" in decision.reasons[0]
    assert decision.evidence_pack[-1]["items"]["latest_drift_status"] == "RECONFIRM"
