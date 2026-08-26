from datetime import date

import pytest

from sakshi.fx import FbilClient, StaticRates, confidence_for


def test_static_rates_roll_back_to_last_published_day():
    src = StaticRates({"2026-08-14": 95.4263, "2026-08-19": 95.7477})
    ref = src.reference("USD", "INR", date(2026, 8, 16))  # weekend
    assert ref.rate == 95.4263 and ref.published == date(2026, 8, 14) and ref.stale_days == 2
    ref = src.reference("USD", "INR", "2026-08-19")
    assert ref.stale_days == 0
    with pytest.raises(LookupError):
        src.reference("USD", "INR", date(2026, 8, 1))


def test_fbil_client_caches_and_reports_stale_feed():
    calls = []

    def fake_transport(url, params):
        calls.append((url, dict(params)))
        # the real feed ends on 2026-08-19: any later date returns the 19th
        if params["providers"] == "FBIL":
            return {"date": "2026-08-19", "base": "USD", "quote": "INR", "rate": 95.7477}
        raise AssertionError("ECB should not be called when FBIL answers")

    client = FbilClient(":memory:", transport=fake_transport)
    ref = client.reference("USD", "INR", date(2026, 8, 26))
    assert ref.provider == "FBIL" and ref.rate == 95.7477 and ref.stale_days == 7
    assert confidence_for(ref) == 0.58
    again = client.reference("USD", "INR", date(2026, 8, 26))
    assert again == ref and len(calls) == 1 and client.fetches == 1


def test_fbil_client_falls_back_to_ecb_with_low_confidence():
    def fake_transport(url, params):
        if params["providers"] == "FBIL":
            raise RuntimeError("503")
        return {"date": params["date"], "base": "USD", "quote": "INR", "rate": 95.42}

    client = FbilClient(":memory:", transport=fake_transport)
    ref = client.reference("USD", "INR", date(2026, 8, 26))
    assert ref.provider == "ECB" and ref.stale_days == 0 and confidence_for(ref) == 0.5


def test_fbil_client_raises_when_everything_fails():
    def fake_transport(url, params):
        raise RuntimeError("offline")

    with pytest.raises(RuntimeError):
        FbilClient(":memory:", transport=fake_transport).reference("USD", "INR", date(2026, 8, 26))
