"""generative_agents.scenario_config

Compatibility re-export. Mechanism code lives in ``modules.health_mechanisms``.
"""

from modules.health_mechanisms.scenario import *  # noqa: F401,F403
from modules.health_mechanisms.scenario import (
    ScenarioConfig,
    ScenarioConfigLoader,
    get_scenario_config,
    get_agent_scenario,
)

__all__ = [
    "ScenarioConfig",
    "ScenarioConfigLoader",
    "get_scenario_config",
    "get_agent_scenario",
]
