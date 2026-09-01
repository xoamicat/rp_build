# SettleX Atlas — human 5:30 pitch and demo script

## Before you record

This is designed to sound like a founder explaining something they care about,
not someone reading a product manual. Speak a little slower than feels natural;
after the first question and the final line, leave a full beat of silence.

Keep the claims precise. The factual proof points are: one completed Razorpay
Test Mode payment with a verified webhook, 104 automated checks, and a
14-scenario internal synthetic strict `pass^5` run. The last is a regression
check—not a τ-bench result, customer traction, or a production-reliability
claim.

## 0:00–1:10 — Face camera: start with the person, not the product

> Every bad commerce dispute begins with one painfully human sentence:
>
> **“But that’s not what I bought.”**
>
> Imagine you are ordering dinner after a very long day.
>
> You tell an AI assistant: “Two pizzas. ₹680. Saturday. And please—no
> substitutions.”
>
> At 9:01, you tap pay. The green tick appears. You relax.
>
> But at 9:03, the delivery date has slipped, the price has changed, or one of
> those pizzas has quietly become something else.
>
> The payment is successful. But was the promise kept?
>
> Nobody has to be lying for this to happen. The payment rail can correctly say
> money moved. The merchant system can correctly say an order exists. And the
> buyer can still be left asking, “Wait… what exactly did I agree to?”
>
> That buyer did not consent to a green tick. They consented to a promise.
>
> I’m building **SettleX Atlas** so that “payment successful” is no longer the
> end of the story. It is a checkpoint.
>
> Atlas is a commercial-promise layer around agentic payments. Before money and
> fulfilment drift apart, it captures what the buyer actually saw, holds risky
> changes for confirmation, and leaves behind proof that a human can understand.
>
> Razorpay should keep doing what it does brilliantly: validate and move money.
> Atlas protects the promise around that payment—at the seam between a buyer
> agent, the merchant’s OMS, and a Razorpay event.

**Cut to Offer Lock.**

## 1:10–1:45 — Screen: `/offer-lock` — make the promise visible

**Show:** the buyer request, bounded-AI card, and versioned ₹680 offer.

> This is the first small but important idea: before an agent buys, the buyer
> should be able to see one clear version of the deal.
>
> Here, AI turns a natural-language request into a structured request against
> the merchant’s known catalogue. But it is deliberately on a short leash.
> The model cannot invent a SKU, set a price, move money, or call consent.
>
> Typed merchant data fills in the price, delivery, return, and substitution
> terms. If something is unknown, we stop instead of guessing.
>
> So the buyer is not approving an AI’s interpretation. They are approving a
> playback: two pizzas, ₹680, Saturday, no substitutions.

## 1:45–2:10 — Screen: sign the offer — turn clarity into evidence

**Click:** `Sign this buyer-visible offer`.

> When they say yes, Atlas creates an **Offer Lock**: a canonical snapshot of
> those visible terms, signed with Ed25519.
>
> Think of it as a receipt for the agreement—not just for the payment. Razorpay
> gets a compact reference in its normal Order notes; Atlas keeps the complete,
> signed promise without putting private buyer text or credentials there.
>
> Later, nobody has to argue from memory or screenshots. We can compare reality
> with the exact version the buyer accepted.

## 2:10–2:40 — Screen: simulate drift — show the product’s point of view

**Click:** `Silent drift`, then `Verify current terms`.

> Now let’s make the uncomfortable thing happen.
>
> The price moves from ₹680 to ₹930. Delivery moves. The return terms change.
>
> Most systems will still see a paid order. Atlas sees a changed promise.
>
> This verdict is not a mysterious AI confidence score. It is a deterministic,
> field-by-field comparison of the signed offer against the current merchant
> terms. The result is simple: **RECONFIRM.**
>
> A successful payment is not permission to quietly fulfil a different deal.

## 2:40–3:10 — Screen: verified evidence journey — make proof reviewable

**Open:** the verified evidence URL or **Review sealed proof**. Ensure the
`rzp.payment.captured` event is visible.

> And when a buyer or support agent asks, “Can we prove that?”, this is the
> answer.
>
> This is a real Razorpay Test Mode payment in the evidence journey. Atlas does
> not mistake a browser callback for payment proof.
>
> It validates Razorpay’s raw-body HMAC, rejects duplicate delivery, and binds
> the payment to the exact Order that Atlas created. Then it reseals the event
> alongside the buyer’s original Offer Lock.
>
> Instead of opening four systems and collecting screenshots, a support person
> gets one readable timeline: promise, payment, change, decision.

## 3:10–3:40 — Screen: `/subscription-preflight` — prevent a quiet renewal

**Show:** changed renewal terms and `PATCH withheld — new confirmation
required`.

> The same problem is even harder with subscriptions, because the change can
> arrive months after the buyer stopped thinking about it.
>
> Before a merchant worker calls Razorpay’s subscription-update API, it sends a
> typed planned patch through Atlas. If the plan or renewal terms have drifted,
> Atlas says **RECONFIRM**, and the PATCH is withheld.
>
> A notification is not consent. Only an explicit **ALLOW** lets the OMS worker
> continue.

## 3:40–4:05 — Screen: `/fx-promise` — show care where people feel it

**Click:** `Assess FX lifecycle` and show the ₹15.00 delta.

> There is another promise buyers feel immediately: the price they thought they
> were paying across currencies.
>
> The displayed rate, payment-day rate, and a later dispute-day rate can all be
> different. Atlas keeps all three as source-linked facts. It calculates in
> integer paise—not floating-point approximations—and makes this ₹15 exposure
> explainable.
>
> It does not pretend to decide a refund. It gives the merchant the evidence to
> explain the difference fairly.

## 4:05–4:25 — Screen: `/release` — show humility, not theatre

> Good agentic products need a way to say, “We tested this,” without pretending
> they are magically reliable.
>
> Atlas currently has 104 automated checks. Its release screen runs 14
> reproducible scenarios under a strict internal `pass^5`: a scenario passes
> only if every repeat respects policy.
>
> That is regression evidence, not a production guarantee. In commerce, that
> distinction is part of product maturity.

## 4:25–5:30 — Face camera: make the idea feel inevitable

> I do not think agentic commerce needs another dashboard. It needs a memory
> that survives every handoff.
>
> The innovation here is a better kind of receipt.
>
> Not just: “We took your money.”
>
> But: “Here is the promise you saw. Here is the payment we verified. Here is
> what changed. And here is why we paused—or proceeded.”
>
> We use AI where it is genuinely useful—understanding what a human asked for.
> We use deterministic rules where trust matters—locking the terms, comparing
> change, and deciding whether to pause.
>
> Under the hood, that means canonical terms signed with Ed25519; Razorpay
> webhooks verified from the raw body, deduplicated, and order-bound;
> subscription changes held behind a server-side gate; FX facts calculated in
> integer paise; and consequential events sealed into an evidence chain.
>
> But the real value is human. Buyers deserve not to be surprised. Honest
> merchants deserve less ambiguity. Support teams deserve evidence they can use
> without becoming detectives.
>
> We would start narrowly: shadow one high-drift workflow for 30 days—delivery
> changes, substitutions, or a renewal. Measure the drift Atlas catches,
> reviewer agreement, evidence completeness, and time to resolution. Then turn
> on the reconfirmation gate.
>
> Agents will make commerce faster.
>
> **SettleX Atlas makes sure trust does not get cheaper in the process.**

## Recording order and on-screen rules

1. Face camera: the dinner story and the question: “Was the promise kept?”
2. Offer Lock: bounded AI, buyer-visible offer, then sign it.
3. Simulate drift and hold on the `RECONFIRM` verdict for a beat.
4. Evidence journey: show `rzp.payment.captured`, the seal, and the readable
   event timeline.
5. Subscription preflight: show `PATCH withheld`.
6. FX Promise: show the three dates and ₹15 delta.
7. Release page: show the strict internal `pass^5` card.
8. Face camera: better receipt, pilot, final line.

If you include the Razorpay Dashboard, use it only as a two-second proof insert
with the spoken line: “This is a successful Test Mode payment.” Blur Order IDs,
payment IDs, email addresses, webhook URLs, and every credential. Never record
`.env`, a terminal, or webhook configuration.
