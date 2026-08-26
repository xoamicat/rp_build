from sakshi.ledger import GENESIS, Ledger


def test_chain_links_and_verifies(ledger):
    a = ledger.append("t1", "intent.captured", "customer", {"x": 1})
    b = ledger.append("t1", "cart.assembled", "agent", {"y": [1, 2]})
    c = ledger.append("t2", "gate.verdict", "sakshi", {"status": "PASS"})
    assert a.prev_hash == GENESIS
    assert b.prev_hash == a.hash and c.prev_hash == b.hash
    ok, bad = ledger.verify()
    assert ok and bad is None
    assert [e.type for e in ledger.chain("t1")] == ["intent.captured", "cart.assembled"]


def test_tamper_is_detected(ledger):
    ledger.append("t1", "intent.captured", "customer", {"cap": 800})
    ledger.append("t1", "gate.verdict", "sakshi", {"status": "PASS"})
    ledger.conn.execute("UPDATE events SET payload = ? WHERE seq = 1", ('{"cap":8000}',))
    ledger.conn.commit()
    ok, bad = ledger.verify()
    assert not ok and bad == 1


def test_delete_is_detected(ledger):
    ledger.append("t1", "a", "x", {})
    ledger.append("t1", "b", "x", {})
    ledger.append("t1", "c", "x", {})
    ledger.conn.execute("DELETE FROM events WHERE seq = 2")
    ledger.conn.commit()
    ok, bad = ledger.verify()
    assert not ok and bad == 3


def test_hash_is_deterministic():
    h1 = Ledger.compute_hash(GENESIS, 1.0, "t", "type", "actor", {"b": 1, "a": [1, 2]})
    h2 = Ledger.compute_hash(GENESIS, 1.0, "t", "type", "actor", {"a": [1, 2], "b": 1})
    assert h1 == h2
