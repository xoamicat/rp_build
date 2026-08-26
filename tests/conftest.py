import pytest

from sakshi.checkers import default_stage1
from sakshi.engine import Engine
from sakshi.intent import IntentItem, IntentReceipt
from sakshi.ledger import Ledger
from sakshi.models import Cart, CartLine, MerchantConfig


@pytest.fixture
def ledger():
    return Ledger(":memory:")


@pytest.fixture
def merchant():
    return MerchantConfig(max_discount_bps=1000, hitl_threshold_paise=200_000)


@pytest.fixture
def engine(ledger, merchant):
    return Engine(ledger=ledger, merchant=merchant, checkers=default_stage1())


@pytest.fixture
def intent():
    return IntentReceipt(
        txn="txn_test1",
        utterance="do margherita, 800 ke andar",
        playback="2 margherita pizzas, total under ₹800",
        items=[IntentItem(name="margherita", qty=2, sku="PZ-MARG")],
        cap_paise=80_000,
        channel="voice",
        lang="hi-en",
        created_at=1_700_000_000.0,
    )


@pytest.fixture
def good_cart():
    return Cart(lines=[CartLine(name="Margherita Pizza", qty=2, unit_paise=32_000, sku="PZ-MARG")])


@pytest.fixture
def bad_cart():
    return Cart(lines=[
        CartLine(name="Margherita Pizza", qty=3, unit_paise=32_000, sku="PZ-MARG"),
        CartLine(name="Garlic Bread", qty=1, unit_paise=19_000, sku="SD-GARL", source="upsell"),
    ])
