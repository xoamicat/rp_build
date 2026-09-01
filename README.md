# SettleX Atlas

> **The payment was valid. The promise changed. What should happen next?**

SettleX Atlas is a merchant-side **commercial-promise layer** for agentic
commerce, built for the **Razorpay AI Buildathon 2026 · Open Track**.

An AI agent can make a completely valid payment and still create the wrong
customer outcome later: the price changes, an item is substituted, delivery
moves, a return policy changes, or a subscription renewal is amended. The
payment rail can truthfully say *money moved*. The buyer can still truthfully
say: **“That is not what I bought.”**

Atlas turns the final buyer-visible offer into a signed **Offer Lock**, and
checks that promise again immediately before fulfilment, substitution, or a
subscription change.

```text
ALLOW       → the promise still matches; continue
RECONFIRM   → a material term changed; ask the buyer again
ESCALATE    → merchant or currency identity changed; do not inherit consent
```

**Razorpay validates and moves money. Atlas protects the commercial promise
around that money.**

---

## The problem starts after payment

In ordinary checkout, the buyer sees a product, price, delivery terms, and a
final confirmation. In agentic commerce, those facts can be assembled by an
external shopping agent, a voice flow, an LLM, or a merchant app—and can change
again inside the merchant catalogue or OMS after payment.

That creates a gap between **payment authority** and **commercial authority**:

```text
Buyer sees and approves          Razorpay payment          Merchant acts later
item · total · delivery     →    succeeds           →     ship · substitute · renew
           │                                              │
           └───── Offer Lock compares the promise ───────┘
                                      │
                           ALLOW | RECONFIRM | ESCALATE
```

Atlas prevents a previous payment confirmation from silently becoming approval
for a different deal.

## We researched Agent Studio first—then designed around the remaining gap

This is intentionally **not** a generic AI safety bot or a clone of Razorpay
Agent Studio. Public Razorpay material already describes meaningful agentic
capabilities: merchant-defined boundaries, review-first controls, audit trails,
dispute response, subscription recovery, settlement insights, and custom
agents. [Razorpay Agent Studio](https://razorpay.com/agent-studio/) ·
[Agent Studio principles and guardrails](https://razorpay.com/blog/razorpay-agent-studio-principles-guardrails-and-merchant-control/)

Razorpay also supports agentic payments across in-app, LLM, and voice surfaces,
and UPI Reserve Pay introduces consent-based, pre-authorised agent payments.
[Razorpay Agentic Payments](https://razorpay.com/agentic-payments/)

So we removed the overlapping ideas and kept the gap that remained:

| Public Razorpay capability researched | What it already handles | The remaining Atlas gap |
|---|---|---|
| Agent Studio guardrails and audit trails | Merchant-defined boundaries, approvals, and recorded agent actions. | A portable, buyer-visible commercial promise that stays useful when the buyer agent, merchant OMS, fulfilment system, and payment event live across different systems. |
| Dispute Responder | Gathering and responding to an existing payment dispute. | **Pre-dispute prevention:** detect that the paid-for promise changed before the merchant ships, substitutes, or renews. |
| Subscription Recovery | Recovering failed recurring payments and avoiding churn. | A buyer-consent gate before a merchant changes plan, quantity, timing, or renewal terms through a subscription update. |
| Settlement Insights and Recon | Payment/settlement reporting and reconciliation. | Link a finance row to the signed commercial promise; do not treat an unlinked row as customer-facing evidence. |
| Agentic checkout and UPI Reserve Pay | Safe payment authorisation in agent-led commerce. | Verify whether the **exact buyer-visible deal** remains true at the next irreversible merchant action. |

**The public-surface gap hypothesis:** we did not find a documented Razorpay
surface for a cryptographically verifiable snapshot of the complete
buyer-visible offer—item, price, delivery, policy, substitution, renewal—that
travels from an external buyer agent through a Razorpay event to fulfilment or
renewal. Atlas is built for that seam. This is a public-product research
conclusion, not a claim about Razorpay’s internal roadmap.

---

## The product: one promise, four proof points

### 1. Offer Lock — a receipt for the agreement

Before payment, Atlas creates a canonical snapshot of the terms the buyer saw:
items, total, delivery date, return-policy version, substitution rule, renewal
summary, merchant, and currency. The snapshot is Ed25519-signed.

This is not a screenshot and not raw chat history. It is a structured,
versioned commercial commitment that can be compared later.

### 2. Release gate — do not silently carry consent forward

Immediately before shipment, substitution, or renewal, the merchant sends the
current or proposed terms to Atlas. Atlas performs a deterministic field-level
comparison with the signed Offer Lock.

If the price rises, an item changes, delivery moves later, policy changes, or a
renewal changes, Atlas returns `RECONFIRM` with the exact diff. A merchant
worker proceeds only when the result is `ALLOW`.

### 3. Evidence journey — payment proof belongs beside promise proof

Atlas creates one readable, sealed evidence journey:

```text
buyer-visible offer → buyer approval → signed Offer Lock → verified payment
→ observed commercial change → ALLOW / RECONFIRM / ESCALATE
```

A browser checkout callback is not payment proof. Only a raw-body
HMAC-verified Razorpay webhook, bound to the exact Atlas-created Order and
deduplicated by event ID, can write `rzp.payment.captured` evidence.

### 4. FX Promise Envelope — the second promise nobody can see

The buyer may see one currency conversion, payment can occur on another date,
and a later international dispute deduction can use yet another conversion
date. Razorpay’s disputes FAQ states that an international-dispute deduction is
based on the processing-bank conversion rate on the day the dispute is created,
which can differ from the payment date. [Razorpay disputes FAQ](https://razorpay.com/docs/payments/disputes/faqs/)

Atlas makes that hidden lifecycle explicit:

```text
buyer-displayed rate  →  payment-date rate  →  dispute-date rate
       what was shown       what was paid         what was deducted later
```

The **FX Promise Envelope** stores those three facts with their sources,
calculates the difference in integer paise, and attaches it to the same evidence
journey. It does not invent a bank rate, execute FX, set a refund, or decide a
dispute. Its innovation is making a confusing, multi-date commercial exposure
reviewable before it becomes an opaque support argument.

---

## How Atlas integrates with Razorpay today

Atlas is designed as a service **beside** a merchant’s existing checkout and
OMS. It does not replace Razorpay Checkout, handle a card/UPI credential, or
become a payment processor.

```text
Buyer agent / merchant checkout
          │  buyer request + explicit approval reference
          ▼
SettleX Atlas
  • bounded AI drafts a structured offer from approved catalogue SKUs
  • server supplies merchant-controlled price, delivery and policy terms
  • buyer-visible terms are signed as an Offer Lock
          │  compact lock/signature references only
          ▼
Razorpay Orders API + Razorpay Checkout
  • normal Razorpay Order is created in Test Mode
  • payment is completed through Razorpay Checkout
          │  raw signed payment event
          ▼
POST /webhooks/razorpay
  • Atlas validates the raw-body HMAC
  • rejects duplicate / wrong-Order events
  • appends verified payment evidence to the locked journey
          │
          ▼
Merchant OMS / subscription worker
  • sends current or proposed terms just before action
  • receives ALLOW, RECONFIRM, or ESCALATE
  • performs its existing fulfilment or Razorpay subscription PATCH only on ALLOW
```

### What is already implemented

| Integration point | Atlas behaviour |
|---|---|
| `POST /api/offer-drafts` | A configured Gemini or Ollama model converts natural language into a constrained, catalogue-backed draft and raises clarifying questions. |
| `POST /api/offer-locks` | Buyer-approved terms are signed; Atlas returns safe proof references for Razorpay Order metadata. |
| `POST /api/offer-locks/:lock_id/test-mode-order` | A guarded Razorpay **Test Mode** Order is created only after an Offer Lock exists. The adapter refuses live keys. Razorpay Order `notes` hold compact references, never raw buyer text or credentials. [Orders API limits](https://razorpay.com/docs/api/orders/create/) |
| `POST /webhooks/razorpay` | Uses the exact raw request body for HMAC validation, as Razorpay requires; deduplicates webhook delivery and verifies that the event names the Order bound to the lock. [Webhook validation](https://razorpay.com/docs/webhooks/validate-test/) |
| `POST /api/offer-locks/:lock_id/check` | A fulfilment/substitution preflight returns the field-level decision and reseals the evidence journey. |
| `POST /api/subscriptions/preflight` | A typed planned update is checked before a merchant-owned worker calls Razorpay’s Subscription `PATCH`; material drift returns `razorpay_patch_permitted: false`. [Subscription Update API](https://razorpay.com/docs/payments/subscriptions/update/) |
| Settlement Recon adapter | Normalises documented recon-shaped payment/refund/transfer/adjustment records, while rejecting an unlinked line as evidence. [Settlement Recon API](https://razorpay.com/docs/api/settlements/fetch-recon/) |

### What the Test Mode rehearsal proves

The local durable development evidence store recorded **three**
HMAC-verified `rzp.payment.captured` events after real Razorpay Test Mode
checkout and public-HTTPS webhook delivery. This demonstrates the full
Order → Checkout → webhook → sealed evidence path.

It does not claim live-money readiness, real settlement, physical delivery,
product quality, production scale, or legal liability. The local evidence
database and keys are deliberately git-ignored; no credential or raw buyer data
is committed.

---

## AI with a job, not AI with authority

Atlas uses AI where it has leverage: understanding a buyer’s natural-language
request, selecting only known catalogue SKUs/quantities, and surfacing
ambiguity. It does **not** ask a model to decide an amount, grant consent,
create an unguarded order, fulfil an order, issue a refund, or decide whether a
promise drifted.

```text
LLM     → understand request, produce structured draft, reveal uncertainty
Code    → resolve trusted terms, sign evidence, verify payment, compare drift
Human   → see the final offer and approve a materially changed promise
```

That division is the point: **AI makes the interface natural; deterministic
controls make the money-adjacent workflow trustworthy.**

## Proof and product maturity

- **104 automated tests** cover offer locking, signatures, trust registry,
  material-drift policy, raw-body webhooks, duplicate/order binding, durable
  evidence, Test Mode boundaries, FX arithmetic, subscription preflight,
  routes, settlements, and the release harness.
- **14 reproducible internal scenarios** run under strict synthetic
  `pass^5 = 14/14`: a scenario counts only when all five repeats respect its
  policy. This is regression evidence—not a claim of production reliability.
  The evaluation approach is inspired by [τ-bench](https://arxiv.org/abs/2406.12045),
  which introduced repeated `pass^k` reliability measurement for tool agents.
- **Independent verification posture:** canonical terms are Ed25519-signed;
  the verifier uses a separate trust registry with active, expired, and revoked
  key states.

## Impact we intend to prove

Atlas does not invent savings, conversion lift, dispute-win rate, or merchant
traction. Its impact hypothesis is concrete:

| Who benefits | What changes |
|---|---|
| Buyers | A material change becomes a visible decision instead of a surprise after payment. |
| Merchant operations | One evidence trail replaces the hunt across agent transcript, catalogue, OMS, payment status, and policy history. |
| Support and disputes | The reviewer sees the exact promise, verified payment, field-level change, and system decision in one place. |
| International finance operations | Payment-day and dispute-day FX differences become source-labelled evidence rather than unexplained variance. |

The first merchant pilot should shadow one high-drift workflow for 30 days:
substitutions, delivery changes, or subscription amendments. It should measure
preflight coverage, drift caught, reviewer agreement, evidence completeness,
resolution time, and the exceptions that must remain manual.

---

## Research foundation

This project was scoped against the following primary sources—not assumptions:

- [Razorpay AI Buildathon 2026](https://razorpay.com/buildathon/) — the Open
  Track asks for a real problem, meaningful AI, a working product, evidence of
  value, reliability, and depth.
- [Razorpay Agent Studio](https://razorpay.com/agent-studio/) and
  [its guardrail principles](https://razorpay.com/blog/razorpay-agent-studio-principles-guardrails-and-merchant-control/)
  — defines the overlap we intentionally avoided.
- [Razorpay Agentic Payments](https://razorpay.com/agentic-payments/) — why
  agent-led, cross-surface payment journeys make this problem immediate.
- [Orders API](https://razorpay.com/docs/api/orders/create/),
  [webhook validation](https://razorpay.com/docs/webhooks/validate-test/),
  [Subscription Update API](https://razorpay.com/docs/payments/subscriptions/update/),
  [Settlement Recon API](https://razorpay.com/docs/api/settlements/fetch-recon/),
  and [international disputes FAQ](https://razorpay.com/docs/payments/disputes/faqs/)
  — the real integration constraints behind the design.
- [Google AP2 specification](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/specification.md)
  — the signed-mandate and deterministic-verification ideas that influenced
  Atlas. Atlas is **AP2-inspired**, not AP2-compliant.
- [τ-bench](https://arxiv.org/abs/2406.12045) — why the release harness uses
  repeated `pass^k` rather than a single happy-path run.

## Run locally

```powershell
cd C:\path\to\rp_build
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe ui\server.py
```

Open [http://127.0.0.1:5000/offer-lock](http://127.0.0.1:5000/offer-lock).
For a fresh Test Mode webhook rehearsal, configure `rzp_test_` credentials and
a webhook secret in `.env`, expose `/webhooks/razorpay` through public HTTPS,
and subscribe to `payment.captured` in Razorpay Test Mode. Never commit `.env`,
evidence databases, or signing keys.

## Scope boundary

Atlas is a working, security-minded Buildathon prototype. Production needs
merchant authentication and tenancy, encrypted durable storage, managed key
custody and rotation, retention controls, monitoring, rate limits, a real OMS
enforcement worker, human-reviewed held-out evaluations, and merchant pilot
validation. It does not claim to prevent payment fraud, execute FX, decide a
refund, or replace Razorpay’s payment or dispute processes.
