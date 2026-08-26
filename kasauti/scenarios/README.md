# Scenario bank (drop 4)

Three packs, twelve scenarios each, three cached paraphrase variants per turn, one ground-truth label per scenario.

| Pack | What it plants | Ground truth field |
|------|----------------|--------------------|
| language | false urgency, confirm shaming, drip pricing, nagging after a no, invented policy | `expected.pattern` |
| money | discount over ceiling, promise-to-order variance, refund without approval, threshold breach | `expected.impact_paise` |
| hijack | instruction text in product pages, reviews, tool outputs | `expected.followed` |

Paraphrases are generated once (about 40 batched calls) and committed, so runs never spend quota on simulators.
