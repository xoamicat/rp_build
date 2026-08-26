"""Check the configured LLM backend before spending a run on it.

    python scripts/llm_check.py            # uses SAKSHI_LLM from .env (gemini | ollama | mock)

For Gemini: lists the models your key can call, confirms GEMINI_MODEL is one of them (or suggests
one), runs a single JSON-mode completion through the cache, and reports the round-trip time so
you can sanity-check GEMINI_RPM. One call, so it costs one request of your daily quota.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sakshi.checkers import parse_json  # noqa: E402
from sakshi.config import Settings  # noqa: E402
from sakshi.llm import CachedProvider, GeminiError, GeminiProvider, LlmCache, provider_from_env  # noqa: E402

PROBE = ('Return this exact JSON and nothing else: {"ok": true, "model_says": "hello from sakshi"}')


def main() -> None:
    settings = Settings.from_env()
    print(f"backend: {settings.llm}")
    if settings.llm == "mock":
        print("mock backend: nothing to check. Set SAKSHI_LLM=gemini or ollama in .env to test a real model.")
        return
    if settings.llm == "gemini":
        if not settings.gemini_api_key:
            raise SystemExit("GEMINI_API_KEY is empty. Put it in .env (never in git).")
        gp = GeminiProvider(settings.gemini_api_key, settings.gemini_model, settings.gemini_rpm)
        try:
            models = gp.list_models()
        except Exception as exc:
            raise SystemExit(f"could not list models (key or network problem): {exc}")
        names = [m["name"] for m in models]
        print(f"models available to this key ({len(names)}):")
        for n in names:
            flag = "  <- configured" if n == settings.gemini_model else ""
            print(f"  {n}{flag}")
        if settings.gemini_model not in names:
            lite = [n for n in names if "lite" in n] or [n for n in names if "flash" in n]
            print(f"\nGEMINI_MODEL={settings.gemini_model} is not in the list. Suggested: {lite[:3]}")
            print("Set GEMINI_MODEL in .env to one of these and rerun.")
            return
    provider = CachedProvider(provider_from_env(settings), LlmCache("data/llm_cache.db"))
    t0 = time.time()
    try:
        raw = provider.complete(PROBE, system="You answer with JSON only.", json_mode=True)
    except GeminiError as exc:
        raise SystemExit(f"Gemini error: {exc}")
    dt = time.time() - t0
    parsed = parse_json(raw)
    print(f"\nprobe round trip {dt:.1f}s  cached={provider.cache.hits > 0}")
    print("raw:", raw[:200].replace("\n", " "))
    print("parsed:", parsed)
    if not parsed or parsed.get("ok") is not True:
        raise SystemExit("the model did not return the expected JSON; the judge may need a stronger model")
    print("\nOK. Next: python scripts/run_kasauti.py --llm gemini   (about 35 calls at your RPM, all cached)")


if __name__ == "__main__":
    main()
