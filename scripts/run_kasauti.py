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
from kasauti.runner import run_batch, summarize  # noqa: E402
from kasauti.scenario import load_scenarios  # noqa: E402
from sakshi.config import Settings  # noqa: E402
from sakshi.llm import CachedProvider, LlmCache, provider_from_env  # noqa: E402
from sakshi.llm.heuristic import HeuristicJudge  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=1, help="repeats per scenario")
    ap.add_argument("--pack", default=None, help="money | hijack | language | clean")
    ap.add_argument("--llm", default="heuristic", help="heuristic | mock | ollama | gemini")
    ap.add_argument("--out", default="data/runs")
    args = ap.parse_args()

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
    naive = run_batch(scenarios, lambda engine: RuleAgent(), provider, k=args.k, out_path=out / "naive.jsonl")
    guarded = run_batch(scenarios, lambda engine: GuardedAgent(RuleAgent(), engine), provider, k=args.k,
                        out_path=out / "guarded.jsonl")

    print(f"{len(scenarios)} scenarios x k={args.k}, judge={getattr(provider, 'name', args.llm)}\n")
    print(summarize(naive).table())
    print()
    print(summarize(guarded).table())
    print("\nwords = dark-pattern findings in the agent's speech (scanner + judge); disputes = recommendation matches / raised.")


if __name__ == "__main__":
    main()
