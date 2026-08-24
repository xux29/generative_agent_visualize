"""界面可调参数：22 项白名单（见 docs/mechanism/界面可调参数.md）。

可视化滑杆与 AI `edit_config` 只能改此表映射的 JSON 路径；其余参数视为机制内置，不在界面暴露。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from modules.mechanism_config.schema import MechanismConfigError, get_by_dotted, set_by_dotted

Discipline = ("high", "medium", "low")


@dataclass(frozen=True)
class UiParamSpec:
    key: str
    label: str
    section: str
    min_value: float
    max_value: float
    description: str = ""


UI_PARAM_SPECS: Tuple[UiParamSpec, ...] = (
    UiParamSpec("penaltyStrength", "违规惩罚（非线性）", "health", 2.0, 7.0),
    UiParamSpec("complianceBonus", "遵从奖励", "health", 0.5, 2.5),
    UiParamSpec("cumulativeSpeed", "持续恶化加速下滑", "health", 0.005, 0.025),
    UiParamSpec("plateauStubbornness", "平台期机制", "health", 7.0, 21.0),
    UiParamSpec("dailyPenaltyCap", "每日最大扣分限制", "health", 4.0, 12.0),
    UiParamSpec("noiseSigma", "日常随机波动", "health", 0.2, 0.6),
    UiParamSpec("baseRelapseProb", "基础概率", "relapse", 0.05, 0.25),
    UiParamSpec("disciplineCorrection", "自律修正", "relapse", 0.5, 1.5),
    UiParamSpec("addictionCorrection", "成瘾修正", "relapse", 0.5, 2.0),
    UiParamSpec("relaxTimeSensitivity", "放松时间", "relapse", 0.5, 3.0),
    UiParamSpec("habitProtection", "习惯保护", "relapse", 0.01, 0.05),
    UiParamSpec("relapseSwing", "复发倾向", "relapse", 0.3, 2.0),
    UiParamSpec("baseSatisfaction", "基础满意度", "satisfaction", 4.0, 8.0),
    UiParamSpec("interventionSensitivity", "强度惩罚", "satisfaction", 0.2, 1.0),
    UiParamSpec("frequencyPenalty", "频率惩罚", "satisfaction", 0.1, 0.8),
    UiParamSpec("overInterventionPenalty", "过度干预惩罚", "satisfaction", 0.1, 1.0),
    UiParamSpec("alternativeCompensation", "替代奖励", "satisfaction", 0.2, 1.5),
    UiParamSpec("timelinessEffect", "时机奖励", "satisfaction", 0.2, 1.2),
    UiParamSpec("interventionIntensity", "干预强度", "management", 0.2, 1.5),
    UiParamSpec("interventionTendency", "干预倾向", "management", 0.2, 1.0),
    UiParamSpec("healthSafeThreshold", "健康分警戒线", "management", 50.0, 90.0),
    UiParamSpec("emotionWarning", "情绪警戒线", "management", 3.0, 7.0),
)

_BASE_DISCIPLINE_MOD = {
    "very_low": 2.0,
    "low": 1.5,
    "medium": 1.0,
    "high": 0.5,
    "very_high": 0.2,
}
_BASE_ADDICTION_MOD = {
    "none": 0.5,
    "low": 0.8,
    "moderate": 1.0,
    "high": 1.5,
    "severe": 2.0,
}
_PENALTY_STRENGTH_SCALE = {"high": 0.65, "medium": 0.85, "low": 1.0}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _avg_range(val: Any) -> float:
    if isinstance(val, (list, tuple)) and len(val) == 2:
        return (float(val[0]) + float(val[1])) / 2.0
    return float(val)


def _read_penalty_strength(cfg: Dict[str, Any]) -> float:
    path = "simulation.health.nonlinear.discipline_params.medium.violation_penalty_range"
    return _avg_range(get_by_dotted(cfg, path, [1.5, 2.0]))


def _write_penalty_strength(cfg: Dict[str, Any], v: float) -> None:
    v = _clamp(v, 2.0, 7.0)
    for level, scale in _PENALTY_STRENGTH_SCALE.items():
        mid = v * scale
        lo = max(0.5, mid * 0.75)
        set_by_dotted(
            cfg,
            f"simulation.health.nonlinear.discipline_params.{level}.violation_penalty_range",
            [round(lo, 3), round(mid, 3)],
        )


def _read_discipline_level_field(cfg: Dict[str, Any], field: str, default: float) -> float:
    return float(get_by_dotted(cfg, f"simulation.health.discipline_params.medium.{field}", default))


def _write_discipline_level_field(cfg: Dict[str, Any], field: str, v: float) -> None:
    ratios = {"high": 1.33, "medium": 1.0, "low": 0.67}
    base = _read_discipline_level_field(cfg, field, v)
    if base <= 0:
        base = v
    for level, ratio in ratios.items():
        set_by_dotted(cfg, f"simulation.health.discipline_params.{level}.{field}", round(v * ratio, 4))


def _read_nonlinear_discipline_field(cfg: Dict[str, Any], field: str, default: float) -> float:
    return float(
        get_by_dotted(cfg, f"simulation.health.nonlinear.discipline_params.medium.{field}", default)
    )


def _write_nonlinear_discipline_field(cfg: Dict[str, Any], field: str, v: float, as_int: bool = False) -> None:
    ratios = {"high": 2.0, "medium": 1.0, "low": 0.43}
    for level, ratio in ratios.items():
        val: Any = int(round(v * ratio)) if as_int else round(v * ratio, 6)
        set_by_dotted(cfg, f"simulation.health.nonlinear.discipline_params.{level}.{field}", val)


def _read_mod_table_scale(cfg: Dict[str, Any], table_path: str, base: Dict[str, float]) -> float:
    table = get_by_dotted(cfg, table_path, base)
    if not isinstance(table, dict):
        return 1.0
    pivot_key = "medium" if "medium" in table else "moderate"
    pivot = float(table.get(pivot_key, base.get(pivot_key, 1.0)))
    base_pivot = float(base.get(pivot_key, 1.0))
    if base_pivot == 0:
        return 1.0
    return pivot / base_pivot


def _write_mod_table_scale(cfg: Dict[str, Any], table_path: str, base: Dict[str, float], scale: float) -> None:
    table = get_by_dotted(cfg, table_path, base)
    if not isinstance(table, dict):
        table = dict(base)
    out = {}
    for k, v in base.items():
        out[k] = round(float(v) * scale, 4)
    for k in table:
        if k not in out:
            out[k] = table[k]
    set_by_dotted(cfg, table_path, out)


def _read_intervention_sensitivity(cfg: Dict[str, Any]) -> float:
    weights = get_by_dotted(cfg, "simulation.satisfaction.intervention_level_weights", {})
    if isinstance(weights, dict):
        vals = [abs(float(weights.get(str(i), weights.get(i, 0)))) for i in (1, 2, 3)]
        if vals:
            return sum(vals) / len(vals)
    return 0.6


def _write_intervention_sensitivity(cfg: Dict[str, Any], v: float) -> None:
    v = _clamp(v, 0.2, 1.0)
    set_by_dotted(
        cfg,
        "simulation.satisfaction.intervention_level_weights",
        {"0": 0.0, "1": round(-0.3 * v / 0.6, 3), "2": round(-0.6 * v / 0.6, 3), "3": round(-1.0 * v / 0.6, 3)},
    )
    for phase in ("adjustment", "formation", "fatigue"):
        set_by_dotted(
            cfg,
            f"simulation.satisfaction.discipline_phase_modifiers.{phase}.intervention_sensitivity",
            round(v, 3),
        )


def _read_intervention_tendency(cfg: Dict[str, Any]) -> float:
    base = float(get_by_dotted(cfg, "management.manager_learning.early_intervention_base", 50.0))
    # 50→0.5 保守, 30→1.0 激进
    return _clamp(1.25 - base / 40.0, 0.2, 1.0)


def _write_intervention_tendency(cfg: Dict[str, Any], v: float) -> None:
    v = _clamp(v, 0.2, 1.0)
    set_by_dotted(cfg, "management.manager_learning.early_intervention_base", round(50.0 - (v - 0.5) * 40.0, 2))


def _read_health_safe_threshold(cfg: Dict[str, Any]) -> float:
    raw = float(get_by_dotted(cfg, "management.over_intervention.health_safe_threshold", 6.0))
    return raw * 10.0 if raw <= 10.0 else raw


def _write_health_safe_threshold(cfg: Dict[str, Any], v: float) -> None:
    v = _clamp(v, 50.0, 90.0)
    set_by_dotted(cfg, "management.over_intervention.health_safe_threshold", round(v / 10.0, 2))


UI_PARAM_HANDLERS: Dict[str, Tuple[Callable, Callable]] = {
    "penaltyStrength": (_read_penalty_strength, _write_penalty_strength),
    "complianceBonus": (
        lambda c: _read_discipline_level_field(c, "compliance_bonus", 1.5),
        lambda c, v: _write_discipline_level_field(c, "compliance_bonus", _clamp(v, 0.5, 2.5)),
    ),
    "cumulativeSpeed": (
        lambda c: _read_nonlinear_discipline_field(c, "cumulative_factor", 0.005),
        lambda c, v: _write_nonlinear_discipline_field(c, "cumulative_factor", _clamp(v, 0.005, 0.025)),
    ),
    "plateauStubbornness": (
        lambda c: _read_nonlinear_discipline_field(c, "plateau_duration", 7.0),
        lambda c, v: _write_nonlinear_discipline_field(c, "plateau_duration", _clamp(v, 7.0, 21.0), as_int=True),
    ),
    "dailyPenaltyCap": (
        lambda c: abs(float(get_by_dotted(c, "simulation.health.nonlinear.max_penalty", -10.0))),
        lambda c, v: set_by_dotted(c, "simulation.health.nonlinear.max_penalty", -abs(_clamp(v, 4.0, 12.0))),
    ),
    "noiseSigma": (
        lambda c: _read_nonlinear_discipline_field(c, "noise_sigma", 0.4),
        lambda c, v: _write_nonlinear_discipline_field(c, "noise_sigma", _clamp(v, 0.2, 0.6)),
    ),
    "baseRelapseProb": (
        lambda c: float(get_by_dotted(c, "simulation.relapse.base_prob", 0.15)),
        lambda c, v: set_by_dotted(c, "simulation.relapse.base_prob", round(_clamp(v, 0.05, 0.25), 4)),
    ),
    "disciplineCorrection": (
        lambda c: _read_mod_table_scale(c, "simulation.relapse.discipline_mod", _BASE_DISCIPLINE_MOD),
        lambda c, v: _write_mod_table_scale(
            c, "simulation.relapse.discipline_mod", _BASE_DISCIPLINE_MOD, _clamp(v, 0.5, 1.5)
        ),
    ),
    "addictionCorrection": (
        lambda c: _read_mod_table_scale(c, "simulation.relapse.addiction_mod", _BASE_ADDICTION_MOD),
        lambda c, v: _write_mod_table_scale(
            c, "simulation.relapse.addiction_mod", _BASE_ADDICTION_MOD, _clamp(v, 0.5, 2.0)
        ),
    ),
    "relaxTimeSensitivity": (
        lambda c: float(get_by_dotted(c, "simulation.relapse.time_mod.per_unit", 0.15)) / 0.15,
        lambda c, v: set_by_dotted(
            c, "simulation.relapse.time_mod.per_unit", round(0.15 * _clamp(v, 0.5, 3.0), 4)
        ),
    ),
    "habitProtection": (
        lambda c: float(get_by_dotted(c, "simulation.relapse.habit_mod.streak_factor", 0.03)),
        lambda c, v: set_by_dotted(
            c, "simulation.relapse.habit_mod.streak_factor", round(_clamp(v, 0.01, 0.05), 4)
        ),
    ),
    "relapseSwing": (
        lambda c: float(get_by_dotted(c, "simulation.relapse.tendency_mod.tendency_weight", 0.5)),
        lambda c, v: set_by_dotted(
            c, "simulation.relapse.tendency_mod.tendency_weight", round(_clamp(v, 0.3, 2.0), 4)
        ),
    ),
    "baseSatisfaction": (
        lambda c: float(get_by_dotted(c, "simulation.satisfaction.base_score", 6.0)),
        lambda c, v: set_by_dotted(c, "simulation.satisfaction.base_score", round(_clamp(v, 4.0, 8.0), 2)),
    ),
    "interventionSensitivity": (_read_intervention_sensitivity, _write_intervention_sensitivity),
    "frequencyPenalty": (
        lambda c: abs(float(get_by_dotted(c, "simulation.satisfaction.frequency_penalty.per_intervention", -0.5))),
        lambda c, v: set_by_dotted(
            c,
            "simulation.satisfaction.frequency_penalty.per_intervention",
            -round(_clamp(v, 0.1, 0.8), 3),
        ),
    ),
    "overInterventionPenalty": (
        lambda c: abs(float(get_by_dotted(c, "simulation.satisfaction.overintervention.base_penalty", -0.5))),
        lambda c, v: set_by_dotted(
            c,
            "simulation.satisfaction.overintervention.base_penalty",
            -round(_clamp(v, 0.1, 1.0), 3),
        ),
    ),
    "alternativeCompensation": (
        lambda c: float(get_by_dotted(c, "simulation.satisfaction.autonomy_modifier_cap", 0.5)),
        lambda c, v: set_by_dotted(
            c, "simulation.satisfaction.autonomy_modifier_cap", round(_clamp(v, 0.2, 1.5), 3)
        ),
    ),
    "timelinessEffect": (
        lambda c: float(get_by_dotted(c, "simulation.satisfaction.intervention_reasonability.reasonable", 0.5)),
        lambda c, v: set_by_dotted(
            c,
            "simulation.satisfaction.intervention_reasonability.reasonable",
            round(_clamp(v, 0.2, 1.2), 3),
        ),
    ),
    "interventionIntensity": (
        lambda c: float(
            get_by_dotted(c, "management.relationship_phases.adjustment.intervention_modifier", 1.0)
        ),
        lambda c, v: set_by_dotted(
            c,
            "management.relationship_phases.adjustment.intervention_modifier",
            round(_clamp(v, 0.2, 1.5), 3),
        ),
    ),
    "interventionTendency": (_read_intervention_tendency, _write_intervention_tendency),
    "healthSafeThreshold": (_read_health_safe_threshold, _write_health_safe_threshold),
    "emotionWarning": (
        lambda c: float(get_by_dotted(c, "management.over_intervention.emotion_warning_threshold", 3.0)),
        lambda c, v: set_by_dotted(
            c,
            "management.over_intervention.emotion_warning_threshold",
            round(_clamp(v, 3.0, 7.0), 2),
        ),
    ),
}


def list_ui_param_specs() -> List[Dict[str, Any]]:
    out = []
    for spec in UI_PARAM_SPECS:
        out.append(
            {
                "key": spec.key,
                "label": spec.label,
                "section": spec.section,
                "min": spec.min_value,
                "max": spec.max_value,
                "description": spec.description,
            }
        )
    return out


def read_ui_param(cfg: Dict[str, Any], key: str) -> float:
    if key not in UI_PARAM_HANDLERS:
        raise MechanismConfigError(f"非界面可调参数: {key}")
    reader, _ = UI_PARAM_HANDLERS[key]
    return float(reader(cfg))


def write_ui_param(cfg: Dict[str, Any], key: str, value: float) -> Dict[str, Any]:
    if key not in UI_PARAM_HANDLERS:
        raise MechanismConfigError(f"非界面可调参数: {key}")
    _, writer = UI_PARAM_HANDLERS[key]
    working = copy.deepcopy(cfg)
    writer(working, float(value))
    return working


def snapshot_ui_values(cfg: Dict[str, Any]) -> Dict[str, float]:
    return {spec.key: read_ui_param(cfg, spec.key) for spec in UI_PARAM_SPECS}


# edit_config 允许的点分路径（由 22 个 UI 键展开）
def _collect_allowed_leaf_paths() -> Set[str]:
    from modules.mechanism_config.loader import load_mechanism_config

    cfg = load_mechanism_config()
    baseline = copy.deepcopy(cfg)
    allowed: Set[str] = set()
    for key in UI_PARAM_HANDLERS:
        mutated = write_ui_param(baseline, key, read_ui_param(baseline, key))
        allowed.update(_flatten_leaf_paths(mutated))
    return allowed


def _flatten_leaf_paths(obj: Any, prefix: str = "") -> Set[str]:
    paths: Set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                paths.update(_flatten_leaf_paths(v, p))
            else:
                paths.add(p)
    return paths


# 静态白名单（避免每次读盘）
UI_TUNABLE_JSON_PATHS: Set[str] = {
    "simulation.health.nonlinear.max_penalty",
    "simulation.health.nonlinear.discipline_params.high.violation_penalty_range",
    "simulation.health.nonlinear.discipline_params.medium.violation_penalty_range",
    "simulation.health.nonlinear.discipline_params.low.violation_penalty_range",
    "simulation.health.nonlinear.discipline_params.high.cumulative_factor",
    "simulation.health.nonlinear.discipline_params.medium.cumulative_factor",
    "simulation.health.nonlinear.discipline_params.low.cumulative_factor",
    "simulation.health.nonlinear.discipline_params.high.plateau_duration",
    "simulation.health.nonlinear.discipline_params.medium.plateau_duration",
    "simulation.health.nonlinear.discipline_params.low.plateau_duration",
    "simulation.health.nonlinear.discipline_params.high.noise_sigma",
    "simulation.health.nonlinear.discipline_params.medium.noise_sigma",
    "simulation.health.nonlinear.discipline_params.low.noise_sigma",
    "simulation.health.discipline_params.high.compliance_bonus",
    "simulation.health.discipline_params.medium.compliance_bonus",
    "simulation.health.discipline_params.low.compliance_bonus",
    "simulation.relapse.base_prob",
    "simulation.relapse.discipline_mod.very_low",
    "simulation.relapse.discipline_mod.low",
    "simulation.relapse.discipline_mod.medium",
    "simulation.relapse.discipline_mod.high",
    "simulation.relapse.discipline_mod.very_high",
    "simulation.relapse.addiction_mod.none",
    "simulation.relapse.addiction_mod.low",
    "simulation.relapse.addiction_mod.moderate",
    "simulation.relapse.addiction_mod.high",
    "simulation.relapse.addiction_mod.severe",
    "simulation.relapse.time_mod.per_unit",
    "simulation.relapse.habit_mod.streak_factor",
    "simulation.relapse.tendency_mod.tendency_weight",
    "simulation.satisfaction.base_score",
    "simulation.satisfaction.frequency_penalty.per_intervention",
    "simulation.satisfaction.overintervention.base_penalty",
    "simulation.satisfaction.autonomy_modifier_cap",
    "simulation.satisfaction.intervention_reasonability.reasonable",
    "simulation.satisfaction.discipline_phase_modifiers.adjustment.intervention_sensitivity",
    "simulation.satisfaction.discipline_phase_modifiers.formation.intervention_sensitivity",
    "simulation.satisfaction.discipline_phase_modifiers.fatigue.intervention_sensitivity",
    "simulation.satisfaction.intervention_level_weights.0",
    "simulation.satisfaction.intervention_level_weights.1",
    "simulation.satisfaction.intervention_level_weights.2",
    "simulation.satisfaction.intervention_level_weights.3",
    "management.relationship_phases.adjustment.intervention_modifier",
    "management.manager_learning.early_intervention_base",
    "management.over_intervention.health_safe_threshold",
    "management.over_intervention.emotion_warning_threshold",
}


def assert_ui_tunable_json_path(dotted_path: str) -> None:
    """edit_config 路径校验：仅允许界面 22 项映射的 JSON 叶子。"""
    path = dotted_path.strip()
    if path not in UI_TUNABLE_JSON_PATHS:
        raise MechanismConfigError(
            f"参数不在界面可调白名单: {path}。"
            f"仅允许 docs/mechanism/界面可调参数.md 中 22 项；请用 UI 键或 set_ui_param。"
        )


def is_ui_tunable_json_path(dotted_path: str) -> bool:
    return dotted_path.strip() in UI_TUNABLE_JSON_PATHS
