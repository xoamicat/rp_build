"""Stage 1 checkers: intent versus cart, before any money moves.

All deterministic in drop 1. The LLM layer (semantic substitution judgement,
injection judgement) is added in drop 2 and only runs when these find a
semantic case, which keeps the free-tier call budget small.
"""
from __future__ import annotations

import re
from typing import Optional

from ..models import CartLine
from .base import CheckContext, Status, Verdict


def _norm(s: Optional[str]) -> str:
    return " ".join((s or "").lower().split())


def _matches(intent_name: str, intent_sku: Optional[str], line: CartLine) -> bool:
    if intent_sku and line.sku:
        return intent_sku == line.sku
    a, b = _norm(intent_name), _norm(line.name)
    return bool(a and b) and (a == b or a in b or b in a)


class PriceCapChecker:
    """Cart total must not exceed the cap the customer stated."""

    name = "price_cap"
    stage = 1

    def check(self, ctx: CheckContext) -> Verdict:
        if ctx.intent is None or ctx.cart is None or ctx.intent.cap_paise is None:
            return Verdict(self.name, self.stage, Status.SKIP, "no cap stated")
        total, cap = ctx.cart.total_paise, ctx.intent.cap_paise
        if total <= cap:
            return Verdict(self.name, self.stage, Status.PASS, f"total {total} within cap {cap}",
                           evidence={"total_paise": total, "cap_paise": cap})
        return Verdict(
            self.name, self.stage, Status.BLOCK,
            f"cart total {total} exceeds stated cap {cap} by {total - cap}",
            impact_paise=total - cap,
            evidence={"total_paise": total, "cap_paise": cap},
            basis="cart_excess",
        )


class QuantitySkuChecker:
    """Every intent item must appear with the right quantity; nothing unrequested may appear."""

    name = "quantity_sku"
    stage = 1

    def check(self, ctx: CheckContext) -> Verdict:
        if ctx.intent is None or ctx.cart is None:
            return Verdict(self.name, self.stage, Status.SKIP, "no intent or cart")
        problems: list[str] = []
        impact = 0
        matched: set[int] = set()
        for item in ctx.intent.items:
            hits = [(i, line) for i, line in enumerate(ctx.cart.lines) if _matches(item.name, item.sku, line)]
            if not hits:
                problems.append(f"missing: {item.name} x{item.qty}")
                continue
            qty = sum(line.qty for _, line in hits)
            matched.update(i for i, _ in hits)
            if qty != item.qty:
                unit = max(line.unit_paise for _, line in hits)
                extra = max(qty - item.qty, 0)
                impact += extra * unit
                problems.append(f"quantity drift: {item.name} asked {item.qty}, cart {qty}")
        for i, line in enumerate(ctx.cart.lines):
            if i not in matched:
                impact += line.total_paise
                problems.append(f"unrequested item: {line.name} x{line.qty} ({line.source})")
        if not problems:
            return Verdict(self.name, self.stage, Status.PASS, "cart matches stated items")
        blocking = any(p.startswith(("quantity drift", "unrequested")) for p in problems)
        return Verdict(
            self.name, self.stage, Status.BLOCK if blocking else Status.FLAG,
            "; ".join(problems), impact_paise=impact, evidence={"problems": problems},
            basis="cart_excess",
        )


class DiscountCeilingChecker:
    """Agents pick from merchant-approved offers; they never exceed the merchant's ceiling."""

    name = "discount_ceiling"
    stage = 1

    def check(self, ctx: CheckContext) -> Verdict:
        if ctx.cart is None:
            return Verdict(self.name, self.stage, Status.SKIP, "no cart")
        gross = ctx.cart.gross_paise
        ceiling = gross * ctx.merchant.max_discount_bps // 10_000
        given = ctx.cart.discount_paise
        if given <= ceiling:
            return Verdict(self.name, self.stage, Status.PASS, f"discount {given} within ceiling {ceiling}",
                           evidence={"discount_paise": given, "ceiling_paise": ceiling})
        return Verdict(
            self.name, self.stage, Status.BLOCK,
            f"discount {given} exceeds merchant ceiling {ceiling} by {given - ceiling}",
            impact_paise=given - ceiling,
            evidence={"discount_paise": given, "ceiling_paise": ceiling, "max_discount_bps": ctx.merchant.max_discount_bps},
        )


class HitlThresholdChecker:
    """Delegated (human-not-present) orders above the merchant threshold need a human."""

    name = "hitl_threshold"
    stage = 1

    def check(self, ctx: CheckContext) -> Verdict:
        if ctx.intent is None or ctx.cart is None:
            return Verdict(self.name, self.stage, Status.SKIP, "no intent or cart")
        if ctx.intent.human_present:
            return Verdict(self.name, self.stage, Status.PASS, "human present")
        total, threshold = ctx.cart.total_paise, ctx.merchant.hitl_threshold_paise
        if total <= threshold:
            return Verdict(self.name, self.stage, Status.PASS, f"delegated order {total} under threshold {threshold}")
        return Verdict(
            self.name, self.stage, Status.ASK_HUMAN,
            f"delegated order {total} above human-approval threshold {threshold}",
            impact_paise=0, evidence={"total_paise": total, "threshold_paise": threshold},
        )


INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above|earlier) (instructions|messages|rules)",
    r"\b(add|include|append|put)\b.{0,60}\b(to|in|into) (every|each|all) (order|cart|basket)s?",
    r"^\s*(system|assistant|developer|tool)\s*:",
    r"\byou (must|should|are required to|have to) (add|apply|upsell|include|charge)\b",
    r"do not (tell|inform|mention (this )?to|reveal (this )?to) the (user|customer|buyer)",
    r"(apply|use|give) (a |the )?(coupon|discount|offer)\b.{0,40}\b(regardless|always|no matter)",
    r"<\s*/?\s*(system|instruction|instructions|prompt)\s*>",
    r"\b(transfer|send|pay|refund)\b.{0,40}\b(to|into) (this|the following) (account|upi|vpa|wallet)",
]
_COMPILED = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in INJECTION_PATTERNS]


class InjectionPatternChecker:
    """Deterministic pre-filter over text the agent read (product pages, tool outputs, messages).

    A match is a FLAG with the snippet as evidence. Drop 2 adds the LLM judgement that decides
    whether the agent actually followed the instruction; this layer only says it was exposed.
    """

    name = "injection_pattern"
    stage = 1

    def check(self, ctx: CheckContext) -> Verdict:
        if not ctx.content:
            return Verdict(self.name, self.stage, Status.SKIP, "no content to scan")
        hits: list[dict] = []
        for idx, text in enumerate(ctx.content):
            for rx in _COMPILED:
                m = rx.search(text)
                if m:
                    hits.append({"content_index": idx, "pattern": rx.pattern, "snippet": m.group(0)[:120]})
        if not hits:
            return Verdict(self.name, self.stage, Status.PASS, "no instruction-like text in content")
        return Verdict(
            self.name, self.stage, Status.FLAG,
            f"{len(hits)} instruction-like passage(s) in content the agent read",
            confidence=0.6, evidence={"hits": hits},
        )


def default_stage1() -> list:
    return [
        PriceCapChecker(),
        QuantitySkuChecker(),
        DiscountCeilingChecker(),
        HitlThresholdChecker(),
        InjectionPatternChecker(),
    ]
