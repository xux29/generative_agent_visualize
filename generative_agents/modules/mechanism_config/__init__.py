"""机制参数 JSON 外置 · 核心 API。

用法::

    from modules.mechanism_config import (
        get_mechanism_config,
        get_path,
        load_mechanism_config,
        set_mechanism_config,
        VersionStore,
    )

    cfg = get_mechanism_config()
    base_prob = get_path("simulation.relapse.base_prob")

    store = VersionStore()
    vid = store.save("实验A", note="提高复发基线")
    store.activate(vid)
    store.rollback("v0_baseline")
"""

from .loader import (
    DEFAULT_ACTIVE_PATH,
    DEFAULT_BASELINE_PATH,
    MECHANISM_DATA_DIR,
    get_loaded_path,
    get_mechanism_config,
    get_path,
    load_defaults,
    load_mechanism_config,
    reset_mechanism_config,
    set_mechanism_config,
)
from .schema import (
    ALLOWED_SELF_DISCIPLINE,
    EXCLUDED_FIELD_NAMES,
    MechanismConfigError,
    deep_merge,
    validate_config,
    validate_self_discipline,
)
from .version_store import VersionStore

__all__ = [
    "ALLOWED_SELF_DISCIPLINE",
    "DEFAULT_ACTIVE_PATH",
    "DEFAULT_BASELINE_PATH",
    "EXCLUDED_FIELD_NAMES",
    "MECHANISM_DATA_DIR",
    "MechanismConfigError",
    "VersionStore",
    "deep_merge",
    "get_loaded_path",
    "get_mechanism_config",
    "get_path",
    "load_defaults",
    "load_mechanism_config",
    "reset_mechanism_config",
    "set_mechanism_config",
    "validate_config",
    "validate_self_discipline",
]
