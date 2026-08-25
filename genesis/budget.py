from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CycleBudget:
    max_research_items: int = 5
    max_model_candidates: int = 10
    max_team_tasks: int = 8

    def validate(self) -> None:
        for value in (self.max_research_items, self.max_model_candidates, self.max_team_tasks):
            if isinstance(value, bool): raise ValueError("cycle budget must be an integer")
            if value < 0 or value > 100:
                raise ValueError("cycle budget out of bounds")
