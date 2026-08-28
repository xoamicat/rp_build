import hashlib
import hmac
import json

import pytest

from sakshi.checkers import default_stage1
from sakshi.dispute import ChainView, DisputeAgent, DisputeClaim
from sakshi.engine import Engine
from sakshi.evidence import EvidenceSigner
from sakshi.gateway import StubGateway
from sakshi.integration import CheckoutBlocked, EvidenceRequired, SakshiCheckout
from sakshi.webhooks import RazorpayWebhookIngestor, WebhookSignatureError


def test_signed_intent_and_chain_seal_are_verifiable(ledger, merchant, intent, good_cart):
    signer = EvidenceSigner.generate_for_demo("test-key-1")
    engine = Engine(ledger, merchant, default_stage1(), signer=signer)
    result = SakshiCheckout(engine, StubGateway()).create_order(intent, good_cart)
    assert result.order["notes"]["sakshi_kid"] == "test-key-1"
    assert result.order["notes"]["sakshi_sig"]
    engine.seal_transaction(intent.txn)
    assert engine.signed_evidence_valid(intent.txn)
    integrity = DisputeAgent(ledger, merchant, signer=signer).evidence_pack(
        ChainView.load(ledger, intent.txn),
        DisputeClaim("other"), {},
    )[-1]["items"]
    assert integrity["signed_chain_seal_verified"] is True


def test_checkout_sidecar_never_creates_an_order_for_a_blocked_cart(ledger, merchant, intent, bad_cart):
    engine = Engine(ledger, merchant, default_stage1())
    gateway = StubGateway()
    with pytest.raises(CheckoutBlocked) as exc:
        SakshiCheckout(engine, gateway).create_order(intent, bad_cart)
    assert exc.value.gate.status.value == "BLOCK"
    assert gateway.orders == {}


def test_signed_evidence_policy_fails_closed_without_a_signer(ledger, merchant, intent, good_cart):
    merchant.extra["require_signed_evidence"] = True
    with pytest.raises(EvidenceRequired):
        SakshiCheckout(Engine(ledger, merchant, default_stage1()), StubGateway()).create_order(intent, good_cart)


def test_webhook_requires_hmac_is_idempotent_and_keeps_transaction_link(ledger):
    secret = "test-secret"
    body = json.dumps({
        "event": "payment.captured",
        "payload": {"payment": {"entity": {
            "id": "pay_1", "amount": 64000, "currency": "INR", "order_id": "order_1",
            "notes": {"sakshi_txn": "txn_webhook"}, "method": "upi", "status": "captured",
        }}},
    }, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    ingestor = RazorpayWebhookIngestor(ledger, secret)
    receipt = ingestor.ingest(body, signature)
    assert receipt.txn == "txn_webhook" and receipt.ledger_event_type == "rzp.payment.captured"
    event = ledger.latest("txn_webhook", "rzp.payment.captured")
    assert event.payload["amount"] == 64000 and "contact" not in event.payload
    assert ingestor.ingest(body, signature).duplicate is True
    with pytest.raises(WebhookSignatureError):
        ingestor.ingest(body, "bad")
