"""Print every dark-pattern finding with its quoted sentence, per agent and scenario.

    python scripts/show_findings.py
"""
from __future__ import annotations

import json
from pathlib import Path

for name in ("naive", "guarded"):
    path = Path("data/runs") / f"{name}.jsonl"
    if not path.exists():
        continue
    print(f"== {name}")
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if not r.get("findings"):
            continue
        print(f"  {r['scenario_id']}  ({r['transcript_hash']})")
        for f in r["findings"]:
            print(f"     {f['pattern']:<18} [{f['source']}, {f['confidence']:.2f}]  \"{f['snippet']}\"")
