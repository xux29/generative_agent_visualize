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
    get_by_dotted,
    set_by_dotted,
    validate_config,
    validate_self_discipline,
)
from .ui_tunable import (
    UI_TUNABLE_JSON_PATHS,
    assert_ui_tunable_json_path,
    is_ui_tunable_json_path,
    list_ui_param_specs,
    read_ui_param,
    snapshot_ui_values,
    write_ui_param,
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
    "get_by_dotted",
    "get_loaded_path",
    "get_mechanism_config",
    "get_path",
    "is_ui_tunable_json_path",
    "list_ui_param_specs",
    "load_defaults",
    "load_mechanism_config",
    "read_ui_param",
    "reset_mechanism_config",
    "set_by_dotted",
    "set_mechanism_config",
    "snapshot_ui_values",
    "validate_config",
    "validate_self_discipline",
    "write_ui_param",
    "UI_TUNABLE_JSON_PATHS",
    "assert_ui_tunable_json_path",
]
