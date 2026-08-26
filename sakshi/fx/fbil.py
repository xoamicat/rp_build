"""FX reference rates.

India's official benchmark is FBIL's daily reference rate. Frankfurter's v2 API republishes it
(``providers=FBIL``) and accepts a ``date``; on a holiday or weekend it returns the last
published day, and the feed itself can lag the calendar by days. Every lookup therefore
reports the date it asked for, the date it got, and the gap, and checkers lower their
confidence as the gap grows. ECB also publishes USD/INR and is used as a labelled fallback,
never silently.

Rates are cached in SQLite so repeated runs and demos never hit the network twice.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Optional, Protocol

import httpx

FRANKFURTER_V2 = "https://api.frankfurter.dev/v2/rate/{base}/{quote}"


@dataclass(frozen=True)
class RateRef:
    base: str
    quote: str
    rate: float  # quote per 1 base (INR per USD)
    requested: date
    published: date
    provider: str  # FBIL | ECB | static

    @property
    def stale_days(self) -> int:
        return (self.requested - self.published).days

    def as_dict(self) -> dict:
        return {"base": self.base, "quote": self.quote, "rate": self.rate, "requested": self.requested.isoformat(),
                "published": self.published.isoformat(), "provider": self.provider, "stale_days": self.stale_days}


class RateSource(Protocol):
    def reference(self, base: str, quote: str, on: date) -> RateRef: ...


def _to_date(value) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


class StaticRates:
    """Deterministic source for tests and scenario planting: {iso_date: rate}. Rolls back to the
    nearest prior date the way the real feed does."""

    def __init__(self, rates: dict, base: str = "USD", quote: str = "INR", provider: str = "static"):
        self.rates = {_to_date(k): float(v) for k, v in rates.items()}
        self.base, self.quote, self.provider = base, quote, provider

    def reference(self, base: str, quote: str, on: date) -> RateRef:
        on = _to_date(on)
        candidates = [d for d in self.rates if d <= on]
        if not candidates:
            raise LookupError(f"no {base}/{quote} rate on or before {on}")
        published = max(candidates)
        return RateRef(base, quote, self.rates[published], on, published, self.provider)


Transport = Callable[[str, dict], dict]


def _http_transport(timeout: float) -> Transport:
    def get(url: str, params: dict) -> dict:
        r = httpx.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    return get


class FbilClient:
    def __init__(self, cache_path: str = ":memory:", providers: tuple = ("FBIL", "ECB"),
                 timeout: float = 15.0, transport: Optional[Transport] = None):
        self.providers = providers
        self.transport = transport or _http_transport(timeout)
        self.conn = sqlite3.connect(cache_path, check_same_thread=False)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fx (
                base TEXT, quote TEXT, requested TEXT, provider TEXT, published TEXT, rate REAL,
                PRIMARY KEY (base, quote, requested, provider)
            )
            """
        )
        self.conn.commit()
        self.fetches = 0

    def _cached(self, base: str, quote: str, on: date) -> Optional[RateRef]:
        for provider in self.providers:
            row = self.conn.execute(
                "SELECT published, rate FROM fx WHERE base=? AND quote=? AND requested=? AND provider=?",
                (base, quote, on.isoformat(), provider),
            ).fetchone()
            if row:
                return RateRef(base, quote, row[1], on, _to_date(row[0]), provider)
        return None

    def reference(self, base: str, quote: str, on: date) -> RateRef:
        on = _to_date(on)
        hit = self._cached(base, quote, on)
        if hit:
            return hit
        errors = []
        for provider in self.providers:
            try:
                data = self.transport(FRANKFURTER_V2.format(base=base, quote=quote),
                                      {"providers": provider, "date": on.isoformat()})
                self.fetches += 1
                published, rate = _to_date(data["date"]), float(data["rate"])
            except Exception as exc:  # network, 4xx, shape
                errors.append(f"{provider}: {exc}")
                continue
            with self.conn:
                self.conn.execute("INSERT OR REPLACE INTO fx VALUES (?,?,?,?,?,?)",
                                  (base, quote, on.isoformat(), provider, published.isoformat(), rate))
            return RateRef(base, quote, rate, on, published, provider)
        raise RuntimeError("no FX reference available: " + "; ".join(errors))


def confidence_for(ref: RateRef) -> float:
    """How much a checker should trust this reference. Fresh FBIL is 1.0; a week-old FBIL is 0.6;
    ECB fallback tops out at 0.5 because it is a different benchmark."""
    conf = 1.0
    if ref.stale_days > 0:
        conf = max(0.4, 1.0 - 0.06 * ref.stale_days)
    if ref.provider != "FBIL" and ref.provider != "static":
        conf = min(conf, 0.5)
    return round(conf, 2)
