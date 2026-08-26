"""Kasauti runner.

For each scenario and each repeat k: build a fresh ledger and engine from the scenario's
merchant settings, script the customer, drive the agent to checkout, then measure the
final cart with Sakshi's Stage 1 checkers against the scenario's ground truth.

Two numbers come out per agent:

  leakage_paise      what the final cart would have cost the merchant if it had been paid as-is
                     (impact found by the checkers on the cart the agent tried to pay)
  caught / missed    whether the gate decision matched the scenario's expected status

The Agent Leakage Rate is leakage per 1,000 conversations, with a range across repeats.
The guarded agent's leakage is measured on the cart that actually reached payment, after
the gate and its correction policy, so the before/after comparison is like for like.
"""
from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from sakshi.checkers import Status, aggregate, default_stage1, total_impact
from sakshi.checkers.base import CheckContext
from sakshi.checkers.llm import stage1_with_llm
from sakshi.engine import Engine
from sakshi.intent import IntentItem, IntentReceipt
from sakshi.ledger import Ledger
from sakshi.llm.provider import Provider
from sakshi.models import MerchantConfig

from .agents import Agent, GuardedAgent
from .scenario import Scenario
from .simulator import ScriptedCustomer

MAX_TURNS = 8


@dataclass
class RunResult:
    scenario_id: str
    pack: str
    agent: str
    repeat: int
    seed: int
    transcript: list[dict]
    final_cart: dict
    gate_status: str
    gate_impact_paise: int
    verdicts: list[dict]
    expected_status: str
    expected_min_impact_paise: int
    status_match: bool
    impact_ok: bool
    asked_human: bool
    leakage_paise: int
    model_calls: int
    duration_ms: int

    def as_dict(self) -> dict:
        return asdict(self)


def make_intent(sc: Scenario, txn: str) -> IntentReceipt:
    spec = sc.intent
    return IntentReceipt(
        txn=txn,
        utterance=sc.turns[0].text if sc.turns else "",
        playback=spec.get("playback") or " ".join(f"{i['qty']} x {i['name']}" for i in spec["items"]),
        items=[IntentItem(name=i["name"], qty=int(i["qty"]), sku=i.get("sku")) for i in spec["items"]],
        cap_paise=spec.get("cap_paise"),
        currency=spec.get("currency", "INR"),
        channel=spec.get("channel", "chat"),
        lang=spec.get("lang", "en"),
        mandate_ref=spec.get("mandate_ref"),
        human_present=bool(spec.get("human_present", True)),
    )


def make_engine(sc: Scenario, provider: Optional[Provider]) -> Engine:
    merchant = MerchantConfig(**{k: v for k, v in sc.merchant.items() if k in MerchantConfig.__dataclass_fields__})
    checkers = stage1_with_llm(provider) if provider is not None else default_stage1()
    return Engine(ledger=Ledger(":memory:"), merchant=merchant, checkers=checkers)


def _calls(provider: Optional[Provider]) -> int:
    if provider is None:
        return 0
    inner = getattr(provider, "inner", provider)
    calls = getattr(inner, "calls", 0)
    return len(calls) if isinstance(calls, list) else int(calls)


def run_one(sc: Scenario, agent_factory: Callable[[Engine], Agent], provider: Optional[Provider],
            repeat: int = 0, seed: int = 0) -> RunResult:
    started = time.time()
    calls_before = _calls(provider)
    engine = make_engine(sc, provider)
    agent = agent_factory(engine)
    agent.start(sc)
    txn = f"{sc.id}-r{repeat}"
    intent = make_intent(sc, txn)
    if isinstance(agent, GuardedAgent):
        agent.bind_intent(intent)
    else:
        engine.capture_intent(intent)

    customer = ScriptedCustomer(sc, seed=seed)
    transcript: list[dict] = []
    reply = None
    for _ in range(MAX_TURNS):
        msg = customer.next_message()
        if msg is None:
            break
        transcript.append({"role": "customer", "text": msg})
        reply = agent.reply(msg)
        customer.hear(reply.text)
        transcript.append({"role": "agent", "text": reply.text})
        if reply.done:
            break

    # Measure the cart that reached checkout with Sakshi's checkers (the guarded agent already
    # gated it; for a naive agent this is what the gate would have said).
    if reply is None:
        raise RuntimeError(f"{sc.id}: scenario produced no agent reply")
    if reply.gate is not None:
        gate_status, verdicts, impact = reply.gate.status, reply.gate.verdicts, reply.gate.impact_paise
    else:
        gate = engine.gate(intent, reply.cart, content=sc.content)
        gate_status, verdicts, impact = gate.status, gate.verdicts, gate.impact_paise

    expected = sc.expected
    # what leaks: for an ungated agent the whole impact; for a gated one only what was allowed through
    if reply.gate is None:
        leakage = impact
    else:
        leakage = impact if gate_status in (Status.PASS, Status.FLAG) else 0

    status_match = gate_status.value == expected.gate_status if reply.gate is None else gate_status in (Status.PASS, Status.FLAG, Status.ASK_HUMAN)
    return RunResult(
        scenario_id=sc.id, pack=sc.pack, agent=agent.name, repeat=repeat, seed=seed,
        transcript=transcript, final_cart=reply.cart.as_dict(),
        gate_status=gate_status.value, gate_impact_paise=impact,
        verdicts=[v.as_dict() for v in verdicts],
        expected_status=expected.gate_status, expected_min_impact_paise=expected.min_impact_paise,
        status_match=status_match, impact_ok=(impact >= expected.min_impact_paise) if reply.gate is None else True,
        asked_human=reply.asked_human, leakage_paise=leakage,
        model_calls=_calls(provider) - calls_before, duration_ms=int((time.time() - started) * 1000),
    )


def run_batch(scenarios: list[Scenario], agent_factory: Callable[[Engine], Agent], provider: Optional[Provider],
              k: int = 1, seed: int = 0, out_path: Optional[Path] = None) -> list[RunResult]:
    results = []
    for sc in scenarios:
        for r in range(k):
            results.append(run_one(sc, agent_factory, provider, repeat=r, seed=seed + r))
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            for res in results:
                fh.write(json.dumps(res.as_dict(), ensure_ascii=False) + "\n")
    return results


@dataclass
class PackSummary:
    pack: str
    runs: int
    status_matches: int
    false_blocks: int  # clean scenarios that did not pass
    leakage_paise: int
    asked_human: int
    model_calls: int


@dataclass
class Summary:
    agent: str
    runs: int
    conversations: int
    leakage_paise: int
    leakage_per_1000: float
    leakage_per_1000_range: tuple[float, float]  # across repeats
    status_match_rate: float
    false_block_rate: float
    packs: list[PackSummary] = field(default_factory=list)
    model_calls: int = 0

    def table(self) -> str:
        head = (f"{self.agent:<14} runs={self.runs} leakage/1000 conv = ₹{self.leakage_per_1000 / 100:,.0f} "
                f"(range ₹{self.leakage_per_1000_range[0] / 100:,.0f}–₹{self.leakage_per_1000_range[1] / 100:,.0f})  "
                f"status match {self.status_match_rate:.0%}  false blocks {self.false_block_rate:.0%}  model calls {self.model_calls}")
        rows = [head]
        for p in self.packs:
            rows.append(f"  {p.pack:<9} n={p.runs:<3} matched={p.status_matches:<3} false_block={p.false_blocks:<2} "
                        f"leak=₹{p.leakage_paise / 100:,.0f}  ask_human={p.asked_human}  calls={p.model_calls}")
        return "\n".join(rows)


def summarize(results: list[RunResult]) -> Summary:
    if not results:
        raise ValueError("no results")
    agent = results[0].agent
    packs: dict[str, PackSummary] = {}
    for r in results:
        p = packs.setdefault(r.pack, PackSummary(r.pack, 0, 0, 0, 0, 0, 0))
        p.runs += 1
        p.status_matches += int(r.status_match)
        p.false_blocks += int(r.pack == "clean" and r.gate_status not in ("PASS", "FLAG"))
        p.leakage_paise += r.leakage_paise
        p.asked_human += int(r.asked_human)
        p.model_calls += r.model_calls
    n = len(results)
    leakage = sum(r.leakage_paise for r in results)
    per_repeat: dict[int, list[RunResult]] = {}
    for r in results:
        per_repeat.setdefault(r.repeat, []).append(r)
    per_1000 = [sum(x.leakage_paise for x in rs) / len(rs) * 1000 for rs in per_repeat.values()]
    clean = [r for r in results if r.pack == "clean"]
    return Summary(
        agent=agent, runs=n, conversations=n, leakage_paise=leakage,
        leakage_per_1000=leakage / n * 1000,
        leakage_per_1000_range=(min(per_1000), max(per_1000)),
        status_match_rate=sum(r.status_match for r in results) / n,
        false_block_rate=(sum(1 for r in clean if r.gate_status not in ("PASS", "FLAG")) / len(clean)) if clean else 0.0,
        packs=sorted(packs.values(), key=lambda p: p.pack),
        model_calls=sum(r.model_calls for r in results),
    )


def stdev_or_zero(values: list[float]) -> float:
    return statistics.pstdev(values) if len(values) > 1 else 0.0
