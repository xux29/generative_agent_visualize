"""Mechanism-layer probes for visualization tabs (no LLM)."""

from __future__ import annotations

import copy
import random
import threading
from typing import Any, Dict, List, Optional, Tuple

from modules.health_mechanisms.agent_mixin import HealthAgentMixin
from modules.health_mechanisms.scoring.nonlinear import NonlinearHealthScorer, Scorer
from modules.mechanism_config import set_mechanism_config
from modules.mechanism_config.ui_tunable import (
    UI_PARAM_SPECS,
    read_ui_param,
    snapshot_ui_values,
    write_ui_param,
)

from viz_backend.services.config_loader import load_baseline_config

_CFG_LOCK = threading.Lock()


def _apply_cfg(cfg: dict) -> None:
    with _CFG_LOCK:
        set_mechanism_config(cfg)


def _fixed_day_events(days: int, seed: int) -> List[Tuple[bool, int, bool, int]]:
    rng = random.Random(seed)
    seq = []
    for _ in range(days):
        had = rng.random() < 0.45
        if had:
            unblocked = rng.randint(0, 2)
            success = unblocked == 0 and rng.random() < 0.6
            count = rng.randint(1, 3)
        else:
            unblocked = 0
            success = True
            count = rng.randint(0, 1)
        seq.append((had, count, success, unblocked if had else 0))
    return seq


def _run_health_sim(cfg: dict, days: int = 30, seed: int = 7) -> Dict[str, Any]:
    _apply_cfg(cfg)
    disc = cfg["simulation"]["subject"].get("self_discipline", "medium")
    init = float(cfg["simulation"]["subject"].get("initial_health", 75))
    scorer = NonlinearHealthScorer(
        initial_score=init, discipline_level=disc, random_seed=seed, floor_score=0.0
    )
    comp_sums: Dict[str, float] = {}
    comp_counts: Dict[str, int] = {}
    scores: List[float] = []
    violation_days = 0

    for had, ic, ok, ub in _fixed_day_events(days, seed):
        change, bd = scorer.calculate_daily_change(
            {},
            had_violation=had,
            intervention_count=ic,
            intervention_success=ok,
            unblocked_violation_count=ub,
        )
        scores.append(scorer.current_score)
        if had:
            violation_days += 1
        for k, v in (bd.get("components") or {}).items():
            if isinstance(v, (int, float)):
                comp_sums[k] = comp_sums.get(k, 0.0) + float(v)
                comp_counts[k] = comp_counts.get(k, 0) + 1

    def avg(key: str) -> float:
        n = comp_counts.get(key, 0)
        return round(comp_sums.get(key, 0.0) / n, 4) if n else 0.0

    return {
        "health_final": round(scores[-1], 3),
        "health_p50": round(sorted(scores)[len(scores) // 2], 3),
        "health_mean": round(sum(scores) / len(scores), 3),
        "violation_days": violation_days,
        "components_avg": {k: round(comp_sums[k] / comp_counts[k], 4) for k in comp_sums if comp_counts[k]},
        "violation_avg": avg("violation"),
        "compliance_avg": avg("compliance_bonus"),
        "decline_avg": avg("decline_acceleration"),
        "noise_avg": avg("daily_noise"),
        "cap_hits": comp_counts.get("daily_penalty_cap", 0),
    }


class _RelapseStub(HealthAgentMixin):
    def __init__(self, cfg: dict, streak: int = 10, tendency: float = 0.2):
        self.self_discipline = cfg["simulation"]["subject"].get("self_discipline", "medium")
        self.addiction_level = cfg["simulation"]["subject"].get("addiction_level", "moderate")
        self.habit_streak = streak
        self.relapse_tendency = tendency


def relapse_factor_breakdown(cfg: dict, days_relaxed: int = 9) -> Dict[str, Any]:
    _apply_cfg(cfg)
    stub = _RelapseStub(cfg)
    from modules.mechanism_config import get_path

    base = float(get_path("simulation.relapse.base_prob", 0.15))
    disc = stub.self_discipline
    addiction = stub.addiction_level
    discipline_mod = float(get_path("simulation.relapse.discipline_mod", {}).get(disc, 1.0))
    addiction_mod = float(get_path("simulation.relapse.addiction_mod", {}).get(addiction, 1.0))
    days_divisor = float(get_path("simulation.relapse.time_mod.days_divisor", 3))
    per_unit = float(get_path("simulation.relapse.time_mod.per_unit", 0.15))
    time_mod = 1.0 + (days_relaxed / days_divisor) * per_unit
    streak_factor = float(get_path("simulation.relapse.habit_mod.streak_factor", 0.03))
    habit_floor = float(get_path("simulation.relapse.habit_mod.floor", 0.3))
    habit_mod = max(habit_floor, 1.0 - stub.habit_streak * streak_factor)
    tendency_weight = float(get_path("simulation.relapse.tendency_mod.tendency_weight", 0.5))
    tendency_add = stub.relapse_tendency * tendency_weight

    prob = min(1.0, base * discipline_mod * addiction_mod * time_mod * habit_mod * (1.0 + tendency_add))

    health = _run_health_sim(cfg, days=90, seed=11)
    return {
        "relapse_probability_pct": round(prob * 100, 2),
        "factors": [
            {"key": "baseRelapseProb", "label": "基础概率", "value": round(base, 4)},
            {"key": "disciplineCorrection", "label": "自律修正", "value": round(discipline_mod, 4)},
            {"key": "addictionCorrection", "label": "成瘾修正", "value": round(addiction_mod, 4)},
            {"key": "relaxTimeSensitivity", "label": "放松时间", "value": round(time_mod, 4)},
            {"key": "habitProtection", "label": "习惯保护", "value": round(habit_mod, 4)},
            {"key": "relapseSwing", "label": "复发倾向", "value": round(1.0 + tendency_add, 4)},
        ],
        "kpis": {
            "relapse_probability_pct": round(prob * 100, 2),
            "violation_days_90d": health["violation_days"],
            "health_final_p50": health["health_p50"],
        },
        "days_relaxed": days_relaxed,
        "discipline": disc,
    }


HEALTH_FACTOR_MAP = [
    ("penaltyStrength", "violation", "违规惩罚"),
    ("complianceBonus", "compliance_bonus", "遵从奖励"),
    ("cumulativeSpeed", "decline_acceleration", "持续恶化加速"),
    ("plateauStubbornness", "natural_recovery", "平台期/恢复"),
    ("dailyPenaltyCap", "violation", "每日最大扣分"),
    ("noiseSigma", "daily_noise", "日常波动"),
]


def health_factor_tab(cfg: dict, baseline_cfg: Optional[dict] = None) -> Dict[str, Any]:
    baseline_cfg = baseline_cfg or load_baseline_config()
    cur = _run_health_sim(cfg)
    base = _run_health_sim(baseline_cfg)

    factors = []
    ui_vals = snapshot_ui_values(cfg)
    ui_base = snapshot_ui_values(baseline_cfg)

    for ui_key, comp_key, label in HEALTH_FACTOR_MAP:
        cur_imp = cur["components_avg"].get(comp_key, cur.get("violation_avg" if comp_key == "violation" else 0))
        base_imp = base["components_avg"].get(comp_key, base.get("violation_avg" if comp_key == "violation" else 0))
        delta = round(cur_imp - base_imp, 4)
        factors.append(
            {
                "ui_key": ui_key,
                "label": label,
                "baseline_ui": ui_base.get(ui_key),
                "current_ui": ui_vals.get(ui_key),
                "baseline_impact": base_imp,
                "current_impact": cur_imp,
                "delta": delta,
                "direction": "improve" if delta > 0 and comp_key in ("compliance_bonus", "natural_recovery") else (
                    "improve" if delta < 0 and comp_key in ("violation", "decline_acceleration", "daily_noise") else (
                        "worsen" if delta != 0 else "neutral"
                    )
                ),
            }
        )

    return {
        "tab": 2,
        "title": "健康分因子分解",
        "gauge": {"health_p50": cur["health_p50"], "health_final": cur["health_final"]},
        "factors": factors,
        "ui_params": {s.key: ui_vals.get(s.key) for s in UI_PARAM_SPECS if s.section == "health"},
    }


def satisfaction_factor_tab(cfg: dict) -> Dict[str, Any]:
    _apply_cfg(cfg)
    actions = [
        {"level": 2, "reasonability": "unnecessary"},
        {"level": 1, "reasonability": "reasonable"},
        {"level": 3, "reasonability": "preventive"},
    ]
    score, bd = Scorer.calculate_satisfaction_score(
        actions, day=25, habit_streak=10, compliance_rate=0.6, health_score=8.0
    )
    ui_vals = snapshot_ui_values(cfg)

    positive = [
        ("baseSatisfaction", bd.get("base_score", bd.get("BASE_SCORE", 6.0)), "基础满意度"),
        ("alternativeCompensation", bd.get("autonomy_modifier", 0), "替代奖励"),
        ("timelinessEffect", bd.get("reasonability_modifier", 0), "时机奖励"),
    ]
    negative = [
        ("interventionSensitivity", bd.get("intensity_modifier", 0), "强度惩罚"),
        ("frequencyPenalty", bd.get("frequency_modifier", 0), "频率惩罚"),
        ("overInterventionPenalty", bd.get("overintervention_penalty", 0), "过度干预惩罚"),
    ]

    bars = []
    for key, val, label in positive:
        v = float(val) if isinstance(val, (int, float)) else 0.0
        if v > 0:
            bars.append({"ui_key": key, "label": label, "value": round(v, 3), "sign": "positive"})
    for key, val, label in negative:
        v = float(val) if isinstance(val, (int, float)) else 0.0
        if v != 0:
            bars.append({"ui_key": key, "label": label, "value": round(v, 3), "sign": "negative"})

    return {
        "tab": 4,
        "title": "满意度因子构成",
        "composite_score": round(float(score), 2),
        "baseline_score": float(bd.get("base_score", 6.0)),
        "breakdown": bd,
        "bars": bars,
        "ui_params": {s.key: ui_vals.get(s.key) for s in UI_PARAM_SPECS if s.section == "satisfaction"},
    }


def management_tab(cfg: dict) -> Dict[str, Any]:
    ui_vals = snapshot_ui_values(cfg)
    from modules.mechanism_config import get_path

    _apply_cfg(cfg)
    health_safe = float(get_path("management.over_intervention.health_safe_threshold", 6))
    emotion_warn = float(get_path("management.over_intervention.emotion_warning_threshold", 3.0))
    early_base = float(get_path("management.manager_learning.early_intervention_base", 50.0))
    phase_mod = float(
        get_path("management.relationship_phases.adjustment.intervention_modifier", 1.0)
    )

    return {
        "tab": 5,
        "title": "管理机制",
        "params": [
            {
                "ui_key": "interventionIntensity",
                "label": "干预强度",
                "value": ui_vals.get("interventionIntensity"),
                "underlying": phase_mod,
            },
            {
                "ui_key": "interventionTendency",
                "label": "干预倾向",
                "value": ui_vals.get("interventionTendency"),
                "underlying_early_intervention_base": early_base,
            },
            {
                "ui_key": "healthSafeThreshold",
                "label": "健康分警戒线",
                "value": ui_vals.get("healthSafeThreshold"),
                "underlying_0_10": health_safe,
            },
            {
                "ui_key": "emotionWarning",
                "label": "情绪警戒线",
                "value": ui_vals.get("emotionWarning"),
                "underlying": emotion_warn,
            },
        ],
        "hints": [
            "实际违规偏多 → 提高干预倾向或降低健康分警戒线",
            "满意度偏低 → 检查过度干预与频率惩罚",
            "干预太频繁 → 提高健康分警戒线",
        ],
    }


def tab_payload(section: str, cfg: dict) -> Dict[str, Any]:
    if section == "health":
        return health_factor_tab(cfg)
    if section == "relapse":
        out = relapse_factor_tab(cfg)
        out["tab"] = 3
        out["title"] = "复发因子分解"
        out["ui_params"] = snapshot_ui_values(cfg)
        for s in UI_PARAM_SPECS:
            if s.section == "relapse":
                out["ui_params"].setdefault(s.key, read_ui_param(cfg, s.key))
        baseline = load_baseline_config()
        base_rel = relapse_factor_breakdown(baseline)
        for f in out["factors"]:
            bf = next((x for x in base_rel["factors"] if x["key"] == f["key"]), None)
            f["baseline_value"] = bf["value"] if bf else None
            f["direction"] = (
                "improve" if f["key"] in ("habitProtection",) and f["value"] > (bf["value"] or 0)
                else "worsen" if f["value"] > (bf["value"] or 0) and f["key"] not in ("habitProtection",)
                else "improve" if f["value"] < (bf["value"] or 0) and f["key"] not in ("habitProtection",)
                else "neutral"
            )
        return out
    if section == "satisfaction":
        return satisfaction_factor_tab(cfg)
    if section == "management":
        return management_tab(cfg)
    raise ValueError(f"unknown section: {section}")


def probe_ui_param_delta(cfg: dict, ui_key: str, value: float) -> Dict[str, Any]:
    """Compare tab KPIs before/after a single UI param change."""
    before_cfg = copy.deepcopy(cfg)
    after_cfg = write_ui_param(copy.deepcopy(cfg), ui_key, value)
    spec = next(s for s in UI_PARAM_SPECS if s.key == ui_key)
    section = spec.section
    return {
        "ui_key": ui_key,
        "section": section,
        "before": tab_payload(section, before_cfg),
        "after": tab_payload(section, after_cfg),
    }
