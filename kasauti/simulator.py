"""Scripted customer.

Runs through a scenario's turns, choosing a paraphrase variant by seed so repeated
runs (pass^k) see different wording with the same meaning. No model is called at
runtime; the variants were generated once by scripts/paraphrase_bank.py and committed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .scenario import Scenario


@dataclass
class ScriptedCustomer:
    scenario: Scenario
    seed: int = 0
    _i: int = 0
    history: list[dict] = field(default_factory=list)

    def next_message(self) -> Optional[str]:
        if self._i >= len(self.scenario.turns):
            return None
        turn = self.scenario.turns[self._i]
        self._i += 1
        text = turn.pick(self.seed + self._i)  # different variant per turn for the same seed
        self.history.append({"role": "customer", "text": text, "note": turn.note})
        return text

    def hear(self, agent_text: str) -> None:
        self.history.append({"role": "agent", "text": agent_text})

    @property
    def finished(self) -> bool:
        return self._i >= len(self.scenario.turns)
