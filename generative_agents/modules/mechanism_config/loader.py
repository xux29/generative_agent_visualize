"""机制参数加载：读 active.json、与 defaults 深合并、进程内单例。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from .schema import (
    MechanismConfigError,
    deep_merge,
    get_by_dotted,
    validate_config,
)

_MODULE_DIR = Path(__file__).resolve().parent
_GENERATIVE_AGENTS_DIR = _MODULE_DIR.parent.parent  # generative_agents/
MECHANISM_DATA_DIR = _GENERATIVE_AGENTS_DIR / "data" / "mechanism"
DEFAULT_ACTIVE_PATH = MECHANISM_DATA_DIR / "active.json"
DEFAULT_BASELINE_PATH = MECHANISM_DATA_DIR / "defaults" / "v0_baseline.json"

_config: Optional[Dict[str, Any]] = None
_loaded_from: Optional[Path] = None


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise MechanismConfigError(f"机制配置文件不存在: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise MechanismConfigError(f"机制配置 JSON 解析失败 ({path}): {e}") from e
    if not isinstance(data, dict):
        raise MechanismConfigError(f"机制配置顶层必须是对象: {path}")
    return data


def load_defaults() -> Dict[str, Any]:
    """加载 defaults/v0_baseline.json（已校验）。"""
    raw = _read_json(DEFAULT_BASELINE_PATH)
    return validate_config(raw)


def load_mechanism_config(path: Optional[str] = None) -> Dict[str, Any]:
    """加载机制配置：与 baseline 深合并后校验，并设为进程内单例。

    Args:
        path: 配置文件路径；默认 ``data/mechanism/active.json``。

    Returns:
        合并校验后的完整配置 dict。
    """
    global _config, _loaded_from

    cfg_path = Path(path) if path else DEFAULT_ACTIVE_PATH
    if not cfg_path.is_absolute():
        # 相对路径：优先相对 CWD，否则相对 generative_agents/
        candidate = Path.cwd() / cfg_path
        if not candidate.is_file():
            candidate = _GENERATIVE_AGENTS_DIR / cfg_path
        cfg_path = candidate

    defaults = load_defaults()
    if cfg_path.resolve() == DEFAULT_BASELINE_PATH.resolve():
        merged = defaults
    else:
        override = _read_json(cfg_path)
        merged = deep_merge(defaults, override)

    validated = validate_config(merged)
    _config = validated
    _loaded_from = cfg_path
    return deepcopy(validated)


def get_mechanism_config() -> Dict[str, Any]:
    """获取进程内单例；若尚未加载则自动 load active.json。"""
    global _config
    if _config is None:
        load_mechanism_config()
    assert _config is not None
    return _config


def set_mechanism_config(cfg: Dict[str, Any]) -> None:
    """设置进程内单例（测试用）；会先校验。"""
    global _config, _loaded_from
    _config = validate_config(cfg)
    _loaded_from = None


def get_path(dotted: str, default: Any = None) -> Any:
    """按点分路径从当前单例取值，如 ``simulation.relapse.base_prob``。"""
    return get_by_dotted(get_mechanism_config(), dotted, default)


def get_loaded_path() -> Optional[Path]:
    """返回最近一次 load_mechanism_config 的路径（测试/调试用）。"""
    return _loaded_from


def reset_mechanism_config() -> None:
    """清除进程内单例（测试用）。"""
    global _config, _loaded_from
    _config = None
    _loaded_from = None
