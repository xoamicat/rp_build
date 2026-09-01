# Buildathon validation record

This is a concise record of what was actually exercised on **29–30 August 2026**.
It separates real external calls from local/synthetic tests so a reviewer can
reproduce or challenge every claim.

## End-to-end proof

| Check | Result | Evidence / reproduction |
|---|---|---|
| Bounded AI composition | Passed with the configured Gemini provider, `gemini-3.1-flash-lite` | The composer selected only `PZ-MARG`; server-derived total was ₹680; the model surfaced the unresolved Saturday-delivery detail. Run the violet dashboard panel or `POST /api/offer-drafts`. |
| AI safety boundary | Passed | Unit tests show model-supplied price is ignored, unknown SKU is rejected, and an AI draft is explicitly marked `consent_captured: false`. |
| Offer Lock and post-consent drift | Passed | A higher price, added garlic bread, later delivery and return-policy change return `RECONFIRM`, with a field-level diff. |
| Evidence and buyer-claim posture | Passed | The Offer Lock’s AI provenance, approval, drift check and Ed25519 chain seal appear in one diary. A changed-offer claim returns `ESCALATE`, never an automatic contest based on stale consent. |
| Razorpay Test Mode order | Passed, unpaid | [Safe artifact](data/evidence/razorpay-test-mode-atlas_verify_1787943567.json): Razorpay order `order_TVIUO2IbdiKcS3` was created and fetched via the official SDK. It contains all 15 permitted notes, including `atlas_lock` and `atlas_sig`; no secret, raw buyer text or payment capture is stored. |
| Durable-flow Test Mode order | Created, unpaid | The upgraded dashboard adapter created Razorpay Test Mode order `order_TVKcJtiEERZ8rb` from a durable signed Offer Lock, returned `status: created`, `₹100`, and all 15 proof-note keys. The separate external fetch was not rerun because the environment blocked further external calls; this row does not claim a fresh fetch or payment capture. |
| Real Razorpay Test Mode capture | Passed, public webhook rehearsal | A Test Mode checkout was completed through the public-HTTPS webhook path. The local durable evidence store recorded three HMAC-verified `rzp.payment.captured` events; browser callbacks were not promoted to payment evidence. The database is git-ignored and contains no submission secret. |
| Browser-to-webhook adapter | Passed, local integration test | The dashboard can create a guarded `rzp_test_` order only, open Razorpay Checkout only after an explicit user click, treat its browser return as untrusted, and write `rzp.payment.captured` only after raw-body HMAC validation. The test uses a Razorpay-shaped fake gateway and a signed local webhook fixture; it is not presented as an external Razorpay payment capture. |
| Order-bound webhook evidence | Passed, local integration test | A correctly HMAC-signed webhook for a different `order_id` is rejected with `409`; it cannot be attached to the Offer Lock journey. |
| AI clarification boundary | Passed, unit test | AI uncertainty creates a clarification question and server-side signing gate; browser-supplied provenance is not trusted. |
| FX Promise Envelope | Passed, unit + API test | The default $10 example calculates ₹957.00 on the payment day and ₹972.00 on the dispute day: a ₹15.00 labelled delta/reserve, not a claimed bank quote or refund. |
| Subscription update preflight | Passed, unit + API test | A proposed renewal term change returns `RECONFIRM` and `razorpay_patch_permitted: false`; the endpoint never calls Razorpay. |
| Strict internal `pass^5` | Passed, synthetic heuristic run | 14/14 guarded scenarios passed every one of five repeats. It is regression evidence only—not a τ-bench or production reliability result. |
| Direct URL routes | Passed | `/offer-lock`, `/release`, `/evidence/<session-id>`, `/claims/<session-id>`, and each sandbox route return the same dashboard shell. The client updates address-bar history and Browser Back/Forward restores the selected page. |
| Durable signed evidence | Passed, local restart proof | A git-ignored local Ed25519 development key enables the durable SQLite Offer Lock store. A signed lock was created, the server was restarted, then the same `/evidence/<full-lock-id>` URL loaded with a valid chain seal. This proves persistence mechanics, not KMS/HSM custody. |
| Kasauti release run | Passed, synthetic | `python scripts/run_kasauti.py --k 1 --llm heuristic` generated [run manifest](data/runs/run-manifest.json), `naive.jsonl`, and `guarded.jsonl`. It is a reproducible fixture run, not a production metric. |

## Automated checks

```bash
python -m pytest -q
python -m py_compile sakshi/offer_composer.py sakshi/offer_lock.py sakshi/dispute.py ui/server.py scripts/verify_razorpay_test_mode.py
```

The suite has **104 passing tests**. It covers the ledger, signature and key-registry controls, order-bound webhooks, Offer Lock drift policy, notes capacity, durable Offer Lock persistence, constrained AI clarification, the browser-facing Test Mode adapter, direct URL routes, FX Promise arithmetic, subscription-update preflight, disputes, settlement/recon adapters, and Kasauti harness.

## Reviewer commands

```bash
python ui/server.py
# Browser: http://127.0.0.1:5000

python scripts/run_kasauti.py --k 1 --llm heuristic
python scripts/report.py

# Requires rzp_test_ credentials. Creates one unpaid order only; refuses live keys.
python scripts/verify_razorpay_test_mode.py --create
```

## Scope boundaries

- The Test Mode proof demonstrates creation/retrieval, `notes` persistence and real HMAC-verified `payment.captured` webhook receipt. It does **not** demonstrate real-money payment, settlement, delivery of goods or product quality.
- The public-HTTPS Test Mode webhook rehearsal was completed on the local development run. A fresh clone must configure its own public endpoint and Dashboard webhook to reproduce it; the durable local evidence database is deliberately git-ignored.
- The current persistent key is a git-ignored local development key generated by `scripts/generate_evidence_key.py`. A production deployment still needs KMS/HSM custody, rotation, revocation and a public-key allow-list.
- The dashboard defaults to an ephemeral signer, but this local run enabled its git-ignored durable development key/store. Production still requires durable encrypted storage, a KMS/HSM key, authentication, key rotation and an OMS connector.
- The Kasauti result uses scripted customers, synthetic settlement rows and an intentionally weak baseline. Its manifest makes that explicit.
- AI proposes a draft only. It has no authority to grant consent, choose a final payment amount, create an order, fulfil an order, issue a refund, or decide an Offer Lock drift verdict.
- The FX Promise Envelope evaluates merchant-supplied labelled facts; it is not a live FX feed, a Razorpay rate, a conversion service, a hedge or a dispute decision.
- The subscription preflight returns a release receipt only. A real merchant worker must enforce it immediately before its authenticated Razorpay subscription update call.
