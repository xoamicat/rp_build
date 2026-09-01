"""Run provenance for evaluation artifacts.

Metrics without a reproducible description of the model, fixtures and
simulation boundary are demo decoration.  Kasauti writes this companion file
next to every run so reports cannot silently relabel a synthetic benchmark as
a production result.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_manifest(path: Path, *, provider: str, repeats: int, seed: int, scenarios: list[Any],
                   memory_applied: bool, pass_k: dict[str, Any] | None = None) -> Path:
    payload = {
        "schema": "kasauti.run-manifest.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "repeats": repeats,
        "seed": seed,
        "scenario_count": len(scenarios),
        "scenario_ids": [scenario.id for scenario in scenarios],
        "simulation": {
            "customer": "scripted paraphrase variants",
            "gateway": "StubGateway (Razorpay-shaped; no live payment)",
            "settlement": "synthetic Settlement Recon-shaped rows",
            "baseline": "RuleAgent deliberately configured with documented bad habits",
        },
        "memory_applied": memory_applied,
    }
    if pass_k is not None:
        payload["strict_pass_k"] = pass_k
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)
