# SettleX Atlas — 5 minute 40 second pitch + demo script

**Delivery:** Begin on black. Be direct and measured. The strongest proof is the live product—not a slide deck.

## 0:00–0:30 — Cold open

> Imagine telling an AI: “Two margheritas, under eight hundred rupees, delivered Saturday.”
>
> It shows you that deal. You agree. Then fulfilment silently makes it more expensive, adds garlic bread, moves delivery to Tuesday and changes the return terms.
>
> Payment can still be perfectly valid. But who can prove what promise the buyer actually approved?

## 0:30–0:55 — Honest positioning

> Razorpay is making agentic payments real. Agent Studio already provides guardrails, audits and dispute support. We are not rebuilding those.
>
> The missing public surface we found is narrower: a signed, versioned record of the complete buyer-visible commercial offer that survives from an external AI agent through Razorpay checkout to fulfilment, renewal and support.

**On screen:** Open **Lock buyer offer**.

## 0:55–1:38 — Meaningful AI, safely bounded

> Here is where AI is genuinely useful. I ask the configured Gemini model for two margheritas, Saturday delivery, no substitutions.
>
> It turns natural language into a structured offer draft and tells us where it is uncertain. But it has no authority to invent money terms: it can select only merchant catalogue SKUs and quantities. Server code sets price, delivery and policy. Unknown SKUs and malformed output are rejected.
>
> And this is still not consent. The buyer must see and confirm this draft.

**On screen:** Use the violet **Bounded AI** panel. Point to model provenance, input hash, catalogue validation, and buyer-review copy.

## 1:38–2:15 — Capture the actual promise

> The buyer now sees the final items, total, delivery and policy terms. I sign it only after that review.
>
> Atlas canonicalises the terms and signs them with Ed25519. It stores an opaque approval reference—not raw chat. The short lock ID, catalogue version, key ID and signature are what travel in Razorpay Order notes.

**On screen:** Click **Sign buyer-approved offer**. Point to the signed commitment card.

## 2:15–3:00 — The failure payment approval misses

> Now the catalogue quietly changes: price rises, garlic bread appears, delivery becomes later and returns change.
>
> I check before fulfilment. Atlas returns `RECONFIRM` with a field-by-field diff. Not “risk 87.” The merchant must ask the buyer again through the channel they already use.

**On screen:** Choose **Silent drift** and click **Verify current terms**.

## 3:00–3:28 — Make evidence operational

> This is not an alert that disappears. I open the signed journey: it contains AI draft provenance, the buyer confirmation, the Offer Lock and the fulfilment check in a hash-chained evidence record.
>
> If the buyer complains that the offer changed, Atlas escalates. It will not use an old approval to contest a new, changed-offer claim.

**On screen:** Click **Review signed journey**, then **Review buyer claim outcome**.

## 3:28–4:15 — Razorpay integration, proven not claimed

> The integration is intentionally boring. The buyer agent sends the draft. Atlas returns the lock. The merchant creates its ordinary Razorpay Order with the compact proof references in `notes`.
>
> I ran our official-SDK verifier against Razorpay Test Mode: it created and fetched an unpaid real order with all fifteen allowed note fields, including `atlas_lock` and `atlas_sig`. The upgraded durable dashboard path also created its own Test Mode order with the same full notes budget; it remains unpaid. The dashboard refuses live keys and marks browser success as untrusted. That safe artifact is in this repository; it contains no secret, raw chat, or payment capture.
>
> Razorpay webhooks bring back payment and refund truth. Before shipping, substitution, or renewal, the OMS calls Atlas: `ALLOW`, `RECONFIRM`, or `ESCALATE`.

**On screen:** Show `data/evidence/razorpay-test-mode-*.json`, then [INTEGRATION.md](INTEGRATION.md).

## 4:15–4:40 — It does not block normal commerce

> Change nothing and Atlas returns `ALLOW`. A price decrease is recorded but does not stop the buyer. A merchant or currency switch is more serious: it escalates for human review.

**On screen:** Select **No change**, run check, show `ALLOW`.

## 4:40–5:10 — Reliability before release

> Kasauti is our release gate for the surrounding AI agent. It runs fourteen reproducible adversarial fixtures: hidden upsells, prompt injection, false urgency, discount abuse, settlement and FX drift.
>
> The report includes its provider, seed, scenarios and simulation boundaries. We label it honestly: synthetic fixtures, not production accuracy. The Offer Lock’s money-sensitive final decision remains deterministic.

**On screen:** Open **Test before release** and point to the manifest banner.

## 5:10–5:40 — Close

> Razorpay makes it possible for an AI to pay. SettleX Atlas makes sure the AI cannot quietly rewrite the deal after the buyer agreed.
>
> In agentic commerce, payment success should not be the only receipt. The buyer’s approved promise should be one too.

---

## Recording direction

Record at 1080p, browser zoom 100%, no background music, and keep the final recording below six minutes. Use the live Gemini draft once; it is cached after the first identical request. The demo is at `http://127.0.0.1:5000`.

### Claims you must not make

- Do not say Atlas prevents all fraud, proves delivery, or is legally conclusive.
- Do not call a dashboard browser return a live payment. The separate Test Mode artifact proves only unpaid-order creation and retrieval; a Test Mode payment becomes evidence only after the public HTTPS webhook is HMAC-verified.
- Do not say Razorpay signs the lock; Atlas signs it and Razorpay carries compact references in supported Order notes.
- Do not say Atlas replaces Razorpay Agentic Payments, Agent Studio, risk controls, Smart Collect or Settlement Recon.
- Do not say a public-doc search proves a private feature does not exist. Call the positioning a documented-public-surface gap hypothesis.
