"""generative_agents.agent_health

Compatibility re-export. Mechanism code lives in ``modules.health_mechanisms``.
"""

from modules.health_mechanisms.agent_mixin import *  # noqa: F401,F403
from modules.health_mechanisms.agent_mixin import HealthAgentMixin

__all__ = ["HealthAgentMixin"]
