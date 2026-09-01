# Atlas pilot plan — prove the gap, not just the demo

Atlas is designed for the moment after an agent has shown a buyer an offer and before a merchant changes, fulfils or renews it. This document is a pilot plan, not a claim that customer research or production performance has already been completed.

## The first real integration

Start with one merchant that has all three systems below:

| Existing system | It sends Atlas | Atlas returns | The system does next |
|---|---|---|---|
| Chat, voice or buyer agent | final buyer-visible offer plus opaque approval reference | signed `OfferLock` ID and compact proof references | creates its existing Razorpay Order with those references in `notes` |
| Razorpay | signed payment/refund/dispute webhooks | privacy-safe lifecycle evidence | Atlas appends the verified event to the same transaction journey |
| OMS or subscription service | current SKU, price, delivery and policy terms before shipment, substitution or renewal | `ALLOW`, `RECONFIRM`, or `ESCALATE` plus a field-level diff | fulfils, asks the buyer again, or creates an operations case |
| Subscription-update worker | proposed Razorpay PATCH metadata plus merchant-mapped buyer-visible terms | preflight receipt + `razorpay_patch_permitted` | calls PATCH only on `ALLOW`; otherwise holds the change for buyer reconfirmation/ops |
| International finance / disputes | labelled displayed, reference, payment-day and dispute-day rates | FX Promise Envelope delta/reserve and evidence attachment | explains exposure; attaches source records; does not execute FX or decide the dispute |

Nothing asks Atlas to handle a card, UPI credential, payout or customer address. `order.notes` carries only short hashes/IDs/signature references; the signed snapshot remains in the merchant evidence store.

## Narrow pilot: substitution and delivery drift

Run a 30-day shadow-mode pilot for one SKU category where substitutions or delivery-date changes occur. First log decisions without blocking fulfilment; after review, enable `RECONFIRM` for the two changes the merchant agrees are material.

| Measure | How to calculate it | Pilot success threshold (to agree before launch) |
|---|---|---|
| Material drift rate | changed-offer checks / fulfilment attempts | establishes baseline; no invented target |
| Silent-drift catches | drift events that would otherwise ship/renew without a buyer message | manually verify every event in the first week |
| False-reconfirm rate | buyer/ops says the flagged diff was not material / all reconfirm requests | under merchant-agreed tolerance |
| Time to resolve | time from detected diff to buyer/ops decision | lower than current support case path |
| Evidence completeness | cases with offer, payment webhook and OMS diff linked / reviewed cases | 100% for pilot cases |
| Subscription release integrity | subscription PATCHs preceded by an Atlas receipt / sampled PATCHs | 100% in pilot scope |
| FX explanation completeness | international-dispute cases with all three labelled rate dates / reviewed FX cases | 100% in pilot scope |

## Five merchant-discovery questions

Record answers in a consented spreadsheet or CRM—do not invent quotes for a buildathon submission.

1. When an item, price, delivery date or policy changes after chat checkout, which system first knows?
2. Which changes must obtain buyer confirmation, and which are acceptable substitutions?
3. How often does support need to reconstruct “what the buyer saw” from chat, catalog and order data?
4. Which opaque order/customer reference may link an approval to OMS and Razorpay without storing personal data in Atlas?
5. Would operations rather receive a hold, a buyer reconfirmation message, or a case queue for each drift class?

## Evidence to collect before claiming product-market fit

Use this header row for interviews and shadow-mode reviews:

```text
record_id,date,merchant_segment,role,flow,source_of_truth,change_type,frequency,current_control,case_cost_minutes,atlas_decision,reviewer_agrees,quote_consent,verbatim_quote,follow_up
```

Keep customer data out of this research record. A judge should see the count of consented interviews, the method, representative anonymised quotes, and the before/after decision data—not anonymous claims of adoption.

## What changes before production

- Replace dashboard memory with an encrypted durable ledger/evidence store.
- Use a KMS/HSM-backed signing key and publish a key-ID/public-key allow-list to verifiers.
- Authenticate agent, OMS and operations calls; use tenant isolation, retention/deletion controls and audit access logs.
- Put verified webhook ingress behind public HTTPS, queue after HMAC verification, and monitor retries/idempotency.
- Make merchant-specific materiality policy versioned, reviewable and reversible.
- Enforce the subscription release receipt inside the merchant worker, not only in the dashboard, and retain the exact associated Razorpay subscription/event IDs.
- Have finance/operations approve FX source selection, expiry/allowed-spread policy and review workflow before using FX assessments operationally.

The repo’s [INTEGRATION.md](INTEGRATION.md) shows the exact data movement and [SECURITY.md](SECURITY.md) describes the present security boundaries.
