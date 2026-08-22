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

# Keep autonomous coding capability-driven rather than provider-name-driven. The
# local Qwen runtime may act as the bounded fallback when no stronger eligible
# coding provider is available; all existing tests/Security/review/validation gates
# still apply before promotion.
from .provider_fallback import install_provider_fallback as _install_provider_fallback

_install_provider_fallback()
del _install_provider_fallback
