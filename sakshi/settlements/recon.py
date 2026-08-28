"""Adapter for real Razorpay Settlement Recon rows.

The test-mode synthesiser deliberately has the same field names.  This adapter
is the boundary for an actual API/CSV record: it coerces only known scalar
fields, parses a serialised ``notes`` object when necessary, and refuses a
row that cannot be linked to the order's Sakshi transaction.
"""
from __future__ import annotations

import json
from typing import Any

from .synth import RECON_FIELDS


class ReconRecordError(ValueError):
    pass


_INT_FIELDS = {"debit", "credit", "amount", "fee", "tax", "created_at", "settled_at", "posted_at"}


def normalize_recon_line(row: dict[str, Any]) -> dict[str, Any]:
    """Normalise one Razorpay Settlement Recon row without inventing missing values."""
    if not isinstance(row, dict):
        raise ReconRecordError("settlement recon row must be an object")
    line = {field: row.get(field) for field in RECON_FIELDS}
    for field in _INT_FIELDS:
        value = line[field]
        if value not in (None, ""):
            try:
                line[field] = int(value)
            except (TypeError, ValueError) as exc:
                raise ReconRecordError(f"{field} must be an integer subunit") from exc
    notes = line["notes"]
    if isinstance(notes, str):
        try:
            notes = json.loads(notes)
        except json.JSONDecodeError as exc:
            raise ReconRecordError("notes is not valid JSON") from exc
    if notes is None:
        notes = {}
    if not isinstance(notes, dict):
        raise ReconRecordError("notes must be an object")
    line["notes"] = notes
    return line


def require_linked_transaction(line: dict[str, Any], txn: str) -> dict[str, Any]:
    """Reject an unlinked/mislinked recon line before it becomes evidence for a transaction."""
    actual = (line.get("notes") or {}).get("sakshi_txn")
    if actual != txn:
        raise ReconRecordError(f"recon row belongs to {actual or 'no Sakshi transaction'}, not {txn}")
    return line
