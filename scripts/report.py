"""Build the report from the last runs.

    python scripts/report.py                      # data/runs/*.jsonl + traffic mix + any labels -> data/reports/report.md
    python scripts/report.py --judge gemini-3.1-flash-lite

Also writes judge overrides into the correction memory (data/memory.db) from every label file,
so the next run applies the humans' corrections.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kasauti.calibrate import LabelSet, agreement, calibrate, label_files, load_runs  # noqa: E402
from kasauti.report import load_mix, render, rows_to_results, write  # noqa: E402
from sakshi.memory import CorrectionMemory  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="data/runs")
    ap.add_argument("--out", default="data/reports/report.md")
    ap.add_argument("--judge", default="see run output")
    ap.add_argument("--merchant", default="merchant_demo")
    args = ap.parse_args()

    naive_rows = load_runs([Path(args.runs) / "naive.jsonl"])
    guarded_rows = load_runs([Path(args.runs) / "guarded.jsonl"])
    mix = load_mix()

    cal = agr = None
    files = label_files()
    if files:
        sets = [LabelSet.load(p) for p in files]
        cal = calibrate(naive_rows + guarded_rows, sets[0])
        if len(sets) > 1:
            agr = agreement(sets[0], sets[1])
        memory = CorrectionMemory("data/memory.db")
        learned = sum(memory.learn_from_labels(args.merchant, naive_rows + guarded_rows, {h: e["patterns"] for h, e in s.labels.items()},
                                               who=s.labeler) for s in sets)
        print(f"corrections learned from labels: {learned} (memory now holds {len(memory)})")

    text = render(rows_to_results(naive_rows), rows_to_results(guarded_rows), mix=mix, calibration=cal,
                  agreement=agr, judge_name=args.judge)
    path = write(Path(args.out), text)
    print(f"report written to {path}")
    if cal:
        print(cal.table())
    if agr:
        print(agr.table())


if __name__ == "__main__":
    main()
