# SettleX Atlas — Agentic Offer Lock

> **The payment was valid. The promise changed.**

SettleX Atlas is a merchant-side proof and release layer for agentic commerce on Razorpay. It locks the final buyer-visible commercial promise—items, total, delivery, return, substitution and renewal terms—then requires a fresh buyer confirmation when that promise materially changes before shipment, substitution or renewal.

**Razorpay moves and validates money. Atlas protects the commercial promise around it.**

Built for Razorpay Buildathon 2026 · Open Innovation

## The 20-second pitch

An AI shopping agent can make a payment that is perfectly authorised and still create the wrong commercial outcome: a different item ships, delivery moves, a fee appears, or a renewal changes. The merchant—not the payment rail—handles that dispute and refund. Atlas creates a signed Offer Lock after the buyer sees the final offer, puts compact proof references on the Razorpay Order, and checks the live merchant terms again before the next irreversible action.

If nothing changed, Atlas returns `ALLOW`. If the promise changed, it returns `RECONFIRM` with a field-level diff. If merchant identity or currency changed, it returns `ESCALATE`.

## The gap—precisely

Razorpay Agent Studio already provides platform-level money validation, merchant-configured guardrails, action audit trails, dark-pattern screening and agent accountability. Atlas does **not** claim to replace those capabilities. [Razorpay’s Agent Studio principles](https://razorpay.com/blog/?p=26508) say as much.

| Existing layer | Atlas adds |
|---|---|
| Razorpay validates the money action against configured amount, scope and compliance boundaries. | A signed snapshot of the complete buyer-visible **commercial** offer and a later comparison against fulfilment or renewal terms. |
| Agent Studio records agent actions and screens communications. | A portable proof package usable when the buyer agent, merchant OMS, fulfilment system or support workflow sits outside Agent Studio. |
| Razorpay payment lifecycle signals tell a merchant a payment happened. | Atlas treats the HMAC-verified webhook as payment truth, then links it to the original offer and any later drift decision. |

This matters because Razorpay has stated that an incorrect agent order remains a merchant dispute/refund problem, while Razorpay remains responsible for payment security. [MediaNama’s March 2026 report](https://www.medianama.com/2026/03/223-razorpay-sarvam-ai-ai-agent-payments-indus-app/) documents that distinction.

**Atlas is not:** a payment gateway, a generic Agent Studio clone, a chargeback auto-responder, a settlement dashboard, or an AP2 implementation.

## How it works

```text
Buyer / external agent             Merchant systems                     Razorpay
─────────────────────            ──────────────────                   ─────────
Natural-language request ──► bounded AI draft ──► server hydrates trusted catalogue terms
                                      │
Buyer sees and confirms final offer ─┴─► Ed25519-signed Offer Lock
                                                │
                                         create Razorpay Test Order ──► compact proof refs in notes
                                                │                                 │
                                      payment webhook ◄──────────────────────────┘
                                                │
Before shipment / substitution / renewal ──► compare current terms with lock
                                                │
                                      ALLOW | RECONFIRM | ESCALATE
```

### Inputs and outputs in a real merchant integration

| System | Atlas receives | Atlas returns |
|---|---|---|
| Buyer agent or checkout | a structured draft plus opaque approval reference | buyer-visible final-offer summary for confirmation |
| Merchant catalogue / OMS | canonical SKUs, price, delivery, policy and renewal terms | signed Offer Lock; later a field-level drift decision |
| Razorpay Orders API | amount, currency and safe proof references | a normal Razorpay order—Atlas never handles payment credentials |
| Razorpay webhook | raw, HMAC-signed lifecycle event | privacy-safe payment evidence appended to the signed journey |
| Fulfilment / subscription service | the current terms immediately before action | `ALLOW`, `RECONFIRM`, or `ESCALATE` |
| Support / disputes | buyer claim plus the linked journey | evidence pack and a recommendation; never an automatic final dispute decision |

## What is implemented in this repository

- **Offer Lock:** canonicalised, versioned commercial terms signed with Ed25519.
- **Material-drift policy:** price increase, extra/removed items, later delivery, return-policy, substitution-policy and renewal changes require reconfirmation; merchant or currency changes escalate.
- **Bounded AI:** Gemini or Ollama may create a structured draft only. Server code hydrates merchant-controlled terms. AI cannot grant consent, decide the payable amount, fulfil, refund, or determine a drift verdict.
- **Razorpay Test Mode order adapter:** rejects live keys, creates a guarded Razorpay Order through the official SDK, and attaches safe proof references.
- **Webhook truth boundary:** browser success is deliberately untrusted. Only a raw-body HMAC-verified Razorpay webhook may write `rzp.payment.captured` evidence.
- **Durable local evidence mode:** a git-ignored local development signing key and SQLite store retain signed locks across a restart. Production key custody is deliberately out of scope.
- **Settlement Recon adapter:** normalises documented Recon fields and refuses unlinked rows before they become evidence.
- **Kasauti release harness:** adversarial synthetic scenarios for agent and communication failures, with manifest/provenance rather than invented production metrics.

## Proof status: what a judge can and cannot claim

| Claim | Status | Evidence |
|---|---|---|
| A signed lock detects commercial drift | demonstrated and tested | 95 automated tests; field-level `RECONFIRM` demo |
| A guarded Razorpay **Test Mode** Order can be created | demonstrated | safe order artifact under [`data/evidence/`](data/evidence/) |
| Atlas survives a local restart with durable evidence enabled | demonstrated | signed lock reopened after restart |
| A browser checkout return is not payment proof | implemented and tested | explicit pending state in the UI and tests |
| A real Razorpay `payment.captured` webhook was received | **not yet claimed** | requires a public webhook rehearsal |
| A real merchant OMS blocks shipment or renewal | **not yet claimed** | integration contract and pilot plan supplied; no merchant pilot invented |
| Production KMS/HSM, encryption, tenancy and retention controls | **not implemented** | required before production |

## Run locally

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
py -m pytest -q
py ui\server.py
```

Open [http://127.0.0.1:5000/offer-lock](http://127.0.0.1:5000/offer-lock).

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m pytest -q
python3 ui/server.py
```

Leave Razorpay keys blank for the offline demo. Do not commit `.env` or `.atlas-evidence.env`.

## Five-minute judge walkthrough

1. Open `/offer-lock` and generate a constrained offer draft.
2. Show the buyer-visible terms, explicit confirmation, signature and proof references.
3. Change a material term such as delivery, price or return policy; Atlas returns `RECONFIRM` with the exact diff.
4. Open the signed evidence journey at `/evidence/<session-id>`.
5. In the optional Test Mode panel, show that an order is allowed only after a signed lock, uses only `rzp_test_` keys, and stays pending until a verified webhook arrives.
6. Open `/release` to show release scenarios and their simulation boundary.

The deck and timed script are available in [SettleX_Atlas_Judge_Deck.pptx](SettleX_Atlas_Judge_Deck.pptx) and [PITCH_AND_VIDEO.md](PITCH_AND_VIDEO.md).

### Deep links

| Route | Purpose |
|---|---|
| `/offer-lock` | primary Offer Lock and drift-check demo |
| `/evidence/<session-id>` | signed evidence journey |
| `/claims/<session-id>` | buyer-claim review from the evidence chain |
| `/release` | release-test dashboard |
| `/settlements` | settlement reconciliation sandbox |
| `/checkout-safety`, `/intent-check`, `/speech-check` | supporting safety demos |

## Razorpay Test Mode webhook rehearsal

Adding `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` enables Test Mode **order creation**. It does not prove a payment was captured.

To produce the final evidence:

1. Add a separate `RAZORPAY_WEBHOOK_SECRET` to local `.env`.
2. Start Atlas and expose it temporarily with a public endpoint.
3. In Razorpay Dashboard **Test Mode**, configure `YOUR-PUBLIC-URL/webhooks/razorpay` and subscribe to `payment.captured`.
4. Create a guarded Test Mode order, complete a Test Mode payment, then inspect the signed journey.

Razorpay requires a public URL for webhook delivery; the detailed safe runbook is in [WEBHOOK_REHEARSAL.md](WEBHOOK_REHEARSAL.md). The app accepts a payment only after HMAC verification, deduplicates webhook events, and never promotes a client-side callback to payment evidence. [Razorpay webhook docs](https://razorpay.com/docs/webhooks/)

### About Order `notes`

Razorpay supports at most 15 `notes` key-value pairs, with each value capped at 256 characters. The Test Mode adapter validates this limit and uses safe proof references—not buyer text or payment credentials. [Orders API reference](https://razorpay.com/docs/api/orders/create/)

The current demo intentionally uses all 15 supported keys to make every boundary inspectable. A production adapter should compress Atlas data to two or three references, leaving room for the merchant’s own metadata. Razorpay `notes` carry Atlas references; Razorpay does not validate the Atlas signature.

## AI and reliability: honest boundary

Atlas uses AI where it is useful—turning natural language into a constrained draft—and deterministic code where it is consequential. This is intentional: financial/fulfilment consent should not depend on model confidence.

Kasauti currently runs 14 reproducible synthetic scenarios with run provenance, fixed seeds and stated assumptions. It is a release harness, **not** τ-bench and not a claim of real-world agent reliability. Before production, run repeated `pass^k` evaluation with merchant policies, production-like tools and human-labelled outcomes. τ-bench introduced `pass^k` because one successful agent run is not evidence that an agent is reliable. [τ-bench paper](https://arxiv.org/abs/2406.12045)

## Security and privacy model

- The full offer snapshot is canonicalised and signed; order notes retain only compact references.
- Raw buyer conversation, payment credentials, card data, UPI VPAs, phone numbers and email addresses are excluded from the lock, notes and submitted artifacts.
- Webhook HMAC is verified over the exact raw body before JSON parsing; event IDs/fingerprints prevent duplicate evidence.
- A verified payment event proves the webhook body came from Razorpay with the configured secret. It does **not** prove delivery, quality or buyer identity.
- The local durable mode is for demo continuity, not production custody. Production requires KMS/HSM keys, rotation/revocation, encrypted storage, tenant isolation, authN/authZ, retention policy, monitoring, rate limits and a security review.

See [SECURITY.md](SECURITY.md) for the threat model and [INTEGRATION.md](INTEGRATION.md) for the deployable integration contract.

## Standards and regulatory alignment—without overclaiming

- **AP2:** Atlas is *inspired by* the idea of a signed commercial mandate and later dispute evidence, but it does not emit AP2 Checkout/Payment Mandate JWTs or AP2 receipts. [Google AP2 specification](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/specification.md)
- **Dark patterns:** the speech guard covers relevant patterns, but Razorpay Agent Studio already screens agent communication; this is supporting assurance, not Atlas’s moat. [CCPA Dark Patterns Guidelines](https://www.pib.gov.in/PressReleasePage.aspx?PRID=1983994)
- **Disputes / FX:** international dispute deductions may use the conversion rate on the dispute date. Atlas models this as a supporting risk check; it is not its headline value. [Razorpay disputes FAQ](https://razorpay.com/docs/payments/disputes/faqs/)
- **NPCI UAP / CERT-In:** these are signals that auditability and agentic-payment controls matter. The NPCI Unified Agent Protocol was reported as under development; Atlas does not claim UAP compliance. [Business Standard reporting](https://www.business-standard.com/finance/news/india-may-allow-agentic-ai-led-upi-transactions-under-new-npci-protocol-126070801343_1.html), [CERT-In report release](https://www.cert-in.org.in/s2cMainServlet?pageid=PUBWEL03)

## Repository map

```text
ui/                    Flask dashboard, deep-link routing and Test Mode UI
sakshi/offer_lock.py   canonical offer, signing and material-drift policy
sakshi/offer_store.py  durable privacy-safe local Offer Lock store
sakshi/webhooks.py     raw-body Razorpay HMAC verification and idempotency
sakshi/integration.py  guarded Order handoff contract
sakshi/settlements/    Recon normalisation and link validation
kasauti/               synthetic adversarial release harness
tests/                 unit, integration, routing and Test Mode boundary tests
docs in root/          pitch, demo, security, integration, pilot and validation material
```

## Further reading

- [Gap and overlap analysis](GAP_ANALYSIS.md)
- [Submission brief](SUBMISSION.md)
- [Integration contract](INTEGRATION.md)
- [Security model](SECURITY.md)
- [Validation ledger](VALIDATION.md)
- [Pilot plan](PILOT_PLAN.md)
- [Demo guide](DEMO.md)
- [Webhook rehearsal](WEBHOOK_REHEARSAL.md)

## The path to a real 9/10

1. Complete one HMAC-verified Test Mode capture over public HTTPS.
2. Connect a real OMS or subscription release hook and demonstrate a shipment/renewal refusal on `RECONFIRM`.
3. Compress Order notes, add tenant authentication and move signing keys to managed custody.
4. Produce a repeated `pass^5` agent evaluation with human-reviewed outcomes.
5. Run three genuine merchant/operations discovery interviews; publish only consented findings.

Until then, Atlas is a strong, honest buildathon prototype—not a production deployment.
