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
