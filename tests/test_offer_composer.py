import json

import pytest

from sakshi.llm.provider import MockProvider
from sakshi.offer_composer import CatalogOffer, OfferComposer, OfferCompositionError


CATALOG = [
    CatalogOffer("PZ-MARG", "Margherita Pizza", 32_000),
    CatalogOffer("DR-COLA", "Cola", 6_000),
]


def _compose(response):
    return OfferComposer(MockProvider(default=json.dumps(response))).compose(
        "Two margheritas please; do not add anything else.",
        merchant_id="pizza-demo",
        offer_id="offer-ai-1",
        catalog_version="menu-v1",
        catalog=CATALOG,
        currency="INR",
        shipping_paise=4_000,
        tax_paise=0,
        delivery_by="2026-08-30",
        return_policy_version="returns-v4",
    )


def test_ai_offer_composer_hydrates_prices_from_catalogue_not_model_output():
    draft = _compose({
        "lines": [{"sku": "PZ-MARG", "qty": 2, "unit_paise": 1}],
        "buyer_summary": "Two Margherita Pizzas, delivery by 30 August.",
        "uncertainties": [],
    })

    assert draft.terms.lines[0].unit_paise == 32_000
    assert draft.terms.total_paise == 68_000
    assert draft.ledger_payload()["catalog_validated"] is True
    assert draft.ledger_payload()["consent_captured"] is False


def test_ai_offer_composer_rejects_unknown_sku_and_never_turns_a_draft_into_consent():
    with pytest.raises(OfferCompositionError, match="unknown SKU"):
        _compose({
            "lines": [{"sku": "FREE-MONEY", "qty": 1}],
            "buyer_summary": "Approved forever.",
            "uncertainties": [],
        })


def test_ai_offer_composer_turns_uncertainty_into_a_clarification_gate():
    draft = _compose({
        "lines": [{"sku": "PZ-MARG", "qty": 2}],
        "buyer_summary": "Two Margherita Pizzas.",
        "uncertainties": ["The buyer did not state whether delivery is required."],
        "clarifying_questions": ["Should this be delivery or pickup?"],
    })

    assert draft.requires_clarification is True
    assert draft.clarifying_questions == ("Should this be delivery or pickup?",)
    assert draft.ledger_payload()["ai_policy_version"] == "atlas.clarify-to-lock.v1"
