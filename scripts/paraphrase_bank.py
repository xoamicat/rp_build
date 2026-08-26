"""Generate paraphrase variants for every scenario turn, once, and write them back.

    python scripts/paraphrase_bank.py                 # offline templated variants (no model)
    python scripts/paraphrase_bank.py --llm gemini    # real paraphrases, ~1 call per turn, cached
    python scripts/paraphrase_bank.py --force         # regenerate even where variants exist

Variants are committed with the scenarios, so Kasauti runs pick them by seed at zero cost.
Keep the meaning identical: same items, same quantities, same cap, same language register.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kasauti.scenario import load_scenarios, save_scenario  # noqa: E402
from sakshi.checkers import parse_json  # noqa: E402
from sakshi.config import Settings  # noqa: E402
from sakshi.llm import CachedProvider, LlmCache, provider_from_env  # noqa: E402

SYSTEM = ("You paraphrase customer messages for testing an ordering assistant. Keep every fact identical: "
          "items, quantities, amounts, currency, refusals. Keep the same language mix (English, Hindi, Hinglish). "
          "Answer only with JSON.")


def templated_variants(text: str, n: int = 3) -> list[str]:
    """Offline variants: same words, different framing. Good enough for development runs."""
    base = text.strip().rstrip(".")
    candidates = [
        f"{base}, please.",
        f"Hi, {base[0].lower() + base[1:]}.",
        f"{base}. Thanks.",
        base.lower() + ".",
    ]
    out = []
    for c in candidates:
        if c != text and c not in out:
            out.append(c)
        if len(out) == n:
            break
    return out


def model_variants(provider, text: str, lang: str, n: int = 3) -> list[str]:
    prompt = json.dumps({"task": f"Write {n} paraphrases of the customer message.", "language": lang,
                         "message": text, "answer_format": {"variants": ["string"]}}, ensure_ascii=False)
    answer = parse_json(provider.complete(prompt, system=SYSTEM, json_mode=True)) or {}
    variants = [str(v).strip() for v in answer.get("variants", []) if str(v).strip() and str(v).strip() != text]
    return variants[:n] or templated_variants(text, n)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", default="offline", help="offline | mock | ollama | gemini")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--n", type=int, default=3)
    args = ap.parse_args()

    provider = None
    if args.llm != "offline":
        settings = Settings(**{**Settings.from_env().__dict__, "llm": args.llm})
        provider = CachedProvider(provider_from_env(settings), LlmCache("data/llm_cache.db"))

    written = 0
    for sc in load_scenarios():
        changed = False
        for turn in sc.turns:
            if turn.variants and not args.force:
                continue
            lang = sc.intent.get("lang", "en")
            turn.variants = model_variants(provider, turn.text, lang, args.n) if provider else templated_variants(turn.text, args.n)
            changed = True
        if changed:
            save_scenario(sc)
            written += 1
    print(f"variants written for {written} scenario(s); mode={args.llm}")


if __name__ == "__main__":
    main()
