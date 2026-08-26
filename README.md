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
pytest                                                # 79 tests, no network
python scripts/demo_drop1.py                          # one transaction, end to end
python scripts/demo_dispute.py                        # two disputes: agent error (refund), cross-border (contest, priced)
```

Run Kasauti, the adversarial bank, at zero quota (rule-based judge):

```bash
python scripts/run_kasauti.py            # naive agent vs guarded agent, 9 scenarios
python scripts/run_kasauti.py --k 3      # repeats with paraphrase variants
python scripts/run_kasauti.py --llm gemini   # real judge for the LLM checkers, cached in data/llm_cache.db
python scripts/show_findings.py              # every dark-pattern finding with its quoted sentence
python scripts/label_transcripts.py --labeler yourname   # hand-label the conversations (judge findings hidden)
python scripts/report.py --judge gemini-3.1-flash-lite   # report + calibration; writes corrections into memory
python scripts/run_kasauti.py --llm gemini --memory      # rerun with the humans' corrections applied
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

Fourteen seed scenarios: two clean controls (one in Hinglish), three money, two hijack, three
language, four settle; five of them carry a planted dispute. Zero-quota run:

```
rule-naive   leakage/1000 conv = ₹70,422   split: cart ₹862 | promise vs charge ₹60 | after payment ₹64
             words: 4 incidents = 286 per 1000 conv     disputes: 5 raised, 100% as expected, ₹3,050 refunds
guarded      leakage/1000 conv = ₹4,565    split: cart ₹0   | promise vs charge ₹0  | after payment ₹64
             words: 0 incidents, 3 messages rewritten    disputes: 4 raised, 100% as expected, ₹0 refunds
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

### Words: the speech guard and the transcript judge

The gate fixes money, not sentences. `sakshi/speech.py` encodes the dark patterns an agent can
commit in speech (from the 2023 guidelines: false urgency, confirm shaming, nagging, drip pricing,
basket sneaking, bait and switch, forced action, misrepresentation, subscription trap). A
deterministic scanner runs on every message the guarded agent is about to send and replaces
blatant phrasing with a compliant line, logging `speech.blocked`. After the conversation, the
transcript judge (`kasauti/judge.py`) scores the whole exchange with the definitions and the
merchant's real policies, so an invented "full refund anytime" is caught against a policy that
says otherwise. Judge calls are counted separately from gate calls: a clean cart still costs zero
gate calls; each transcript costs one judge call with a real model.

### The report and the two headline numbers

`scripts/report.py` writes `data/reports/report.md`: the Agent Leakage Rate before and after
the guard, on the bank and weighted by a declared traffic mix (`kasauti/traffic_mix.json`, an
assumption stated in the report), the leakage split, incidents, disputes, judge calibration,
the model-call budget, and what is simulated. Quote the mix-weighted figure as the estimate; the
bank figure is a stress number.

### Calibration and Stage 4 memory

The judge is graded against people, not itself. `scripts/label_transcripts.py` shows each unique
conversation blind (shuffled order, scenario names hidden, judge findings hidden) and records what
a human sees. Eighteen conversations labelled by two people is a small set, so the report gives
counts rather than a single accuracy figure, and the second labeller, who did not write the
scenarios, is the one that matters. `kasauti/calibrate.py`
scores the scanner alone, the model judge alone, and the merged verdict against those labels
(precision, recall, F1, strict and by pattern family, since drip pricing and basket sneaking both
mean "something joined the bill without being said"), and reports agreement between two labelers
(Cohen's kappa). `sakshi/memory.py` then turns the disagreements into corrections: a pattern the
judge found that the human did not is suppressed on that conversation next time, a merchant's
substitution tolerance is raised from an override, and a dispute policy ("always return an
undisclosed delivery fee") maps a claim type to a recommendation. Batch 2 with `--memory` is the
self-improving demo: the false positive from batch 1 is gone, and no new quota was spent because
the transcripts are cached.

First real-model batch (gemini-3.1-flash-lite, 21 uncached calls): the judge found the four
language-pack patterns, two silent additions the scanner cannot see from phrasing (a third pizza,
an injected garlic bread, both called drip pricing, a family match for basket sneaking), and one
false positive (a clean USD tee order flagged because the price was only said at checkout). The
scanner had zero false positives and missed those two. Merged is better than either, which is
the design, and the false positive is what the labels are for.

### Stage 3: the dispute agent

`sakshi/dispute.py` reads the chain back and recommends CONTEST, REFUND, PARTIAL_REFUND or
ESCALATE with reasons. Rules, not vibes: a cart that matched intent before payment is contested
with the intent receipt; a blocked cart that was paid anyway is refunded as agent error; an
undisclosed charge above the stated total is partially refunded; a delegated order held or
blocked by the gate and paid without a human approval on record is refunded; delivery claims
escalate because that evidence is outside the chain. Every result prices the cost of refunding:
amount, fee and GST Razorpay keeps, and on international payments the gap between the
payment-day rate and the dispute-day rate, because Razorpay deducts disputes at the dispute-day
rate. The evidence pack has nine sections in Razorpay's representment order, from transaction
details through customer authorisation to ledger integrity, and a plain-language explanation is
written for the customer. Anything below the confidence threshold, above the merchant's approval
threshold, or escalated is marked for a human.

## Layout

```
sakshi/
  ledger.py           append-only, hash-chained events (SQLite)
  intent.py           IntentReceipt -> Razorpay-safe notes, hashes, limits enforced
  models.py           Cart, CartLine, MerchantConfig
  checkers/           checker protocol; Stage 1 deterministic checkers; LLM checkers (llm.py); Stage 2 (stage2.py)
  speech.py           dark-pattern definitions, phrase scanner, speech guard
  dispute.py          Stage 3: chain view, decision rules, cost of refund, evidence pack, customer explanation
  memory.py           Stage 4: corrections (substitution tolerance, judge overrides, dispute policy)
  engine.py           runs checkers, writes the ledger, returns notes for the order
  gateway.py          StubGateway (tests, demo) and LiveGateway (official SDK, test mode)
  proxy/app.py        intercepting proxy in front of api.razorpay.com
  settlements/        fee math, refund fee burn, schema-faithful synthetic recon lines
  llm/                provider interface (mock, Ollama, rate-limited Gemini), response cache, heuristic judge
  fx/fbil.py          FBIL reference via Frankfurter v2, cache, stale-day reporting, labelled ECB fallback
kasauti/
  scenario.py         scenario schema, loader, validation
  simulator.py        scripted customer with seeded paraphrase variants
  judge.py            transcript judge (model + scanner, memory-aware), transcript hashing
  calibrate.py        judge vs labels, pattern families, two-labeler agreement
  report.py           mix-weighted headline, before/after tables, markdown report
  traffic_mix.json    the traffic-share assumption
  labels/             hand labels, one file per labeler
  agents.py           RuleAgent (naive), GuardedAgent (gate + correction policy), LlmAgent (minimal)
  runner.py           run k times, measure, summarize (Agent Leakage Rate)
  scenarios/*.json    the bank
scripts/
  demo_drop1.py       one transaction end to end
  demo_dispute.py     two disputes with evidence packs
  run_kasauti.py      naive vs guarded over the bank
  paraphrase_bank.py  one-time variant generation (offline or model), written back to the bank
  fx_check.py         FBIL lookup with staleness
  llm_check.py        verify the model backend, list models, one probe call
  label_transcripts.py  hand-labelling session
  report.py           build the report, learn corrections from labels
  show_findings.py    findings with quoted sentences
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
| 3 | Stage 2: promise-to-order, settlement fee, FX vs FBIL (with staleness), refund burn; FX quote check; settle pack; leakage split | done |
| 4 | Speech guard and transcript judge (words); Stage 3 dispute agent with evidence pack, customer explanation and dispute-day FX; planted disputes | done |
| 5 | Report with mix-weighted headline; labelling tool; calibration and two-labeler agreement; Stage 4 correction memory; findings with quotes | this commit |
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
