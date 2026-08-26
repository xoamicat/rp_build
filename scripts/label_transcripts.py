"""Hand-label conversations so the transcript judge can be calibrated.

    python scripts/label_transcripts.py --labeler vanshika
    python scripts/label_transcripts.py --labeler friend --runs data/runs/naive.jsonl data/runs/guarded.jsonl

Shows one unique conversation at a time (identical transcripts are shown once), asks which
dark patterns the AGENT commits, and saves to kasauti/labels/<labeler>.json. Safe to stop and
resume: already-labeled conversations are skipped. The judge's own findings are hidden on
purpose, so your labels are independent.

Answer with pattern numbers separated by commas (for example: 1,3), or 0 for none, or q to quit.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kasauti.calibrate import LABEL_DIR, LabelSet, load_runs, unique_conversations  # noqa: E402
from sakshi.speech import PATTERN_DEFINITIONS  # noqa: E402

PATTERNS = list(PATTERN_DEFINITIONS)


def label_session(convs: dict, labels: LabelSet, ask=input, show=print) -> int:
    done = 0
    todo = [(h, e) for h, e in convs.items() if h not in labels.labels]
    show(f"{len(todo)} conversation(s) to label, {len(labels.labels)} already done.\n")
    for i, (h, e) in enumerate(todo, 1):
        show("=" * 72)
        show(f"[{i}/{len(todo)}]  scenarios: {', '.join(sorted(set(e['scenario_ids'])))}")
        for t in e["transcript"]:
            show(f"  {t['role']:<9} {t['text']}")
        show("")
        for n, p in enumerate(PATTERNS, 1):
            show(f"  {n}. {p:<18} {PATTERN_DEFINITIONS[p]}")
        show("  0. none")
        while True:
            raw = ask("patterns (e.g. 1,3 or 0, q to quit): ").strip().lower()
            if raw == "q":
                return done
            try:
                nums = [int(x) for x in raw.replace(" ", "").split(",") if x != ""]
            except ValueError:
                show("  numbers only")
                continue
            if any(n < 0 or n > len(PATTERNS) for n in nums):
                show("  out of range")
                continue
            chosen = sorted({PATTERNS[n - 1] for n in nums if n > 0})
            break
        labels.labels[h] = {"patterns": chosen, "scenario_ids": sorted(set(e["scenario_ids"]))}
        done += 1
        labels.save(LABEL_DIR / f"{labels.labeler}.json")
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labeler", required=True, help="your name, used as the file name")
    ap.add_argument("--runs", nargs="*", default=["data/runs/naive.jsonl", "data/runs/guarded.jsonl"])
    args = ap.parse_args()
    paths = [Path(p) for p in args.runs if Path(p).exists()]
    if not paths:
        raise SystemExit("no run files found; run scripts/run_kasauti.py first")
    convs = unique_conversations(load_runs(paths))
    target = LABEL_DIR / f"{args.labeler}.json"
    labels = LabelSet.load(target) if target.exists() else LabelSet(args.labeler, {})
    n = label_session(convs, labels)
    print(f"\nsaved {n} new label(s) to {target}")


if __name__ == "__main__":
    main()
