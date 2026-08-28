"""Create and fetch one unpaid Razorpay *test-mode* order carrying an Offer Lock.

This is deliberately opt-in: ``--create`` writes a single unpaid order to the
configured Razorpay Test Mode account. It never opens Checkout, captures money,
or accepts a live-mode key. The JSON artifact contains IDs and proof references,
never credentials or raw buyer text.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sakshi.checkers import default_stage1
from sakshi.config import Settings
from sakshi.engine import Engine
from sakshi.evidence import EvidenceSigner
from sakshi.gateway import LiveGateway
from sakshi.integration import SakshiCheckout
from sakshi.intent import IntentItem, IntentReceipt
from sakshi.ledger import Ledger
from sakshi.models import Cart, CartLine, MerchantConfig
from sakshi.offer_lock import BuyerApproval, OfferLine, OfferLockService, OfferTerms


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create", action="store_true", help="create one unpaid order in Razorpay Test Mode")
    parser.add_argument("--verify-order-id", help="fetch and verify an existing unpaid Test Mode order")
    parser.add_argument("--out", default="data/evidence", help="directory for the safe verification artifact")
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.has_razorpay_keys:
        raise SystemExit("RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are required")
    if not settings.razorpay_key_id.startswith("rzp_test_"):
        raise SystemExit("Refusing to run: this verifier accepts Razorpay Test Mode keys only (rzp_test_...)")
    if args.create and args.verify_order_id:
        raise SystemExit("Choose either --create or --verify-order-id, not both")
    if args.verify_order_id:
        fetched = LiveGateway(settings).fetch_order(args.verify_order_id)
        notes = fetched.get("notes", {})
        required = {"atlas_lock", "atlas_ver", "atlas_sig", "sakshi_txn", "sakshi_kid"}
        missing = sorted(required - set(notes))
        if missing:
            raise RuntimeError(f"Razorpay order did not retain expected Atlas notes: {missing}")
        artifact = {
            "mode": "razorpay_test_mode_guarded_order_verified",
            "verified_at": int(time.time()),
            "order_id": fetched["id"],
            "status": fetched.get("status"),
            "amount": fetched.get("amount"),
            "currency": fetched.get("currency"),
            "note_keys": sorted(notes),
            "atlas_lock": notes.get("atlas_lock"),
            "atlas_ver": notes.get("atlas_ver"),
            "evidence_key_id": notes.get("sakshi_kid"),
            "raw_buyer_text_stored": False,
            "payment_capture_claimed": False,
        }
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"razorpay-test-mode-guarded-{fetched['id']}.json"
        path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(artifact | {"artifact": str(path)}, indent=2))
        return
    if not args.create:
        print("Test-mode credentials detected. Re-run with --create to create one unpaid verification order.")
        return

    txn = f"atlas_verify_{int(time.time())}"
    signer = EvidenceSigner.generate_for_demo("atlas-test-mode-verifier")
    ledger = Ledger()
    merchant = MerchantConfig(merchant_id="atlas_test_mode", extra={"require_signed_evidence": True})
    engine = Engine(ledger, merchant, default_stage1(), signer=signer)
    terms = OfferTerms(
        merchant_id="atlas_test_mode", offer_id="test-mode-offer", catalog_version="atlas-test-v1",
        lines=(OfferLine("PZ-MARG", "Margherita Pizza", 2, 32_000),), shipping_paise=0,
        delivery_by="2026-08-30", return_policy_version="returns-v4", substitution_policy="no_substitution",
    )
    approval = BuyerApproval("test-mode-opaque-approval", "Two Margherita Pizzas for ₹640. Buyer reviewed this offer.",
                              channel="test_mode_verifier", principal_ref="opaque-test-session")
    lock = OfferLockService(signer, ledger).lock(txn, terms, approval)
    intent = IntentReceipt(
        txn=txn, utterance="Two margherita pizzas", playback=approval.playback,
        items=[IntentItem("Margherita Pizza", 2, "PZ-MARG")], cap_paise=64_000,
        channel="test_mode_verifier", human_present=True,
    )
    cart = Cart([CartLine("Margherita Pizza", 2, 32_000, sku="PZ-MARG")])
    gateway = LiveGateway(settings)
    guarded = SakshiCheckout(engine, gateway).create_order(intent, cart, receipt=txn, offer_lock=lock)
    fetched = gateway.fetch_order(guarded.order["id"])
    notes = fetched.get("notes", {})
    required = {"atlas_lock", "atlas_ver", "atlas_sig", "sakshi_txn", "sakshi_kid"}
    missing = sorted(required - set(notes))
    if missing:
        raise RuntimeError(f"Razorpay order did not retain expected Offer Lock notes: {missing}")

    artifact = {
        "mode": "razorpay_test_mode_unpaid_order",
        "verified_at": int(time.time()),
        "order_id": fetched["id"],
        "status": fetched.get("status"),
        "amount": fetched.get("amount"),
        "currency": fetched.get("currency"),
        "note_keys": sorted(notes),
        "atlas_lock": notes.get("atlas_lock"),
        "atlas_ver": notes.get("atlas_ver"),
        "evidence_key_id": notes.get("sakshi_kid"),
        "raw_buyer_text_stored": False,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"razorpay-test-mode-{txn}.json"
    path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(artifact | {"artifact": str(path)}, indent=2))


if __name__ == "__main__":
    main()
