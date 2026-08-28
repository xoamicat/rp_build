# Five-minute judge demo

Start with the result: **“SettleX Atlas is a signed Offer Lock for agentic commerce: it preserves the exact commercial promise a buyer agent showed, then catches any material change before fulfilment or renewal.”**

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python ui/server.py
```

Open `http://127.0.0.1:5000`. The interaction/evidence screens default to ephemeral in-memory demo storage, but switch to the durable local evidence store when a development signing key is configured. The optional **Create guarded Test Mode order** action uses the official Razorpay SDK only when `rzp_test_` credentials are configured; it refuses live keys. Say clearly that a popup/browser success is not payment truth—the verified webhook is. The deployment contract is in [INTEGRATION.md](INTEGRATION.md).

For the strongest local recording, run `python scripts/generate_evidence_key.py` once before starting the server. The dashboard will show **Durable key-pinned store configured** and signed Offer Locks will survive a server restart. Call it a local development key in the video—never a production KMS.

## Judge flow

1. **0:00–0:35 — name the gap:** Open **Lock buyer offer**. Say: “A payment approval proves money may move. It does not preserve the complete promise an AI buyer was shown: exact SKUs, delivery date, returns, substitutions and future renewal terms.”
2. **0:35–1:20 — show meaningful, bounded AI:** In the violet panel enter “Two margheritas, Saturday, no substitutions,” then click **Ask configured AI to draft offer**. Point to provider/model and input hash. Say: “The model selects a catalogue SKU and quantity. It cannot set a price, alter a policy, approve itself, or create payment. Server code validates every field and presents uncertainty.”
3. **1:20–2:00 — show consent:** Review the generated offer and click **Sign buyer-approved offer**. Atlas signs the canonical snapshot and displays the lock ID, key ID and compact Razorpay-safe order-note references. No raw conversation, address, card data or UPI identifier is carried in those notes.
4. **2:00–2:45 — show the failure:** Select **Silent drift**. The merchant catalogue has a higher pizza price, an added item, later delivery and changed returns policy. Click **Verify current terms**. Atlas returns `RECONFIRM`, names every material delta, and says the buyer must be asked again. This is a deterministic diff, not an opaque AI score.
5. **2:45–3:15 — close the evidence loop:** Click **Review signed journey**, then **Review buyer claim outcome**. The same Offer Lock, post-consent diff and signed chain are available to operations. The claim view escalates rather than pretending the original approval settles a changed-offer complaint.
6. **3:15–4:00 — show real Razorpay fit:** In the new **Optional live proof** panel, create the guarded Test Mode order. Point to `15/15` notes capacity, the explicit Test-Mode-only boundary and **Open Razorpay Test Checkout**. Do not click Pay in a recorded dry-run unless your public HTTPS webhook is configured. Show [the safe artifact](data/evidence/razorpay-test-mode-atlas_verify_1787943567.json): the repository already created and fetched an unpaid real Test Mode order. Explain: “The popup return is intentionally untrusted; only the signed `payment.captured` webhook changes the evidence state.”
7. **4:00–4:40 — show normal commerce and safety:** Select **No change**, recheck, and show `ALLOW`. Explain that a price decrease is recorded but can proceed; merchant or currency identity changes become `ESCALATE` for human review.
8. **4:40–5:00 — release responsibly:** Open **Test before release**. Kasauti’s current `run-manifest.json` names provider, seed, fixtures and every synthetic boundary. It evaluates the surrounding agent for hidden upsells, prompt injection, false urgency and fee drift. It is not claimed as production accuracy.

## Questions to invite

- “Which buyer-agent approval key or merchant key should the verifier allow-list in a pilot?”
- “Which OMS event is the best first insertion point: shipment creation, substitution, or renewal?”
- “What change should trigger buyer reconfirmation for this merchant?”

Those questions show that Atlas is a deployable control plane alongside Razorpay, not a vague fraud claim.
