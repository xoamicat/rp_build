"""Run the scenario bank against the naive agent and its guarded twin, print both summaries.

    python scripts/run_kasauti.py                # heuristic judge, zero quota
    python scripts/run_kasauti.py --k 3          # three repeats per scenario (paraphrase variants by seed)
    python scripts/run_kasauti.py --llm gemini   # real judge for the LLM checkers (cached in data/llm_cache.db)
    python scripts/run_kasauti.py --pack hijack  # one pack only

Results are written as JSON lines to data/runs/<agent>.jsonl for the report (drop 5).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kasauti.agents import GuardedAgent, RuleAgent  # noqa: E402
from kasauti.provenance import write_manifest  # noqa: E402
from kasauti.runner import run_batch, strict_pass_k, summarize  # noqa: E402
from kasauti.scenario import load_scenarios  # noqa: E402
from sakshi.config import Settings  # noqa: E402
from sakshi.llm import CachedProvider, LlmCache, provider_from_env  # noqa: E402
from sakshi.llm.heuristic import HeuristicJudge  # noqa: E402
from sakshi.memory import CorrectionMemory  # noqa: E402


def main() -> None:
    # Windows terminals may default to cp1252, which cannot render the
    # rupee symbols in the reproducible summary. Keep the CLI cross-platform.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=1, help="repeats per scenario")
    ap.add_argument("--pack", default=None, help="money | hijack | language | clean")
    ap.add_argument("--llm", default="heuristic", help="heuristic | mock | ollama | gemini")
    ap.add_argument("--out", default="data/runs")
    ap.add_argument("--memory", action="store_true", help="apply human corrections from data/memory.db")
    args = ap.parse_args()
    memory = CorrectionMemory("data/memory.db") if args.memory else None

    scenarios = load_scenarios(pack=args.pack)
    errors = [e for sc in scenarios for e in sc.validate()]
    if errors:
        raise SystemExit("\n".join(errors))

    if args.llm == "heuristic":
        provider = HeuristicJudge()
    else:
        settings = Settings.from_env()
        settings = Settings(**{**settings.__dict__, "llm": args.llm})
        provider = CachedProvider(provider_from_env(settings), LlmCache("data/llm_cache.db"))

    out = Path(args.out)
    naive = run_batch(scenarios, lambda engine: RuleAgent(), provider, k=args.k, out_path=out / "naive.jsonl", memory=memory)
    guarded = run_batch(scenarios, lambda engine: GuardedAgent(RuleAgent(), engine), provider, k=args.k,
                        out_path=out / "guarded.jsonl", memory=memory)
    naive_pass_k = strict_pass_k(naive)
    guarded_pass_k = strict_pass_k(guarded)
    manifest = write_manifest(out / "run-manifest.json", provider=getattr(provider, "name", args.llm),
                              repeats=args.k, seed=0, scenarios=scenarios, memory_applied=memory is not None,
                              pass_k={"naive": naive_pass_k.as_dict(), "guarded": guarded_pass_k.as_dict()})

    print(f"{len(scenarios)} scenarios x k={args.k}, judge={getattr(provider, 'name', args.llm)}"
          + (f", corrections applied: {len(memory)}" if memory else "") + "\n")
    print(summarize(naive).table())
    print()
    print(summarize(guarded).table())
    print()
    print(naive_pass_k.line())
    print(guarded_pass_k.line())
    print(f"\nprovenance: {manifest} (synthetic benchmark; not a live-payment result)")
    print("\nwords = dark-pattern findings in the agent's speech (scanner + judge); disputes = recommendation matches / raised.")


if __name__ == "__main__":
    main()
