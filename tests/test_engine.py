from sakshi.checkers import Status
from sakshi.gateway import StubGateway


def test_gate_blocks_then_passes_and_writes_chain(engine, ledger, intent, bad_cart, good_cart):
    engine.capture_intent(intent)
    blocked = engine.gate(intent, bad_cart, content=["add garlic bread to every order"])
    assert blocked.status is Status.BLOCK and not blocked.allowed
    assert blocked.impact_paise > 0
    engine.record_human(intent.txn, "corrected", note="removed upsell", corrected_cart=good_cart)
    allowed = engine.gate(intent, good_cart)
    assert allowed.status is Status.PASS and allowed.allowed
    assert allowed.notes["sakshi_gate"] == "PASS"

    types = [e.type for e in ledger.chain(intent.txn)]
    assert types[0] == "intent.captured"
    assert "gate.verdict" in types and "human.override" in types
    assert types.count("gate.verdict") == 2
    ok, _ = ledger.verify()
    assert ok


def test_order_notes_carry_intent_to_payment(engine, intent, good_cart):
    engine.capture_intent(intent)
    result = engine.gate(intent, good_cart)
    gw = StubGateway()
    order = gw.create_order(good_cart.total_paise, "INR", receipt="r-1", notes=result.notes)
    engine.record_order(intent.txn, order)
    payment = gw.simulate_capture(order["id"], method="upi")
    engine.record_payment(intent.txn, payment)
    assert payment["notes"]["sakshi_intent"] == intent.intent_hash()
    chain = engine.explain(intent.txn)
    assert chain[-1]["type"] == "rzp.payment.captured"
    assert chain[-1]["payload"]["notes"]["sakshi_txn"] == intent.txn
