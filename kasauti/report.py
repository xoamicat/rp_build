"""The report.

Reads run files, an optional traffic mix and optional labels, and writes one markdown page:
the Agent Leakage Rate before and after the guard, its split, dark-pattern incidents, dispute
outcomes, judge calibration, the model-call budget, and what is simulated.

Two headline figures are given on purpose. The bank figure is measured on the scenario bank,
where most conversations carry a planted fault, and is a stress number. The mix-weighted figure
reweights each pack by the share of real traffic the merchant expects (kasauti/traffic_mix.json,
an assumption stated in the report), so it reads as an estimate rather than a bank artefact.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .calibrate import Agreement, Calibration
from .runner import RunResult, Summary, summarize

MIX_PATH = Path(__file__).parent / "traffic_mix.json"


def load_mix(path: Path = MIX_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    weights = d["weights"]
    total = sum(weights.values())
    return {"weights": {k: v / total for k, v in weights.items()}, "note": d.get("note", "")}


def rows_to_results(rows: list[dict]) -> list[RunResult]:
    fields = set(RunResult.__dataclass_fields__)
    return [RunResult(**{k: v for k, v in r.items() if k in fields}) for r in rows]


@dataclass
class Weighted:
    leakage_per_1000: float
    incidents_per_1000: float
    by_pack: dict  # pack -> {"weight", "n", "leak_per_conv", "incidents_per_conv"}
    missing_packs: list[str]


def weighted(results: list[RunResult], mix: dict) -> Weighted:
    by_pack: dict[str, list[RunResult]] = {}
    for r in results:
        by_pack.setdefault(r.pack, []).append(r)
    leak = inc = 0.0
    detail, missing = {}, []
    for pack, w in mix["weights"].items():
        rs = by_pack.get(pack)
        if not rs:
            missing.append(pack)
            continue
        lpc = sum(r.leakage_paise for r in rs) / len(rs)
        ipc = sum(len(r.patterns) for r in rs) / len(rs)
        leak += w * lpc
        inc += w * ipc
        detail[pack] = {"weight": w, "n": len(rs), "leak_per_conv": lpc, "incidents_per_conv": ipc}
    return Weighted(leak * 1000, inc * 1000, detail, missing)


def _rs(paise: float) -> str:
    return f"₹{paise / 100:,.0f}"


def render(naive: list[RunResult], guarded: list[RunResult], mix: Optional[dict] = None,
           calibration: Optional[Calibration] = None, agreement: Optional[Agreement] = None,
           judge_name: str = "unknown", notes: Optional[list[str]] = None) -> str:
    sn, sg = summarize(naive), summarize(guarded)
    out: list[str] = []
    out.append("# Sakshi report: Agent Leakage Rate, before and after the guard\n")
    out.append(f"Judge: `{judge_name}`. Scenarios: {len({r.scenario_id for r in naive})}. Repeats per scenario: "
               f"{max(r.repeat for r in naive) + 1}. Conversations per agent: {sn.runs}.\n")

    out.append("## Headline\n")
    out.append("| | Naive agent | Guarded agent |\n|---|---|---|")
    out.append(f"| Leakage per 1,000 conversations (bank) | {_rs(sn.leakage_per_1000)} | {_rs(sg.leakage_per_1000)} |")
    if mix:
        wn, wg = weighted(naive, mix), weighted(guarded, mix)
        out.append(f"| Leakage per 1,000 conversations (traffic-mix weighted) | {_rs(wn.leakage_per_1000)} | {_rs(wg.leakage_per_1000)} |")
        out.append(f"| Dark-pattern incidents per 1,000 (mix weighted) | {wn.incidents_per_1000:,.0f} | {wg.incidents_per_1000:,.0f} |")
    out.append(f"| Dark-pattern incidents per 1,000 (bank) | {sn.incidents_per_1000:,.0f} | {sg.incidents_per_1000:,.0f} |")
    out.append(f"| Gate decisions as expected | {sn.status_match_rate:.0%} | {sg.status_match_rate:.0%} |")
    out.append(f"| False blocks on clean conversations | {sn.false_block_rate:.0%} | {sg.false_block_rate:.0%} |")
    out.append(f"| Disputes resolved as expected | {sn.dispute_match_rate if sn.dispute_match_rate is None else f'{sn.dispute_match_rate:.0%}'} | "
               f"{sg.dispute_match_rate if sg.dispute_match_rate is None else f'{sg.dispute_match_rate:.0%}'} |")
    out.append(f"| Refunds recommended on disputed orders | {_rs(sn.dispute_refunds_paise)} | {_rs(sg.dispute_refunds_paise)} |")
    out.append("")
    out.append("The bank figure is a stress number: most conversations in the bank carry a planted fault. "
               "The mix-weighted figure applies the traffic shares below and is the one to quote as an estimate.\n")

    out.append("## Where the money leaks\n")
    out.append("| Stage | Naive | Guarded | What it means |\n|---|---|---|---|")
    out.append(f"| Cart (Stage 1) | {_rs(sn.stage1_paise)} | {_rs(sg.stage1_paise)} | Unrequested items, quantity drift, discounts over the ceiling, hijacked carts. The gate prevents these. |")
    out.append(f"| Promise vs charge (order) | {_rs(sn.order_paise)} | {_rs(sg.order_paise)} | Amount on the order above the total the agent stated. Checked before payment. |")
    out.append(f"| After payment (Stage 2) | {_rs(sn.stage2_paise)} | {_rs(sg.stage2_paise)} | Settlement fees above schedule, conversion under the FBIL reference, fee and GST burned on refunds. Found, not prevented. |")
    out.append("")
    out.append("| Pack | n | Naive leak | Guarded leak | Naive incidents | Guarded incidents | Disputes (match/raised) |\n|---|---|---|---|---|---|---|")
    packs_n = {p.pack: p for p in sn.packs}
    packs_g = {p.pack: p for p in sg.packs}
    for pack in sorted(packs_n):
        pn, pg = packs_n[pack], packs_g.get(pack)
        out.append(f"| {pack} | {pn.runs} | {_rs(pn.leakage_paise)} | {_rs(pg.leakage_paise) if pg else 'n/a'} | {pn.incidents} | "
                   f"{pg.incidents if pg else 'n/a'} | {pn.dispute_matches}/{pn.disputes} vs {pg.dispute_matches if pg else 0}/{pg.disputes if pg else 0} |")
    out.append("")

    if mix:
        out.append("## Traffic mix (assumption)\n")
        out.append("| Pack | Share of traffic | Leak per conversation (naive) | Leak per conversation (guarded) |\n|---|---|---|---|")
        for pack, d in wn.by_pack.items():
            g = wg.by_pack.get(pack, {})
            out.append(f"| {pack} | {d['weight']:.0%} | {_rs(d['leak_per_conv'])} | {_rs(g.get('leak_per_conv', 0))} |")
        if wn.missing_packs:
            out.append(f"\nPacks in the mix with no runs: {', '.join(wn.missing_packs)}.")
        out.append(f"\n{mix.get('note', '')}\n")

    out.append("## Words\n")
    out.append(f"Naive agent: {sn.incidents} dark-pattern incident(s) in {sn.runs} conversations. "
               f"Guarded agent: {sg.incidents}, with {sg.speech_blocked} message(s) rewritten by the speech guard before sending. "
               f"Expected-pattern check: naive {sn.pattern_match_rate if sn.pattern_match_rate is None else f'{sn.pattern_match_rate:.0%}'}, "
               f"guarded {sg.pattern_match_rate if sg.pattern_match_rate is None else f'{sg.pattern_match_rate:.0%}'}.\n")
    seen = set()
    for r in naive + guarded:
        for f in r.findings:
            key = (r.scenario_id, r.agent, f["pattern"], f["snippet"])
            if key in seen:
                continue
            seen.add(key)
            out.append(f"- `{r.scenario_id}` ({r.agent}): **{f['pattern']}** [{f['source']}] \"{f['snippet']}\"")
    out.append("")

    if calibration:
        out.append("## Judge calibration\n")
        out.append("```\n" + calibration.table() + "\n```\n")
    if agreement:
        out.append("```\n" + agreement.table() + "\n```\n")
    if not calibration:
        out.append("## Judge calibration\n\nNo hand labels yet. Run `python scripts/label_transcripts.py --labeler yourname` "
                   "and rerun the report.\n")

    out.append("## Model-call budget\n")
    out.append(f"Gate calls: naive {sn.model_calls}, guarded {sg.model_calls}. Judge calls: naive {sn.judge_calls}, guarded {sg.judge_calls}. "
               "Identical conversations are served from the cache; a clean cart costs zero gate calls.\n")

    out.append("## What is simulated\n")
    for n in (notes or DEFAULT_NOTES):
        out.append(f"- {n}")
    out.append("")
    return "\n".join(out)


DEFAULT_NOTES = [
    "Customers are scripted with cached paraphrase variants; no live customers and no live model on the customer side.",
    "Settlements are synthetic in the Settlement Recon API schema; Razorpay test mode does not settle.",
    "Reserve Pay mandates are represented by a reference string; the cap is enforced by Sakshi, not by a live mandate.",
    "FX references in scenarios are planted for determinism; the live FBIL client is exercised by scripts/fx_check.py.",
    "The naive agent is a deliberately bad rule agent; it exists so the baseline is reproducible.",
    "Rupee figures use placeholder fee rates from sakshi/settlements/fees.py; set your own plan's rates.",
]


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
