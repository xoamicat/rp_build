# Why Agentic Offer Lock is the gap, not another payment agent

**Research date:** 28 August 2026. This document is intentionally strict: it separates a documented Razorpay capability from a complementary, buildable layer.

## What the original combined idea overlaps with

| Original capability | Razorpay surface already documented | Decision |
|---|---|---|
| Agent checkout limits, discount ceilings, approval gates | Agentic Payments and UPI Reserve Pay let users set boundaries for trusted agents; Agent Studio validates amount, scope and compliance before actions execute. | Do not pitch this as the core product. |
| Agent audit diary and dark-pattern detection | Agent Studio documents full action audit trails and automated screening for dark patterns. | Keep only as support for external-agent evidence. |
| Chargeback evidence/dispute recommendation | Agent Studio includes a Dispute Responder that gathers evidence, scores cases and submits or drafts responses. | Do not pitch a generic dispute agent. |
| Settlement monitoring and cash-flow follow-up | Agent Studio lists Settlement Insights and cash-flow agents; Razorpay exposes Settlement Recon reports/API. | Do not pitch generic reconciliation as the differentiator. |
| Bank-transfer narration matching | Smart Collect creates unique customer identifiers, tracks UTRs and automatically reconciles bank transfers; RazorpayX also syncs statement context to Tally. | Keep only for untagged legacy bank lines, not the main story. |
| International documents/compliance | Razorpay International Payments auto-generates FIRC/FIRS; onboarding already handles international compliance. | Do not build a generic document checklist. |
| Agent testing/certification | Agent Studio describes internal evaluation and certification screening. | Keep Kasauti as a transparent release gate for the Atlas logic, not as the product headline. |

Sources: [Agent Studio guardrails](https://razorpay.com/blog/?p=26508), [Agent Studio products](https://razorpay.com/agent-studio/), [UPI Reserve Pay](https://razorpay.com/blog/upi-reserve-pay/), [Settlement Recon API](https://razorpay.com/docs/api/settlements/fetch-recon/), [Smart Collect](https://razorpay.com/smart-collect/), [International Payments](https://razorpay.com/docs/payments/international-payments/?preferred-country=IN).

## The documented gap hypothesis

Razorpay is the payment and merchant-control system. Its public material explains payment authorisation, agent guardrails, payment audit logs, settlement reports and merchant-side dispute response. I did **not** find a documented public surface that carries a **signed, versioned snapshot of the complete buyer-visible commercial offer** across an external buyer agent, Razorpay checkout, a later fulfilment/renewal system and a dispute.

This matters because valid payment authorisation is not the same thing as proof that all commercial terms remained the same. In an AI journey, the buyer can see a dynamic product card in ChatGPT, a voice summary, an app chat, or an external agent’s UI. Between that moment and fulfilment, a merchant catalogue can change: price, included item, delivery date, return policy, substitute rule or renewal condition. Today that often becomes a support argument rather than an explicit new consent.

The gap is therefore **post-consent commercial drift**, not payment fraud and not checkout automation.

## Product: SettleX Atlas — Agentic Offer Lock

Atlas takes a buyer-visible offer snapshot from a merchant or external buyer agent:

```text
catalogue version + SKU/quantity + price + shipping/tax
+ delivery promise + return-policy version + substitution rule + renewal terms
+ buyer-visible approval summary
                         ↓
                 Ed25519-signed Offer Lock
                         ↓
        compact references in Razorpay Order notes
                         ↓
before fulfilment, subscription renewal, or a material amendment:
compare current terms with the signed lock
                         ↓
ALLOW | RECONFIRM BUYER | ESCALATE IDENTITY CHANGE
```

The full commitment stays in the merchant evidence store. Razorpay `notes` carries only the lock ID, catalogue version, key ID and signature. Razorpay supports up to 15 `notes` entries of up to 256 characters, which the code validates before order creation. [Orders API](https://razorpay.com/docs/api/orders/create/)

### The stronger wedge: mutable promises, not payment execution

The current public Agent Studio page lists revenue-operations agents such as Dispute Responder, Subscription Recovery and Settlement Insights, and offers custom-agent building. Its public material does **not** describe a portable, cryptographically verifiable buyer-visible commercial receipt that is carried from an external buyer agent through a Razorpay payment event into a merchant OMS or a preflight subscription update. That is the gap hypothesis to test with Razorpay—not a claim about private/internal capabilities. [Agent Studio product page](https://razorpay.com/agent-studio/)

Two high-value slices make the hypothesis concrete:

| Moment | Existing documented rail | Atlas's narrowly different decision |
|---|---|---|
| Subscription plan/quantity/interval/effective-date change | Razorpay accepts a subscription `PATCH`, allows a schedule and lets Razorpay or the merchant notify the customer. | Before the merchant calls the PATCH, compare the proposed commercial promise to the signed prior playback. A material change requires new buyer confirmation; notification alone is not treated as consent proof. |
| Cross-border payment later disputed | Payment-date settlement and dispute-date debit can use different processing-bank rates. | Bind displayed/reference/payment/dispute rates as separate evidence facts; calculate a review reserve and make the delta explainable. Do not claim to set the rate, execute FX or decide the dispute. |

This is complementary to Agent Studio’s money-action validation: Agent Studio can validate the money action; Atlas asks whether the buyer's earlier commercial confirmation is still safe to carry into a **different downstream operational action**.

## Why this is complementary

- **Razorpay continues to authorise and move money.** Atlas does not collect credentials, replace checkout, decide card risk, or claim to change Razorpay’s settlement process.
- **The merchant still owns its catalogue and fulfilment.** Atlas reads a versioned snapshot and returns a decision for the merchant’s OMS, subscription engine or fulfilment queue.
- **External buyer-agent proof is the focus.** This works when the buyer starts in a ChatGPT app, voice assistant, marketplace, merchant chatbot or another agentic surface, including one outside Razorpay Agent Studio.
- **No raw chat in payment metadata.** The stored approval is a buyer-visible summary and its hash; Razorpay notes store only compact proof references.

## What is implemented here

- `sakshi/offer_lock.py`: typed terms, canonical hashes, Ed25519 signatures, material-drift policy and Razorpay-notes capacity management.
- `sakshi/integration.py`: optional OfferLock is verified and attached to a guarded Razorpay order only when the signed proof matches the configured trusted key.
- `POST /api/offer-locks`: create a signed lock; `POST /api/offer-locks/{lock_id}/check`: compare fulfilment/renewal terms.
- Dashboard: a live demonstration of price, item, delivery and return-policy drift returning **RECONFIRM**.
- `sakshi/fx/promise.py` and `/fx-promise`: three-date FX Promise Envelope using labelled rate inputs and integer-paise calculations; it can append an assessment to a signed journey.
- Tests: price increase, added item, late delivery, price decrease, seller change, notes-key capacity, FX quote/capture/dispute arithmetic and order-bound webhook rejection.

## Honest boundaries

- A signed offer proves the snapshot recorded by its signer, not physical delivery, product quality, or legal liability.
- Production needs merchant authentication, a durable encrypted evidence store, KMS/HSM signing keys, key rotation/revocation, consent/retention policy, and an OMS/fulfilment connector.
- The demo signer and storage are deliberately ephemeral. It never represents a live Razorpay payment or a legal decision.
- This is a gap hypothesis based on publicly documented Razorpay product material, not a claim that no internal/private feature exists.
