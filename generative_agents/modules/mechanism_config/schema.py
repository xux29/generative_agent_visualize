"""机制参数 schema：可外置字段定义与校验。

排除项（不进入 JSON / 校验时剥离）：
- natural_recovery / natural_recovery_range
- blocked_violation_factor
- MAX_EFFECTIVE_VIOLATIONS / max_effective_violations

self_discipline 仅允许 low | medium | high。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Set, Tuple

ALLOWED_SELF_DISCIPLINE = frozenset({"low", "medium", "high"})

# 标注「删除」——不得外置；出现在配置中时会被剥离（不生效）
EXCLUDED_FIELD_NAMES = frozenset(
    {
        "natural_recovery",
        "natural_recovery_range",
        "blocked_violation_factor",
        "MAX_EFFECTIVE_VIOLATIONS",
        "max_effective_violations",
    }
)

# 顶层与二级分区（供文档/校验参考）
TOP_LEVEL_KEYS = ("meta", "simulation", "management", "ui_params")

SIMULATION_SECTIONS = (
    "subject",
    "health",
    "relapse",
    "mood",
    "compliance",
    "behavior_scores",
    "habit",
    "satisfaction",
    "composite",
)

MANAGEMENT_SECTIONS = (
    "intervention",
    "tidal",
    "relationship_phases",
    "trust_capital",
    "habit_consolidation",
    "manager_learning",
    "over_intervention",
    "reflection",
)


class MechanismConfigError(ValueError):
    """机制配置校验错误。"""


def _walk_strip_excluded(
    node: Any,
    path: str = "",
    stripped: Optional[List[str]] = None,
) -> Any:
    """递归剥离排除字段，返回新对象。"""
    if stripped is None:
        stripped = []

    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else key
            if key in EXCLUDED_FIELD_NAMES:
                stripped.append(child_path)
                continue
            out[key] = _walk_strip_excluded(value, child_path, stripped)
        return out
    if isinstance(node, list):
        return [
            _walk_strip_excluded(item, f"{path}[{i}]", stripped)
            for i, item in enumerate(node)
        ]
    return node


def strip_excluded_fields(cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """剥离排除字段，返回 (新配置, 被剥离路径列表)。"""
    stripped: List[str] = []
    cleaned = _walk_strip_excluded(deepcopy(cfg), "", stripped)
    return cleaned, stripped


def validate_self_discipline(value: Any, path: str = "simulation.subject.self_discipline") -> str:
    """校验自律档位，非法值抛出清晰错误。"""
    if not isinstance(value, str):
        raise MechanismConfigError(
            f"{path} 必须是字符串，且仅允许 {sorted(ALLOWED_SELF_DISCIPLINE)}，"
            f"收到: {value!r} ({type(value).__name__})"
        )
    normalized = value.strip().lower()
    if normalized not in ALLOWED_SELF_DISCIPLINE:
        raise MechanismConfigError(
            f"{path} 仅允许 'low' | 'medium' | 'high'，收到非法值: {value!r}。"
            f"请勿使用 very_low / very_high 等扩展档位。"
        )
    return normalized


def _find_self_discipline_paths(cfg: Dict[str, Any]) -> List[Tuple[str, Any]]:
    """收集配置中所有 self_discipline 出现位置。"""
    found: List[Tuple[str, Any]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                child = f"{path}.{key}" if path else key
                if key == "self_discipline":
                    found.append((child, value))
                else:
                    walk(value, child)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(cfg, "")
    return found


def validate_config(cfg: Dict[str, Any], *, strip_excluded: bool = True) -> Dict[str, Any]:
    """校验并规范化机制配置。

    - 剥离排除字段（默认）
    - 校验所有 self_discipline 为三档
    - 确保顶层结构为 dict

    Returns:
        规范化后的配置（深拷贝）
    """
    if not isinstance(cfg, dict):
        raise MechanismConfigError(f"机制配置必须是 JSON 对象，收到: {type(cfg).__name__}")

    if strip_excluded:
        cleaned, _ = strip_excluded_fields(cfg)
    else:
        cleaned = deepcopy(cfg)
        # 若未剥离，发现排除字段则报错
        _, found = strip_excluded_fields(cfg)
        if found:
            raise MechanismConfigError(
                "配置包含已删除/不可外置字段: " + ", ".join(found)
            )

    for path, value in _find_self_discipline_paths(cleaned):
        normalized = validate_self_discipline(value, path=path)
        # 写回规范化值
        parts = path.split(".")
        cursor: Any = cleaned
        for part in parts[:-1]:
            cursor = cursor[part]
        cursor[parts[-1]] = normalized

    if "simulation" in cleaned and not isinstance(cleaned["simulation"], dict):
        raise MechanismConfigError("simulation 必须是对象")
    if "management" in cleaned and not isinstance(cleaned["management"], dict):
        raise MechanismConfigError("management 必须是对象")

    return cleaned


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """深合并：override 覆盖 base；dict 递归合并，其余类型直接替换。"""
    result = deepcopy(base)
    for key, value in override.items():
        if key in EXCLUDED_FIELD_NAMES:
            continue
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def get_by_dotted(cfg: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    """按点分路径取值，如 simulation.relapse.base_prob。"""
    if not dotted:
        return cfg
    cursor: Any = cfg
    for part in dotted.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return default
        cursor = cursor[part]
    return cursor


def set_by_dotted(cfg: Dict[str, Any], dotted: str, value: Any) -> None:
    """按点分路径写入（原地修改）。"""
    parts = dotted.split(".")
    cursor: Any = cfg
    for part in parts[:-1]:
        if part not in cursor or not isinstance(cursor[part], dict):
            cursor[part] = {}
        cursor = cursor[part]
    cursor[parts[-1]] = value


def flatten_diff(
    a: Dict[str, Any],
    b: Dict[str, Any],
    prefix: str = "",
) -> Dict[str, Dict[str, Any]]:
    """比较两棵配置树，返回 {path: {"a": ..., "b": ...}}。"""
    diffs: Dict[str, Dict[str, Any]] = {}
    keys: Set[str] = set()
    if isinstance(a, dict):
        keys.update(a.keys())
    if isinstance(b, dict):
        keys.update(b.keys())

    a_dict = a if isinstance(a, dict) else {}
    b_dict = b if isinstance(b, dict) else {}

    for key in sorted(keys):
        path = f"{prefix}.{key}" if prefix else key
        va = a_dict.get(key, _MISSING)
        vb = b_dict.get(key, _MISSING)
        if isinstance(va, dict) and isinstance(vb, dict):
            diffs.update(flatten_diff(va, vb, path))
        elif va != vb:
            diffs[path] = {
                "a": None if va is _MISSING else va,
                "b": None if vb is _MISSING else vb,
            }
    return diffs


class _Missing:
    pass


_MISSING = _Missing()
