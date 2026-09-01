# SettleX Atlas — the receipt for the promise, not just the payment

> **The payment was valid. The promise changed. What should happen next?**

**SettleX Atlas** is a merchant-side proof and release layer for agentic
commerce, built for the **Razorpay AI Buildathon 2026 · Track 05: Open
Innovation**.

When an AI shopper pays, the payment may be perfectly authorised while the
commercial deal later changes: a price rises, an item is substituted, delivery
moves, a return policy changes, or a renewal is amended. The payment rail can
truthfully say *money moved*. The buyer can still truthfully say *that is not
what I agreed to*.

Atlas preserves the exact, buyer-visible commercial promise, then checks it
again immediately before a merchant fulfils, substitutes, or changes a
renewal. It returns one of three human-readable decisions:

```text
ALLOW       → the promise still matches; the merchant worker may continue
RECONFIRM   → a material term changed; ask the buyer again
ESCALATE    → merchant or currency identity changed; do not inherit consent
```

Razorpay continues to validate and move money. **Atlas protects the commercial
promise around that payment.**

---

## Why this should exist

The next commerce dispute may not begin with a failed payment. It may begin
with an AI agent doing exactly what it was allowed to do, while the product,
delivery, price, or renewal promise quietly changes afterwards.

This is especially relevant because agentic commerce is becoming real: Razorpay
now supports agentic payment journeys across in-app, LLM, and voice surfaces,
and UPI Reserve Pay enables consent-based, pre-authorised agent payments.
[Razorpay Agentic Payments](https://razorpay.com/agentic-payments/)

The gap Atlas targets is **post-consent commercial drift**:

```text
Buyer-visible offer             Payment                 Later merchant action
price · item · delivery   →   authorised   →   ship · substitute · renew
       │                                               │
       └──── signed Offer Lock ── compare again ───────┘
                                      │
                          ALLOW | RECONFIRM | ESCALATE
```

It is deliberately not a payment gateway, a checkout replacement, a generic
dispute bot, a settlement dashboard, or an Agent Studio clone.

## The Razorpay fit — and the honest overlap boundary

Razorpay Agent Studio already has serious capabilities: merchant-configured
agent boundaries, approval controls, action trails, dispute-response agents,
subscription recovery, settlement insights, and custom agents. Agentic Payments
already makes AI-native checkout possible. [Agent Studio](https://razorpay.com/agent-studio/)
[Agent Studio guardrails](https://razorpay.com/blog/razorpay-agent-studio-principles-guardrails-and-merchant-control/)

Atlas does **not** claim to replace any of them. Its narrow, complementary
proposition is a portable proof object that travels across systems which may
not live in the same product boundary: an external buyer agent, merchant
catalogue/OMS, Razorpay payment event, fulfilment worker, and support review.

| Razorpay’s role | Atlas’s complementary role |
|---|---|
| Validate and execute the money action under configured limits and controls. | Capture the complete buyer-visible commercial offer, then decide if it is still safe to carry into a later fulfilment or renewal action. |
| Emit payment lifecycle events. | Treat a raw-body HMAC-verified webhook as payment truth and attach it to the exact signed commercial promise. |
| Provide agent controls, audit trails, and dispute workflows. | Give merchant operations and external buyer-agent flows a signed, field-level “what changed?” proof package. |
| Support subscription operations. | Put a release receipt immediately before a merchant’s subscription-change worker: changed promise → `RECONFIRM`, not silent continuation. |
| Process international payments and disputes. | Preserve displayed, payment-date, and dispute-date FX facts as separate evidence; explain the integer-paise delta without claiming to set a rate or decide a refund. |

The public product material does not describe this exact cross-system,
cryptographically verifiable commercial-promise lifecycle. That is the gap
hypothesis Atlas demonstrates; it is **not** a claim about Razorpay’s private
roadmap or internal capabilities.

---

## Research-to-design traceability

Atlas was designed by starting with the existing rails and asking a narrower
question: **what becomes hard when an authorised agentic payment meets a
mutable merchant workflow?** The answer was not “build another payment agent.”
It was “make the buyer-visible promise independently reviewable at the next
irreversible action.”

This table records the public research basis as of **1 September 2026** and the
specific product decision it informed.

| Research finding | Why it matters | Atlas design response |
|---|---|---|
| The Buildathon explicitly asks for meaningful AI, a working product, evidence of value, execution, reliability, and depth; it calls verification capacity a bottleneck. [Buildathon brief](https://razorpay.com/buildathon/) | A glossy agent demo is not enough. | Atlas exposes what it knows, what it refuses to infer, and what it can prove in a signed evidence journey. |
| Razorpay Agentic Payments brings payments into in-app, LLM, and voice experiences; UPI Reserve Pay supports consent-based agent payments. [Agentic Payments](https://razorpay.com/agentic-payments/) | AI buyers can create valid payments across surfaces outside a merchant’s OMS. | The Offer Lock is designed to travel from an external buyer agent to merchant operations without collecting payment credentials. |
| Agent Studio already offers merchant boundaries, review-first operation, action audit trails, and specialist agents for disputes, subscriptions, and settlement operations. [Agent Studio](https://razorpay.com/agent-studio/) · [guardrails](https://razorpay.com/blog/razorpay-agent-studio-principles-guardrails-and-merchant-control/) | A generic “AI safety,” “reconciliation,” or “dispute” agent would overlap heavily. | Atlas does not compete with those agents; it supplies a signed commercial-state input for a later fulfilment, renewal, or support decision. |
| Razorpay Order `notes` allow at most 15 key-value pairs, each at most 256 characters. [Orders API](https://razorpay.com/docs/api/orders/create/) | Payment metadata is not a safe place for raw buyer conversation or a full commercial contract. | Atlas puts compact identifiers and signature references in Order notes; the full snapshot stays in merchant-side evidence storage. |
| Razorpay says webhook validation must use the exact raw request body, and documents `x-razorpay-event-id` for duplicate detection. [Webhook validation](https://razorpay.com/docs/webhooks/validate-test/) | A client-side “success” callback is neither authentic payment proof nor replay-safe evidence. | Only a raw-body HMAC-verified, deduplicated, Order-bound webhook can create `rzp.payment.captured` evidence. |
| Razorpay Subscription updates are a `PATCH` that can alter plan, quantity, timing, and customer-notification handling. [Update Subscription API](https://razorpay.com/docs/api/payments/subscriptions/update/) | A notification setting is not, by itself, proof that the buyer accepted a materially new commercial promise. | Atlas returns a release receipt immediately before the merchant worker calls the PATCH; material drift yields `RECONFIRM` and `razorpay_patch_permitted: false`. |
| Razorpay states that an international-dispute deduction can use the processing-bank conversion rate on the date the dispute is created, which may differ from the payment date. [Disputes FAQ](https://razorpay.com/docs/payments/disputes/faqs/) | One “FX rate” is not enough to explain a cross-border commerce outcome. | The FX Promise Envelope stores displayed, payment-date, and dispute-date facts separately and calculates only an explainable INR-paise delta. |
| Razorpay’s Settlement Recon endpoint returns payment, refund, transfer, and adjustment lines with identifiers and debit/credit fields. [Settlement Recon API](https://razorpay.com/docs/api/settlements/fetch-recon/) | Payment evidence must not be confused with an unlinked finance row. | Atlas normalises recon-shaped rows and refuses unlinked records before treating them as evidence. |
| AP2 defines checkout/payment mandates and receipts, including evidence at dispute time; it also requires deterministic verification regardless of whether a role is agentic. [AP2 specification](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/specification.md) | The direction of travel is verifiable intent, not unconstrained agent autonomy. | Atlas is AP2-inspired, not AP2-compliant: it signs merchant-side buyer-visible terms and uses deterministic drift checks; it does not emit AP2 mandates or JWT receipts. |
| τ-bench introduced `pass^k` because a single successful agent run is weak evidence of reliability. [τ-bench](https://arxiv.org/abs/2406.12045) | A one-click happy path is not a release criterion for AI near commerce. | Kasauti records a strict internal synthetic `pass^5` regression run with provenance. It is clearly labelled as non-production evidence. |

### Why the AI is meaningful—and deliberately bounded

Atlas does not use an LLM to make a money or consent decision. It uses a
configured Gemini or Ollama provider for the task language models are useful
for: converting an ambiguous human request into a structured draft and exposing
what still needs clarification. Server-side code then verifies catalogue SKUs,
hydrates merchant-controlled price and policy data, produces the final
buyer-visible playback, and retains model provenance.

This creates a deliberate split:

```text
LLM: understand request, extract structured intent, surface ambiguity
Code: resolve trusted terms, sign evidence, verify webhook, compare drift, gate action
Human: see the final offer and explicitly confirm a changed promise
```

The result is not “less AI.” It is **controlled agency**: AI handles language
and uncertainty; deterministic systems handle authority, money-adjacent state,
and evidence.

## Impact model: what changes for each human in the workflow

Atlas does not claim savings, conversion lift, dispute-win rate, or merchant
traction before a pilot. Its impact case is causal and testable:

| Person | Before Atlas | Atlas intervention | Measurable pilot signal |
|---|---|---|---|
| Buyer | A valid payment can be followed by a changed item, price, delivery promise, or renewal with no obvious consent boundary. | One buyer-visible playback is locked; material change requires a fresh decision. | Number and category of material changes caught before fulfilment/renewal. |
| Merchant operations | Teams reconcile chat, catalogue, OMS, payment status, and policy history when something goes wrong. | One evidence journey links signed terms, verified payment, change, and decision. | Reviewer agreement and time-to-resolution compared with the merchant’s current process. |
| Support / dispute reviewer | They receive disconnected screenshots and conflicting recollections. | They receive a privacy-minimised, tamper-evident sequence with the precise field-level diff. | Evidence completeness and escalation rate. |
| Finance / international operations | A payment-day and dispute-day amount can look inconsistent without a clear explanation. | The three rate dates are labelled separately and the paise delta is calculated reproducibly. | Percentage of FX exceptions with source-linked, reviewer-accepted explanation. |

### Pilot measurement plan—no invented ROI

The first deployment should shadow one high-drift workflow for 30 days: a
substitution, delivery change, or subscription amendment. Atlas will observe
before it gates. The merchant and support reviewers should then assess:

1. **Eligible-action coverage:** What proportion of targeted fulfilment or
   renewal actions had an Offer Lock preflight?
2. **Drift detection:** How often did current terms differ materially from the
   buyer-confirmed terms, and which fields changed?
3. **Reviewer agreement:** Did a human reviewer agree with `ALLOW`,
   `RECONFIRM`, or `ESCALATE`?
4. **Evidence completeness:** Did every reviewed case contain the lock,
   signature status, linked Order/payment reference, and decision trace?
5. **Resolution time:** How long did the team take to explain or resolve the
   case relative to its existing workflow?
6. **Exception list:** Which cases remain unsafe to automate and why?

This is the proof path from a compelling Buildathon prototype to a credible
merchant product.

---

## What is working now

| Capability | What the repository demonstrates |
|---|---|
| Buyer-visible Offer Lock | Canonical commercial terms—items, total, delivery, return, substitution, renewal, merchant, currency—are versioned and Ed25519-signed. |
| Bounded AI composition | Gemini or Ollama may translate a natural-language request into a structured draft against known merchant SKUs. Server code hydrates trusted price/policy data; AI cannot set an amount, grant consent, fulfil, refund, or decide a drift verdict. |
| Material-drift policy | Price increase, added/removed item, later delivery, return/substitution-policy change, and renewal change return `RECONFIRM`; merchant/currency identity changes return `ESCALATE`. |
| Razorpay Test Mode flow | Atlas creates a guarded `rzp_test_` Order with compact proof references only. A real Razorpay Test Mode checkout and public-HTTPS webhook rehearsal have been completed. |
| Payment evidence | The durable development evidence store contains **three** HMAC-verified `rzp.payment.captured` events from the Test Mode rehearsal. Browser return is explicitly untrusted and cannot create payment proof. |
| Evidence integrity | Raw-body HMAC validation, duplicate rejection, exact Order binding, hash-chained events, Ed25519 sealing, and a verifier-side key trust registry. |
| Subscription release preflight | A typed planned change returns a signed receipt. When material terms drift, `razorpay_patch_permitted: false`; a merchant worker must obtain fresh confirmation before it calls Razorpay. |
| FX Promise Envelope | A three-date, source-labelled display/payment/dispute-rate assessment using integer paise—not floating-point arithmetic—and an explainable INR delta. |
| Release discipline | **104 automated tests** plus a 14-scenario, reproducible, synthetic internal `pass^5` regression run. |

### Evidence status, stated precisely

The Test Mode capture is a real Razorpay event received through the configured
webhook. It proves that Atlas can create the guarded Test Mode order, receive a
public webhook, verify its HMAC over the raw body, reject duplicate delivery,
and bind the event to the correct Offer Lock.

It does **not** prove real-money readiness, delivery of goods, product quality,
buyer identity, legal liability, or production scale. Test Mode uses no real
money. The evidence database and keys are local development artifacts and are
not committed to this repository.

---

## How it works

```text
1. BUYER / EXTERNAL AGENT
   “Two margheritas, Saturday, no substitutions.”
                         │
                         ▼
2. ATLAS — BOUNDED AI + TRUSTED MERCHANT DATA
   AI creates a structured draft only.
   Server resolves approved SKU, ₹ total, delivery and policy versions.
                         │
                         ▼
3. BUYER CONFIRMATION
   Buyer reviews a clear playback and confirms it.
   Atlas canonicalises the terms and creates an Ed25519-signed Offer Lock.
                         │
                         ▼
4. RAZORPAY ORDER + PAYMENT TRUTH
   Atlas adds compact proof references to a Razorpay Test Mode Order.
   Only a raw-body HMAC-verified Razorpay webhook becomes payment evidence.
                         │
                         ▼
5. BEFORE A CONSEQUENTIAL MERCHANT ACTION
   OMS / fulfilment / subscription worker sends current or proposed terms.
   Atlas compares them with the lock and returns ALLOW, RECONFIRM or ESCALATE.
                         │
                         ▼
6. HUMAN-REVIEWABLE EVIDENCE
   Support or operations receives one sealed journey:
   buyer-visible promise → payment proof → change → decision.
```

### Real-system inputs and outputs

| Existing system | Atlas receives | Atlas gives back |
|---|---|---|
| Buyer agent or checkout | structured request and opaque approval reference | buyer-visible final-offer playback for explicit confirmation |
| Merchant catalogue / OMS | approved SKUs, price, policy, delivery and renewal terms | signed Offer Lock and later field-level drift decision |
| Razorpay Orders API | amount, currency and compact proof references | standard Razorpay Order; Atlas never touches card, UPI, or payment credentials |
| Razorpay webhook | raw signed lifecycle payload | privacy-minimised payment evidence linked to exactly one Offer Lock |
| Fulfilment / renewal worker | current terms immediately before action | `ALLOW`, `RECONFIRM`, or `ESCALATE` release receipt |
| Finance / disputes operations | labelled display, payment, reference and dispute-date rates | integer-paise delta plus source-linked evidence attachment |
| Support / claims team | claim plus Offer Lock journey | sealed evidence package and recommendation—not an automatic dispute outcome |

---

## Five-minute judge walkthrough

1. Open [`/offer-lock`](http://127.0.0.1:5000/offer-lock). Generate a
   constrained offer draft and show the buyer-visible playback.
2. Sign the offer. Point out that the snapshot, not raw chat, becomes the
   Offer Lock; the UI displays its signature and safe proof references.
3. Trigger **Silent drift**. The price, item/delivery/policy terms change;
   Atlas produces a field-level `RECONFIRM` verdict.
4. Open the sealed evidence journey. Show `rzp.payment.captured`, the verified
   evidence seal, and the human-readable, per-journey timeline.
5. Open [`/subscription-preflight`](http://127.0.0.1:5000/subscription-preflight).
   Show that a changed renewal produces `PATCH withheld — new confirmation
   required`.
6. Open [`/fx-promise`](http://127.0.0.1:5000/fx-promise). Show displayed,
   payment, and dispute dates; explain that the ₹15 delta is evidence for an
   operations review—not an invented refund.
7. Finish at [`/release`](http://127.0.0.1:5000/release). Show the strict
   internal `pass^5` label and clearly say it is synthetic regression evidence.

For the strongest video, tell one story only: **buyer sees ₹680 → payment is
real → price/delivery changes → Atlas holds fulfilment → support can prove why.**
The other pages are proof of depth, not separate product pitches.

---

## Trust boundaries and security design

The product is intentionally strict about what counts as evidence:

- A checkout success screen or browser callback is **not** payment proof.
- A webhook is accepted only after HMAC verification over the original raw
  request body; it is deduplicated and must name the exact Order bound to the
  Offer Lock.
- The full commercial snapshot is canonicalised and Ed25519-signed. Razorpay
  Order notes hold compact proof references only—never buyer chat, credentials,
  card data, UPI VPAs, phone numbers, or email addresses.
- Drift decisions are deterministic, field-level comparisons—not an LLM score.
- AI can compose a draft and surface ambiguity; it cannot obtain consent,
  choose a final amount, create an unguarded order, issue a refund, fulfil, or
  determine the final verdict.
- Portable signatures are verified against a separate trust registry with
  active, expired, and revoked key states.
- The FX module preserves labelled facts. It does not claim to be a bank quote,
  execute conversion, hedge FX, or decide a dispute.

See [SECURITY.md](SECURITY.md) and [GOVERNANCE.md](GOVERNANCE.md) for the
threat model, data-minimisation rules, and control record.

## What this deliberately does not claim

| Not claimed | Why |
|---|---|
| Production readiness | Production needs tenancy, authentication/authorisation, encrypted storage, KMS/HSM signing custody, key rotation, rate limits, monitoring, retention policy, incident response, and a security review. |
| An automatic refund or dispute verdict | Atlas can explain commercial and FX evidence; the merchant and payment/dispute process make the decision. |
| Payment fraud prevention or buyer identity verification | These remain payment-rail and merchant identity concerns. |
| An AP2 or NPCI UAP implementation | Atlas is inspired by signed-mandate/evidence ideas, but it does not emit their protocol artifacts or claim compliance. |
| Real-world accuracy or traction | The current `pass^5` run is synthetic regression testing. No customer metric or merchant pilot is claimed. |

---

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

Leave Razorpay keys blank for the offline walkthrough. Never commit `.env`,
the durable development evidence database, or signing keys.

The judge walkthrough bundles its core browser assets locally. The frontend
uses Tailwind’s browser build only as a demo convenience; a production frontend
would compile and pin its assets. See
[`ui/vendor/THIRD_PARTY_NOTICES.md`](ui/vendor/THIRD_PARTY_NOTICES.md).

## Routes

| Route | Purpose |
|---|---|
| `/offer-lock` | Primary buyer-visible offer, signature, Test Mode, and drift-check flow |
| `/evidence/<session-id>` | Sealed evidence journey |
| `/claims/<session-id>` | Buyer-claim review from the evidence chain |
| `/subscription-preflight` | Material-change gate before a merchant subscription worker acts |
| `/fx-promise` | Three-date international FX Promise Envelope |
| `/release` | Synthetic release-test dashboard and boundary labels |
| `/settlements` | Settlement-reconciliation sandbox |
| `/intent-check`, `/speech-check`, `/checkout-safety` | Supporting assurance demonstrations |

---

## Repository map

```text
ui/                         Flask dashboard, deep-link routing and Test Mode UI
sakshi/offer_lock.py        Canonical Offer Lock, signatures, drift policy
sakshi/offer_composer.py    Bounded AI offer composition and clarification gate
sakshi/webhooks.py          Raw-body Razorpay HMAC verification and idempotency
sakshi/offer_store.py       Durable privacy-safe local Offer Lock storage
sakshi/subscriptions.py     Release receipt before a subscription PATCH
sakshi/fx/promise.py        Labelled FX evidence and paise arithmetic
sakshi/settlements/         Recon normalisation and link validation
kasauti/                    Synthetic adversarial release harness
tests/                      Unit, integration, routing, and Test Mode tests
```

## Submission material

- [Five-minute pitch and demo script](PITCH_AND_DEMO_SCRIPT.md)
- [Demo guide](DEMO.md)
- [Validation record](VALIDATION.md)
- [Integration contract](INTEGRATION.md)
- [Gap and overlap analysis](GAP_ANALYSIS.md)
- [Security model](SECURITY.md)
- [Governance record](GOVERNANCE.md)
- [Pilot plan](PILOT_PLAN.md)
- [Webhook rehearsal runbook](WEBHOOK_REHEARSAL.md)

## Primary research links

These are the primary materials used to define the scope. They are included so
a reviewer can distinguish a documented platform capability, an external
standard, and an Atlas design inference.

### Razorpay and Buildathon

- [Razorpay AI Buildathon 2026](https://razorpay.com/buildathon/) — Track 05
  bar, submission format, and the emphasis on evidence and depth.
- [Razorpay Agentic Payments](https://razorpay.com/agentic-payments/) — current
  agentic-payment surfaces and consent-based agent payment methods.
- [Razorpay Agent Studio](https://razorpay.com/agent-studio/) and
  [Agent Studio principles and guardrails](https://razorpay.com/blog/razorpay-agent-studio-principles-guardrails-and-merchant-control/)
  — documented overlap boundary for agent controls, audit, dispute, and
  operations workflows.
- [Create an Order](https://razorpay.com/docs/api/orders/create/) — Order
  metadata capacity that shapes Atlas’s compact-reference design.
- [Validate and test webhooks](https://razorpay.com/docs/webhooks/validate-test/)
  — raw-body signature validation, test-mode webhook delivery, and idempotency.
- [Update a Subscription](https://razorpay.com/docs/api/payments/subscriptions/update/)
  — the mutation Atlas preflights; Atlas does not execute this call.
- [Settlement Recon details](https://razorpay.com/docs/api/settlements/fetch-recon/)
  — settlement line types and fields used by the adapter.
- [International payment disputes FAQ](https://razorpay.com/docs/payments/disputes/faqs/)
  — documented dispute-date FX-rate behavior that motivates the FX envelope.

### Standards and evaluation research

- [Google AP2 specification](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/specification.md)
  — signed checkout/payment mandates, receipts, and deterministic verification;
  Atlas is inspired by the evidence model and makes no compliance claim.
- [τ-bench paper](https://arxiv.org/abs/2406.12045) — the motivation for a
  repeated `pass^k` reliability check rather than a single successful run.

## The next production-shaped milestones

1. Put an authenticated merchant OMS or fulfilment worker behind the release
   receipt and demonstrate that `RECONFIRM` actually blocks action.
2. Move signing keys to managed custody, encrypt the evidence store, and add
   tenant isolation, retention, and operator access controls.
3. Validate one narrow workflow—substitution, delivery change, or renewal—with
   merchant/support reviewers and human-labelled cases.
4. Replace demo FX inputs with source-bound finance/dispute records after an
   international-operations validation.
5. Run held-out, human-reviewed agent evaluations before expanding autonomy.

Until then, Atlas is exactly what it claims to be: a working, security-minded
Buildathon prototype for making agentic commerce more honest and explainable.
