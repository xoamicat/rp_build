from datetime import date

from sakshi.checkers import (
    CheckContext,
    FxQuoteChecker,
    FxRateChecker,
    PromiseOrderChecker,
    RefundBurnChecker,
    SettlementFeeChecker,
    Status,
    default_stage1,
    default_stage2,
)
from sakshi.engine import Engine
from sakshi.fx import StaticRates
from sakshi.gateway import StubGateway
from sakshi.ledger import Ledger
from sakshi.models import Cart, CartLine, MerchantConfig
from sakshi.settlements import FeeSchedule, settlement_lines

FBIL = StaticRates({"2026-08-19": 95.7477})


def _ref(on="2026-08-19"):
    return FBIL.reference("USD", "INR", on)


def test_promise_order_blocks_before_payment_and_flags_after(merchant, good_cart):
    good_cart.quoted_total_paise = 64_000
    order = {"amount": 70_000}
    pre = PromiseOrderChecker().check(CheckContext(merchant=merchant, cart=good_cart, order=order, extras={"prepayment": True}))
    assert pre.status is Status.BLOCK and pre.impact_paise == 6_000 and "drip" in pre.reason
    post = PromiseOrderChecker().check(CheckContext(merchant=merchant, cart=good_cart, order=order, extras={"prepayment": False}))
    assert post.status is Status.FLAG and post.impact_paise == 6_000
    under = PromiseOrderChecker().check(CheckContext(merchant=merchant, cart=good_cart, order={"amount": 60_000}))
    assert under.status is Status.FLAG and "undercharged" in under.reason
    ok = PromiseOrderChecker().check(CheckContext(merchant=merchant, cart=good_cart, order={"amount": 64_000}))
    assert ok.status is Status.PASS


def test_settlement_fee_checker_prices_excess_fee():
    gw = StubGateway()
    order = gw.create_order(64_000, "INR")
    pay = gw.simulate_capture(order["id"], method="card")
    good = settlement_lines([pay], fees=FeeSchedule())[0]
    ctx = CheckContext(merchant=MerchantConfig(), payment=pay, settlement=good, extras={"fees": FeeSchedule()})
    assert SettlementFeeChecker().check(ctx).status is Status.PASS

    bad = dict(good, fee=2_240, tax=403, credit=64_000 - 2_240 - 403)  # 3.5 percent instead of 2
    v = SettlementFeeChecker().check(CheckContext(merchant=MerchantConfig(), payment=pay, settlement=bad, extras={"fees": FeeSchedule()}))
    assert v.status is Status.FLAG and v.impact_paise == (2_240 + 403) - (1_280 + 230)

    short = dict(good, amount=60_000, credit=60_000 - good["fee"] - good["tax"])
    v = SettlementFeeChecker().check(CheckContext(merchant=MerchantConfig(), payment=pay, settlement=short, extras={"fees": FeeSchedule()}))
    assert v.status is Status.FLAG and "differs from payment" in v.reason


def test_fx_rate_checker_flags_off_band_and_reports_staleness():
    gw = StubGateway()
    order = gw.create_order(1_000, "USD")  # $10.00
    merchant = MerchantConfig(fx_band_bps=150)
    pay_ok = gw.simulate_capture(order["id"], method="card", rate=94.9)  # 0.9 percent under reference
    v = FxRateChecker().check(CheckContext(merchant=merchant, payment=pay_ok, extras={"fx": _ref()}))
    assert v.status is Status.PASS and v.confidence == 1.0

    order2 = gw.create_order(1_000, "USD")
    pay_bad = gw.simulate_capture(order2["id"], method="card", rate=92.0)  # 3.9 percent under
    v = FxRateChecker().check(CheckContext(merchant=merchant, payment=pay_bad, extras={"fx": _ref()}))
    assert v.status is Status.FLAG and v.impact_paise == round(95.7477 * 1_000) - 92_000
    assert v.evidence["spread_bps"] == 391

    stale = FBIL.reference("USD", "INR", date(2026, 8, 26))
    v = FxRateChecker().check(CheckContext(merchant=merchant, payment=pay_bad, extras={"fx": stale}))
    assert "7 day(s) stale" in v.reason and v.confidence < 0.7

    domestic = gw.simulate_capture(gw.create_order(64_000, "INR")["id"], method="upi")
    assert FxRateChecker().check(CheckContext(merchant=merchant, payment=domestic)).status is Status.SKIP


def test_fx_quote_checker_blocks_over_quote_and_flags_under_quote():
    merchant = MerchantConfig(fx_band_bps=150)
    cart = Cart(lines=[CartLine(name="Tee", qty=1, unit_paise=1_000)], currency="USD")  # $10.00
    cart.quoted_rate = 100.0  # 4.4 percent over 95.7477
    v = FxQuoteChecker().check(CheckContext(merchant=merchant, cart=cart, extras={"fx": _ref()}))
    assert v.status is Status.BLOCK and v.evidence["markup_bps"] == 444
    assert v.impact_paise == round((100.0 - 95.7477) * 1_000)
    cart.quoted_rate = 93.0
    v = FxQuoteChecker().check(CheckContext(merchant=merchant, cart=cart, extras={"fx": _ref()}))
    assert v.status is Status.FLAG and "absorbs" in v.reason
    cart.quoted_rate = 96.0
    assert FxQuoteChecker().check(CheckContext(merchant=merchant, cart=cart, extras={"fx": _ref()})).status is Status.PASS
    cart.quoted_rate = None
    assert FxQuoteChecker().check(CheckContext(merchant=merchant, cart=cart)).status is Status.SKIP


def test_refund_burn_checker():
    gw = StubGateway()
    pay = gw.simulate_capture(gw.create_order(64_000, "INR")["id"], method="card")
    refund = gw.create_refund(pay["id"])
    v = RefundBurnChecker().check(CheckContext(merchant=MerchantConfig(), payment=pay, extras={"refunds": [refund], "fees": FeeSchedule()}))
    assert v.status is Status.FLAG and v.impact_paise == 1_280 + 230
    assert RefundBurnChecker().check(CheckContext(merchant=MerchantConfig(), payment=pay)).status is Status.SKIP


def test_engine_reconcile_and_check_order_write_the_chain(intent, good_cart):
    engine = Engine(ledger=Ledger(":memory:"), merchant=MerchantConfig(fx_band_bps=150),
                    checkers=default_stage1() + default_stage2())
    engine.capture_intent(intent)
    gate = engine.gate(intent, good_cart)
    assert gate.status is Status.PASS
    good_cart.quoted_total_paise = good_cart.total_paise
    gw = StubGateway()
    order = gw.create_order(good_cart.total_paise + 6_000, "INR", notes=gate.notes)  # silent delivery fee
    pre = engine.check_order(intent, good_cart, order, prepayment=True)
    assert pre.status is Status.BLOCK and pre.impact_paise == 6_000

    order = gw.create_order(good_cart.total_paise, "INR", notes=gate.notes)
    assert engine.check_order(intent, good_cart, order).status is Status.PASS
    engine.record_order(intent.txn, order)
    pay = gw.simulate_capture(order["id"], method="card")
    engine.record_payment(intent.txn, pay)
    line = settlement_lines([pay], fees=engine.fees)[0]
    engine.record_settlement_line(intent.txn, line)
    refund = gw.create_refund(pay["id"], amount=32_000)
    res = engine.reconcile(intent.txn, pay, settlement=line, refunds=[refund], intent=intent, cart=good_cart, order=order)
    names = {v.checker: v for v in res.verdicts}
    assert names["promise_order"].status is Status.PASS
    assert names["settlement_fee"].status is Status.PASS
    assert names["fx_rate"].status is Status.SKIP
    assert names["refund_burn"].status is Status.FLAG and res.impact_paise == names["refund_burn"].impact_paise
    types = [e.type for e in engine.ledger.chain(intent.txn)]
    assert "order.verdict" in types and "reconcile.verdict" in types and types[-1] == "reconcile.verdict"
    assert engine.ledger.verify()[0]
