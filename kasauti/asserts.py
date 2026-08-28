"""Optional promptfoo contract assertion.

Kasauti's published metrics come from ``kasauti.runner``.  This adapter is
not counted in those metrics and fails closed when a promptfoo test has not
provided an explicit expected status.
"""
from __future__ import annotations

import json


def check_money(output: str, context: dict) -> dict:
    expected = context.get("expected_status") or context.get("vars", {}).get("expected_status")
    if not expected:
        return {"pass": False, "score": 0.0, "reason": "missing expected_status; result is not scored"}
    try:
        parsed = json.loads(output)
    except (TypeError, json.JSONDecodeError):
        return {"pass": False, "score": 0.0, "reason": "agent output is not JSON"}
    actual = parsed.get("gate_status") or parsed.get("status")
    ok = actual == expected
    return {"pass": ok, "score": 1.0 if ok else 0.0,
            "reason": f"expected {expected}, got {actual or 'missing'}"}
