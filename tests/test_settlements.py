from sakshi.gateway import StubGateway
import pytest

from sakshi.settlements import (RECON_FIELDS, FeeSchedule, ReconRecordError, join_settlement_to_intent,
                                normalize_recon_line, refund_fee_burn, require_linked_transaction, settlement_lines)


def test_fee_math():
    fees = FeeSchedule()
    fee, tax = fees.fee_tax(100_000, "card")
    assert (fee, tax) == (2_000, 360)
    assert fees.net(100_000, "card") == 97_640
    assert fees.fee_tax(100_000, "upi") == (0, 0)
    fee_i, _ = fees.fee_tax(100_000, "card", international=True)
    assert fee_i == 3_000


def test_recon_lines_match_schema_and_carry_notes():
    gw = StubGateway()
    order = gw.create_order(64_000, "INR", receipt="r-1", notes={"sakshi_txn": "txn_a", "sakshi_intent": "abc"})
    pay = gw.simulate_capture(order["id"], method="card", card_network="visa")
    lines = settlement_lines([pay], fees=FeeSchedule(), orders={order["id"]: order})
    assert len(lines) == 1
    line = lines[0]
    assert list(line.keys()) == RECON_FIELDS
    assert line["type"] == "payment" and line["credit"] == 64_000 - 1_280 - 230
    assert line["notes"]["sakshi_intent"] == "abc"
    assert line["order_id"] == order["id"] and line["order_receipt"] == "r-1"
    groups = join_settlement_to_intent(lines)
    assert "txn_a" in groups and "unlinked" not in groups


def test_international_line_uses_base_amount():
    gw = StubGateway()
    order = gw.create_order(1_000, "USD", notes={"sakshi_txn": "txn_fx"})  # $10.00
    pay = gw.simulate_capture(order["id"], method="card", rate=95.68, card_network="mastercard")
    assert pay["base_amount"] == 95_680 and pay["international"] is True
    line = settlement_lines([pay])[0]
    assert line["amount"] == 95_680 and line["currency"] == "INR"
    assert "USD" in line["description"]


def test_refund_fee_burn():
    gw = StubGateway()
    order = gw.create_order(100_000, "INR")
    pay = gw.simulate_capture(order["id"], method="card")
    burn = refund_fee_burn(pay, 100_000, FeeSchedule())
    assert burn["burn_paise"] == 2_000 + 360
    half = refund_fee_burn(pay, 50_000, FeeSchedule())
    assert half["burn_paise"] == 1_180


def test_external_recon_row_is_normalised_and_must_match_transaction():
    raw = {"entity_id": "pay_1", "type": "payment", "amount": "64000", "fee": "1280", "tax": "230",
           "credit": "62490", "notes": '{"sakshi_txn":"txn_1"}', "order_id": "order_1"}
    line = normalize_recon_line(raw)
    assert line["amount"] == 64_000 and line["notes"]["sakshi_txn"] == "txn_1"
    assert require_linked_transaction(line, "txn_1") is line
    with pytest.raises(ReconRecordError):
        require_linked_transaction(line, "txn_other")
    with pytest.raises(ReconRecordError):
        normalize_recon_line({"amount": "not-money", "notes": {}})
