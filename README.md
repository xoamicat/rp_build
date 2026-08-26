# Sakshi

**The witness layer for agent-initiated payments on Razorpay.**

When an AI agent buys on a customer's behalf, UPI Reserve Pay proves that money up to a cap was
pre-approved. Nothing proves what the customer asked for, whether the agent stayed inside that
intent, what the agent promised versus what was charged, or what actually settled. When the
customer says "I never wanted this," the merchant has no evidence and refunds.

Sakshi records the intent, gates the cart against it before payment, reconciles promise against
charge against settlement after payment, and turns disputes into evidence. Razorpay validates the
money. Sakshi validates the words, and the receipt rides along.

## One engine, four moments

Every stage is the same primitive: a **claim** is recorded, an **observation** arrives, a
**checker** compares them, a **verdict** with a rupee impact is written to a hash-chained **ledger**.

| Moment | Claim | Observation | Checkers |
|---|---|---|---|
| 1. Gate (before payment) | intent: items, cap, mandate | the cart the agent built, the content it read | price cap, quantity/SKU drift, discount ceiling, human-approval threshold, injection pre-filter |
| 2. Reconcile (after payment) | what the agent promised | order, payment, settlement line | promise-to-order variance, order-to-settlement fees, applied rate vs FBIL, refund fee burn |
| 3. Dispute | the whole chain | the customer's claim | the same checkers in explain mode, plus dispute-day FX exposure |
| 4. Learn | human overrides | later cases | checker calibration from corrections |

### The Intent Receipt rides in `notes`

Razorpay entities carry a `notes` object (up to 15 key-value pairs, 256 characters each), and the
Settlement Recon API returns `notes` and `order_id` on every settled line. Sakshi writes the intent
hash, a short playback, the cap and the mandate reference into the order's notes at creation. From
then on the intent travels with the money: into the payment, into the settlement report, into the
dispute. No new fields, no side database.

Privacy: the raw customer utterance is never stored, only its hash and the agent's playback.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # leave keys blank for stub mode
pytest                                                # 57 tests, no network
python scripts/demo_drop1.py                          # one transaction, end to end
```

Run Kasauti, the adversarial bank, at zero quota (rule-based judge):

```bash
python scripts/run_kasauti.py            # naive agent vs guarded agent, 9 scenarios
python scripts/run_kasauti.py --k 3      # repeats with paraphrase variants
python scripts/run_kasauti.py --llm gemini   # real judge for the LLM checkers, cached in data/llm_cache.db
```

Look up the FBIL reference for a date and see how stale the feed is (cached after first run):

```bash
python scripts/fx_check.py               # today: the feed usually trails by several days
python scripts/fx_check.py 2026-08-15    # a holiday: rolls back to the last published day
```

Run the interceptor (stub mode until keys exist in `.env`):

```bash
python -m sakshi.proxy.app        # http://127.0.0.1:8787, GET /healthz
```

Point any agent's Razorpay base URL at `http://127.0.0.1:8787` and every call it makes is logged
to the ledger, linked by the `X-Sakshi-Txn` header or by `notes.sakshi_txn`.

## How the LLM is spent

Deterministic checkers run first and are free. The two LLM checkers (semantic substitution,
injection judgement) only run when a deterministic checker found a semantic case, so a clean
cart costs zero model calls. Every model response is cached by prompt hash
(`sakshi/llm/cache.py`), so re-runs, re-judging and demos never spend quota twice. Development
runs use `HeuristicJudge`, a rule-based stand-in; numbers you report come from a real judge.

## Kasauti: the numbers

Kasauti scripts a customer through a scenario (paraphrase variants picked by seed), drives the
agent to checkout, and measures the cart that reached payment with Sakshi's checkers against
ground truth. Two agents ship: `RuleAgent`, a deliberately naive ordering agent with switchable
bad habits (caves on discounts, follows injected instructions, manufactures urgency, nags after
a no, rounds orders up to unlock combos), and `GuardedAgent`, the same agent behind the gate.

Thirteen seed scenarios: two clean controls (one in Hinglish), three money, two hijack, two
language, four settle. Zero-quota run:

```
rule-naive   leakage/1000 conv = ₹75,839   split: cart ₹862 | promise vs charge ₹60 | after payment ₹64
guarded      leakage/1000 conv = ₹4,916    split: cart ₹0   | promise vs charge ₹0  | after payment ₹64
```

Read the split, not the headline. Cart and promise leakage is what the agent caused and the gate
prevented. After-payment findings (a settlement fee above schedule, a conversion 3.9 percent under
the FBIL reference, fee and GST burned on a refund) are the same for both agents: Sakshi finds that
money, it cannot prevent it, and the dispute stage prices it. The headline is a stress number on a
bank where 11 of 13 conversations carry a planted fault; the report (drop 5) weights it by a
declared traffic mix. Language-pack patterns are judged on transcripts in drop 4.

### Stage 2 in one transaction

`promise_order` compares what the agent said the total was with the amount it put on the order,
before payment (BLOCK) or after (FLAG). `settlement_fee` compares the settlement line with the
payment and the merchant's fee schedule. `fx_rate` compares the applied conversion on an
international payment with the FBIL reference for that day and lowers its confidence as the
reference gets staler. `refund_burn` prices the fee and GST that Razorpay keeps on a refund.
`fx_quote` (Stage 1) checks a rate the agent quoted to a foreign customer against the same reference.

## Layout

```
sakshi/
  ledger.py           append-only, hash-chained events (SQLite)
  intent.py           IntentReceipt -> Razorpay-safe notes, hashes, limits enforced
  models.py           Cart, CartLine, MerchantConfig
  checkers/           checker protocol; Stage 1 deterministic checkers; LLM checkers (llm.py); Stage 2 (stage2.py)
  engine.py           runs checkers, writes the ledger, returns notes for the order
  gateway.py          StubGateway (tests, demo) and LiveGateway (official SDK, test mode)
  proxy/app.py        intercepting proxy in front of api.razorpay.com
  settlements/        fee math, refund fee burn, schema-faithful synthetic recon lines
  llm/                provider interface (mock, Ollama, rate-limited Gemini), response cache, heuristic judge
  fx/fbil.py          FBIL reference via Frankfurter v2, cache, stale-day reporting, labelled ECB fallback
kasauti/
  scenario.py         scenario schema, loader, validation
  simulator.py        scripted customer with seeded paraphrase variants
  agents.py           RuleAgent (naive), GuardedAgent (gate + correction policy), LlmAgent (minimal)
  runner.py           run k times, measure, summarize (Agent Leakage Rate)
  scenarios/*.json    the bank
scripts/
  demo_drop1.py       one transaction end to end
  run_kasauti.py      naive vs guarded over the bank
  paraphrase_bank.py  one-time variant generation (offline or model), written back to the bank
  fx_check.py         FBIL lookup with staleness
tests/
```

## What is simulated, and why

- **Settlements.** Razorpay test mode never settles. Stage 2 runs on synthetic settlement lines
  that use the exact field set of `GET /v1/settlements/recon/combined`, so the code runs unchanged
  on a real recon export. Fee rates are placeholders; set yours from your pricing page.
- **Reserve Pay mandates.** Not available in test mode. The mandate reference is a string carried
  in the receipt. The cap logic is enforced by Sakshi, not by the mandate.
- **International payments.** `StubGateway.simulate_capture(rate=...)` derives `base_amount` the way
  Razorpay documents it (processing bank's rate on the payment date). Whether test mode returns
  `base_amount` for international test cards is being verified.
- **FX reference.** FBIL's daily reference rate via Frankfurter v2 (`providers=FBIL`, with `date`).
  The feed rolls back on holidays and can trail the calendar by a week; every reference carries
  its published date and the checker's confidence falls with the gap. ECB is a labelled fallback.
  In Kasauti scenarios the reference is planted (`stage2.fbil`) so runs are deterministic.

## Drops

| Drop | Contents | Status |
|---|---|---|
| 1 | engine, ledger, intent receipt, Stage 1 checkers, interceptor, settlement synth, providers, tests | done |
| 2 | LLM layer for Stage 1 with response cache; scenario bank, scripted customer, naive and guarded agents, runner, first leakage numbers | done |
| 3 | Stage 2: promise-to-order, settlement fee, FX vs FBIL (with staleness), refund burn; FX quote check; settle pack; leakage split | this commit |
| 4 | Stage 3 explain mode, verdict rules, evidence pack in Razorpay's representment order; Kasauti runs | |
| 5 | Agent Leakage Rate report, before/after guardrail comparison, judge calibration | |
| 6 | README final, benchmark page, video script | |

## Sources the design rests on

- Razorpay Agent Studio principles and guardrails (March 30, 2026): platform validates money actions; certification screens communication patterns; agent provider is accountable.
- Razorpay on agentic shopping liability (Medianama, March 26, 2026): if the agent orders the wrong item, the merchant handles the dispute and refund.
- Razorpay Orders API and Settlement Recon API reference: `notes` limits; recon line fields.
- Razorpay Disputes FAQ: international dispute deductions use the conversion rate on the dispute date.
- NPCI Unified Agent Protocol reporting (Business Standard, July 2026); CERT-In Digital Threat Report 2025-26 (human-in-the-loop above thresholds, full audit trails).
- Guidelines for Prevention and Regulation of Dark Patterns, 2023; CCPA self-audit advisory (June 5, 2025).
- Google AP2 specification (Intent / Cart / Payment Mandates, prompt playback).
- τ-bench (Yao et al., 2024): pass^k for agent reliability.
