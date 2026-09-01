"""Integration checks for the browser-facing Test Mode evidence flow."""
from __future__ import annotations

import hashlib
import hmac
import json

import ui.server as server

from sakshi.config import Settings


class _FakeLiveGateway:
    """No-network Razorpay-shaped gateway used to exercise the Flask adapter."""

    def __init__(self, _settings):
        pass

    def create_order(self, amount, currency="INR", receipt=None, notes=None):
        return {
            "id": "order_test_atlas_001", "entity": "order", "amount": amount,
            "currency": currency, "status": "created", "receipt": receipt,
            "notes": dict(notes or {}),
        }


def _offer_payload():
    return {
        "txn": "offer_test_mode_001",
        "terms": {
            "merchant_id": "merchant_test", "offer_id": "offer_test", "catalog_version": "menu-v1",
            "lines": [{"sku": "PZ-MARG", "name": "Margherita Pizza", "qty": 2, "unit_paise": 32000}],
            "currency": "INR", "shipping_paise": 4000, "tax_paise": 0,
            "delivery_by": "2026-09-01", "return_policy_version": "returns-v1",
            "substitution_policy": "no_substitution",
        },
        "approval": {
            "approval_ref": "opaque-approval", "playback": "Two pizzas for ₹680 including delivery.",
            "channel": "test", "principal_ref": "opaque-principal",
        },
    }


def test_test_mode_order_requires_signed_lock_and_verified_webhook(monkeypatch):
    monkeypatch.setattr(server, "_offer_locks", {})
    monkeypatch.setattr(server, "_offer_evidence_sessions", {})
    monkeypatch.setattr(server, "_offer_lock_service", None)
    monkeypatch.setattr(server, "_test_mode_orders", {})
    monkeypatch.setattr(server, "_offer_store", None)
    monkeypatch.setattr("sakshi.gateway.LiveGateway", _FakeLiveGateway)
    settings = Settings(
        razorpay_key_id="rzp_test_atlas", razorpay_key_secret="test-secret",
        razorpay_webhook_secret="webhook-test-secret",
    )
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: settings))
    client = server.app.test_client()

    signed = client.post("/api/offer-locks", json=_offer_payload())
    assert signed.status_code == 201
    lock_id = signed.get_json()["lock"]["lock_id"]

    created = client.post(f"/api/offer-locks/{lock_id}/test-mode-order")
    assert created.status_code == 201
    data = created.get_json()
    assert data["mode"] == "razorpay_test_mode"
    assert data["order"]["id"] == "order_test_atlas_001"
    assert len(data["order"]["note_keys"]) == 15
    assert {"atlas_lock", "sakshi_txn", "sakshi_sig"}.issubset(data["order"]["note_keys"])

    order_id = data["order"]["id"]
    returned = client.post(f"/api/test-mode/orders/{order_id}/checkout-return", json={
        "razorpay_payment_id": "pay_test_atlas_001", "razorpay_signature": "browser-value-not-trusted",
    })
    assert returned.status_code == 200
    assert returned.get_json()["payment_truth"] == "pending_verified_webhook"

    txn = _offer_payload()["txn"]
    webhook = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {
            "id": "pay_test_atlas_001", "entity": "payment", "amount": 68000,
            "currency": "INR", "status": "captured", "captured": True,
            "order_id": order_id, "method": "card", "notes": {"sakshi_txn": txn},
        }}},
    }
    raw = json.dumps(webhook, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(settings.razorpay_webhook_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    ingested = client.post("/webhooks/razorpay", data=raw, headers={
        "Content-Type": "application/json", "x-razorpay-signature": signature,
        "x-razorpay-event-id": "evt_test_atlas_001",
    })
    assert ingested.status_code == 200
    assert ingested.get_json()["ledger_event_type"] == "rzp.payment.captured"

    wrong_order = json.loads(json.dumps(webhook))
    wrong_order["payload"]["payment"]["entity"]["order_id"] = "order_not_bound_to_lock"
    wrong_raw = json.dumps(wrong_order, separators=(",", ":")).encode("utf-8")
    wrong_signature = hmac.new(settings.razorpay_webhook_secret.encode("utf-8"), wrong_raw, hashlib.sha256).hexdigest()
    rejected = client.post("/webhooks/razorpay", data=wrong_raw, headers={
        "Content-Type": "application/json", "x-razorpay-signature": wrong_signature,
        "x-razorpay-event-id": "evt_wrong_order",
    })
    assert rejected.status_code == 409

    status = client.get(f"/api/test-mode/orders/{order_id}/status")
    assert status.status_code == 200
    assert status.get_json()["payment_captured_by_verified_webhook"] is True


def test_dashboard_routes_are_directly_loadable():
    client = server.app.test_client()
    for path in (
        "/", "/offer-lock", "/evidence", "/evidence/offer-demo", "/claims", "/claims/offer-demo",
        "/release", "/checkout-safety", "/fx", "/fx-promise", "/subscription-preflight", "/settlements", "/intent-check", "/speech-check",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert b"SettleX" in response.data


def test_fx_promise_endpoint_prices_three_dates_without_claiming_a_gateway_rate():
    client = server.app.test_client()
    result = client.post("/api/fx-promise/assess", json={
        "envelope": {
            "buyer_currency": "USD", "foreign_amount_minor": 1_000, "minor_per_unit": 100,
            "displayed_rate": 96.00, "reference_rate": 95.68, "reference_provider": "FBIL",
            "reference_source_ref": "fbil-usdinr-2026-08-20",
            "reference_date": "2026-08-20", "valid_through": "2026-08-21", "allowed_spread_bps": 150,
        },
        "payment_rate": 95.70, "payment_date": "2026-08-21", "payment_source_ref": "pay_pay_123",
        "dispute_rate": 97.20, "dispute_date": "2026-09-02", "dispute_source_ref": "dispute_disp_123",
    })

    assert result.status_code == 200
    payload = result.get_json()
    assert payload["payment_value_paise"] == 95_700
    assert payload["dispute_fx_delta_paise"] == 1_500
    assert payload["evidence_attached"] is False


def test_subscription_preflight_refuses_to_release_a_changed_renewal_without_reconfirmation(monkeypatch):
    monkeypatch.setattr(server, "_offer_locks", {})
    monkeypatch.setattr(server, "_offer_evidence_sessions", {})
    monkeypatch.setattr(server, "_offer_lock_service", None)
    monkeypatch.setattr(server, "_offer_store", None)
    client = server.app.test_client()
    signed = client.post("/api/offer-locks", json=_offer_payload())
    lock_id = signed.get_json()["lock"]["lock_id"]
    proposed = _offer_payload()["terms"]
    proposed["renewal_summary"] = "Renews monthly at ₹680 including delivery."

    result = client.post("/api/subscriptions/preflight", json={
        "lock_id": lock_id,
        "patch": {
            "subscription_id": "sub_test_001", "plan_id": "plan_test_v2", "quantity": 2,
            "remaining_count": 12, "schedule_change_at": "cycle_end", "customer_notify": False,
        },
        "proposed_terms": proposed,
    })

    assert result.status_code == 200
    payload = result.get_json()
    assert payload["decision"]["status"] == "RECONFIRM"
    assert payload["razorpay_patch_permitted"] is False
    assert "Do not call Razorpay PATCH" in payload["next_step"]
