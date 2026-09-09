"""Health simulation mechanisms (Stanford town extension).

Mechanism Code layer: formulas, state machines, agent health behaviors.
Parameter Config layer remains in ``data/mechanism/`` + ``mechanism_config``.
Prompt templates: ``data/mechanism/prompts/health_*.txt``.
"""

from modules.health_mechanisms.agent_mixin import HealthAgentMixin
from modules.health_mechanisms.intention import Intention
from modules.health_mechanisms.asymmetric_game import (
    AsymmetricGameEngine,
    ManagerGoalType,
)
from modules.health_mechanisms.scenario import (
    ScenarioConfig,
    ScenarioConfigLoader,
    get_scenario_config,
    get_agent_scenario,
)
from modules.health_mechanisms.scoring import (
    NonlinearHealthScorer,
    Scorer,
    CumulativeHealthScorer,
    SelfDisciplineLevel,
    InitialHealthScore,
)
from modules.health_mechanisms.management import (
    Strategy,
    StrategyManager,
    LongTermStrategyManager,
)
from modules.health_mechanisms.registry import (
    ai_editable_mechanisms,
    editable_code_roots,
    get_config_path,
    get_implementation,
    get_mechanism,
    get_prompt_templates,
    get_registry,
    list_mechanisms,
    reload_registry,
)
from modules.health_mechanisms.prompts import HEALTH_PROMPT_DIR, HealthPromptsMixin
from modules.health_mechanisms.model_version import ModelVersionStore
# The editor/sandbox layer is optional.  Runtime simulations and Monte Carlo
# consumers only need the mechanism/scoring layer and should remain importable
# in a minimal deployment.
try:
    from modules.health_mechanisms.ai_edit import AIEditAPI
    from modules.health_mechanisms.sandbox import validate_target, run_sim
except ModuleNotFoundError:
    AIEditAPI = None
    validate_target = None
    run_sim = None

__all__ = [
    "HealthAgentMixin",
    "Intention",
    "AsymmetricGameEngine",
    "ManagerGoalType",
    "ScenarioConfig",
    "ScenarioConfigLoader",
    "get_scenario_config",
    "get_agent_scenario",
    "NonlinearHealthScorer",
    "Scorer",
    "CumulativeHealthScorer",
    "SelfDisciplineLevel",
    "InitialHealthScore",
    "Strategy",
    "StrategyManager",
    "LongTermStrategyManager",
    "HealthPromptsMixin",
    "HEALTH_PROMPT_DIR",
    "get_registry",
    "list_mechanisms",
    "get_mechanism",
    "get_implementation",
    "get_config_path",
    "get_prompt_templates",
    "ai_editable_mechanisms",
    "editable_code_roots",
    "reload_registry",
    "ModelVersionStore",
    "AIEditAPI",
    "validate_target",
    "run_sim",
]
