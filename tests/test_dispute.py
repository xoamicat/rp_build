from datetime import date

from sakshi.checkers import default_stage1, default_stage2
from sakshi.dispute import ChainView, DisputeAgent, DisputeClaim
from sakshi.engine import Engine
from sakshi.fx import StaticRates
from sakshi.gateway import StubGateway
from sakshi.intent import IntentItem, IntentReceipt
from sakshi.ledger import Ledger
from sakshi.models import Cart, CartLine, MerchantConfig
from sakshi.settlements import settlement_lines


def _flow(ledger, merchant, txn, cart, pay=True, method="upi", human_present=True, gate_content=None, currency="INR",
          rate=None, order_extra=0, items=None, cap=80_000):
    engine = Engine(ledger=ledger, merchant=merchant, checkers=default_stage1() + default_stage2())
    intent = IntentReceipt(txn=txn, utterance="x", playback="2 margherita pizzas, total under ₹800",
                           items=items or [IntentItem("margherita", 2, "PZ-MARG")], cap_paise=cap,
                           currency=currency, human_present=human_present, mandate_ref=None if human_present else "mandate_1")
    engine.capture_intent(intent)
    cart.quoted_total_paise = cart.total_paise
    gate = engine.gate(intent, cart, content=gate_content or [])
    gw = StubGateway()
    order = gw.create_order(cart.total_paise + order_extra, currency, notes=gate.notes)
    engine.check_order(intent, cart, order, prepayment=True)
    if not pay:
        return engine, gate
    engine.record_order(txn, order)
    payment = gw.simulate_capture(order["id"], method=method, rate=rate, international=currency != "INR")
    engine.record_payment(txn, payment)
    line = settlement_lines([payment], fees=engine.fees)[0]
    engine.record_settlement_line(txn, line)
    engine.reconcile(txn, payment, settlement=line, intent=intent, cart=cart, order=order)
    return engine, gate


MARG2 = lambda: Cart(lines=[CartLine("Margherita Pizza", 2, 32_000, "PZ-MARG")])  # noqa: E731


def test_contest_when_cart_matched_and_hash_rides_with_money():
    ledger, merchant = Ledger(":memory:"), MerchantConfig()
    _flow(ledger, merchant, "t1", MARG2())
    res = DisputeAgent(ledger, merchant).decide("t1", DisputeClaim("wrong_item", "not what I ordered", opened_on=date(2026, 8, 30)))
    assert res.recommendation == "CONTEST" and res.refund_amount_paise == 0 and res.confidence >= 0.85
    assert not res.requires_human
    assert ChainView.load(ledger, "t1").hash_rides_with_money is True
    sections = [s["section"] for s in res.evidence_pack]
    assert sections[0].startswith("1.") and sections[-1].startswith("9.") and len(sections) == 9
    assert res.evidence_pack[8]["items"]["ledger_verified"] is True
    assert "not able to refund" in res.customer_explanation
    assert res.cost_of_refund["if_full_refund"]["refund_amount_paise"] == 64_000
    types = [e.type for e in ledger.chain("t1")]
    assert types[-2:] == ["dispute.opened", "dispute.verdict"]


def test_refund_when_blocked_cart_was_paid_anyway():
    ledger, merchant = Ledger(":memory:"), MerchantConfig()
    bad = Cart(lines=[CartLine("Margherita Pizza", 2, 32_000, "PZ-MARG"), CartLine("Garlic Bread", 1, 19_000, "SD-GARL", source="upsell")])
    _flow(ledger, merchant, "t2", bad, method="card")
    res = DisputeAgent(ledger, merchant).decide("t2", DisputeClaim("wrong_item", "never ordered garlic bread"))
    assert res.recommendation == "REFUND" and res.refund_amount_paise == 83_000
    assert res.cost_of_refund["fee_burn_paise"] == 1_660 + 299  # 2 percent of 83,000 plus 18 percent GST
    assert res.cost_of_refund["total_paise"] == 83_000 + 1_959
    assert "mistake" in res.customer_explanation


def test_partial_refund_for_undisclosed_charge():
    ledger, merchant = Ledger(":memory:"), MerchantConfig()
    _flow(ledger, merchant, "t3", MARG2(), order_extra=6_000)
    res = DisputeAgent(ledger, merchant).decide("t3", DisputeClaim("amount_differs", "you said 640 and charged 700"))
    assert res.recommendation == "PARTIAL_REFUND" and res.refund_amount_paise == 6_000
    assert "did not tell you about" in res.customer_explanation


def test_not_authorized_contest_for_present_customer_and_refund_for_unapproved_delegated():
    ledger, merchant = Ledger(":memory:"), MerchantConfig(hitl_threshold_paise=200_000)
    _flow(ledger, merchant, "t4", MARG2())
    res = DisputeAgent(ledger, merchant).decide("t4", DisputeClaim("not_authorized", "don't recognise this"))
    assert res.recommendation == "CONTEST"

    big = Cart(lines=[CartLine("Farmhouse Pizza", 4, 45_000, "PZ-FARM"), CartLine("Coke 300ml", 6, 6_000, "BV-COKE")])
    _flow(ledger, merchant, "t5", big, human_present=False, cap=None,
          items=[IntentItem("farmhouse", 4, "PZ-FARM"), IntentItem("coke", 6, "BV-COKE")])
    res = DisputeAgent(ledger, merchant).decide("t5", DisputeClaim("not_authorized", "my assistant could not spend this"))
    assert res.recommendation == "REFUND" and res.refund_amount_paise == 216_000
    assert res.requires_human  # above the merchant's approval threshold


def test_escalate_without_intent_or_for_delivery_claims():
    ledger, merchant = Ledger(":memory:"), MerchantConfig()
    engine = Engine(ledger=ledger, merchant=merchant, checkers=default_stage1())
    gw = StubGateway()
    order = gw.create_order(64_000, "INR")  # created outside the gate: no intent, no notes
    engine.record_order("t6", order)
    engine.record_payment("t6", gw.simulate_capture(order["id"]))
    res = DisputeAgent(ledger, merchant).decide("t6", DisputeClaim("wrong_item", "wrong"))
    assert res.recommendation == "ESCALATE" and res.requires_human
    _flow(ledger, merchant, "t7", MARG2())
    res = DisputeAgent(ledger, merchant).decide("t7", DisputeClaim("not_received", "never came"))
    assert res.recommendation == "ESCALATE" and "delivery" in res.reasons[0]


def test_cross_border_dispute_prices_dispute_day_fx():
    ledger, merchant = Ledger(":memory:"), MerchantConfig(fx_band_bps=150)
    tee = Cart(lines=[CartLine("Cotton Tee", 1, 1_000, "TS-TEE")], currency="USD")
    _flow(ledger, merchant, "t8", tee, method="card", currency="USD", rate=94.9, items=[IntentItem("cotton tee", 1, "TS-TEE")], cap=None)
    fx_now = StaticRates({"2026-08-31": 97.2}).reference("USD", "INR", "2026-08-31")
    res = DisputeAgent(ledger, merchant).decide("t8", DisputeClaim("wrong_item", "not what I ordered", opened_on=date(2026, 8, 31)), fx_now=fx_now)
    assert res.recommendation == "CONTEST"
    full = res.cost_of_refund["if_full_refund"]
    assert full["refund_amount_paise"] == 94_900
    assert full["fx_delta_paise"] == round((97.2 - 94.9) * 1_000)  # 2,300 paise
    assert full["fee_burn_paise"] == 2_847 + 512
    assert full["total_paise"] == 94_900 + 3_359 + 2_300
    assert "USD 10.00" in res.customer_explanation
