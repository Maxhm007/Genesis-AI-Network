from __future__ import annotations

from .devlab.iterative import IterativeGenesisDevLab
from .efficient_engineering import EfficientAutonomousEngineeringLoop


class IterativeAutonomousEngineeringLoop(EfficientAutonomousEngineeringLoop):
    """Golden engineering path backed by an iterative DevLab worktree loop."""

    def __init__(self, root, providers=None) -> None:
        super().__init__(root, providers)
        self.devlab = IterativeGenesisDevLab(self.root, self.providers)
