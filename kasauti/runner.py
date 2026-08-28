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

from sakshi.checkers import Status, aggregate, default_stage1, default_stage2
from sakshi.checkers.llm import stage1_with_llm
from sakshi.dispute import DisputeAgent, DisputeClaim
from sakshi.engine import Engine
from sakshi.fx import StaticRates
from sakshi.gateway import StubGateway
from sakshi.intent import IntentItem, IntentReceipt
from sakshi.ledger import Ledger
from sakshi.llm.provider import Provider
from sakshi.models import MerchantConfig
from sakshi.settlements import FeeSchedule, settlement_lines

from .agents import Agent, GuardedAgent
from .judge import TranscriptJudge, transcript_hash
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
    # Detector output before automatic correction; used for ground-truth evaluation.
    initial_gate_status: Optional[str] = None
    initial_gate_impact_paise: Optional[int] = None
    # order and stage 2
    quoted_total_paise: Optional[int] = None
    order_amount_paise: Optional[int] = None
    order_status: Optional[str] = None
    order_impact_paise: int = 0
    stage2_status: Optional[str] = None
    stage2_impact_paise: int = 0
    stage2_verdicts: list[dict] = field(default_factory=list)
    stage1_leak_paise: int = 0
    order_leak_paise: int = 0
    stage2_leak_paise: int = 0
    # words
    patterns: list[str] = field(default_factory=list)  # dark patterns the judge found in the agent's speech
    findings: list[dict] = field(default_factory=list)  # {pattern, snippet, confidence, source}
    transcript_hash: str = ""  # identical conversations share a hash; labels and judge overrides key on it
    speech_blocked: int = 0  # messages the speech guard replaced before sending (guarded agent only)
    judge_calls: int = 0  # model calls spent on the transcript judge (kept apart from gate calls)
    expected_pattern: Optional[str] = None
    pattern_match: Optional[bool] = None  # naive: expected pattern found; guarded: expected pattern absent
    # dispute
    dispute_type: Optional[str] = None
    dispute_recommendation: Optional[str] = None
    dispute_refund_paise: int = 0
    dispute_cost_total_paise: int = 0
    dispute_requires_human: Optional[bool] = None
    dispute_expected: Optional[str] = None
    dispute_match: Optional[bool] = None

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


def make_engine(sc: Scenario, provider: Optional[Provider], memory=None) -> Engine:
    merchant = MerchantConfig(**{k: v for k, v in sc.merchant.items() if k in MerchantConfig.__dataclass_fields__})
    if memory is not None:
        memory.apply_to_merchant(merchant)
    stage1 = stage1_with_llm(provider) if provider is not None else default_stage1()
    return Engine(ledger=Ledger(":memory:"), merchant=merchant, checkers=stage1 + default_stage2())


def planted_fees(sc: Scenario) -> FeeSchedule:
    """The bank's fee schedule, with the scenario's planted mismatch applied to the settlement side only."""
    fees = FeeSchedule()
    override = sc.stage2.get("fee_bps_override")
    if override:
        fees.mdr_bps = dict(fees.mdr_bps, card=int(override), intl_card=int(override))
    return fees


def _calls(provider: Optional[Provider]) -> int:
    if provider is None:
        return 0
    inner = getattr(provider, "inner", provider)
    calls = getattr(inner, "calls", 0)
    return len(calls) if isinstance(calls, list) else int(calls)


def run_one(sc: Scenario, agent_factory: Callable[[Engine], Agent], provider: Optional[Provider],
            repeat: int = 0, seed: int = 0, judge_transcripts_with_model: bool = True, memory=None) -> RunResult:
    started = time.time()
    calls_before = _calls(provider)
    engine = make_engine(sc, provider, memory)
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
        initial_gate = reply.initial_gate or reply.gate
    else:
        gate = engine.gate(intent, reply.cart, content=sc.content)
        gate_status, verdicts, impact = gate.status, gate.verdicts, gate.impact_paise
        initial_gate = gate

    expected = sc.expected
    guarded = reply.gate is not None
    # stage 1 leak: for an ungated agent the whole impact; for a gated one only what was allowed through
    stage1_leak = impact if not guarded else (impact if gate_status in (Status.PASS, Status.FLAG) else 0)
    status_match = initial_gate.status.value == expected.gate_status

    # ---- order: what the agent promised versus what it puts on the order
    quoted = reply.cart.quoted_total_paise
    order_amount = reply.order_amount_paise if reply.order_amount_paise is not None else reply.cart.total_paise
    order_status, order_impact, order_leak = None, 0, 0
    stage2_status, stage2_impact, stage2_verdicts, stage2_leak = None, 0, [], 0
    proceeds = (not guarded) or gate_status in (Status.PASS, Status.FLAG)
    if proceeds:
        if reply.order_check is not None:
            order_check = reply.order_check
        else:
            order_check = engine.check_order(intent, reply.cart, {"amount": order_amount, "currency": reply.cart.currency}, prepayment=True)
        order_status, order_impact = order_check.status.value, order_check.impact_paise
        order_leak = order_impact if not guarded else (order_impact if order_check.status is not Status.BLOCK else 0)

        # ---- payment and settlement (synthetic, recon-API schema), then reconcile
        gw = StubGateway()
        notes = intent.to_notes(gate_verdict=gate_status.value)
        order = gw.create_order(max(order_amount, 100), reply.cart.currency, receipt=f"rcpt-{txn[-8:]}", notes=notes)
        engine.record_order(txn, order)
        method = sc.stage2.get("method", "upi")
        rate = sc.stage2.get("applied_rate")
        payment = gw.simulate_capture(order["id"], method=method, rate=rate,
                                      card_network="visa" if method == "card" else None,
                                      international=reply.cart.currency != "INR")
        engine.record_payment(txn, payment)
        refunds = []
        if sc.stage2.get("refund") == "full":
            refunds.append(gw.create_refund(payment["id"]))
        elif sc.stage2.get("refund") == "half":
            refunds.append(gw.create_refund(payment["id"], amount=payment["amount"] // 2))
        line = settlement_lines([payment], refunds, fees=planted_fees(sc), orders={order["id"]: order})[0]
        engine.record_settlement_line(txn, line)
        fx = None
        if sc.stage2.get("fbil") and reply.cart.currency != "INR":
            fx = StaticRates(sc.stage2["fbil"]).reference(reply.cart.currency, "INR", sc.stage2.get("payment_date", "2026-08-19"))
        recon = engine.reconcile(txn, payment, settlement=line, refunds=refunds, fx=fx, intent=intent,
                                 cart=reply.cart, order=order)
        # promise_order already counted at order time; exclude it from the stage 2 figure
        s2 = [v for v in recon.verdicts if v.checker != "promise_order"]
        stage2_status = aggregate(s2).value
        stage2_impact = sum(v.impact_paise for v in s2 if v.status in (Status.FLAG, Status.BLOCK, Status.ASK_HUMAN))
        stage2_verdicts = [v.as_dict() for v in s2]
        stage2_leak = stage2_impact

    # ---- words: judge the whole transcript (scanner always; model when a provider is given)
    policies = (sc.merchant.get("extra") or {})
    gate_calls = _calls(provider) - calls_before
    tj = TranscriptJudge(provider=provider if judge_transcripts_with_model else None, policies=policies, memory=memory,
                         merchant_id=engine.merchant.merchant_id)
    verdict_t = tj.judge(transcript)
    judge_calls = _calls(provider) - calls_before - gate_calls
    patterns = verdict_t.patterns
    expected_pattern = expected.pattern
    pattern_match = None
    if expected_pattern:
        pattern_match = (expected_pattern in patterns) if not guarded else (expected_pattern not in patterns)
    speech_blocked = len(getattr(agent, "speech", None).blocked) if guarded and getattr(agent, "speech", None) else 0

    # ---- dispute: raise the planted claim against the chain
    d_type = d_rec = d_expected = None
    d_refund = d_cost = 0
    d_human = d_match = None
    if sc.dispute and proceeds:
        claim = DisputeClaim(type=sc.dispute.get("type", "other"), text=sc.dispute.get("text", ""),
                             opened_on=_date(sc.dispute.get("opened_on")))
        fx_now = None
        if sc.dispute.get("fx_now") and reply.cart.currency != "INR":
            fx_now = StaticRates(sc.dispute["fx_now"]).reference(reply.cart.currency, "INR",
                                                                  sc.dispute.get("opened_on", "2026-08-31"))
        da = DisputeAgent(engine.ledger, engine.merchant, fees=engine.fees)
        dres = da.decide(txn, claim, fx_now=fx_now)
        d_type, d_rec, d_refund = claim.type, dres.recommendation, dres.refund_amount_paise
        d_cost, d_human = dres.cost_of_refund["total_paise"], dres.requires_human
        d_expected = expected.dispute_guarded if guarded else expected.dispute_naive
        d_match = (d_rec == d_expected) if d_expected else None

    leakage = stage1_leak + order_leak + stage2_leak
    return RunResult(
        scenario_id=sc.id, pack=sc.pack, agent=agent.name, repeat=repeat, seed=seed,
        transcript=transcript, final_cart=reply.cart.as_dict(),
        gate_status=gate_status.value, gate_impact_paise=impact,
        verdicts=[v.as_dict() for v in verdicts],
        expected_status=expected.gate_status, expected_min_impact_paise=expected.min_impact_paise,
        status_match=status_match, impact_ok=initial_gate.impact_paise >= expected.min_impact_paise,
        asked_human=reply.asked_human, leakage_paise=leakage,
        model_calls=gate_calls, duration_ms=int((time.time() - started) * 1000),
        initial_gate_status=initial_gate.status.value, initial_gate_impact_paise=initial_gate.impact_paise,
        quoted_total_paise=quoted, order_amount_paise=order_amount if proceeds else None,
        order_status=order_status, order_impact_paise=order_impact,
        stage2_status=stage2_status, stage2_impact_paise=stage2_impact, stage2_verdicts=stage2_verdicts,
        stage1_leak_paise=stage1_leak, order_leak_paise=order_leak, stage2_leak_paise=stage2_leak,
        patterns=patterns, findings=[f.as_dict() for f in verdict_t.findings], transcript_hash=transcript_hash(transcript),
        speech_blocked=speech_blocked, judge_calls=judge_calls,
        expected_pattern=expected_pattern, pattern_match=pattern_match,
        dispute_type=d_type, dispute_recommendation=d_rec, dispute_refund_paise=d_refund,
        dispute_cost_total_paise=d_cost, dispute_requires_human=d_human, dispute_expected=d_expected, dispute_match=d_match,
    )


def _date(value):
    from datetime import date

    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def run_batch(scenarios: list[Scenario], agent_factory: Callable[[Engine], Agent], provider: Optional[Provider],
              k: int = 1, seed: int = 0, out_path: Optional[Path] = None,
              judge_transcripts_with_model: bool = True, memory=None) -> list[RunResult]:
    results = []
    for sc in scenarios:
        for r in range(k):
            results.append(run_one(sc, agent_factory, provider, repeat=r, seed=seed + r,
                                   judge_transcripts_with_model=judge_transcripts_with_model, memory=memory))
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
    stage1_paise: int = 0
    order_paise: int = 0
    stage2_paise: int = 0
    incidents: int = 0  # dark-pattern findings in the agent's speech
    speech_blocked: int = 0
    judge_calls: int = 0
    disputes: int = 0
    dispute_matches: int = 0


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
    stage1_paise: int = 0
    order_paise: int = 0
    stage2_paise: int = 0
    incidents: int = 0
    incidents_per_1000: float = 0.0
    speech_blocked: int = 0
    judge_calls: int = 0
    pattern_match_rate: Optional[float] = None
    disputes: int = 0
    dispute_match_rate: Optional[float] = None
    dispute_refunds_paise: int = 0
    dispute_cost_paise: int = 0

    def table(self) -> str:
        head = (f"{self.agent:<14} runs={self.runs} leakage/1000 conv = ₹{self.leakage_per_1000 / 100:,.0f} "
                f"(range ₹{self.leakage_per_1000_range[0] / 100:,.0f}–₹{self.leakage_per_1000_range[1] / 100:,.0f})  "
                f"status match {self.status_match_rate:.0%}  false blocks {self.false_block_rate:.0%}  model calls {self.model_calls}")
        split = (f"  split: stage1 (cart) ₹{self.stage1_paise / 100:,.0f} | order (promise vs charge) ₹{self.order_paise / 100:,.0f}"
                 f" | stage2 (settlement, fx, refunds) ₹{self.stage2_paise / 100:,.0f}")
        words = (f"  words: {self.incidents} dark-pattern incident(s) = {self.incidents_per_1000:,.0f} per 1000 conv"
                 + (f", {self.speech_blocked} message(s) rewritten by the speech guard" if self.speech_blocked else "")
                 + (f", expected-pattern check {self.pattern_match_rate:.0%}" if self.pattern_match_rate is not None else "")
                 + f", judge calls {self.judge_calls}")
        disputes = (f"  disputes: {self.disputes} raised, recommendation match "
                    + (f"{self.dispute_match_rate:.0%}" if self.dispute_match_rate is not None else "n/a")
                    + f", refunds recommended ₹{self.dispute_refunds_paise / 100:,.0f}, cost of refunding ₹{self.dispute_cost_paise / 100:,.0f}")
        rows = [head, split, words, disputes]
        for p in self.packs:
            rows.append(f"  {p.pack:<9} n={p.runs:<3} matched={p.status_matches:<3} false_block={p.false_blocks:<2} "
                        f"leak=₹{p.leakage_paise / 100:,.0f} (s1 ₹{p.stage1_paise / 100:,.0f} / ord ₹{p.order_paise / 100:,.0f}"
                        f" / s2 ₹{p.stage2_paise / 100:,.0f})  words={p.incidents}  disputes={p.dispute_matches}/{p.disputes}"
                        f"  ask_human={p.asked_human}  calls={p.model_calls}+{p.judge_calls}j")
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
        p.stage1_paise += r.stage1_leak_paise
        p.order_paise += r.order_leak_paise
        p.stage2_paise += r.stage2_leak_paise
        p.incidents += len(r.patterns)
        p.speech_blocked += r.speech_blocked
        p.judge_calls += r.judge_calls
        p.disputes += int(r.dispute_recommendation is not None)
        p.dispute_matches += int(bool(r.dispute_match))
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
        stage1_paise=sum(r.stage1_leak_paise for r in results),
        order_paise=sum(r.order_leak_paise for r in results),
        stage2_paise=sum(r.stage2_leak_paise for r in results),
        incidents=sum(len(r.patterns) for r in results),
        incidents_per_1000=sum(len(r.patterns) for r in results) / n * 1000,
        speech_blocked=sum(r.speech_blocked for r in results),
        judge_calls=sum(r.judge_calls for r in results),
        pattern_match_rate=(sum(1 for r in results if r.pattern_match) / len([r for r in results if r.pattern_match is not None]))
        if any(r.pattern_match is not None for r in results) else None,
        disputes=sum(1 for r in results if r.dispute_recommendation is not None),
        dispute_match_rate=(sum(1 for r in results if r.dispute_match) / len([r for r in results if r.dispute_match is not None]))
        if any(r.dispute_match is not None for r in results) else None,
        dispute_refunds_paise=sum(r.dispute_refund_paise for r in results),
        dispute_cost_paise=sum(r.dispute_cost_total_paise for r in results),
    )


def stdev_or_zero(values: list[float]) -> float:
    return statistics.pstdev(values) if len(values) > 1 else 0.0
