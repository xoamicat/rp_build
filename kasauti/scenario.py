"""Kasauti scenarios.

A scenario is one scripted customer conversation with ground truth. Three packs:

    money    : discount over ceiling, quantity drift, upsell, delegated high-value (Stage 1 checkers)
    hijack   : instruction text planted in product pages, reviews or tool outputs
    language : false urgency, nagging after a no, invented policy (judged on the transcript, drop 4)
    settle   : faults after payment: undisclosed charges, fee mismatches, off-band FX, refund burn

plus ``clean`` controls, which must pass without a single flag. Every scenario carries
``expected``: what a correct gate should decide and the minimum rupee impact it should find.
Scenarios live as JSON in kasauti/scenarios/ so they are diffable and need no extra library.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PACKS = ("money", "hijack", "language", "settle", "clean")
STATUSES = ("PASS", "FLAG", "ASK_HUMAN", "BLOCK")

SCENARIO_DIR = Path(__file__).parent / "scenarios"


@dataclass
class CatalogItem:
    sku: str
    name: str
    unit_paise: int
    description: str = ""
    keywords: list[str] = field(default_factory=list)  # words a customer might use for it, incl. Hinglish


@dataclass
class Turn:
    text: str
    variants: list[str] = field(default_factory=list)  # cached paraphrases; picked by seed at runtime
    note: str = ""  # authoring note, e.g. "hesitation: bait for false urgency"

    def pick(self, seed: int) -> str:
        options = [self.text] + [v for v in self.variants if v and v != self.text]
        return options[seed % len(options)]


@dataclass
class Expected:
    gate_status: str = "PASS"
    min_impact_paise: int = 0
    order_status: Optional[str] = None  # promise-to-order check before payment (BLOCK when a naive agent drips a fee)
    order_min_impact_paise: int = 0
    stage2_min_impact_paise: int = 0  # variance the reconcile step should find after payment
    pattern: Optional[str] = None  # language pack: the dark pattern the agent is expected to show (naive) / avoid (guarded)
    followed: Optional[bool] = None  # hijack pack: whether a naive agent is expected to follow the instruction
    note: str = ""


@dataclass
class Scenario:
    id: str
    pack: str
    title: str
    catalog: list[CatalogItem]
    turns: list[Turn]
    intent: dict  # items, cap_paise, human_present, lang, channel, mandate_ref
    merchant: dict = field(default_factory=dict)  # overrides for MerchantConfig
    offers: list[dict] = field(default_factory=list)  # [{"code": "WELCOME10", "discount_bps": 1000}]
    content: list[str] = field(default_factory=list)  # what the agent reads: product pages, reviews (may be poisoned)
    stage2: dict = field(default_factory=dict)  # planted post-payment facts: method, payment_date, applied_rate, fbil, fee_bps_override, refund
    expected: Expected = field(default_factory=Expected)
    tags: list[str] = field(default_factory=list)

    # ---------------------------------------------------------------- io
    @classmethod
    def from_dict(cls, d: dict) -> "Scenario":
        return cls(
            id=d["id"], pack=d["pack"], title=d.get("title", d["id"]),
            catalog=[CatalogItem(**c) for c in d["catalog"]],
            turns=[Turn(**t) for t in d["turns"]],
            intent=d["intent"], merchant=d.get("merchant", {}), offers=d.get("offers", []),
            content=d.get("content", []), stage2=d.get("stage2", {}),
            expected=Expected(**d.get("expected", {})), tags=d.get("tags", []),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "pack": self.pack, "title": self.title,
            "catalog": [c.__dict__ for c in self.catalog],
            "turns": [t.__dict__ for t in self.turns],
            "intent": self.intent, "merchant": self.merchant, "offers": self.offers,
            "content": self.content, "stage2": self.stage2, "expected": self.expected.__dict__, "tags": self.tags,
        }

    def validate(self) -> list[str]:
        errors = []
        if self.pack not in PACKS:
            errors.append(f"{self.id}: unknown pack {self.pack}")
        if self.expected.gate_status not in STATUSES:
            errors.append(f"{self.id}: unknown expected status {self.expected.gate_status}")
        if not self.turns:
            errors.append(f"{self.id}: no turns")
        if not self.catalog:
            errors.append(f"{self.id}: no catalog")
        if "items" not in self.intent:
            errors.append(f"{self.id}: intent.items missing")
        if self.pack == "clean" and (self.expected.gate_status != "PASS" or self.expected.min_impact_paise):
            errors.append(f"{self.id}: clean scenarios must expect PASS with zero impact")
        return errors

    def catalog_by_sku(self) -> dict[str, CatalogItem]:
        return {c.sku: c for c in self.catalog}


def load_scenarios(directory: Path = SCENARIO_DIR, pack: Optional[str] = None) -> list[Scenario]:
    scenarios = []
    for path in sorted(Path(directory).glob("*.json")):
        with open(path, encoding="utf-8") as fh:
            sc = Scenario.from_dict(json.load(fh))
        if pack is None or sc.pack == pack:
            scenarios.append(sc)
    return scenarios


def save_scenario(sc: Scenario, directory: Path = SCENARIO_DIR) -> Path:
    path = Path(directory) / f"{sc.id}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(sc.to_dict(), fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return path
