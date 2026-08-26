"""The one primitive: a checker compares a claim with an observation and issues a verdict.

Deterministic where money is arithmetic (caps, quantities, fees, rates).
LLM-backed where language is involved (semantic substitution, injection judgement,
dark patterns). Every verdict carries a rupee impact so the Agent Leakage Rate
can be summed across stages.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable

from ..intent import IntentReceipt
from ..models import Cart, MerchantConfig


class Status(str, Enum):
    PASS = "PASS"
    FLAG = "FLAG"  # worth recording, does not stop the payment
    ASK_HUMAN = "ASK_HUMAN"  # stop and ask (CERT-In style human-in-the-loop)
    BLOCK = "BLOCK"  # stop
    SKIP = "SKIP"  # checker had nothing to check


SEVERITY = {Status.SKIP: 0, Status.PASS: 1, Status.FLAG: 2, Status.ASK_HUMAN: 3, Status.BLOCK: 4}


@dataclass
class Verdict:
    checker: str
    stage: int
    status: Status
    reason: str
    impact_paise: int = 0  # positive = money that would have leaked or is exposed
    confidence: float = 1.0  # 1.0 deterministic; lower for LLM-derived judgements
    evidence: dict = field(default_factory=dict)
    basis: Optional[str] = None  # checkers measuring the same rupees share a basis (no double counting)

    def as_dict(self) -> dict:
        return {
            "checker": self.checker,
            "stage": self.stage,
            "status": self.status.value,
            "reason": self.reason,
            "impact_paise": self.impact_paise,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "basis": self.basis or self.checker,
        }


@dataclass
class CheckContext:
    """Everything a checker may look at. Stages fill in more fields as the transaction moves."""

    merchant: MerchantConfig
    intent: Optional[IntentReceipt] = None
    cart: Optional[Cart] = None
    order: Optional[dict] = None
    payment: Optional[dict] = None
    settlement: Optional[dict] = None
    dispute: Optional[dict] = None
    content: list[str] = field(default_factory=list)  # text the agent read: product pages, tool outputs
    extras: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Checker(Protocol):
    name: str
    stage: int

    def check(self, ctx: CheckContext) -> Verdict: ...


def aggregate(verdicts: list[Verdict]) -> Status:
    """Worst status wins. SKIP-only means PASS (nothing to check is not a failure)."""
    worst = Status.SKIP
    for v in verdicts:
        if SEVERITY[v.status] > SEVERITY[worst]:
            worst = v.status
    return Status.PASS if worst == Status.SKIP else worst


def total_impact(verdicts: list[Verdict]) -> int:
    """Rupee impact of a set of verdicts. Verdicts that share a ``basis`` measure the same
    money from different angles (a cart over its cap is over the cap because of the extra
    items), so within a basis the largest impact is taken, and bases are summed."""
    by_basis: dict[str, int] = {}
    for v in verdicts:
        if v.status not in (Status.FLAG, Status.ASK_HUMAN, Status.BLOCK):
            continue
        key = v.basis or v.checker
        by_basis[key] = max(by_basis.get(key, 0), v.impact_paise)
    return sum(by_basis.values())
