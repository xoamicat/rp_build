"""Calibration of the transcript judge against hand labels.

Labels live in kasauti/labels/<labeler>.json as {"labeler": name, "labels": {transcript_hash:
{"patterns": [...], "scenario_ids": [...]}}}. Runs live in data/runs/*.jsonl with per-conversation
findings tagged by source (scanner or judge).

Reported per pattern and overall: precision, recall and F1 for the scanner alone, the model
judge alone, and the merged verdict. Two labelers give inter-rater agreement (Cohen's kappa on
"any pattern present", plus simple agreement per pattern). Pattern families collapse labels that
lawyers split but readers merge: drip pricing and basket sneaking both mean "something was added
to the bill without being said", so a judge that picks the sibling is counted right at family level.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from sakshi.speech import PATTERN_DEFINITIONS

FAMILIES = {
    "silent_addition": {"drip_pricing", "basket_sneaking"},
    "pressure": {"false_urgency", "confirm_shaming", "nagging"},
    "false_promise": {"misrepresentation", "bait_and_switch"},
}

LABEL_DIR = Path(__file__).parent / "labels"


def family_of(pattern: str) -> str:
    for fam, members in FAMILIES.items():
        if pattern in members:
            return fam
    return pattern


@dataclass
class LabelSet:
    labeler: str
    labels: dict  # transcript_hash -> {"patterns": [...], "scenario_ids": [...]}

    @classmethod
    def load(cls, path: Path) -> "LabelSet":
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return cls(d.get("labeler", path.stem), d.get("labels", {}))

    def patterns(self, h: str) -> Optional[set]:
        entry = self.labels.get(h)
        return set(entry.get("patterns", [])) if entry is not None else None

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"labeler": self.labeler, "labels": self.labels}, fh, ensure_ascii=False, indent=2)


def load_runs(paths: Iterable[Path]) -> list[dict]:
    rows = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            rows.extend(json.loads(line) for line in fh if line.strip())
    return rows


def unique_conversations(rows: list[dict]) -> dict[str, dict]:
    """One entry per transcript hash: transcript, scenario ids, and findings by source."""
    out: dict[str, dict] = {}
    for r in rows:
        h = r.get("transcript_hash")
        if not h:
            continue
        e = out.setdefault(h, {"transcript": r["transcript"], "scenario_ids": [], "agents": set(),
                               "scanner": set(), "judge": set(), "merged": set()})
        e["scenario_ids"].append(r["scenario_id"])
        e["agents"].add(r["agent"])
        for f in r.get("findings", []):
            src = "judge" if f.get("source") == "judge" else "scanner"
            e[src].add(f["pattern"])
            e["merged"].add(f["pattern"])
    return out


@dataclass
class PRF:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> Optional[float]:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else None

    @property
    def recall(self) -> Optional[float]:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else None

    @property
    def f1(self) -> Optional[float]:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if p and r else (0.0 if (p is not None and r is not None) else None)


def _score(pred: set, truth: set, by_family: bool) -> tuple[set, set, set]:
    if by_family:
        pred, truth = {family_of(p) for p in pred}, {family_of(p) for p in truth}
    return pred & truth, pred - truth, truth - pred


@dataclass
class Calibration:
    labeler: str
    conversations: int
    labeled: int
    overall: dict = field(default_factory=dict)  # source -> {"strict": PRF, "family": PRF}
    per_pattern: dict = field(default_factory=dict)  # pattern -> source -> PRF (strict)
    disagreements: list[dict] = field(default_factory=list)

    def table(self) -> str:
        rows = [f"judge calibration vs labels by {self.labeler}: {self.labeled} of {self.conversations} unique conversations labeled"]
        for source in ("scanner", "judge", "merged"):
            for level in ("strict", "family"):
                prf = self.overall[source][level]
                rows.append(f"  {source:<8} {level:<7} precision {_pct(prf.precision)} recall {_pct(prf.recall)} f1 {_pct(prf.f1)} "
                            f"(tp {prf.tp} fp {prf.fp} fn {prf.fn})")
        for pattern, by_src in sorted(self.per_pattern.items()):
            m = by_src["merged"]
            if m.tp + m.fp + m.fn:
                rows.append(f"  {pattern:<18} merged precision {_pct(m.precision)} recall {_pct(m.recall)} (tp {m.tp} fp {m.fp} fn {m.fn})")
        if self.disagreements:
            rows.append("  disagreements (judge vs human):")
            for d in self.disagreements[:12]:
                rows.append(f"    {d['scenario_ids'][0]:<30} judge {sorted(d['judge'])} human {sorted(d['human'])}")
        return "\n".join(rows)


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def calibrate(rows: list[dict], labels: LabelSet) -> Calibration:
    convs = unique_conversations(rows)
    cal = Calibration(labels.labeler, len(convs), 0)
    cal.overall = {s: {"strict": PRF(), "family": PRF()} for s in ("scanner", "judge", "merged")}
    for h, e in convs.items():
        truth = labels.patterns(h)
        if truth is None:
            continue
        cal.labeled += 1
        for source in ("scanner", "judge", "merged"):
            pred = e[source]
            for level, fam in (("strict", False), ("family", True)):
                tp, fp, fn = _score(pred, truth, fam)
                prf = cal.overall[source][level]
                prf.tp += len(tp); prf.fp += len(fp); prf.fn += len(fn)
            for pattern in set(pred) | truth:
                prf = cal.per_pattern.setdefault(pattern, {s: PRF() for s in ("scanner", "judge", "merged")})[source]
                if pattern in pred and pattern in truth:
                    prf.tp += 1
                elif pattern in pred:
                    prf.fp += 1
                else:
                    prf.fn += 1
        if e["merged"] != truth:
            cal.disagreements.append({"hash": h, "scenario_ids": e["scenario_ids"], "judge": e["merged"], "human": truth})
    return cal


@dataclass
class Agreement:
    labeler_a: str
    labeler_b: str
    shared: int
    kappa_any: Optional[float]
    agreement_any: Optional[float]
    per_pattern_agreement: dict

    def table(self) -> str:
        rows = [f"inter-rater agreement {self.labeler_a} vs {self.labeler_b}: {self.shared} shared conversations"]
        rows.append(f"  any-pattern agreement {_pct(self.agreement_any)}  Cohen's kappa {('n/a' if self.kappa_any is None else f'{self.kappa_any:.2f}')}")
        for p, a in sorted(self.per_pattern_agreement.items()):
            rows.append(f"  {p:<18} agreement {_pct(a)}")
        return "\n".join(rows)


def agreement(a: LabelSet, b: LabelSet) -> Agreement:
    shared = sorted(set(a.labels) & set(b.labels))
    if not shared:
        return Agreement(a.labeler, b.labeler, 0, None, None, {})
    xa = [1 if a.patterns(h) else 0 for h in shared]
    xb = [1 if b.patterns(h) else 0 for h in shared]
    n = len(shared)
    po = sum(1 for i in range(n) if xa[i] == xb[i]) / n
    pa1, pb1 = sum(xa) / n, sum(xb) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    kappa = None if pe == 1 else (po - pe) / (1 - pe)
    per: dict = {}
    for p in PATTERN_DEFINITIONS:
        agree = sum(1 for h in shared if (p in a.patterns(h)) == (p in b.patterns(h)))
        if any(p in a.patterns(h) or p in b.patterns(h) for h in shared):
            per[p] = agree / n
    return Agreement(a.labeler, b.labeler, n, kappa, po, per)


def label_files(directory: Path = LABEL_DIR) -> list[Path]:
    return sorted(Path(directory).glob("*.json"))
