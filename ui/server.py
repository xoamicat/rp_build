"""SettleX Atlas interactive demo server.
Run:  python ui/server.py  →  http://localhost:5000
"""
import json, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify, request, send_file

app = Flask(__name__, static_folder=None)

# ── Pre-load run data ────────────────────────────────────────────────
def _load_runs():
    rows = []
    for p in (ROOT / "data" / "runs").glob("*.jsonl"):
        with open(p, encoding="utf-8") as f:
            rows.extend(json.loads(line) for line in f if line.strip())
    return rows

RUNS = _load_runs()

@app.route("/")
@app.route("/offer-lock")
@app.route("/evidence")
@app.route("/evidence/<session_id>")
@app.route("/claims")
@app.route("/claims/<session_id>")
@app.route("/release")
@app.route("/checkout-safety")
@app.route("/settlements")
@app.route("/intent-check")
@app.route("/speech-check")
def index(session_id=None):
    template = (ROOT / "ui" / "dashboard.html").read_text(encoding="utf-8")
    runs_json = json.dumps(RUNS, ensure_ascii=False).replace("</", "<\\/")
    html = template.replace("__RUNS_DATA__", runs_json)
    return html, 200, {"Content-Type": "text/html; charset=utf-8",
                         "Cache-Control": "no-store, no-cache, must-revalidate",
                         "Pragma": "no-cache"}

@app.route("/api/runs")
def api_runs():
    return jsonify(_load_runs())


@app.route("/api/run-manifest")
def api_run_manifest():
    path = ROOT / "data" / "runs" / "run-manifest.json"
    if not path.exists():
        return jsonify({"error": "Run Kasauti to generate data/runs/run-manifest.json"}), 404
    return jsonify(json.loads(path.read_text(encoding="utf-8")))

# ── LIVE: Speech Guard Scanner ───────────────────────────────────────
@app.route("/api/scan", methods=["POST"])
def api_scan():
    from sakshi.speech import SpeechGuard
    data = request.json or {}
    text = data.get("text", "")
    after_refusal = data.get("after_refusal", False)
    guard = SpeechGuard()
    replacement, findings = guard.filter(text, after_refusal=after_refusal)
    return jsonify({
        "original": text,
        "replacement": replacement,
        "blocked": replacement != text,
        "findings": [{"pattern": f.pattern, "snippet": f.snippet} for f in findings],
    })

# ── LIVE: Cart Gate Check ────────────────────────────────────────────
@app.route("/api/gate", methods=["POST"])
def api_gate():
    """Check a cart against a customer intent — the core evidence feature.
    Body: { intent_items: [{name, qty, unit_paise}], cart_items: [{name, qty, unit_paise}],
            merchant: {max_discount_pct, auto_approve_limit_paise} }
    """
    from sakshi.checkers import default_stage1, default_stage2
    from sakshi.evidence import EvidenceSigner
    from sakshi.engine import Engine
    from sakshi.intent import IntentItem, IntentReceipt
    from sakshi.ledger import Ledger
    from sakshi.models import Cart, CartLine, MerchantConfig

    data = request.json or {}

    try:
        # Build intent (IntentItem has name + qty only, no price)
        intent_items = [IntentItem(name=i["name"], qty=i.get("qty", 1))
                        for i in data.get("intent_items", [])]
        utterance = ", ".join(f"{i['qty']}x {i['name']}" for i in data.get("intent_items", []))
        receipt = IntentReceipt(txn="demo-1", utterance=utterance, playback=utterance, items=intent_items)

        # Build cart (CartLine has name + qty + unit_paise)
        cart_lines = [CartLine(name=c["name"], qty=c.get("qty", 1), unit_paise=c["unit_paise"])
                      for c in data.get("cart_items", [])]
        cart = Cart(lines=cart_lines)

        # Merchant config
        mc = data.get("merchant", {})
        merchant = MerchantConfig(
            max_discount_bps=mc.get("max_discount_bps", 1000),
            hitl_threshold_paise=mc.get("hitl_threshold_paise", 200000),
        )

        # Run the gate
        engine = Engine(ledger=Ledger(), merchant=merchant, checkers=default_stage1())
        engine.capture_intent(receipt)
        result = engine.gate(receipt, cart)

        return jsonify({
            "status": result.status.value,
            "impact_paise": result.impact_paise,
            "allowed": result.allowed,
            "verdicts": [{"checker": v.checker, "status": v.status.value,
                          "reason": v.reason, "impact_paise": v.impact_paise}
                         for v in result.verdicts],
        })
    except Exception as e:
        return jsonify({"status": "ERROR", "impact_paise": 0, "allowed": False,
                        "verdicts": [{"checker": "server", "status": "BLOCK",
                                      "reason": str(e), "impact_paise": 0}]}), 200

# ── LIVE: Corrections ────────────────────────────────────────────────
@app.route("/api/corrections")
def api_corrections():
    db = ROOT / "data" / "memory.db"
    if not db.exists():
        return jsonify([])
    from sakshi.memory import CorrectionMemory
    return jsonify(CorrectionMemory(str(db)).all())

# ── LIVE: AI Agent Chat ──────────────────────────────────────────────
# Session store for active agent conversations
_sessions = {}
_offer_locks = {}
_offer_lock_service = None
_offer_evidence_sessions = {}
_offer_composer = None
_test_mode_orders = {}
_offer_store = None

OFFER_COMPOSER_CATALOG = (
    {"sku": "PZ-MARG", "name": "Margherita Pizza", "unit_paise": 32000},
    {"sku": "SD-GARL", "name": "Garlic Bread", "unit_paise": 19000},
    {"sku": "DR-COLA", "name": "Cola", "unit_paise": 6000},
)


def _get_offer_lock_service():
    """Use durable, key-pinned evidence when configured; otherwise label the demo signer."""
    global _offer_lock_service
    if _offer_lock_service is None:
        from sakshi.config import Settings
        from sakshi.evidence import EvidenceSigner
        from sakshi.ledger import Ledger
        from sakshi.offer_lock import OfferLockService

        settings = Settings.from_env()
        signer = EvidenceSigner.from_env(settings.evidence_private_key_b64, settings.evidence_key_id)
        if signer is not None:
            ledger_path = Path(settings.atlas_evidence_db)
            if not ledger_path.is_absolute():
                ledger_path = ROOT / ledger_path
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            _offer_lock_service = OfferLockService(signer, Ledger(str(ledger_path)))
        else:
            _offer_lock_service = OfferLockService(
                EvidenceSigner.generate_for_demo("atlas-offer-demo-1"), Ledger()
            )
    return _offer_lock_service


def _get_offer_store():
    """Return persistence only when the server has a configured signing key."""
    global _offer_store
    if _offer_store is not None:
        return _offer_store
    from sakshi.config import Settings
    from sakshi.offer_store import DurableOfferStore

    settings = Settings.from_env()
    if not settings.has_durable_atlas_evidence:
        return None
    path = Path(settings.atlas_evidence_db)
    if not path.is_absolute():
        path = ROOT / path
    _offer_store = DurableOfferStore(str(path))
    return _offer_store


def _find_offer_lock(lock_id):
    lock = _offer_locks.get(lock_id)
    if lock is not None:
        return lock
    store = _get_offer_store()
    lock = store.get_lock(lock_id) if store is not None else None
    if lock is not None:
        _offer_locks[lock_id] = lock
    return lock


def _find_test_mode_order(order_id):
    info = _test_mode_orders.get(order_id)
    if info is not None:
        return info
    store = _get_offer_store()
    info = store.get_test_order(order_id) if store is not None else None
    if info is not None:
        _test_mode_orders[order_id] = info
    return info


def _save_test_mode_order(order_id, info):
    _test_mode_orders[order_id] = info
    store = _get_offer_store()
    if store is not None:
        store.put_test_order(order_id, info)


@app.route("/api/runtime-readiness")
def api_runtime_readiness():
    """Non-sensitive deployment posture displayed in the demo and useful in a pilot."""
    from sakshi.config import Settings

    settings = Settings.from_env()
    return jsonify({
        "evidence_mode": "durable_key_pinned_sqlite" if settings.has_durable_atlas_evidence else "ephemeral_demo",
        "evidence_key_configured": bool(settings.evidence_private_key_b64),
        "offer_state_survives_restart": settings.has_durable_atlas_evidence,
        "test_mode_key_configured": bool(settings.has_razorpay_keys and settings.razorpay_key_id.startswith("rzp_test_")),
        "webhook_signature_configured": bool(settings.razorpay_webhook_secret),
        "public_https_required_for_webhook": True,
        "raw_buyer_text_in_notes": False,
    })


def _get_offer_composer():
    """Return the configured real LLM adapter, cached for repeatable demo calls."""
    global _offer_composer
    if _offer_composer is None:
        from sakshi.config import Settings
        from sakshi.llm import CachedProvider, LlmCache, provider_from_env
        from sakshi.offer_composer import OfferComposer

        settings = Settings.from_env()
        if settings.llm not in {"gemini", "ollama"}:
            raise RuntimeError("Set SAKSHI_LLM=gemini or ollama to compose a live AI offer draft")
        _offer_composer = OfferComposer(CachedProvider(
            provider_from_env(settings), LlmCache(str(ROOT / "data" / "llm_cache.db"))
        ))
    return _offer_composer


def _offer_terms_from_body(raw):
    from sakshi.offer_lock import OfferLine, OfferTerms

    return OfferTerms(
        merchant_id=raw["merchant_id"],
        offer_id=raw["offer_id"],
        catalog_version=raw["catalog_version"],
        lines=tuple(OfferLine(
            sku=line["sku"], name=line["name"], qty=int(line["qty"]), unit_paise=int(line["unit_paise"])
        ) for line in raw["lines"]),
        currency=raw.get("currency", "INR"),
        shipping_paise=int(raw.get("shipping_paise", 0)),
        tax_paise=int(raw.get("tax_paise", 0)),
        delivery_by=raw.get("delivery_by"),
        return_policy_version=raw.get("return_policy_version"),
        substitution_policy=raw.get("substitution_policy", "no_substitution"),
        renewal_summary=raw.get("renewal_summary"),
    )


@app.route("/api/offer-drafts", methods=["POST"])
def api_offer_draft():
    """Use a configured LLM to draft only catalogue-backed buyer-visible terms.

    This deliberately creates no lock and no payment. A human/buyer must still
    see the returned offer and explicitly create the signed OfferLock.
    """
    from sakshi.offer_composer import CatalogOffer, OfferCompositionError

    data = request.json or {}
    try:
        composer = _get_offer_composer()
        composition = composer.compose(
            data.get("buyer_request", ""),
            merchant_id="demo-pizza-co",
            offer_id="offer_pizza_ai_draft",
            catalog_version="menu-2026-08-28.1",
            catalog=[CatalogOffer(**item) for item in OFFER_COMPOSER_CATALOG],
            currency="INR",
            shipping_paise=4000,
            tax_paise=0,
            delivery_by="2026-08-30",
            return_policy_version="returns-v4",
            substitution_policy="no_substitution",
        )
        return jsonify({
            "terms": composition.terms.as_dict(),
            "buyer_summary": composition.buyer_summary,
            "uncertainties": list(composition.uncertainties),
            "provenance": composition.provenance,
            "guardrails": [
                "AI can select only merchant-catalogue SKUs and quantities.",
                "Code—not the model—sets prices, delivery and policy terms.",
                "This is a draft. Buyer confirmation is required before the Offer Lock is signed.",
            ],
        })
    except (OfferCompositionError, RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 422


@app.route("/api/offer-locks", methods=["POST"])
def api_offer_lock_create():
    """Commit the exact buyer-visible offer before Razorpay checkout or fulfilment."""
    from sakshi.offer_lock import BuyerApproval, merge_offer_notes

    data = request.json or {}
    try:
        approval_raw = data["approval"]
        service = _get_offer_lock_service()
        terms = _offer_terms_from_body(data["terms"])
        ai_provenance = data.get("ai_provenance")
        if isinstance(ai_provenance, dict):
            # Only provenance hashes and the configured provider cross this boundary;
            # raw buyer text and raw model output never enter the ledger.
            service.ledger.append(data["txn"], "offer.ai.composed", "atlas_ai", {
                "input_hash": str(ai_provenance.get("input_hash", "")),
                "output_hash": str(ai_provenance.get("output_hash", "")),
                "provider": str(ai_provenance.get("provider", "unknown")),
                "model": str(ai_provenance.get("model", "unknown")),
                "catalog_hash": str(ai_provenance.get("catalog_hash", "")),
                "catalog_version": terms.catalog_version,
                "consent_captured": False,
            })
        approval = BuyerApproval(
            approval_ref=approval_raw["approval_ref"],
            playback=approval_raw["playback"],
            channel=approval_raw.get("channel", "agent"),
            principal_ref=approval_raw.get("principal_ref"),
        )
        lock = service.lock(data["txn"], terms, approval)
        _offer_locks[lock.lock_id] = lock
        store = _get_offer_store()
        if store is not None:
            store.put_lock(lock)
        evidence_session_id = "offer-" + lock.lock_id
        _offer_evidence_sessions[evidence_session_id] = {
            "txn": lock.txn, "lock": lock, "ledger": service.ledger, "signer": service.signer,
        }
        return jsonify({
            "lock": lock.public_summary(),
            "order_notes": merge_offer_notes({}, lock),
            "storage": "durable configured evidence store" if store is not None else "ephemeral demo memory; configure SAKSHI_EVIDENCE_PRIVATE_KEY_B64 to persist",
            "evidence_session_id": evidence_session_id,
        }), 201
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/offer-locks/<lock_id>/check", methods=["POST"])
def api_offer_lock_check(lock_id):
    """Check a changed fulfilment or renewal against the buyer-approved OfferLock."""
    lock = _find_offer_lock(lock_id)
    if lock is None:
        return jsonify({"error": "OfferLock not found. Create it before checking fulfilment."}), 404
    try:
        observed = _offer_terms_from_body((request.json or {})["terms"])
        service = _get_offer_lock_service()
        decision = service.check(lock, observed)
        # A fresh chain seal covers the new operational decision as well as the
        # signed OfferLock. This is a demo signer; production pins a durable key.
        service.signer.seal_transaction(service.ledger, lock.txn)
        return jsonify({
            "decision": decision.as_dict(),
            "lock": lock.public_summary(),
            "observed_terms": observed.as_dict(),
            "evidence_session_id": "offer-" + lock.lock_id,
        })
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/offer-locks/<lock_id>/test-mode-order", methods=["POST"])
def api_offer_lock_test_mode_order(lock_id):
    """Create a Test Mode order from a signed OfferLock, never a live-mode order.

    The Checkout popup is initiated separately by the browser.  A browser callback
    is intentionally not treated as payment evidence: only the verified webhook
    route below can record ``rzp.payment.captured`` in the sealed ledger.
    """
    from sakshi.checkers import default_stage1, default_stage2
    from sakshi.config import Settings
    from sakshi.engine import Engine
    from sakshi.gateway import LiveGateway
    from sakshi.integration import SakshiCheckout
    from sakshi.intent import IntentItem, IntentReceipt
    from sakshi.models import Cart, CartLine, MerchantConfig

    lock = _find_offer_lock(lock_id)
    if lock is None:
        return jsonify({"error": "OfferLock not found. Sign the buyer-visible offer first."}), 404
    settings = Settings.from_env()
    if not settings.has_razorpay_keys:
        return jsonify({"error": "Razorpay Test Mode API keys are not configured on this demo server."}), 422
    if not settings.razorpay_key_id.startswith("rzp_test_"):
        return jsonify({"error": "Refusing checkout: this demo only creates Razorpay Test Mode orders."}), 422

    existing = next((item for item in _test_mode_orders.values() if item["lock_id"] == lock_id), None)
    if existing is None:
        store = _get_offer_store()
        existing = store.find_test_order_for_lock(lock_id) if store is not None else None
    if existing is not None:
        return jsonify({
            "mode": "razorpay_test_mode",
            "order": existing["order"],
            "checkout": {
                "key_id": settings.razorpay_key_id, "order_id": existing["order"]["id"],
                "amount": existing["order"]["amount"], "currency": existing["order"]["currency"],
                "name": "SettleX Atlas — Test Mode",
                "description": "Signed Offer Lock demo; no live payment is possible.",
            },
            "evidence_session_id": existing["evidence_session_id"],
            "webhook_truth": "Payment is pending until a valid Razorpay payment.captured webhook is received.",
            "notes_budget": existing["notes_budget"],
        }), 200

    try:
        service = _get_offer_lock_service()
        terms = lock.terms
        intent_items = [IntentItem(line.name, line.qty, line.sku) for line in terms.lines]
        cart_lines = [CartLine(line.name, line.qty, line.unit_paise, sku=line.sku) for line in terms.lines]
        # Delivery and tax are buyer-visible commercial terms as well.  They are
        # explicit intent/cart lines so the Stage-1 item matcher cannot overlook them.
        if terms.shipping_paise:
            intent_items.append(IntentItem("Delivery", 1, "ATLAS-DELIVERY"))
            cart_lines.append(CartLine("Delivery", 1, terms.shipping_paise, sku="ATLAS-DELIVERY", source="merchant"))
        if terms.tax_paise:
            intent_items.append(IntentItem("Tax", 1, "ATLAS-TAX"))
            cart_lines.append(CartLine("Tax", 1, terms.tax_paise, sku="ATLAS-TAX", source="merchant"))
        cart = Cart(cart_lines, currency=terms.currency, quoted_total_paise=terms.total_paise)
        intent = IntentReceipt(
            txn=lock.txn,
            utterance="Buyer reviewed the exact signed offer; raw request is not retained here.",
            playback=lock.approval.playback,
            items=intent_items,
            cap_paise=terms.total_paise,
            currency=terms.currency,
            channel="atlas_test_mode_checkout",
            human_present=True,
        )
        merchant = MerchantConfig(
            merchant_id=terms.merchant_id,
            name="Atlas Test Mode Merchant",
            currency=terms.currency,
            extra={"require_signed_evidence": True},
        )
        engine = Engine(service.ledger, merchant, default_stage1() + default_stage2(), signer=service.signer)
        guarded = SakshiCheckout(engine, LiveGateway(settings)).create_order(
            intent, cart, receipt=lock.txn[:40], offer_lock=lock
        )
        promise_order = engine.check_order(intent, cart, guarded.order, prepayment=True)
        if promise_order.status.value == "BLOCK":
            return jsonify({"error": "Order amount diverged from the signed offer; Checkout was not opened."}), 409
        service.signer.seal_transaction(service.ledger, lock.txn)
        public_order = {
            "id": guarded.order["id"], "amount": guarded.order["amount"],
            "currency": guarded.order["currency"], "status": guarded.order.get("status"),
            "note_keys": sorted((guarded.order.get("notes") or {}).keys()),
        }
        test_order_state = {
            "txn": lock.txn,
            "lock_id": lock.lock_id,
            "evidence_session_id": "offer-" + lock.lock_id,
            "amount": cart.total_paise,
            "currency": cart.currency,
            "client_returned": False,
            "order": public_order,
            "notes_budget": f"{len((guarded.order.get('notes') or {}))}/15 Razorpay order.notes keys used",
        }
        _save_test_mode_order(guarded.order["id"], test_order_state)
        return jsonify({
            "mode": "razorpay_test_mode",
            "order": public_order,
            "checkout": {
                "key_id": settings.razorpay_key_id,
                "order_id": guarded.order["id"],
                "amount": guarded.order["amount"],
                "currency": guarded.order["currency"],
                "name": "SettleX Atlas — Test Mode",
                "description": "Signed Offer Lock demo; no live payment is possible.",
            },
            "evidence_session_id": "offer-" + lock.lock_id,
            "webhook_truth": "Payment is pending until a valid Razorpay payment.captured webhook is received.",
            "notes_budget": test_order_state["notes_budget"],
        }), 201
    except Exception as exc:
        # Avoid passing SDK internals or credentials back into a browser response.
        return jsonify({"error": f"Test Mode order could not be created ({type(exc).__name__}). Check server configuration and the signed offer."}), 502


@app.route("/api/test-mode/orders/<order_id>/checkout-return", methods=["POST"])
def api_test_mode_checkout_return(order_id):
    """Record an untrusted browser return, explicitly separate from payment truth."""
    info = _find_test_mode_order(order_id)
    if info is None:
        return jsonify({"error": "Unknown Test Mode order."}), 404
    data = request.json or {}
    payment_id = str(data.get("razorpay_payment_id", ""))[:80]
    if not payment_id:
        return jsonify({"error": "Checkout returned without a payment reference."}), 400
    service = _get_offer_lock_service()
    service.ledger.append(info["txn"], "checkout.client.returned", "browser", {
        "order_id": order_id, "payment_id": payment_id,
        "signature_present": bool(data.get("razorpay_signature")),
        "payment_truth": "pending_verified_webhook",
    })
    info["client_returned"] = True
    _save_test_mode_order(order_id, info)
    return jsonify({
        "accepted": True,
        "payment_truth": "pending_verified_webhook",
        "message": "Browser success is not payment evidence. Atlas is waiting for the signed Razorpay webhook.",
    })


@app.route("/api/test-mode/orders/<order_id>/status")
def api_test_mode_status(order_id):
    from sakshi.config import Settings

    info = _find_test_mode_order(order_id)
    if info is None:
        return jsonify({"error": "Unknown Test Mode order."}), 404
    service = _get_offer_lock_service()
    events = service.ledger.chain(info["txn"])
    payment = next((event for event in reversed(events) if event.type == "rzp.payment.captured"), None)
    settings = Settings.from_env()
    return jsonify({
        "order_id": order_id,
        "checkout_returned": info["client_returned"],
        "payment_captured_by_verified_webhook": payment is not None,
        "webhook_configured": bool(settings.razorpay_webhook_secret),
        "evidence_session_id": info["evidence_session_id"],
        "next_step": "Review the signed evidence journey" if payment else "Expose /webhooks/razorpay over HTTPS and configure the Test Mode webhook before treating payment as complete.",
    })


@app.route("/webhooks/razorpay", methods=["POST"])
def razorpay_webhook():
    """Verified payment truth for this demo server; raw body first, JSON second."""
    from sakshi.config import Settings
    from sakshi.webhooks import RazorpayWebhookIngestor, WebhookSignatureError

    settings = Settings.from_env()
    if not settings.razorpay_webhook_secret:
        return jsonify({"error": "Razorpay webhook verification is not configured."}), 503
    try:
        service = _get_offer_lock_service()
        receipt = RazorpayWebhookIngestor(service.ledger, settings.razorpay_webhook_secret).ingest(
            request.get_data(cache=False), request.headers.get("x-razorpay-signature"),
            request.headers.get("x-razorpay-event-id"),
        )
        # The webhook HMAC is the authority boundary. Any linked, verified lifecycle
        # event advances and reseals its existing offer journey, including after restart.
        if not receipt.duplicate and receipt.txn != "unlinked" and service.ledger.chain(receipt.txn):
            service.signer.seal_transaction(service.ledger, receipt.txn)
        return jsonify(receipt.as_dict()), 200
    except WebhookSignatureError:
        return jsonify({"error": "Invalid Razorpay webhook signature."}), 401
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

def _build_session(scenario_id):
    """Create a fresh agent plus evidence engine for a scenario."""
    from kasauti.scenario import load_scenarios
    from kasauti.agents import RuleAgent, GuardedAgent
    from sakshi.checkers import default_stage1
    from sakshi.engine import Engine
    from sakshi.intent import IntentItem, IntentReceipt
    from sakshi.ledger import Ledger
    from sakshi.models import MerchantConfig
    from sakshi.speech import SpeechGuard

    scenarios = {s.id: s for s in load_scenarios()}
    sc = scenarios.get(scenario_id)
    if not sc:
        return None, None, None

    merchant = MerchantConfig(
        merchant_id=sc.merchant.get("merchant_id", "demo"),
        name=sc.merchant.get("name", "Demo Pizza Co"),
        max_discount_bps=sc.merchant.get("max_discount_bps", 1000),
        hitl_threshold_paise=sc.merchant.get("hitl_threshold_paise", 200000),
    )

    # Naive agent (with bad habits ON)
    naive = RuleAgent()
    naive.start(sc)

    # Guarded agent wraps the naïve agent with the evidence engine.
    engine = Engine(ledger=Ledger(), merchant=merchant, checkers=default_stage1() + default_stage2(),
                    signer=EvidenceSigner.generate_for_demo(f"demo-{scenario_id}"))
    guarded = GuardedAgent(inner=naive, engine=engine, speech=SpeechGuard())
    guarded.start(sc)

    # Build intent from scenario
    intent_items = [IntentItem(name=i["name"], qty=i.get("qty", 1), sku=i.get("sku"))
                    for i in sc.intent.get("items", [])]
    utterance = sc.intent.get("utterance", ", ".join(f"{i.qty}x {i.name}" for i in intent_items))
    receipt = IntentReceipt(
        txn=f"demo-{scenario_id}",
        utterance=utterance,
        playback=utterance,
        items=intent_items,
        human_present=sc.intent.get("human_present", True),
    )
    guarded.bind_intent(receipt)

    return guarded, sc, receipt

def _build_compare_session(scenario_id):
    """Create BOTH a naive and guarded agent for side-by-side comparison."""
    from kasauti.scenario import load_scenarios
    from kasauti.agents import RuleAgent, GuardedAgent
    from sakshi.checkers import default_stage1, default_stage2
    from sakshi.engine import Engine
    from sakshi.evidence import EvidenceSigner
    from sakshi.intent import IntentItem, IntentReceipt
    from sakshi.ledger import Ledger
    from sakshi.models import MerchantConfig
    from sakshi.speech import SpeechGuard

    scenarios = {s.id: s for s in load_scenarios()}
    sc = scenarios.get(scenario_id)
    if not sc:
        return None, None, None, None

    merchant = MerchantConfig(
        merchant_id=sc.merchant.get("merchant_id", "demo"),
        name=sc.merchant.get("name", "Demo Pizza Co"),
        max_discount_bps=sc.merchant.get("max_discount_bps", 1000),
        hitl_threshold_paise=sc.merchant.get("hitl_threshold_paise", 200000),
    )

    # Standalone naive agent (NO Sakshi)
    naive_standalone = RuleAgent()
    naive_standalone.start(sc)

    # Guarded agent. The judge demo defaults to deterministic checkers so an unavailable
    # local/model endpoint cannot break a live presentation. Set SAKSHI_DEMO_LLM=1 to opt in.
    naive_inner = RuleAgent()
    naive_inner.start(sc)
    checkers = default_stage1()
    if os.environ.get("SAKSHI_DEMO_LLM") == "1":
        try:
            from sakshi.checkers.llm import stage1_with_llm
            from sakshi.llm.provider import provider_from_env
            checkers = stage1_with_llm(provider_from_env())
        except Exception:
            checkers = default_stage1()
    engine = Engine(ledger=Ledger(), merchant=merchant, checkers=checkers + default_stage2(),
                    signer=EvidenceSigner.generate_for_demo(f"demo-{scenario_id}"))
    guarded = GuardedAgent(inner=naive_inner, engine=engine, speech=SpeechGuard())
    guarded.start(sc)

    intent_items = [IntentItem(name=i["name"], qty=i.get("qty", 1), sku=i.get("sku"))
                    for i in sc.intent.get("items", [])]
    utterance = sc.intent.get("utterance", ", ".join(f"{i.qty}x {i.name}" for i in intent_items))
    receipt = IntentReceipt(
        txn=f"demo-{scenario_id}",
        utterance=utterance,
        playback=utterance,
        items=intent_items,
        human_present=sc.intent.get("human_present", True),
    )
    guarded.bind_intent(receipt)

    return naive_standalone, guarded, sc, receipt

@app.route("/api/scenarios")
def api_scenarios():
    """List available scenarios for the chat demo."""
    from kasauti.scenario import load_scenarios
    return jsonify([{
        "id": s.id, "title": s.title, "pack": s.pack,
        "catalog": [{"name": c.name, "sku": c.sku, "unit_paise": c.unit_paise} for c in s.catalog],
        "turns": s.turns,
    } for s in load_scenarios()])

@app.route("/api/chat/start", methods=["POST"])
def api_chat_start():
    """Start a new agent conversation for a scenario."""
    data = request.json or {}
    scenario_id = data.get("scenario_id", "hijack_product_page_upsell")

    guarded, sc, receipt = _build_session(scenario_id)
    if not guarded:
        return jsonify({"error": f"Unknown scenario: {scenario_id}"}), 400

    import uuid
    sid = str(uuid.uuid4())[:8]
    _sessions[sid] = {"agent": guarded, "scenario": sc, "receipt": receipt,
                      "history": [], "naive_history": []}

    return jsonify({
        "session_id": sid,
        "scenario": {"id": sc.id, "title": sc.title, "pack": sc.pack},
        "catalog": [{"name": c.name, "sku": c.sku, "unit_paise": c.unit_paise} for c in sc.catalog],
        "suggested_turns": sc.turns,
        "intent": sc.intent,
    })

@app.route("/api/chat/message", methods=["POST"])
def api_chat_message():
    """Send a customer message and return its evidence-aware interception details."""
    data = request.json or {}
    sid = data.get("session_id")
    message = data.get("message", "")

    session = _sessions.get(sid)
    if not session:
        return jsonify({"error": "Session not found. Start a new chat first."}), 400

    agent = session["agent"]

    # Count existing speech events BEFORE this reply
    try:
        prev_count = agent.engine.ledger.conn.execute("SELECT COUNT(*) FROM events WHERE type='speech.blocked'").fetchone()[0]
    except Exception:
        prev_count = 0

    # Get the ORIGINAL text from the inner agent before Sakshi filters
    from sakshi.speech import SpeechGuard
    temp_guard = SpeechGuard()

    try:
        reply = agent.reply(message)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Build response with interception details
    entry = {
        "agent_text": reply.text,
        "original_text": None,
        "cart": reply.cart.as_dict() if reply.cart else {},
        "done": reply.done,
        "gate": None,
        "speech_intercepted": False,
        "speech_findings": [],
        "asked_human": reply.asked_human,
    }

    if reply.gate:
        entry["gate"] = {
            "status": reply.gate.status.value,
            "impact_paise": reply.gate.impact_paise,
            "allowed": reply.gate.allowed,
            "verdicts": [{"checker": v.checker, "status": v.status.value,
                          "reason": v.reason, "impact_paise": v.impact_paise}
                         for v in reply.gate.verdicts if v.status.value != "SKIP"],
        }

    # Check if speech guard intercepted by looking for NEW speech.blocked events
    try:
        ledger = agent.engine.ledger
        new_events = ledger.conn.execute(
            "SELECT payload FROM events WHERE type='speech.blocked' ORDER BY seq DESC LIMIT ?",
            (1,)  # get latest
        ).fetchall()
        new_count = ledger.conn.execute("SELECT COUNT(*) FROM events WHERE type='speech.blocked'").fetchone()[0]
        if new_count > prev_count and new_events:
            entry["speech_intercepted"] = True
            p = json.loads(new_events[0][0]) if isinstance(new_events[0][0], str) else new_events[0][0]
            entry["speech_findings"] = p.get("findings", [])
            # Reconstruct what the agent TRIED to say from findings
            # The findings have snippets of what was caught
            original_len = p.get("original_len", 0)
            if original_len > 0:
                entry["original_text"] = "(blocked - contained dark pattern)"
    except Exception:
        pass

    session["history"].append({"role": "customer", "text": message})
    session["history"].append({"role": "agent", "text": reply.text})

    return jsonify(entry)

# ── Side-by-Side Comparison ──────────────────────────────────────────
@app.route("/api/compare/start", methods=["POST"])
def api_compare_start():
    """Start a comparison session with BOTH naive and guarded agents."""
    data = request.json or {}
    scenario_id = data.get("scenario_id", "hijack_product_page_upsell")

    naive, guarded, sc, receipt = _build_compare_session(scenario_id)
    if not naive:
        return jsonify({"error": f"Unknown scenario: {scenario_id}"}), 400

    import uuid
    sid = str(uuid.uuid4())[:8]
    _sessions[sid] = {"naive": naive, "guarded": guarded, "scenario": sc,
                      "receipt": receipt, "history": [], "is_compare": True, "razorpay": None}

    return jsonify({
        "session_id": sid,
        "scenario": {"id": sc.id, "title": sc.title, "pack": sc.pack},
        "catalog": [{"name": c.name, "sku": c.sku, "unit_paise": c.unit_paise} for c in sc.catalog],
        "suggested_turns": [{"text": t.text, "note": getattr(t, 'note', '')} for t in sc.turns],
        "intent": sc.intent,
    })

@app.route("/api/compare/message", methods=["POST"])
def api_compare_message():
    """Send message to BOTH agents, return side-by-side results."""
    data = request.json or {}
    sid = data.get("session_id")
    message = data.get("message", "")

    session = _sessions.get(sid)
    if not session or not session.get("is_compare"):
        return jsonify({"error": "Comparison session not found"}), 400

    naive_agent = session["naive"]
    guarded_agent = session["guarded"]

    # Count speech events before
    try:
        prev_count = guarded_agent.engine.ledger.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type='speech.blocked'").fetchone()[0]
    except Exception:
        prev_count = 0

    # Get NAIVE response (no Sakshi)
    try:
        naive_reply = naive_agent.reply(message)
        naive_entry = {
            "text": naive_reply.text,
            "cart": naive_reply.cart.as_dict() if naive_reply.cart else None,
            "done": naive_reply.done,
        }
    except Exception as e:
        naive_entry = {"text": f"Error: {e}", "cart": None, "done": False}

    # Get GUARDED response (with Sakshi)
    try:
        guarded_reply = guarded_agent.reply(message)
        guarded_entry = {
            "text": guarded_reply.text,
            "cart": guarded_reply.cart.as_dict() if guarded_reply.cart else None,
            "done": guarded_reply.done,
            "gate": None,
            "speech_intercepted": False,
            "speech_findings": [],
            "asked_human": guarded_reply.asked_human,
        }

        if guarded_reply.gate:
            guarded_entry["gate"] = {
                "status": guarded_reply.gate.status.value,
                "impact_paise": guarded_reply.gate.impact_paise,
                "allowed": guarded_reply.gate.allowed,
                "verdicts": [{"checker": v.checker, "status": v.status.value,
                              "reason": v.reason, "impact_paise": v.impact_paise}
                             for v in guarded_reply.gate.verdicts if v.status.value != "SKIP"],
            }

        # The demo records the same lifecycle a production integration sees.  It uses the
        # in-memory Razorpay-shaped gateway only when no test-mode gateway is configured.
        if guarded_reply.done and guarded_reply.gate and guarded_reply.gate.allowed and not session.get("razorpay"):
            from sakshi.gateway import StubGateway
            from sakshi.settlements import settlement_lines

            gateway = StubGateway()
            order_amount = guarded_reply.order_amount_paise or guarded_reply.cart.total_paise
            order = gateway.create_order(max(order_amount, 100), guarded_reply.cart.currency,
                                         receipt=session["receipt"].txn, notes=guarded_reply.gate.notes)
            guarded_agent.engine.record_order(session["receipt"].txn, order)
            payment = gateway.simulate_capture(order["id"], method="upi")
            guarded_agent.engine.record_payment(session["receipt"].txn, payment)
            settlement = settlement_lines([payment], fees=guarded_agent.engine.fees, orders={order["id"]: order})[0]
            guarded_agent.engine.record_settlement_line(session["receipt"].txn, settlement)
            reconcile = guarded_agent.engine.reconcile(session["receipt"].txn, payment, settlement=settlement,
                                                        intent=session["receipt"], cart=guarded_reply.cart, order=order)
            seal = guarded_agent.engine.seal_transaction(session["receipt"].txn)
            session["razorpay"] = {"mode": "stub", "order": order, "payment": payment,
                                    "settlement": settlement, "reconcile": reconcile.summary(),
                                    "evidence_sealed": seal is not None}
        if session.get("razorpay"):
            guarded_entry["razorpay"] = {
                "mode": session["razorpay"]["mode"],
                "order_id": session["razorpay"]["order"]["id"],
                "payment_id": session["razorpay"]["payment"]["id"],
                "evidence_sealed": session["razorpay"]["evidence_sealed"],
            }

        # Check for new speech blocks
        try:
            ledger = guarded_agent.engine.ledger
            new_count = ledger.conn.execute(
                "SELECT COUNT(*) FROM events WHERE type='speech.blocked'").fetchone()[0]
            if new_count > prev_count:
                guarded_entry["speech_intercepted"] = True
                new_events = ledger.conn.execute(
                    "SELECT payload FROM events WHERE type='speech.blocked' ORDER BY seq DESC LIMIT 1"
                ).fetchall()
                if new_events:
                    p = json.loads(new_events[0][0]) if isinstance(new_events[0][0], str) else new_events[0][0]
                    guarded_entry["speech_findings"] = p.get("findings", [])
        except Exception:
            pass

    except Exception as e:
        guarded_entry = {"text": f"Error: {e}", "cart": None, "done": False,
                         "gate": None, "speech_intercepted": False, "speech_findings": []}

    # Build pipeline steps for the agentic view
    pipeline = []
    if guarded_entry.get("speech_intercepted"):
        pipeline.append({"step": "Speech Guard", "action": "BLOCKED",
                         "detail": ", ".join(f.get("pattern","") for f in guarded_entry["speech_findings"]),
                         "before": naive_entry["text"], "after": guarded_entry["text"]})
    if guarded_entry.get("gate"):
        g = guarded_entry["gate"]
        for v in g.get("verdicts", []):
            pipeline.append({"step": v["checker"].replace("_", " ").title(),
                             "action": v["status"], "detail": v["reason"]})

    # Calculate savings (naive total - guarded total)
    savings_paise = 0
    naive_cart = naive_entry.get("cart")
    guarded_cart = guarded_entry.get("cart")
    if naive_cart and guarded_cart:
        n_total = naive_cart.get("total_paise", 0) if isinstance(naive_cart, dict) else 0
        g_total = guarded_cart.get("total_paise", 0) if isinstance(guarded_cart, dict) else 0
        if n_total > g_total:
            savings_paise = n_total - g_total

    # These are the actual (privacy-safe) notes placed on the demo order, never raw utterance text.
    order_notes = (session.get("razorpay") or {}).get("order", {}).get("notes")

    # Get diary session ID for linking
    diary_session_id = sid

    return jsonify({
        "naive": naive_entry,
        "guarded": guarded_entry,
        "pipeline": pipeline,
        "different": naive_entry["text"] != guarded_entry["text"],
        "savings_paise": savings_paise,
        "order_notes": order_notes,
        "diary_session_id": diary_session_id,
    })

# ── Sealed Diary (Audit Trail) ───────────────────────────────────────
def _evidence_context(session_id):
    """Resolve either an agent checkout session or the primary OfferLock journey."""
    session = _sessions.get(session_id)
    if session:
        agent = session.get("agent") or session.get("guarded")
        if not agent:
            return None
        return {
            "kind": "agent_checkout", "txn": session["receipt"].txn,
            "ledger": agent.engine.ledger, "signer": agent.engine.signer, "session": session,
        }
    offer_session = _offer_evidence_sessions.get(session_id)
    if offer_session:
        return {"kind": "offer_lock", **offer_session}
    if session_id.startswith("offer-"):
        lock_id = session_id.removeprefix("offer-")
        lock = _find_offer_lock(lock_id)
        if lock is None:
            # Compatibility with older 12-character evidence-session URLs.
            store = _get_offer_store()
            lock = store.find_lock_by_prefix(lock_id) if store is not None else next(
                (value for key, value in _offer_locks.items() if key.startswith(lock_id)), None
            )
        if lock is not None:
            service = _get_offer_lock_service()
            return {"kind": "offer_lock", "txn": lock.txn, "lock": lock,
                    "ledger": service.ledger, "signer": service.signer}
    return None


@app.route("/api/diary/<session_id>")
def api_diary(session_id):
    """Return the full tamper-evident event chain and its signed-seal status."""
    context = _evidence_context(session_id)
    if not context:
        return jsonify({"error": "Session not found"}), 400
    try:
        ledger = context["ledger"]
        rows = ledger.chain(context["txn"])
        events = []
        for r in rows:
            events.append({
                "seq": r.seq, "ts": r.ts, "txn": r.txn, "type": r.type,
                "actor": r.actor, "payload": r.payload,
                "prev_hash": r.prev_hash[:12] + "..." if r.prev_hash else None,
                "hash": r.hash[:12] + "..." if r.hash else None,
            })
        signer = context.get("signer")
        return jsonify({"session_id": session_id, "events": events,
                        "chain_length": len(events), "tamper_evident": True,
                        "evidence_kind": context["kind"],
                        "signed_evidence_valid": bool(signer and signer.verify_latest_seal(ledger, context["txn"], signer.public_key_b64))})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Dispute Resolver ─────────────────────────────────────────────────
@app.route("/api/dispute/<session_id>")
def api_dispute(session_id):
    """Resolve a demo dispute from the same evidence chain, not a UI-only rule."""
    context = _evidence_context(session_id)
    if not context:
        return jsonify({"error": "Session not found"}), 400
    try:
        if context["kind"] == "offer_lock":
            lock = context["lock"]
            drift = context["ledger"].latest(context["txn"], "offer.drift.checked")
            status = (drift.payload if drift else {}).get("status", "ESCALATE")
            deltas = (drift.payload if drift else {}).get("deltas", [])
            signer = context["signer"]
            evidence = [
                {"section": "1. Buyer-approved Offer Lock", "items": {
                    "lock_id": lock.lock_id, "catalog_version": lock.terms.catalog_version,
                    "terms_hash": lock.terms.material_hash(), "approval_ref": lock.approval.approval_ref,
                    "key_id": lock.evidence.key_id, "signature": lock.evidence.signature,
                }},
                {"section": "2. Buyer-visible commercial terms", "items": lock.terms.as_dict()},
                {"section": "3. Post-consent fulfilment check", "items": {
                    "status": status, "deltas": deltas,
                    "action": "request new buyer confirmation" if status == "RECONFIRM" else "hold for human review",
                }},
                {"section": "4. Integrity and boundaries", "items": {
                    "ledger_verified": context["ledger"].verify()[0],
                    "signed_chain_seal_verified": signer.verify_latest_seal(context["ledger"], context["txn"], signer.public_key_b64),
                    "boundary": "No delivery or payment-dispute outcome is asserted without those external facts.",
                }},
            ]
            reason = ("Material commercial drift is recorded after consent; do not contest the buyer's claim on the old approval. "
                      "Obtain fresh confirmation or place the fulfilment in human review.")
            return jsonify({"session_id": session_id, "verdict": "ESCALATE", "reason": reason,
                            "evidence": evidence, "requires_human": True,
                            "stats": {"total_events": len(context["ledger"].chain(context["txn"])),
                                      "signed_evidence_valid": signer.verify_latest_seal(context["ledger"], context["txn"], signer.public_key_b64)}})

        session = context["session"]
        agent = session.get("agent") or session.get("guarded")
        if not agent:
            return jsonify({"error": "No agent in session"}), 400
        if session.get("dispute") is None:
            from sakshi.dispute import DisputeAgent, DisputeClaim

            session["dispute"] = DisputeAgent(agent.engine.ledger, agent.engine.merchant,
                                                fees=agent.engine.fees, signer=agent.engine.signer).decide(
                session["receipt"].txn, DisputeClaim("wrong_item", "demo dispute: wrong item"))
        result = session["dispute"]
        return jsonify({"session_id": session_id, "verdict": result.recommendation,
                        "reason": "; ".join(result.reasons), "evidence": result.evidence_pack,
                        "requires_human": result.requires_human,
                        "stats": {"total_events": len(agent.engine.ledger.chain(session["receipt"].txn)),
                                  "signed_evidence_valid": agent.engine.signed_evidence_valid(session["receipt"].txn)}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Bank Narration Matcher ───────────────────────────────────────────
@app.route("/api/narration", methods=["POST"])
def api_narration():
    """Match a bank narration string against known customers/vendors."""
    data = request.json or {}
    narration = data.get("narration", "")
    # Demo customer database
    customers = [
        {"id": "C001", "name": "ABC Corp", "aliases": ["ABCCORP", "ABC CORP", "ABC CORPORATION"]},
        {"id": "C002", "name": "Global Textiles", "aliases": ["GLOBALTEX", "GLOBAL TEXTILES", "GTEXTILES"]},
        {"id": "C003", "name": "Zenith Foods", "aliases": ["ZENITHFOODS", "ZENITH FOODS", "ZF FOODS"]},
        {"id": "C004", "name": "BlueStar Exports", "aliases": ["BLUESTAR", "BLUE STAR", "BSE"]},
        {"id": "C005", "name": "Metro Fresh", "aliases": ["METROFRESH", "METRO FRESH", "MF"]},
    ]
    narration_upper = narration.upper().replace("/", " ").replace("-", " ").replace("_", " ")
    tokens = narration_upper.split()

    matches = []
    for c in customers:
        score = 0
        matched_token = ""
        all_names = [c["name"].upper()] + [a.upper() for a in c["aliases"]]
        for name in all_names:
            for token in tokens:
                if token in name or name in token:
                    s = len(token) / max(len(name), len(token))
                    if s > score:
                        score = s
                        matched_token = token
        if score > 0.3:
            matches.append({"customer_id": c["id"], "customer_name": c["name"],
                            "confidence": round(min(score, 1.0), 2), "matched_token": matched_token})

    matches.sort(key=lambda m: m["confidence"], reverse=True)

    # Parse narration metadata
    parsed = {"type": "UNKNOWN", "ref": None, "amount": None}
    if "NEFT" in narration_upper: parsed["type"] = "NEFT"
    elif "RTGS" in narration_upper: parsed["type"] = "RTGS"
    elif "IMPS" in narration_upper: parsed["type"] = "IMPS"
    elif "UPI" in narration_upper: parsed["type"] = "UPI"
    import re
    ref_match = re.search(r'REF\s*(\w+)', narration_upper)
    if ref_match: parsed["ref"] = ref_match.group(1)

    return jsonify({"narration": narration, "parsed": parsed,
                    "matches": matches, "matched": len(matches) > 0,
                    "best_match": matches[0] if matches else None})

# ── Settlement Check (FX + Fees + Refund) ────────────────────────────
@app.route("/api/settlement", methods=["POST"])
def api_settlement():
    """Run FX rate, fee, and refund burn checks on a settlement record."""
    data = request.json or {}

    results = []

    # FX Rate Check
    if data.get("fx_check"):
        fx = data["fx_check"]
        # Simulate: compare quoted rate vs FBIL
        quoted = fx.get("quoted_rate", 83.50)
        official = fx.get("official_rate", 83.90)
        spread_bps = abs(quoted - official) / official * 10000
        results.append({
            "checker": "fx_rate",
            "status": "FLAG" if spread_bps > fx.get("band_bps", 100) else "PASS",
            "detail": f"Quoted: {quoted:.2f}, Official (FBIL): {official:.2f}, Spread: {spread_bps:.0f} bps",
            "impact": f"{spread_bps:.0f} bps spread",
            "currency_pair": fx.get("pair", "USD/INR"),
        })

    # Fee Check
    if data.get("fee_check"):
        fee = data["fee_check"]
        expected_pct = fee.get("plan_rate_pct", 2.0)
        actual_pct = fee.get("actual_rate_pct", 3.5)
        order_paise = fee.get("order_paise", 100000)
        expected_fee = int(order_paise * expected_pct / 100)
        actual_fee = int(order_paise * actual_pct / 100)
        diff = actual_fee - expected_fee
        results.append({
            "checker": "settlement_fee",
            "status": "BLOCK" if diff > 0 else "PASS",
            "detail": f"Plan: {expected_pct}% (₹{expected_fee/100:.0f}), Charged: {actual_pct}% (₹{actual_fee/100:.0f})",
            "impact_paise": diff,
            "overcharge": diff > 0,
        })

    # Refund Burn Check
    if data.get("refund_check"):
        ref = data["refund_check"]
        order_paise = ref.get("order_paise", 100000)
        mdr_pct = ref.get("mdr_pct", 2.0)
        gst_pct = 18.0
        mdr_fee = int(order_paise * mdr_pct / 100)
        gst_on_fee = int(mdr_fee * gst_pct / 100)
        burn = mdr_fee + gst_on_fee
        results.append({
            "checker": "refund_burn",
            "status": "FLAG",
            "detail": f"MDR: ₹{mdr_fee/100:.0f} + GST: ₹{gst_on_fee/100:.0f} = ₹{burn/100:.0f} lost on refund",
            "burn_paise": burn,
            "mdr_paise": mdr_fee,
            "gst_paise": gst_on_fee,
        })

    return jsonify({"checks": results, "total_issues": sum(1 for r in results if r["status"] != "PASS")})

# ── AI Explain (Gemini-powered verdict explanation) ──────────────────
@app.route("/api/explain", methods=["POST"])
def api_explain():
    """Use Gemini to explain a verdict in plain English — shows real LLM reasoning."""
    data = request.json or {}
    verdict_text = data.get("verdict", "")
    context = data.get("context", "")

    try:
        from sakshi.llm.provider import provider_from_env
        provider = provider_from_env()
        prompt = f"""You are SettleX Atlas, an AI witness for agent commerce. Explain this verdict to a non-technical business owner in 2-3 sentences. Be specific about what happened, why it matters, and what the evidence layer did about it.

Verdict: {verdict_text}
Context: {context}

Respond with a JSON object: {{"explanation": "...", "risk_level": "high|medium|low", "money_impact": "description of financial impact"}}"""

        raw = provider.complete(prompt, system="You are SettleX Atlas, a strict financial auditor for Indian merchants. Answer only with the JSON requested.", json_mode=True)
        result = json.loads(raw) if raw.strip().startswith("{") else {"explanation": raw, "risk_level": "medium", "money_impact": "unknown"}
        return jsonify(result)
    except Exception as e:
        return jsonify({"explanation": f"LLM unavailable: {e}", "risk_level": "unknown", "money_impact": "unknown"})

# ── Self-Improving Memory ────────────────────────────────────────────
@app.route("/api/memory/correct", methods=["POST"])
def api_memory_correct():
    """Store a human correction — demonstrates self-improving learning."""
    data = request.json or {}
    checker = data.get("checker", "unknown")
    correction = data.get("correction", "PASS")
    reason = data.get("reason", "")

    from sakshi.memory import CorrectionMemory
    db = ROOT / "data" / "memory.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    mem = CorrectionMemory(str(db))
    row_id = mem.learn(
        merchant="demo",
        kind="judge_override",
        key=checker,
        value={"correction": correction, "original": data.get("original_verdict", "")},
        note=reason,
        who="human_demo"
    )

    return jsonify({"stored": True, "correction_id": row_id, "total_corrections": len(mem),
                    "message": f"Atlas will remember: '{reason}'. Future similar cases will be auto-classified."})

@app.route("/api/memory/list")
def api_memory_list():
    """Show all stored corrections."""
    from sakshi.memory import CorrectionMemory
    db = ROOT / "data" / "memory.db"
    if not db.exists():
        return jsonify([])
    return jsonify(CorrectionMemory(str(db)).all())

if __name__ == "__main__":
    print("\n  SettleX Atlas Interactive Demo")
    print("  http://localhost:5000\n")
    app.run(debug=False, port=5000)
