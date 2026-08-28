# Security and evidence model

## What Atlas proves—and does not prove

- A hash chain makes edits/deletions detectable. By itself it is **not tamper-proof**.
- An Ed25519-signed intent binds the recorded privacy-safe intent hash to a key; a signed transaction seal binds a completed transaction chain head to that key.
- An **Offer Lock** binds a versioned snapshot of the buyer-visible commercial promise—line items, prices, delivery, policy, substitutions and renewal terms—to an opaque buyer approval reference. It does not claim to prove the buyer's identity, delivery, or product quality.
- The AI Offer Composer can draft a catalogue-backed offer but is not an authority. It cannot set prices/policies, grant consent, create an order, fulfil, refund, or decide drift; those boundaries are enforced by typed validation and deterministic code.
- A verifier must pin/allow-list the public key for `sakshi_kid`. The public key present in a portable bundle is useful for transport, not identity by itself.
- A verified webhook proves that the body was signed with the configured Razorpay webhook secret. It does not prove delivery, product quality, or facts outside the payment lifecycle.
- The dispute agent is a recommendation system. It must escalate when confidence, signature policy, or evidence coverage is insufficient.

## Controls implemented in this repository

| Risk | Control |
|---|---|
| Model inventing an item, price, or approval | Composer accepts only known SKU + bounded quantity; server hydrates merchant prices/policies; malformed/unknown output fails closed; buyer confirmation precedes signing. |
| A fulfilment or renewal silently changing the approved offer | Signed, versioned Offer Lock; deterministic pre-fulfilment diff returns `ALLOW`, `RECONFIRM`, or identity `ESCALATE`. |
| Raw utterance or payment PII leaking into proof | Intent receipt stores a raw-utterance hash and playback only; notes are limit-checked; event slimming/redaction removes contact/card fields. |
| Database-only rewrite of an audit trail | Optional Ed25519 signed intent and signed completed-chain seal. |
| Process restart losing an Offer Lock | With `SAKSHI_EVIDENCE_PRIVATE_KEY_B64`, `DurableOfferStore` keeps the signed snapshot and safe Test Mode handoff state in its dedicated SQLite evidence store; direct full-lock evidence URLs resolve after restart. |
| Forged or replayed lifecycle event | Constant-time HMAC validation of exact webhook bytes; `x-razorpay-event-id` idempotency with SHA-256 fallback. |
| Agent bypassing policy to create an order | `SakshiCheckout` invokes Razorpay only for allowed gate results. |
| An automatic correction being presented as human approval | `policy.correction` and `human.override` are distinct event types and actors. |
| Unverifiable automatic dispute outcome | `require_signed_evidence` policy makes invalid/missing seals escalate. |

## Production hardening still required

This buildathon repository is not a complete production security program. Before a merchant deployment: use an HSM/KMS for the signing key, key rotation and revocation, encrypted database/storage backups, least-privilege service identities, immutable external audit retention, webhook IP/network controls where documented, encrypted transcript retention with consent/retention policy, rate limits, alerting, independent security review, and merchant-specific dispute/fee policies.

Never put secrets, raw transcripts, card data, UPI VPAs, phone numbers, or email addresses in the ledger, order notes, screenshots, or submitted run artifacts.

The repository can generate a **local development** Ed25519 key through `scripts/generate_evidence_key.py`. Its `.atlas-evidence.env` file and `data/atlas_evidence.db` are git-ignored. This makes the demo’s persistence testable; it does not satisfy production key-custody requirements.
