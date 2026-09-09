"""界面可调参数（权威清单：docs/界面可调参数.md）。

专家滑杆 **所见即所得**：数值原样存在配置顶层 ``ui_params.{key}``。
写入时再同步到机制运行时字段（供仿真代码读取），专家无需关心也不经 AI。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from modules.mechanism_config.schema import MechanismConfigError, get_by_dotted, set_by_dotted

UI_PARAMS_ROOT = "ui_params"

Discipline = ("high", "medium", "low")

PHASE_JSON = {
    "HONEYMOON": "honeymoon",
    "ADJUSTMENT": "adjustment",
    "FATIGUE": "fatigue",
    "STABLE": "stable",
    "RELAPSE": "relapse",
}

_PHASE_MOD_DEFAULTS = {
    "honeymoon": 0.8,
    "adjustment": 1.0,
    "fatigue": 0.9,
    "stable": 0.6,
    "relapse": 1.3,
}


@dataclass(frozen=True)
class UiParamSpec:
    key: str
    label: str
    section: str
    min_value: float
    max_value: float
    slider_low: str = ""
    slider_high: str = ""
    description: str = ""
    inverted: bool = False  # True：左端点对应 max（如 放大↔缩小 / 1.5~0.5）


UI_PARAM_SPECS: Tuple[UiParamSpec, ...] = (
    # —— 健康分演算 ——
    UiParamSpec("penaltyStrength", "违规扣分（非线性）", "health", 2.0, 7.0, "轻", "重", "未阻止违规的基础扣分力度"),
    UiParamSpec("complianceBonus", "遵从加分", "health", 0.5, 2.5, "少", "多", "无违规时健康分恢复量，上限≤初始分"),
    UiParamSpec("cumulativeSpeed", "连续犯规加速下滑", "health", 0.005, 0.025, "缓", "急", "连续犯规后加速下滑"),
    UiParamSpec("plateauStubbornness", "平台期机制", "health", 7.0, 21.0, "易破", "顽固", "连续好天后进入平台期的长度（天）"),
    UiParamSpec("dailyPenaltyCap", "每日最大扣分限制", "health", 4.0, 12.0, "低", "高", "单日扣分上限，防止单日崩溃"),
    UiParamSpec("noiseSigma", "日常随机波动", "health", 0.2, 0.6, "小", "大", "每日健康分随机扰动幅度"),
    # —— 违规/复发概率 ——
    UiParamSpec("baseRelapseProb", "违规基础概率", "relapse", 0.05, 0.25, "低", "高", "基准违规概率（放松后再次违规的可能性）"),
    UiParamSpec(
        "disciplineCorrection", "自律修正", "relapse", 0.5, 1.5, "放大", "缩小",
        "控制自律对违规的放大/缩小倍数", inverted=True,
    ),
    UiParamSpec("addictionCorrection", "成瘾修正", "relapse", 0.5, 2.0, "弱", "强", "成瘾越重，违规概率放大越多"),
    UiParamSpec("relaxTimeSensitivity", "放松时间", "relapse", 0.5, 3.0, "迟钝", "敏锐", "放松越久，违规概率上升速度"),
    UiParamSpec("habitProtection", "习惯保护", "relapse", 0.01, 0.05, "弱", "强", "连续无违规天数越长，违规概率越低"),
    UiParamSpec("relapseSwing", "复发倾向", "relapse", 0.3, 2.0, "小", "大", "复发倾向摆幅（加项）"),
    # —— 满意度 ——
    UiParamSpec("baseSatisfaction", "基础满意度", "satisfaction", 4.0, 8.0, "低", "高", "满意度基线"),
    UiParamSpec("interventionSensitivity", "干预强度扣分", "satisfaction", 0.2, 1.0, "轻", "重", "干预等级越高，满意度扣分越多"),
    UiParamSpec("frequencyPenalty", "干预频率扣分", "satisfaction", 0.1, 0.8, "轻", "重", "干预次数越多，满意度扣分越多"),
    UiParamSpec("overInterventionPenalty", "过度干预扣分", "satisfaction", 0.1, 1.0, "轻", "重", "健康分高于警戒线仍严管时触发"),
    UiParamSpec("alternativeCompensation", "替代加分", "satisfaction", 0.2, 1.5, "少", "多", "提供替代选项时满意度的补偿分"),
    UiParamSpec("timelinessEffect", "合理干预加分", "satisfaction", 0.2, 1.2, "弱", "强", "及时干预效果好时满意度加分"),
    # —— 管理 ——
    UiParamSpec("interventionIntensity", "干预强度", "management", 0.2, 1.5, "温和", "强硬", "直接决定松紧度"),
    UiParamSpec("interventionTendency", "干预倾向", "management", 0.2, 1.0, "保守", "激进", "越激进→L0观察概率越低→实际干预率越高"),
    UiParamSpec("healthSafeThreshold", "健康分阈值", "management", 50.0, 90.0, "低", "高", "健康分高于此值时可放松干预"),
    UiParamSpec("SatisfactionWarning", "满意度阈值", "management", 3.0, 7.0, "低", "高", "满意度低于此值时触发满意度保护机制"),
    # —— 长期关系阶段 ——
    UiParamSpec("HONEYMOON.mod", "蜜月期强度修正", "phase_honeymoon", 0.5, 1.2, "温和", "偏严", "蜜月期整体干预修正系数（默认 0.8）"),
    UiParamSpec("HONEYMOON.trustMul", "蜜月期信任放大", "phase_honeymoon", 1.0, 2.0, "弱", "强", "信任→干预修正的放大倍数（默认 1.5）"),
    UiParamSpec("HONEYMOON.minDays", "蜜月期最短天数", "phase_honeymoon", 1.0, 7.0, "短", "长", "蜜月期最短保持天数（默认 3）"),
    UiParamSpec("HONEYMOON.conflictThreshold", "蜜月期冲突退出线", "phase_honeymoon", 1.0, 4.0, "少", "多", "累计冲突达此次数后退出蜜月期（默认 2）"),
    UiParamSpec("ADJUSTMENT.mod", "磨合期强度修正", "phase_adjustment", 0.7, 1.3, "轻", "重", "磨合期整体干预修正系数（默认 1.0）"),
    UiParamSpec("ADJUSTMENT.minDays", "磨合期最短天数", "phase_adjustment", 5.0, 14.0, "短", "长", "磨合期最短保持天数（默认 7）"),
    UiParamSpec("ADJUSTMENT.complianceThreshold", "磨合期退出遵从率", "phase_adjustment", 0.4, 0.8, "低", "高", "退出磨合期所需的最低遵从率（默认 0.6）"),
    UiParamSpec("ADJUSTMENT.streakThreshold", "磨合期退出连好天数", "phase_adjustment", 3.0, 10.0, "短", "长", "退出磨合期所需的连续好天数（默认 5）"),
    UiParamSpec("FATIGUE.mod", "倦怠期强度修正", "phase_fatigue", 0.7, 1.1, "轻", "重", "倦怠期整体干预修正系数（默认 0.9）"),
    UiParamSpec("FATIGUE.minDays", "倦怠期最短天数", "phase_fatigue", 7.0, 21.0, "短", "长", "倦怠期最短保持天数（默认 14）"),
    UiParamSpec("FATIGUE.internalizationReq", "倦怠期内化要求", "phase_fatigue", 0.3, 0.8, "低", "高", "退出倦怠期所需的内化分阈值"),
    UiParamSpec("STABLE.mod", "稳定期强度修正", "phase_stable", 0.3, 0.9, "轻", "重", "稳定期整体干预修正系数（默认 0.6）"),
    UiParamSpec("STABLE.trustMul", "稳定期信任修正", "phase_stable", 0.5, 1.2, "弱", "强", "稳定期信任→干预修正系数（默认 0.8）"),
    UiParamSpec("RELAPSE.mod", "复发期强度修正", "phase_relapse", 1.0, 1.6, "轻", "重", "复发期干预加严幅度（默认 1.3）"),
    UiParamSpec("RELAPSE.trustMul", "复发期信任修正", "phase_relapse", 0.3, 0.7, "弱", "强", "复发期信任→干预修正系数（默认 0.5）"),
    UiParamSpec("RELAPSE.streakThreshold", "复发期退出连好天数", "phase_relapse", 3.0, 10.0, "短", "长", "退出复发期所需的连续好天数（默认 5）"),
)

# 兼容旧键名
_UI_KEY_ALIASES = {
    "emotionWarning": "SatisfactionWarning",
}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _avg_range(val: Any) -> float:
    if isinstance(val, (list, tuple)) and len(val) == 2:
        return (float(val[0]) + float(val[1])) / 2.0
    return float(val)


def _resolve_ui_key(key: str) -> str:
    return _UI_KEY_ALIASES.get(key, key)


def _phase_root(phase_ui: str) -> str:
    json_name = PHASE_JSON[phase_ui]
    return f"management.relationship_phases.{json_name}"


def _read_penalty_strength(cfg: Dict[str, Any]) -> float:
    path = "simulation.health.nonlinear.discipline_params.medium.violation_penalty_range"
    return _avg_range(get_by_dotted(cfg, path, [1.5, 2.0]))


_PENALTY_STRENGTH_SCALE = {"high": 0.65, "medium": 0.85, "low": 1.0}


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


def _read_phase_mod(cfg: Dict[str, Any], phase_ui: str) -> float:
    default = _PHASE_MOD_DEFAULTS[PHASE_JSON[phase_ui]]
    return float(get_by_dotted(cfg, f"{_phase_root(phase_ui)}.intervention_modifier", default))


def _write_phase_mod(cfg: Dict[str, Any], phase_ui: str, v: float, lo: float, hi: float) -> None:
    set_by_dotted(cfg, f"{_phase_root(phase_ui)}.intervention_modifier", round(_clamp(v, lo, hi), 3))


def _read_phase_trust(cfg: Dict[str, Any], phase_ui: str, default: float) -> float:
    return float(get_by_dotted(cfg, f"{_phase_root(phase_ui)}.trust_earn_bonus", default))


def _write_phase_trust(cfg: Dict[str, Any], phase_ui: str, v: float, lo: float, hi: float) -> None:
    set_by_dotted(cfg, f"{_phase_root(phase_ui)}.trust_earn_bonus", round(_clamp(v, lo, hi), 3))


def _read_exit(cfg: Dict[str, Any], phase_ui: str, field: str, default: float) -> float:
    return float(get_by_dotted(cfg, f"{_phase_root(phase_ui)}.exit_conditions.{field}", default))


def _write_exit(cfg: Dict[str, Any], phase_ui: str, field: str, v: float, as_int: bool = False) -> None:
    path = f"{_phase_root(phase_ui)}.exit_conditions"
    exit_cfg = get_by_dotted(cfg, path, None)
    if not isinstance(exit_cfg, dict):
        exit_cfg = {}
        set_by_dotted(cfg, path, exit_cfg)
    exit_cfg = dict(get_by_dotted(cfg, path, {}))
    exit_cfg[field] = int(round(v)) if as_int else round(float(v), 4)
    set_by_dotted(cfg, path, exit_cfg)


def _read_internalization_req(cfg: Dict[str, Any]) -> float:
    score = get_by_dotted(cfg, f"{_phase_root('FATIGUE')}.exit_conditions.habit_internalization_score", None)
    if score is not None:
        return float(score)
    return float(get_by_dotted(cfg, "management.habit_consolidation.stage_thresholds.internalized", 0.6))


def _write_internalization_req(cfg: Dict[str, Any], v: float) -> None:
    v = _clamp(v, 0.3, 0.8)
    set_by_dotted(cfg, "management.habit_consolidation.stage_thresholds.internalized", round(v, 3))
    if v <= 0.45:
        stage = "compliant"
    elif v <= 0.7:
        stage = "internalized"
    else:
        stage = "autonomous"
    path = f"{_phase_root('FATIGUE')}.exit_conditions"
    exit_cfg = dict(get_by_dotted(cfg, path, {}) or {})
    exit_cfg["habit_internalization"] = stage
    exit_cfg["habit_internalization_score"] = round(v, 3)
    set_by_dotted(cfg, path, exit_cfg)


# 从旧机制字段反推初值（仅当 ui_params 尚未写入时）
UI_PARAM_DERIVE: Dict[str, Callable[[Dict[str, Any]], float]] = {
    "penaltyStrength": _read_penalty_strength,
    "complianceBonus": lambda c: _read_discipline_level_field(c, "compliance_bonus", 1.5),
    "cumulativeSpeed": lambda c: _read_nonlinear_discipline_field(c, "cumulative_factor", 0.005),
    "plateauStubbornness": lambda c: _read_nonlinear_discipline_field(c, "plateau_duration", 7.0),
    "dailyPenaltyCap": lambda c: abs(float(get_by_dotted(c, "simulation.health.nonlinear.max_penalty", -10.0))),
    "noiseSigma": lambda c: _read_nonlinear_discipline_field(c, "noise_sigma", 0.4),
    "baseRelapseProb": lambda c: float(get_by_dotted(c, "simulation.relapse.base_prob", 0.15)),
    "disciplineCorrection": lambda c: _read_mod_table_scale(c, "simulation.relapse.discipline_mod", _BASE_DISCIPLINE_MOD),
    "addictionCorrection": lambda c: _read_mod_table_scale(c, "simulation.relapse.addiction_mod", _BASE_ADDICTION_MOD),
    "relaxTimeSensitivity": lambda c: float(get_by_dotted(c, "simulation.relapse.time_mod.per_unit", 0.15)) / 0.15,
    "habitProtection": lambda c: float(get_by_dotted(c, "simulation.relapse.habit_mod.streak_factor", 0.03)),
    "relapseSwing": lambda c: float(get_by_dotted(c, "simulation.relapse.tendency_mod.tendency_weight", 0.5)),
    "baseSatisfaction": lambda c: float(get_by_dotted(c, "simulation.satisfaction.base_score", 6.0)),
    "interventionSensitivity": _read_intervention_sensitivity,
    "frequencyPenalty": lambda c: abs(float(get_by_dotted(c, "simulation.satisfaction.frequency_penalty.per_intervention", -0.5))),
    "overInterventionPenalty": lambda c: abs(float(get_by_dotted(c, "simulation.satisfaction.overintervention.base_penalty", -0.5))),
    "alternativeCompensation": lambda c: float(get_by_dotted(c, "simulation.satisfaction.autonomy_modifier_cap", 0.5)),
    "timelinessEffect": lambda c: float(get_by_dotted(c, "simulation.satisfaction.intervention_reasonability.reasonable", 0.5)),
    "interventionIntensity": lambda c: float(get_by_dotted(c, "management.intervention.intensity", 1.0)),
    "interventionTendency": _read_intervention_tendency,
    "healthSafeThreshold": _read_health_safe_threshold,
    "SatisfactionWarning": lambda c: float(get_by_dotted(c, "management.over_intervention.emotion_warning_threshold", 3.0)),
    "HONEYMOON.mod": lambda c: _read_phase_mod(c, "HONEYMOON"),
    "HONEYMOON.trustMul": lambda c: _read_phase_trust(c, "HONEYMOON", 1.5),
    "HONEYMOON.minDays": lambda c: _read_exit(c, "HONEYMOON", "min_days", 3.0),
    "HONEYMOON.conflictThreshold": lambda c: _read_exit(c, "HONEYMOON", "conflict_threshold", 2.0),
    "ADJUSTMENT.mod": lambda c: _read_phase_mod(c, "ADJUSTMENT"),
    "ADJUSTMENT.minDays": lambda c: _read_exit(c, "ADJUSTMENT", "min_days", 7.0),
    "ADJUSTMENT.complianceThreshold": lambda c: _read_exit(c, "ADJUSTMENT", "habit_compliance_rate", 0.6),
    "ADJUSTMENT.streakThreshold": lambda c: _read_exit(c, "ADJUSTMENT", "consecutive_good_days", 5.0),
    "FATIGUE.mod": lambda c: _read_phase_mod(c, "FATIGUE"),
    "FATIGUE.minDays": lambda c: _read_exit(c, "FATIGUE", "min_days", 14.0),
    "FATIGUE.internalizationReq": _read_internalization_req,
    "STABLE.mod": lambda c: _read_phase_mod(c, "STABLE"),
    "STABLE.trustMul": lambda c: _read_phase_trust(c, "STABLE", 0.8),
    "RELAPSE.mod": lambda c: _read_phase_mod(c, "RELAPSE"),
    "RELAPSE.trustMul": lambda c: _read_phase_trust(c, "RELAPSE", 0.5),
    "RELAPSE.streakThreshold": lambda c: _read_exit(c, "RELAPSE", "consecutive_good_days", 5.0),
}

# 写入仿真仍读取的字段（专家只看见 ui_params；此步对专家透明）
UI_PARAM_APPLY: Dict[str, Callable[[Dict[str, Any], float], None]] = {
    "penaltyStrength": _write_penalty_strength,
    "complianceBonus": lambda c, v: _write_discipline_level_field(c, "compliance_bonus", _clamp(v, 0.5, 2.5)),
    "cumulativeSpeed": lambda c, v: _write_nonlinear_discipline_field(c, "cumulative_factor", _clamp(v, 0.005, 0.025)),
    "plateauStubbornness": lambda c, v: _write_nonlinear_discipline_field(c, "plateau_duration", _clamp(v, 7.0, 21.0), as_int=True),
    "dailyPenaltyCap": lambda c, v: set_by_dotted(c, "simulation.health.nonlinear.max_penalty", -abs(_clamp(v, 4.0, 12.0))),
    "noiseSigma": lambda c, v: _write_nonlinear_discipline_field(c, "noise_sigma", _clamp(v, 0.2, 0.6)),
    "baseRelapseProb": lambda c, v: set_by_dotted(c, "simulation.relapse.base_prob", round(_clamp(v, 0.05, 0.25), 4)),
    "disciplineCorrection": lambda c, v: _write_mod_table_scale(c, "simulation.relapse.discipline_mod", _BASE_DISCIPLINE_MOD, _clamp(v, 0.5, 1.5)),
    "addictionCorrection": lambda c, v: _write_mod_table_scale(c, "simulation.relapse.addiction_mod", _BASE_ADDICTION_MOD, _clamp(v, 0.5, 2.0)),
    "relaxTimeSensitivity": lambda c, v: set_by_dotted(c, "simulation.relapse.time_mod.per_unit", round(0.15 * _clamp(v, 0.5, 3.0), 4)),
    "habitProtection": lambda c, v: set_by_dotted(c, "simulation.relapse.habit_mod.streak_factor", round(_clamp(v, 0.01, 0.05), 4)),
    "relapseSwing": lambda c, v: set_by_dotted(c, "simulation.relapse.tendency_mod.tendency_weight", round(_clamp(v, 0.3, 2.0), 4)),
    "baseSatisfaction": lambda c, v: set_by_dotted(c, "simulation.satisfaction.base_score", round(_clamp(v, 4.0, 8.0), 2)),
    "interventionSensitivity": _write_intervention_sensitivity,
    "frequencyPenalty": lambda c, v: set_by_dotted(c, "simulation.satisfaction.frequency_penalty.per_intervention", -round(_clamp(v, 0.1, 0.8), 3)),
    "overInterventionPenalty": lambda c, v: set_by_dotted(c, "simulation.satisfaction.overintervention.base_penalty", -round(_clamp(v, 0.1, 1.0), 3)),
    "alternativeCompensation": lambda c, v: set_by_dotted(c, "simulation.satisfaction.autonomy_modifier_cap", round(_clamp(v, 0.2, 1.5), 3)),
    "timelinessEffect": lambda c, v: set_by_dotted(c, "simulation.satisfaction.intervention_reasonability.reasonable", round(_clamp(v, 0.2, 1.2), 3)),
    "interventionIntensity": lambda c, v: set_by_dotted(c, "management.intervention.intensity", round(_clamp(v, 0.2, 1.5), 3)),
    "interventionTendency": _write_intervention_tendency,
    "healthSafeThreshold": _write_health_safe_threshold,
    "SatisfactionWarning": lambda c, v: set_by_dotted(c, "management.over_intervention.emotion_warning_threshold", round(_clamp(v, 3.0, 7.0), 2)),
    "HONEYMOON.mod": lambda c, v: _write_phase_mod(c, "HONEYMOON", v, 0.5, 1.2),
    "HONEYMOON.trustMul": lambda c, v: _write_phase_trust(c, "HONEYMOON", v, 1.0, 2.0),
    "HONEYMOON.minDays": lambda c, v: _write_exit(c, "HONEYMOON", "min_days", _clamp(v, 1.0, 7.0), as_int=True),
    "HONEYMOON.conflictThreshold": lambda c, v: _write_exit(c, "HONEYMOON", "conflict_threshold", _clamp(v, 1.0, 4.0), as_int=True),
    "ADJUSTMENT.mod": lambda c, v: _write_phase_mod(c, "ADJUSTMENT", v, 0.7, 1.3),
    "ADJUSTMENT.minDays": lambda c, v: _write_exit(c, "ADJUSTMENT", "min_days", _clamp(v, 5.0, 14.0), as_int=True),
    "ADJUSTMENT.complianceThreshold": lambda c, v: _write_exit(c, "ADJUSTMENT", "habit_compliance_rate", _clamp(v, 0.4, 0.8)),
    "ADJUSTMENT.streakThreshold": lambda c, v: _write_exit(c, "ADJUSTMENT", "consecutive_good_days", _clamp(v, 3.0, 10.0), as_int=True),
    "FATIGUE.mod": lambda c, v: _write_phase_mod(c, "FATIGUE", v, 0.7, 1.1),
    "FATIGUE.minDays": lambda c, v: _write_exit(c, "FATIGUE", "min_days", _clamp(v, 7.0, 21.0), as_int=True),
    "FATIGUE.internalizationReq": _write_internalization_req,
    "STABLE.mod": lambda c, v: _write_phase_mod(c, "STABLE", v, 0.3, 0.9),
    "STABLE.trustMul": lambda c, v: _write_phase_trust(c, "STABLE", v, 0.5, 1.2),
    "RELAPSE.mod": lambda c, v: _write_phase_mod(c, "RELAPSE", v, 1.0, 1.6),
    "RELAPSE.trustMul": lambda c, v: _write_phase_trust(c, "RELAPSE", v, 0.3, 0.7),
    "RELAPSE.streakThreshold": lambda c, v: _write_exit(c, "RELAPSE", "consecutive_good_days", _clamp(v, 3.0, 10.0), as_int=True),
}

# 兼容旧名
UI_PARAM_HANDLERS = UI_PARAM_APPLY



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
                "slider_low": spec.slider_low,
                "slider_high": spec.slider_high,
                "description": spec.description,
                "inverted": spec.inverted,
                "wysiwyg": True,
            }
        )
    return out


def _ui_path(key: str) -> str:
    return f"{UI_PARAMS_ROOT}.{key}"


def _spec_for(key: str) -> UiParamSpec:
    for spec in UI_PARAM_SPECS:
        if spec.key == key:
            return spec
    raise MechanismConfigError(f"非界面可调参数: {key}")


def seed_ui_params(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """若缺少 ui_params，从机制字段反推填满（不改仿真语义）。"""
    working = copy.deepcopy(cfg)
    store = dict(working.get(UI_PARAMS_ROOT) or {})
    changed = False
    for spec in UI_PARAM_SPECS:
        if spec.key in store:
            continue
        derive = UI_PARAM_DERIVE.get(spec.key)
        if derive is None:
            continue
        raw = float(derive(working))
        store[spec.key] = round(_clamp(raw, spec.min_value, spec.max_value), 6)
        changed = True
    if changed or UI_PARAMS_ROOT not in working:
        working[UI_PARAMS_ROOT] = store
    return working


def read_ui_param(cfg: Dict[str, Any], key: str) -> float:
    """所见即所得：优先读 ui_params.{key}。"""
    key = _resolve_ui_key(key)
    spec = _spec_for(key)
    stored = get_by_dotted(cfg, _ui_path(key), None)
    if stored is not None:
        return float(stored)
    derive = UI_PARAM_DERIVE.get(key)
    if derive is None:
        raise MechanismConfigError(f"非界面可调参数: {key}")
    return float(_clamp(float(derive(cfg)), spec.min_value, spec.max_value))


def write_ui_param(cfg: Dict[str, Any], key: str, value: float) -> Dict[str, Any]:
    """写入 ui_params 原值，并同步到机制运行时字段。"""
    key = _resolve_ui_key(key)
    spec = _spec_for(key)
    apply = UI_PARAM_APPLY.get(key)
    if apply is None:
        raise MechanismConfigError(f"非界面可调参数: {key}")
    working = seed_ui_params(cfg)
    v = _clamp(float(value), spec.min_value, spec.max_value)
    # 整数类参数存整型观感
    if key.endswith(("minDays", "conflictThreshold", "streakThreshold")) or key == "plateauStubbornness":
        stored: Any = int(round(v))
    else:
        stored = round(v, 6)
    store = dict(working.get(UI_PARAMS_ROOT) or {})
    store[key] = stored
    working[UI_PARAMS_ROOT] = store
    apply(working, float(stored))
    return working


def snapshot_ui_values(cfg: Dict[str, Any]) -> Dict[str, float]:
    seeded = seed_ui_params(cfg)
    return {spec.key: read_ui_param(seeded, spec.key) for spec in UI_PARAM_SPECS}


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


UI_TUNABLE_JSON_PATHS: Set[str] = {
    # 专家所见即所得主存
    *[f"{UI_PARAMS_ROOT}.{spec.key}" for spec in UI_PARAM_SPECS],
    # 同步后的机制叶子（edit_config 仍可走这些路径，但优先 set_ui_param）
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
    "management.intervention.intensity",
    "management.manager_learning.early_intervention_base",
    "management.over_intervention.health_safe_threshold",
    "management.over_intervention.emotion_warning_threshold",
    "management.habit_consolidation.stage_thresholds.internalized",
    "management.relationship_phases.honeymoon.intervention_modifier",
    "management.relationship_phases.honeymoon.trust_earn_bonus",
    "management.relationship_phases.honeymoon.exit_conditions.min_days",
    "management.relationship_phases.honeymoon.exit_conditions.conflict_threshold",
    "management.relationship_phases.adjustment.intervention_modifier",
    "management.relationship_phases.adjustment.exit_conditions.min_days",
    "management.relationship_phases.adjustment.exit_conditions.habit_compliance_rate",
    "management.relationship_phases.adjustment.exit_conditions.consecutive_good_days",
    "management.relationship_phases.fatigue.intervention_modifier",
    "management.relationship_phases.fatigue.exit_conditions.min_days",
    "management.relationship_phases.fatigue.exit_conditions.habit_internalization",
    "management.relationship_phases.fatigue.exit_conditions.habit_internalization_score",
    "management.relationship_phases.stable.intervention_modifier",
    "management.relationship_phases.stable.trust_earn_bonus",
    "management.relationship_phases.relapse.intervention_modifier",
    "management.relationship_phases.relapse.trust_earn_bonus",
    "management.relationship_phases.relapse.exit_conditions.consecutive_good_days",
}


def assert_ui_tunable_json_path(dotted_path: str) -> None:
    """edit_config 路径校验：仅允许 ui_params.* 或已登记的机制同步叶子。"""
    path = dotted_path.strip()
    if path not in UI_TUNABLE_JSON_PATHS and not path.startswith(f"{UI_PARAMS_ROOT}."):
        raise MechanismConfigError(
            f"参数不在界面可调白名单: {path}。"
            f"专家参数请改 ui_params.<键> 或用 set_ui_param；见 docs/界面可调参数.md。"
        )


def is_ui_tunable_json_path(dotted_path: str) -> bool:
    path = dotted_path.strip()
    return path in UI_TUNABLE_JSON_PATHS or path.startswith(f"{UI_PARAMS_ROOT}.")
