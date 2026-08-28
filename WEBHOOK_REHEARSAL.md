# Razorpay Test Mode webhook rehearsal

This is the final external-proof rehearsal. It is deliberately separate from the local test suite: a webhook becomes evidence only when Razorpay sends it to a public HTTPS endpoint and Atlas verifies its raw-body HMAC.

## What is already implemented

- `POST /webhooks/razorpay` verifies `x-razorpay-signature` before parsing.
- `x-razorpay-event-id` prevents duplicate evidence; the raw-body SHA-256 is a fallback.
- `payment.captured` maps to `rzp.payment.captured` and reseals the offer journey.
- The browser’s checkout success callback is stored as `checkout.client.returned` and cannot fake a payment.

## One-time local setup

```powershell
python scripts/generate_evidence_key.py   # creates a local git-ignored dev key once
python ui/server.py
ngrok http 5000
```

Copy the HTTPS forwarding URL from ngrok. In the Razorpay Dashboard **Test Mode**, create a webhook:

```text
https://YOUR-NGROK-DOMAIN/webhooks/razorpay
```

Subscribe to `payment.captured` and copy Razorpay’s webhook secret into `RAZORPAY_WEBHOOK_SECRET` in `.env`, then restart the server. Do not put the secret in a video, screenshot, issue, or commit.

## Rehearse

1. Open `/offer-lock`, sign a buyer-visible offer, then create the guarded Test Mode order.
2. Click **Open Razorpay Test Checkout**. The payment step is intentionally a human decision.
3. Complete a Razorpay Test Mode payment using Razorpay’s current official test-payment instructions.
4. Click **Check webhook status**. It changes only when `payment_captured_by_verified_webhook` is true.
5. Open the signed evidence journey; it will show the verified Razorpay event and a fresh chain seal.

Save only the resulting order ID, payment ID (if needed), accepted webhook event ID and redacted evidence screenshot in the submission artifact. Do not claim this rehearsal was completed until those facts are present.
