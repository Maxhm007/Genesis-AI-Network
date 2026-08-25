"""Genesis AI Network runtime package."""

from pathlib import Path

__version__ = "0.1.0"

# Validated benchmark evidence is correctness-critical state, not a cache detail.
# Restore repository-backed measurements before installing routing/evolution hooks
# so every Genesis entrypoint sees the same independently validated baseline even
# if an Actions runtime cache is stale, missing, or restored out of order.
from .benchmark_state import hydrate_validated_benchmark_state as _hydrate_validated_benchmark_state

_hydrate_validated_benchmark_state(Path(__file__).resolve().parents[1])
del _hydrate_validated_benchmark_state

# A paused shared-queue task must stay durable without masquerading as runnable
# pipeline work. This prevents provider-wait tasks from blocking higher-priority
# measured capability growth; resuming the task makes it active again.
from .pipeline_task_state_guard import install_pipeline_task_state_guard as _install_pipeline_task_state_guard

_install_pipeline_task_state_guard()
del _install_pipeline_task_state_guard

# Install the bounded new-capability extension at package initialization so every
# Genesis entrypoint (Pulse, tests, CLI, and workers) uses the same evolution
# routing without a second promotion path.
from .capability_routing import install_new_capability_routing as _install_new_capability_routing

_install_new_capability_routing()
del _install_new_capability_routing

# Translate validated benchmark deficits into capability-growth work and require
# post-promotion benchmark evidence before counting an improvement.
from .capability_evolution import install_capability_evolution_controller as _install_capability_evolution_controller

_install_capability_evolution_controller()
del _install_capability_evolution_controller

# Separate improvement of existing capabilities from new-capability development,
# and require a dedicated merge boundary before learning closes promoted work.
from .improvement_merge_routing import install_improvement_merge_submodules as _install_improvement_merge_submodules

_install_improvement_merge_submodules()
del _install_improvement_merge_submodules

# Preserve pipeline completion priority while ensuring measured benchmark-growth
# work outranks speculative learning when both need the same bounded coding lane.
from .goal_priority import install_measured_growth_goal_priority as _install_measured_growth_goal_priority

_install_measured_growth_goal_priority()
del _install_measured_growth_goal_priority

# Keep autonomous coding capability-driven rather than provider-name-driven.
# Repeatedly timing-out Qwen runtimes remain excluded from autonomous coding;
# tests/Security/review/validation gates still apply before promotion.
from .provider_fallback import install_provider_fallback as _install_provider_fallback

_install_provider_fallback()
del _install_provider_fallback

# Reconcile the historical Qwen-first fallback with live repair evidence. Prefer
# another eligible coder when one exists, keep Qwen as a usable last trained
# provider, remove the accidental 256-token transport choke point, and permit at
# most two tightly related bounded edits so implementation plus regression coverage
# can travel through one candidate. All normal validation/promotion gates remain.
from .coding_provider_policy import install_coding_provider_policy as _install_coding_provider_policy

_install_coding_provider_policy()
del _install_coding_provider_policy

# Give known benchmark-integration tasks a deterministic, provider-independent
# coding template before waiting for an external non-Qwen model. This lane cannot
# fabricate scores and still uses the normal candidate/test/security/review path.
from .deterministic_coding_fallback import (
    install_deterministic_coding_fallback as _install_deterministic_coding_fallback,
)

_install_deterministic_coding_fallback()
del _install_deterministic_coding_fallback

# When a bounded Python edit fails syntax validation, derive the smallest complete
# statement from the original repository AST and feed that structural range into
# the next retry. Genesis still authors the replacement and every normal gate runs.
from .python_syntax_retry import install_python_syntax_retry_guidance as _install_python_syntax_retry_guidance

_install_python_syntax_retry_guidance()
del _install_python_syntax_retry_guidance

# Git review refs are durable evidence even if an ephemeral Actions runtime cache
# is lost. Reconstruct only strict Genesis-owned orphaned review work, then resume
# the existing tests, internal review, independent validation, and promotion gates.
from .review_recovery import install_orphan_review_recovery as _install_orphan_review_recovery

_install_orphan_review_recovery()
del _install_orphan_review_recovery

# Review the exact autonomous patch against the latest main snapshot rather than
# running the full suite on a stale candidate base. The original Genesis SHA stays
# authoritative and is restored before the normal validation/promotion handoff.
from .current_main_review import install_current_main_review as _install_current_main_review

_install_current_main_review()
del _install_current_main_review

# Compatibility is not capability. Reject newly introduced duplicate/unreachable
# Python statements before model review, and require measured capability-growth
# patches to change reachable runtime behavior before validation/promotion.
from .review_materiality import install_review_materiality_gate as _install_review_materiality_gate

_install_review_materiality_gate()
del _install_review_materiality_gate
