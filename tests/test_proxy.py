from fastapi.testclient import TestClient

from sakshi.config import Settings
from sakshi.ledger import Ledger
from sakshi.proxy import create_app, redact


def test_stub_proxy_logs_and_links_by_notes():
    ledger = Ledger(":memory:")
    app = create_app(ledger, Settings(), forward=False)
    client = TestClient(app)
    r = client.post("/v1/orders", json={"amount": 64_000, "currency": "INR", "receipt": "r-9",
                                        "notes": {"sakshi_txn": "txn_p1", "sakshi_intent": "h"}})
    assert r.status_code == 200
    order = r.json()
    assert order["id"].startswith("order_stub") and order["notes"]["sakshi_txn"] == "txn_p1"
    types = [(e.type, e.txn) for e in ledger.events()]
    assert types == [("rzp.request", "txn_p1"), ("rzp.response", "txn_p1")]
    assert client.get(f"/v1/orders/{order['id']}").status_code == 200
    assert client.get("/healthz").json()["mode"] == "stub"


def test_unlinked_and_header_txn():
    ledger = Ledger(":memory:")
    client = TestClient(create_app(ledger, Settings(), forward=False))
    client.post("/v1/orders", json={"amount": 500, "currency": "INR"})
    client.post("/v1/orders", json={"amount": 500, "currency": "INR"}, headers={"X-Sakshi-Txn": "txn_h"})
    assert [e.txn for e in ledger.events()] == ["unlinked", "unlinked", "txn_h", "txn_h"]


def test_unsupported_path_is_404_in_stub():
    client = TestClient(create_app(Ledger(":memory:"), Settings(), forward=False))
    assert client.get("/v1/settlements").status_code == 404


def test_redact_drops_card_fields():
    out = redact({"amount": 1, "card": {"number": "4111"}, "notes": {"contact": "x", "ok": "y"}})
    assert out["card"] == "<redacted>" and out["notes"]["contact"] == "<redacted>" and out["notes"]["ok"] == "y"
