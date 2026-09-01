# Atlas governance and regulatory design record

This is a product-control record for a pilot conversation. It is **not** legal advice, a certification, or a claim that SettleX Atlas or a merchant is compliant by using this repository.

## The precise regulated decision

Atlas never authorises a payment, determines an FX conversion rate, or decides a chargeback. Its decision is narrower:

> May a merchant carry the buyer's previous commercial confirmation forward to this proposed fulfilment, subscription amendment, or evidence review?

The answer is deterministic and explainable: `ALLOW`, `RECONFIRM`, or `ESCALATE`. A material difference stops automation; an operator or the buyer remains accountable for the next step.

## Controls already implemented

| Control objective | Atlas implementation | Honest limit |
|---|---|---|
| Purpose and minimisation | Hash/provenance fields and an opaque approval reference; no raw buyer chat, card data, UPI VPA, address, phone or email in the lock or Razorpay `notes`. | The merchant is still responsible for its own lawful notice, collection and retention decisions. |
| Meaningful buyer confirmation | Final playback is stored with the versioned commercial terms; the AI composer cannot create consent. AI ambiguity produces a clarification question and blocks signing. | An opaque approval reference is not identity proof and does not replace a merchant's consent UX. |
| Explainable automated outcome | Field-level terms diff; material changes are `RECONFIRM`, seller/currency changes are `ESCALATE`. | Materiality thresholds need merchant approval and change management. |
| Evidence integrity | Canonical Ed25519 signatures, hash chain, signed chain seals, verifier-side key registry with active/expired/revoked status. | Demo storage/key custody is not a KMS/HSM or immutable-retention service. |
| Payment-event authenticity | HMAC checked over Razorpay's raw webhook body, replay/idempotency checks, and exact Order-to-Offer-Lock binding. | A valid payment event does not prove delivery, quality, identity or a final legal outcome. |
| Human oversight | A lock can never silently clear an AI uncertainty; material operational changes stop for buyer/operator action. | Production needs role-based access, case queues and named decision owners. |

## How this maps to public guidance

- The DPDP Act, 2023 places the burden on a data fiduciary to prove notice and consent when consent is the basis of processing. Atlas’s playback, purpose-limited evidence fields and explicit approval boundary are designed to help a merchant retain that proof—not to declare compliance. [DPDP Act, 2023](https://www.meity.gov.in/static/uploads/2024/02/Digital-Personal-Data-Protection-Act-2023.pdf)
- The Consumer Protection dark-pattern guidelines are why Atlas treats a buyer-visible replay and a refusal to silently alter terms as product controls; the speech guard is supporting assurance, not a compliance certification. [Department of Consumer Affairs guidance](https://consumeraffairs.nic.in/acts-and-rules/consumer-protection/consumer-protection)
- Razorpay’s own Agent Studio principles place irreversible-action approval and platform validation on the money-action layer. Atlas stays on the adjacent commercial-promise and merchant-operations layer. [Agent Studio principles](https://razorpay.com/blog/?p=26508)
- CERT-In's 2025–26 BFSI threat-report release reinforces the need for layered controls, logging and incident readiness. Atlas adopts those as design goals; it is not a regulated entity or a CERT-In certification. [CERT-In release](https://www.cert-in.org.in/s2cMainServlet?pageid=PUBWEL03)

## Required pilot operating policy

Before a real merchant pilot, write and approve these items outside the repository:

1. **Purpose / retention policy:** what proof is retained, where, for how long, who can export it, and how deletion/legal-hold conflicts are handled.
2. **Approval UX policy:** exact playback language, accessibility/language variants, withdrawal/cancellation route, and treatment of delegated buyer agents.
3. **Materiality policy:** which changes require reconfirmation, thresholds, merchant approver, version, rollback and effective date.
4. **Key / trust policy:** KMS/HSM owner, key IDs, public-key registry, rotation overlap, revocation procedure and independent verifier distribution.
5. **Incident policy:** webhook-secret compromise, incorrect lock, missing proof, model outage, dispute escalation and audit-log preservation paths.
6. **Human ownership:** roles allowed to release a case, override a result, amend a policy or request a re-confirmation. Every override needs an actor, reason and new evidence event.

## Non-negotiable launch gates

- Verify a Test Mode `payment.captured` webhook over public HTTPS and preserve only safe evidence.
- Run the exact production agent/prompt/tool version through a labelled `pass^5` holdout; do not promote the repository's synthetic result to a real-world reliability number.
- Demonstrate one OMS or subscription worker that genuinely stops an outbound action on `RECONFIRM`.
- Obtain security review, tenant authentication/authorisation, encrypted storage, monitoring and incident response sign-off.
- Obtain merchant/legal review of notice, consent, retention, cross-border data and consumer-communication obligations.

Until those gates are met, Atlas is a transparent buildathon prototype with production-shaped controls—not a production compliance product.
