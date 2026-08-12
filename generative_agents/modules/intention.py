"""generative_agents.intention

Compatibility re-export. Mechanism code lives in ``modules.health_mechanisms``.
"""

from modules.health_mechanisms.intention import *  # noqa: F401,F403
from modules.health_mechanisms.intention import Intention

__all__ = ["Intention"]
