"""Versioned offer commitments for agentic commerce.

Razorpay already authorises and records a payment.  ``OfferLock`` covers a
different boundary: the exact offer an external buyer/merchant agent showed
before the payment or later fulfilment action.  It creates a signed,
privacy-safe commitment to the material terms (items, price, delivery,
returns, substitutions and renewals), then requires a new buyer confirmation
when a later version becomes materially worse or different.

The lock is deliberately small enough to reference from Razorpay ``notes``;
the complete signed snapshot is retained in the merchant's evidence store.
It is not a legal conclusion, delivery proof, or a replacement for Razorpay's
native payment authorisation.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Optional

from .evidence import EvidenceSigner, SignedEvidence
from .intent import NOTES_MAX_KEYS, truncate, validate_notes
from .ledger import Ledger, canonical

OFFER_LOCK_VERSION = "atlas.offer-lock.v1"


class OfferLockError(ValueError):
    """Raised for a malformed or impossible offer commitment."""


@dataclass(frozen=True)
class OfferLine:
    """A catalog-backed, buyer-visible line in the committed offer."""

    sku: str
    name: str
    qty: int
    unit_paise: int

    def __post_init__(self) -> None:
        if not self.sku.strip() or not self.name.strip():
            raise OfferLockError("each offer line needs a non-empty sku and name")
        if self.qty < 1:
            raise OfferLockError("offer quantity must be positive")
        if self.unit_paise < 0:
            raise OfferLockError("offer price cannot be negative")

    @property
    def total_paise(self) -> int:
        return self.qty * self.unit_paise

    def as_dict(self) -> dict[str, Any]:
        return {
            "sku": self.sku,
            "name": self.name,
            "qty": self.qty,
            "unit_paise": self.unit_paise,
            "total_paise": self.total_paise,
        }


@dataclass(frozen=True)
class OfferTerms:
    """The material commercial terms that must not silently drift."""

    merchant_id: str
    offer_id: str
    catalog_version: str
    lines: tuple[OfferLine, ...]
    currency: str = "INR"
    shipping_paise: int = 0
    tax_paise: int = 0
    delivery_by: Optional[str] = None  # ISO date promised to the buyer
    return_policy_version: Optional[str] = None
    substitution_policy: str = "no_substitution"
    renewal_summary: Optional[str] = None  # e.g. "Renews monthly at ₹499"

    def __post_init__(self) -> None:
        if not self.merchant_id.strip() or not self.offer_id.strip() or not self.catalog_version.strip():
            raise OfferLockError("merchant_id, offer_id and catalog_version are required")
        if not self.lines:
            raise OfferLockError("an offer needs at least one line")
        if self.shipping_paise < 0 or self.tax_paise < 0:
            raise OfferLockError("shipping and tax cannot be negative")
        if self.delivery_by:
            try:
                date.fromisoformat(self.delivery_by)
            except ValueError as exc:
                raise OfferLockError("delivery_by must be an ISO date") from exc
        if len({line.sku for line in self.lines}) != len(self.lines):
            raise OfferLockError("an offer cannot contain the same sku twice")

    @property
    def subtotal_paise(self) -> int:
        return sum(line.total_paise for line in self.lines)

    @property
    def total_paise(self) -> int:
        return self.subtotal_paise + self.shipping_paise + self.tax_paise

    def as_dict(self) -> dict[str, Any]:
        return {
            "merchant_id": self.merchant_id,
            "offer_id": self.offer_id,
            "catalog_version": self.catalog_version,
            "lines": [line.as_dict() for line in self.lines],
            "currency": self.currency,
            "subtotal_paise": self.subtotal_paise,
            "shipping_paise": self.shipping_paise,
            "tax_paise": self.tax_paise,
            "total_paise": self.total_paise,
            "delivery_by": self.delivery_by,
            "return_policy_version": self.return_policy_version,
            "substitution_policy": self.substitution_policy,
            "renewal_summary": self.renewal_summary,
        }

    def material_hash(self) -> str:
        return hashlib.sha256(canonical(self.as_dict()).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BuyerApproval:
    """A privacy-safe acknowledgement, not a raw transcript or payment credential."""

    approval_ref: str
    playback: str
    channel: str = "agent"
    principal_ref: Optional[str] = None  # opaque user/session reference only

    def __post_init__(self) -> None:
        if not self.approval_ref.strip() or not self.playback.strip():
            raise OfferLockError("approval_ref and buyer-visible playback are required")

    def as_dict(self) -> dict[str, Any]:
        return {
            "approval_ref": self.approval_ref,
            "playback": truncate(self.playback),
            "channel": self.channel,
            "principal_ref": self.principal_ref,
        }

    def proof_hash(self) -> str:
        return hashlib.sha256(canonical(self.as_dict()).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OfferLock:
    """A signed, versioned snapshot of what the buyer was shown and approved."""

    txn: str
    terms: OfferTerms
    approval: BuyerApproval
    evidence: SignedEvidence
    version: str = OFFER_LOCK_VERSION

    @property
    def lock_id(self) -> str:
        return self.evidence.payload_hash

    def public_summary(self) -> dict[str, Any]:
        """Safe enough for an API/UI response; it excludes raw conversation text."""
        return {
            "lock_id": self.lock_id,
            "version": self.version,
            "terms": self.terms.as_dict(),
            "approval_ref": self.approval.approval_ref,
            "approval_playback": truncate(self.approval.playback),
            "key_id": self.evidence.key_id,
            "signature": self.evidence.signature,
        }

    def note_fields(self) -> dict[str, str]:
        """Four Razorpay-safe references. The full snapshot stays off-entity."""
        return {
            "atlas_lock": self.lock_id[:24],
            "atlas_ver": truncate(self.terms.catalog_version, 64),
            "atlas_kid": self.evidence.key_id,
            "atlas_sig": self.evidence.signature,
        }


@dataclass(frozen=True)
class OfferDelta:
    field: str
    locked: Any
    observed: Any
    material: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "locked": self.locked,
            "observed": self.observed,
            "material": self.material,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class OfferDecision:
    status: str  # ALLOW | RECONFIRM | ESCALATE
    deltas: tuple[OfferDelta, ...]

    @property
    def allowed(self) -> bool:
        return self.status == "ALLOW"

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "allowed": self.allowed, "deltas": [delta.as_dict() for delta in self.deltas]}


def _lines_by_sku(lines: Iterable[OfferLine]) -> dict[str, OfferLine]:
    return {line.sku: line for line in lines}


def compare_offer(lock: OfferLock, observed: OfferTerms) -> OfferDecision:
    """Compare a fulfilment/renewal offer to the buyer-approved offer.

    A price increase, extra/changed item, later delivery, stricter/changed return
    terms, different substitution rule or renewal condition requires a fresh
    buyer acknowledgement. Merchant/currency identity changes escalate instead
    of being treated as a normal confirmation screen.
    """
    locked = lock.terms
    deltas: list[OfferDelta] = []

    if observed.merchant_id != locked.merchant_id:
        deltas.append(OfferDelta("merchant_id", locked.merchant_id, observed.merchant_id, True,
                                 "seller identity changed; do not carry consent across merchants"))
    if observed.currency != locked.currency:
        deltas.append(OfferDelta("currency", locked.currency, observed.currency, True,
                                 "currency changed; amount comparison is no longer meaningful"))

    locked_lines, observed_lines = _lines_by_sku(locked.lines), _lines_by_sku(observed.lines)
    for sku in sorted(set(locked_lines) | set(observed_lines)):
        before, after = locked_lines.get(sku), observed_lines.get(sku)
        if before is None:
            deltas.append(OfferDelta(f"line.{sku}", None, after.as_dict(), True,
                                     "a new item was added after buyer approval"))
            continue
        if after is None:
            deltas.append(OfferDelta(f"line.{sku}", before.as_dict(), None, True,
                                     "an approved item was removed or substituted"))
            continue
        if before.qty != after.qty:
            deltas.append(OfferDelta(f"line.{sku}.qty", before.qty, after.qty, True,
                                     "quantity changed after buyer approval"))
        if before.unit_paise != after.unit_paise:
            material = after.unit_paise > before.unit_paise
            deltas.append(OfferDelta(f"line.{sku}.unit_paise", before.unit_paise, after.unit_paise, material,
                                     "item price increased" if material else "item price decreased"))

    for field in ("shipping_paise", "tax_paise"):
        before, after = getattr(locked, field), getattr(observed, field)
        if before != after:
            deltas.append(OfferDelta(field, before, after, after > before,
                                     f"{field.replace('_paise', '')} increased" if after > before else f"{field.replace('_paise', '')} decreased"))

    if locked.delivery_by != observed.delivery_by:
        later = bool(locked.delivery_by and observed.delivery_by and observed.delivery_by > locked.delivery_by)
        deltas.append(OfferDelta("delivery_by", locked.delivery_by, observed.delivery_by, later,
                                 "delivery promise moved later" if later else "delivery promise changed"))
    for field, reason in (
        ("return_policy_version", "return-policy version changed"),
        ("substitution_policy", "substitution policy changed"),
        ("renewal_summary", "renewal terms changed"),
    ):
        before, after = getattr(locked, field), getattr(observed, field)
        if before != after:
            deltas.append(OfferDelta(field, before, after, True, reason))

    if any(delta.field in {"merchant_id", "currency"} for delta in deltas):
        return OfferDecision("ESCALATE", tuple(deltas))
    return OfferDecision("RECONFIRM" if any(delta.material for delta in deltas) else "ALLOW", tuple(deltas))


def merge_offer_notes(existing: Optional[dict[str, str]], lock: OfferLock) -> dict[str, str]:
    """Attach an OfferLock reference without silently breaking Razorpay notes limits.

    Existing Sakshi intent notes already have a key id.  When both evidence
    objects use that same signing key, OfferLock reuses it and needs only three
    extra fields, taking the legacy signed intent object from 12 to exactly 15
    documented Razorpay note keys.
    """
    notes = dict(existing or {})
    fields = lock.note_fields()
    shared_key = notes.get("sakshi_kid") == lock.evidence.key_id
    if shared_key:
        fields.pop("atlas_kid")
    notes.update(fields)
    if len(notes) > NOTES_MAX_KEYS:
        raise OfferLockError(
            "not enough Razorpay notes capacity for OfferLock; use the same signer as the intent proof or store only atlas_lock"
        )
    validate_notes(notes)
    return notes


@dataclass
class OfferLockService:
    """Creates and checks OfferLocks while recording only privacy-safe facts."""

    signer: EvidenceSigner
    ledger: Optional[Ledger] = None

    def lock(self, txn: str, terms: OfferTerms, approval: BuyerApproval) -> OfferLock:
        payload = {
            "type": OFFER_LOCK_VERSION,
            "txn": txn,
            "terms": terms.as_dict(),
            "terms_hash": terms.material_hash(),
            "approval_hash": approval.proof_hash(),
            "approval_ref": approval.approval_ref,
        }
        lock = OfferLock(txn=txn, terms=terms, approval=approval, evidence=self.signer.sign(payload))
        if self.ledger is not None:
            self.ledger.append(txn, "offer.locked", "atlas", {
                "lock_id": lock.lock_id,
                "terms_hash": terms.material_hash(),
                "offer_id": terms.offer_id,
                "catalog_version": terms.catalog_version,
                "approval_ref": approval.approval_ref,
                "signed_evidence": lock.evidence.as_dict(),
            })
        return lock

    def check(self, lock: OfferLock, observed: OfferTerms) -> OfferDecision:
        decision = compare_offer(lock, observed)
        if self.ledger is not None:
            self.ledger.append(lock.txn, "offer.drift.checked", "atlas", {
                "lock_id": lock.lock_id,
                "status": decision.status,
                "observed_catalog_version": observed.catalog_version,
                "deltas": [delta.as_dict() for delta in decision.deltas],
            })
        return decision
