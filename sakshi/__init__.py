"""Sakshi: the witness layer for agent-initiated payments on Razorpay.

One engine, four moments. A claim is recorded (what the customer asked for,
what the agent promised, what was quoted). An observation arrives (the cart,
the order, the payment, the settlement, the dispute). Checkers compare claim
and observation and issue a verdict. Every step lands in a hash-chained
ledger, and the customer's intent rides with the money through Razorpay's
own ``notes`` field.
"""

__version__ = "0.1.0"
