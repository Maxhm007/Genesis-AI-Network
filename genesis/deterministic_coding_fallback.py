from __future__ import annotations

from types import MethodType

from .autonomous_engineering import AutonomousEngineeringLoop
from .deterministic_benchmark_builder import DeterministicBenchmarkIntegrationProvider


INSTALL_MARKER = "_genesis_deterministic_coding_fallback_installed"
_ORIGINAL_ATTEMPT_TASK = AutonomousEngineeringLoop._attempt_task


def _attempt_task_with_deterministic_benchmark(
    self: AutonomousEngineeringLoop,
    task,
    runtime,
):
    provider = DeterministicBenchmarkIntegrationProvider.for_task(
        self.root,
        task,
        self.coding,
    )
    if provider is None:
        return _ORIGINAL_ATTEMPT_TASK(self, task, runtime)

    had_override = "_coding_provider" in self.__dict__
    previous_override = self.__dict__.get("_coding_provider")

    def deterministic_provider(_self):
        return provider

    self._coding_provider = MethodType(deterministic_provider, self)
    try:
        result = _ORIGINAL_ATTEMPT_TASK(self, task, runtime)
    finally:
        if had_override:
            self.__dict__["_coding_provider"] = previous_override
        else:
            self.__dict__.pop("_coding_provider", None)

    result["provider_policy"] = "deterministic_benchmark_template_then_non_qwen"
    if result.get("coding_strategy") == "external_non_qwen_provider":
        result["coding_strategy"] = "deterministic_benchmark_integration"
    return result


def install_deterministic_coding_fallback() -> None:
    """Install the deterministic benchmark lane once after provider policy hooks."""
    if getattr(AutonomousEngineeringLoop, INSTALL_MARKER, False):
        return
    AutonomousEngineeringLoop._attempt_task = _attempt_task_with_deterministic_benchmark
    setattr(AutonomousEngineeringLoop, INSTALL_MARKER, True)
