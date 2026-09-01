# SettleX Atlas — Agentic Offer Lock

**Razorpay Buildathon 2026 — Track 5: Open Innovation**

**SettleX Atlas** is a merchant-side evidence layer for a problem that begins *after* an AI buyer appears to consent: the price, items, delivery promise, return policy or renewal term can change before the merchant fulfils it. Atlas turns the buyer-visible offer into a versioned, Ed25519-signed commitment, carries a compact reference in the Razorpay Order, and forces a fresh confirmation if current terms materially drift.

## The real gap

Razorpay's 2026 Agentic Payments and Agent Studio already provide payment controls, agent audit trails, dark-pattern screening and dispute support. Smart Collect and Settlement Recon also cover important collection and reconciliation workflows. We do **not** compete with those capabilities. The public product gap we address is a portable, signed snapshot of the full **buyer-visible commercial offer** for external buyer agents and merchant fulfilment systems.

Payment authorisation means “this payment may execute.” It does not by itself mean “the buyer accepted this exact catalogue version, delivery date, return-policy version and renewal condition.” In agentic commerce, that difference becomes a support, refund and trust problem. The sharpest live-system moments are a merchant's preflight before it updates a subscription and the three different FX dates surrounding an international-payment dispute.

The output is an **Agentic Offer Lock**:

```text
External buyer agent / voice / chat app
        │ natural-language request
        ▼
 bounded Gemini/Ollama composer ──► catalogue-backed buyer-visible draft
        │ explicit buyer confirmation
        ▼
 SettleX Atlas Offer Lock ──► Ed25519-signed offer snapshot ──► Razorpay Orders API
        │                                                          │
        │                                                          │ `notes`: lock ID + version + key ID + signature
        ▼                                             ▼
 merchant evidence store                         payment authorisation and lifecycle
        │                                             │
        └── before fulfilment / renewal: compare current terms ───► allow | reconfirm | escalate

Kasauti release gate: adversarial drift fixtures and an honest exception list before deployment
```

## Why this is a credible Open Track product

- **Complementary, not a replacement claim.** Atlas writes no payment rail and makes no risk decision. It uses Razorpay's supported Orders `notes` field to link the merchant's signed commercial commitment to an ordinary Razorpay order.
- **Evidence validity.** The offer payload is canonicalised and Ed25519-signed. Seller/currency changes escalate; extra items, increased price, delayed delivery, changed return policy, changed substitution policy and changed renewal terms require a reconfirmation.
- **Privacy by construction.** Raw buyer conversation and payment credentials never enter the order or the offer lock. The buyer-visible summary is hashed; order metadata holds only short proof references.
- **Real system boundary.** Inputs come from an external agent and the merchant catalogue/OMS. Outputs go to normal Razorpay order creation, then to an OMS, subscription renewal worker or support/dispute workflow.
- **AI where it has leverage, bounded where money is involved.** A configured Gemini/Ollama model converts natural language into a structured draft and exposes uncertainty. It can select only merchant catalogue SKUs and quantities; code, not the model, hydrates price/policy terms. The buyer confirms the draft, and the final drift decision is deterministic and reviewable.
- **Not another generic agent.** Atlas becomes a release receipt in front of a merchant’s existing OMS/subscription worker. It does not call Razorpay’s subscription PATCH; it returns `razorpay_patch_permitted: false` when a changed renewal needs fresh confirmation. The companion FX Promise Envelope preserves displayed, payment-date and dispute-date rates as three labelled facts and explains the integer-paise difference without pretending to set FX.

## Submission proof bar

The dashboard and code must be demonstrated as two modes, never conflated:

| Capability | Demo mode | Production-shaped path |
|---|---|---|
| Offer lock | ephemeral demo key + memory store, labelled as simulated | KMS/HSM Ed25519 key + durable encrypted evidence store |
| Order creation | `StubGateway`, labelled as simulated | guarded `LiveGateway` using Razorpay Test Mode credentials only |
| Browser checkout return | not payment evidence | `checkout.client.returned`, explicitly labelled untrusted |
| Post-payment truth | signed local webhook fixture in tests | HMAC-verified Razorpay webhook over public HTTPS |
| Settlement | synthetic recon-shaped row (test mode does not settle) | import/adapter from Settlement Recon data |
| Evidence signature | ephemeral demo key | Ed25519 private key from secret manager + key allow-list |
| Offer state across restart | browser-memory only | durable dedicated evidence store; the repo locally verifies the mechanism with a git-ignored dev key |
| AI offer composition | configured Gemini/Ollama call, catalog/schema validation, output provenance hashes | merchant-scoped model access, version pinning, offline adversarial eval and audit retention |
| Subscription mutation | signed preflight receipt; no outbound PATCH from Atlas | merchant worker enforces `ALLOW` immediately before authenticated Razorpay Subscription PATCH |
| International dispute FX | deterministic three-date calculation with labelled demo inputs | source-bound payment/recon/dispute records and finance-operations validation |
| Evaluation | scripted scenarios, provenance manifest | holdout scenarios and human labels before a merchant rollout |

Do not quote the current scenario-bank score as real-world precision/recall. It is a reproducible stress test, not production traffic.

## Buildathon demo outcome

1. Gemini converts “two margheritas, Saturday, no substitutions” into a structured draft, selecting only the merchant catalogue SKU and reporting any uncertainty. Server code supplies the ₹680 total and policy terms.
2. The buyer reviews and confirms that exact draft. Atlas signs the offer snapshot and returns four compact `atlas_*` references that fit in Razorpay `order.notes`; the complete signed offer stays in the merchant evidence store.
3. Before fulfilment, the merchant catalogue changes: the price rises, garlic bread appears, delivery moves later and the return-policy version changes.
4. Atlas returns **RECONFIRM** with a field-level diff, so the prior consent cannot silently carry forward. The subscription-preflight screen uses that same decision to withhold a merchant's downstream Razorpay PATCH.
5. The same comparison with unchanged terms returns **ALLOW**. A seller or currency change returns **ESCALATE** rather than trusting an inherited consent.
6. The FX Promise screen independently shows why cross-border disputes need a three-date explanation: default supplied values produce a ₹15.00 payment-to-dispute delta for a $10.00 order. No rate is claimed to be Razorpay’s or a bank’s.
7. `scripts/verify_razorpay_test_mode.py --create` has created and fetched a real, unpaid Razorpay Test Mode order with all 15 allowed notes, including the Atlas proof references. Its safe artifact is under `data/evidence/`. The dashboard exposes the same guarded Test Mode path: order creation is Test-Mode-only; a browser return remains pending until the HMAC-verified webhook arrives.

See [VALIDATION.md](VALIDATION.md), [GAP_ANALYSIS.md](GAP_ANALYSIS.md), [DEMO.md](DEMO.md), [INTEGRATION.md](INTEGRATION.md), [PILOT_PLAN.md](PILOT_PLAN.md), and [SECURITY.md](SECURITY.md) for the exact proof, runbook and trust boundaries.
