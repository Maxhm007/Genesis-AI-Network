"""Genesis AI Network runtime package."""

__version__ = "0.1.0"

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

# Keep autonomous coding capability-driven rather than provider-name-driven.
# Repeatedly timing-out Qwen runtimes remain excluded from autonomous coding;
# tests/Security/review/validation gates still apply before promotion.
from .provider_fallback import install_provider_fallback as _install_provider_fallback

_install_provider_fallback()
del _install_provider_fallback

# Give known benchmark-integration tasks a deterministic, provider-independent
# coding template before waiting for an external non-Qwen model. This lane cannot
# fabricate scores and still uses the normal candidate/test/security/review path.
from .deterministic_coding_fallback import (
    install_deterministic_coding_fallback as _install_deterministic_coding_fallback,
)

_install_deterministic_coding_fallback()
del _install_deterministic_coding_fallback

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
