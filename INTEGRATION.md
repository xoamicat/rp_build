# Razorpay integration contract — Agentic Offer Lock

SettleX Atlas integrates around Razorpay; it does not process, store, or replace payment credentials. Its primary boundary is the commercial offer an external buyer agent displayed, not the payment rail itself.

## 1. Configure secrets

Copy `.env.example`. Use Razorpay **test-mode** API keys while building. Configure `RAZORPAY_WEBHOOK_SECRET` from the Dashboard webhook configuration. Put `SAKSHI_EVIDENCE_PRIVATE_KEY_B64` in a secret manager and deploy its public-key/key-id allow-list to the evidence verifier.

Never generate the production evidence key inside the web process or commit it to `.env`.

## 2. Let AI draft—but never approve—the buyer-visible offer

The buyer agent can use `OfferComposer` with a configured Gemini or Ollama provider to turn a
natural-language request into a typed draft. Its JSON schema accepts **only** a merchant-catalogue
SKU and a positive quantity. The server hydrates price, delivery and policy terms from merchant
systems; unknown SKUs, duplicated lines, invalid quantities and malformed JSON are rejected.

Persist the provider/model and input/output hashes as provenance, not raw buyer conversation or
raw model output. Render the resulting draft to the buyer. Do not create a lock until the buyer
explicitly confirms it. The LLM never chooses a payment action, grants consent or decides the
post-consent drift result.

## 3. Lock a buyer-visible offer before the Razorpay call

The merchant's chat/voice/LLM agent passes a **structured offer snapshot** after it has rendered the final buyer-visible card or summary. It contains only material terms: merchant and catalogue version, SKU/quantity, price, tax/shipping, delivery promise, return-policy version, substitution rule, renewal summary and an opaque buyer approval reference.

```python
from sakshi.evidence import EvidenceSigner
from sakshi.ledger import Ledger
from sakshi.offer_lock import BuyerApproval, OfferLine, OfferLockService, OfferTerms

ledger = Ledger("/var/lib/atlas/evidence.db")
signer = EvidenceSigner.from_env(settings.evidence_private_key_b64, settings.evidence_key_id)
if signer is None:
    raise RuntimeError("production offer locks require SAKSHI_EVIDENCE_PRIVATE_KEY_B64")

terms = OfferTerms(
    merchant_id="merchant_123",
    offer_id="catalogue-offer-123",
    catalog_version="catalogue-2026-08-28.4",
    lines=(OfferLine("TSHIRT-BLK-M", "Black tee, M", 1, 129900),),
    shipping_paise=9900,
    delivery_by="2026-09-03",
    return_policy_version="returns-v7",
    substitution_policy="no_substitution",
    renewal_summary=None,
)
approval = BuyerApproval(
    approval_ref="opaque-buyer-approval-id",
    playback="One black tee, size M, ₹1,398 including delivery; delivery by 3 September; no substitutions.",
    channel="chatgpt_app",
    principal_ref="opaque-session-id",
)
offer_lock = OfferLockService(signer, ledger).lock(txn="atlas_txn_123", terms=terms, approval=approval)
```

The full signed snapshot belongs in the merchant's encrypted evidence store. `offer_lock.note_fields()` produces only `atlas_lock`, `atlas_ver`, `atlas_kid` and `atlas_sig` for the Razorpay Order. Never place raw chat, an email address, a phone number or an address in `notes`.

## 4. Create the Razorpay order with the signed lock

```python
from sakshi.checkers import default_stage1, default_stage2
from sakshi.config import Settings
from sakshi.engine import Engine
from sakshi.evidence import EvidenceSigner
from sakshi.gateway import gateway_from_env
from sakshi.integration import SakshiCheckout
from sakshi.ledger import Ledger
from sakshi.models import MerchantConfig
from sakshi.offer_lock import OfferLock

settings = Settings.from_env()
signer = EvidenceSigner.from_env(settings.evidence_private_key_b64, settings.evidence_key_id)
if signer is None:
    raise RuntimeError("production checkout requires SAKSHI_EVIDENCE_PRIVATE_KEY_B64")

merchant = MerchantConfig(extra={"require_signed_evidence": True})
engine = Engine(Ledger(settings.db_path), merchant, default_stage1() + default_stage2(), signer=signer)
checkout = SakshiCheckout(engine, gateway_from_env(settings))
# `offer_lock` must have the same txn and be signed by the configured trusted key.
guarded_order = checkout.create_order(
    intent, cart, receipt="merchant-order-reference", content=agent_context, offer_lock=offer_lock
)
```

`SakshiCheckout` creates the order only for `PASS` or `FLAG`. `BLOCK` and `ASK_HUMAN` never call the gateway. If an OfferLock is provided, it must use the transaction ID and trusted signing key; its reference is merged into Razorpay-safe `notes`. When it shares the intent proof's key, the merge uses exactly the documented 15-key notes budget.

## 5. Recheck before fulfilment or renewal

Before an OMS creates a shipment, an order-management worker swaps a SKU, or a subscription engine renews, it submits the current terms to the same OfferLock service:

```python
decision = offer_lock_service.check(offer_lock, current_terms)
if decision.status == "ALLOW":
    fulfil_order()
elif decision.status == "RECONFIRM":
    send_buyer_change_summary(decision.deltas)
else:  # ESCALATE: seller/currency identity change
    place_in_human_review_queue(decision.deltas)
```

`RECONFIRM` is raised for extra/removed items, higher price, later delivery, return-policy, substitution-policy or renewal changes. A price decrease is recorded but can proceed; merchant/currency changes escalate. The response is a diff, not a black-box risk score.

## 6. Receive payment truth through a verified webhook

Run the proxy in test mode or deploy its webhook route alongside the merchant integration:

```bash
python -m sakshi.proxy.app
# POST https://your-domain/webhooks/razorpay
```

The route checks `X-Razorpay-Signature` against the **raw body** before parsing it. It uses Razorpay's `x-razorpay-event-id` as the primary idempotency key (falling back to a SHA-256 raw-body fingerprint), maps supported events to ledger events, and discards contact/card fields. A missing webhook secret returns `503`; a bad signature returns `401`.

Supported mappings: `payment.captured`, `refund.created`, `refund.processed`, and payment-dispute events. Add an explicit mapping and test for any event type your merchant uses—do not silently rely on a generic event.

The buildathon adapter records the accepted event synchronously so its behavior is inspectable. A production deployment should verify the signature, enqueue the raw event/idempotency key, return `200` promptly, and process the queue asynchronously; this avoids webhook retries caused by a slow database or reconciliation call.

## 7. Reconcile settlement and seal

Join Settlement Recon records by `order_id` and `notes.sakshi_txn`, call `engine.ingest_recon_line(txn, row)`, then `engine.reconcile(...)`. The adapter normalises the documented recon fields and refuses an unlinked/mislinked row before it becomes evidence. Once all expected facts are present, call `engine.seal_transaction(txn)`. A verifier must pin the expected public key for that `sakshi_kid`; merely trusting the public key attached to an evidence bundle is insufficient.

Razorpay references used by this integration:

- [Orders API](https://razorpay.com/docs/api/orders/create/?preferred-country=IN)
- [Payment webhooks](https://razorpay.com/docs/webhooks/payments/?preferred-country=IN)
- [Settlement Recon API](https://razorpay.com/docs/api/settlements/fetch-recon/?preferred-country=IN)
- [International-currency conversion fields](https://razorpay.com/docs/payments/international-payments/currency-conversion/?preferred-country=IN)

## 8. Demonstrate a real Test Mode order safely

With `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` set to Test Mode credentials, run:

```bash
python scripts/verify_razorpay_test_mode.py --create
```

The script refuses any key that does not begin `rzp_test_`. It creates one **unpaid** Order,
fetches it back through the official SDK and verifies that the Atlas and signed-intent references
survived in `notes`. Its generated artifact has the order ID, status and note keys only; no secret,
raw buyer text or capture is involved.

To verify an order created by the interactive adapter later, run:

```bash
python scripts/verify_razorpay_test_mode.py --verify-order-id order_xxx
```

It fetches the existing Test Mode order, validates the required Atlas/Sakshi note references and writes a safe artifact. It does not open Checkout, capture a payment or print credentials.

### Interactive Test Mode handoff

The local dashboard provides the same guarded path after an Offer Lock is signed:

1. **Create guarded Test Mode order** calls `POST /api/offer-locks/:lock_id/test-mode-order`. It refuses missing credentials and every non-`rzp_test_` key, runs the intent/cart gate, runs the pre-payment promise-to-order check, and uses the 15-key `notes` budget deliberately.
2. **Open Razorpay Test Checkout** loads Razorpay Checkout only after a person explicitly clicks it. The browser return is written as `checkout.client.returned`, labelled `pending_verified_webhook`; it never becomes payment evidence by itself.
3. Razorpay sends `payment.captured` to `POST /webhooks/razorpay`. Expose this route over public HTTPS and configure the Test Mode dashboard webhook. Atlas validates the raw body with `X-Razorpay-Signature`, deduplicates the event, records its privacy-safe fields, and seals the chain again.

`http://127.0.0.1:5000/webhooks/razorpay` is useful for local unit tests but cannot receive Razorpay's external webhook. Use a real deployment or an approved HTTPS tunnel for a live Test Mode rehearsal. Never put a webhook secret or a payment credential in the browser.

## 9. Release gate

Run Kasauti against the exact agent configuration before enabling checkout. Keep the generated `run-manifest.json` next to the JSONL results. It names the provider, scenario set, repeats, seed, and every simulated boundary so an evaluation cannot be mislabeled as a live-payment result.
