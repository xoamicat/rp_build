from datetime import date

import pytest

from sakshi.fx import FbilClient, FxPromiseEnvelope, StaticRates, confidence_for


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


def test_fx_promise_prices_payment_and_later_dispute_date_exposure_in_paise():
    envelope = FxPromiseEnvelope(
        buyer_currency="USD", foreign_amount_minor=1_000, minor_per_unit=100,
        displayed_rate=96.00, reference_rate=95.68, reference_provider="FBIL",
        reference_source_ref="fbil-usdinr-2026-08-20",
        reference_date="2026-08-20", valid_through="2026-08-21", allowed_spread_bps=150,
    )
    result = envelope.assess(payment_rate=95.70, payment_date="2026-08-21", dispute_rate=97.20,
                             dispute_date="2026-09-02", payment_source_ref="pay_pay_123",
                             dispute_source_ref="dispute_disp_123")

    assert result.quote_status == "ALLOW"
    assert result.capture_status == "PASS"
    assert result.payment_value_paise == 95_700
    assert result.dispute_value_paise == 97_200
    assert result.dispute_fx_delta_paise == 1_500
    assert result.dispute_reserve_paise == 1_500
    assert result.dispute_source_ref == "dispute_disp_123"


def test_fx_promise_blocks_an_excessive_displayed_quote_and_marks_an_expired_quote():
    envelope = FxPromiseEnvelope(
        buyer_currency="USD", foreign_amount_minor=1_000, minor_per_unit=100,
        displayed_rate=100.00, reference_rate=95.68, reference_provider="FBIL",
        reference_source_ref="fbil-usdinr-2026-08-20",
        reference_date="2026-08-20", valid_through="2026-08-20", allowed_spread_bps=150,
    )
    result = envelope.assess(payment_rate=95.70, payment_date="2026-08-21", payment_source_ref="pay_pay_123")

    assert result.quote_status == "BLOCK"
    assert result.quote_expired is True
