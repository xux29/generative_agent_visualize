#!/usr/bin/env python3
"""机制参数升降影响 · 批量验参仿真（无 LLM）。

对 active/baseline JSON 中可测叶子参数做 ↑/↓，跑机制层探针，记录指标变化。

用法（在 generative_agents/ 下）::

    python3 tools/param_impact_sweep.py --config data/mechanism/active.json
    python3 tools/param_impact_sweep.py --out-dir ../docs/mechanism/param_impact
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.mechanism_config import (
    DEFAULT_ACTIVE_PATH,
    load_defaults,
    load_mechanism_config,
    reset_mechanism_config,
    set_mechanism_config,
)
from tools.param_zh_catalog import describe_param
from modules.mechanism_config.ui_tunable import UI_TUNABLE_JSON_PATHS
from modules.health_mechanisms.agent_mixin import HealthAgentMixin
from modules.health_mechanisms.scoring.nonlinear import (
    NonlinearHealthScorer,
    Scorer,
)
from modules.health_mechanisms.management.strategy import (
    HabitConsolidation,
    LongTermStrategyManager,
    ManagerLearning,
    StrategyManager,
    TrustCapital,
)


# ---------------------------------------------------------------------------
# config path helpers
# ---------------------------------------------------------------------------

def get_by_path(cfg: dict, dotted: str) -> Any:
    cur: Any = cfg
    for part in dotted.split("."):
        cur = cur[part]
    return cur


def set_by_path(cfg: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = cfg
    for part in parts[:-1]:
        cur = cur[part]
    cur[parts[-1]] = value


def flatten_leaves(obj: Any, prefix: str = "") -> List[Tuple[str, Any]]:
    out: List[Tuple[str, Any]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in {"description", "name", "goal", "recommended_style"}:
                continue
            p = f"{prefix}.{k}" if prefix else k
            out.extend(flatten_leaves(v, p))
    elif isinstance(obj, list):
        # treat homogeneous numeric lists / range pairs as atomic leaves
        if obj and all(isinstance(x, (int, float)) for x in obj):
            out.append((prefix, obj))
        elif obj and all(isinstance(x, str) for x in obj):
            out.append((prefix, obj))
        else:
            for i, v in enumerate(obj):
                out.extend(flatten_leaves(v, f"{prefix}[{i}]"))
    else:
        out.append((prefix, obj))
    return out


def algebraic_hi_lo(value: Any) -> Optional[Tuple[Any, Any]]:
    """Return (high, low) where high = algebraically larger."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        if value == 0:
            return 1, 0
        step = max(1, abs(value) // 2)
        return value + step, value - step
    if isinstance(value, float):
        if value == 0.0:
            return 0.15, -0.15
        if value > 0:
            return value * 1.5, value * 0.5
        # negative: algebraic ↑ closer to 0
        return value * 0.5, value * 1.5
    if isinstance(value, list) and value and all(isinstance(x, (int, float)) for x in value):
        his, los = [], []
        for x in value:
            pair = algebraic_hi_lo(x)
            if pair is None:
                return None
            his.append(pair[0])
            los.append(pair[1])
        return his, los
    return None


SKIP_PREFIXES = (
    "meta.",
    "management.intervention.levels",
)

SKIP_SUFFIXES = (
    ".exit_conditions",  # handled partially; skip whole nested non-numeric blobs via type
)


def should_skip(path: str, value: Any) -> Optional[str]:
    if path.startswith(SKIP_PREFIXES):
        return "meta/levels 非数值旋钮"
    if path.endswith(".exit_conditions") or ".exit_conditions." in path:
        if not isinstance(value, (int, float)):
            return "阶段退出条件非纯数值"
    if isinstance(value, str):
        if path.endswith("habit_internalization") or path.endswith("autonomy_level"):
            return "枚举字符串（需专用探针）"
        if path in {
            "simulation.subject.self_discipline",
            "simulation.subject.addiction_level",
            "simulation.subject.habit_formation_speed",
        }:
            return None  # special
        return "字符串/描述"
    if isinstance(value, list) and value and isinstance(value[0], str):
        return "情绪标签列表（专用）"
    if isinstance(value, bool):
        return "布尔"
    if algebraic_hi_lo(value) is None and path not in {
        "simulation.subject.self_discipline",
        "simulation.subject.addiction_level",
        "simulation.subject.habit_formation_speed",
    }:
        return "无法构造 ↑/↓"
    return None


# ---------------------------------------------------------------------------
# probes (mechanism-layer sims)
# ---------------------------------------------------------------------------

class _RelapseStub(HealthAgentMixin):
    def __init__(self, discipline="medium", addiction="moderate", streak=0, tendency=0.0):
        self.self_discipline = discipline
        self.addiction_level = addiction
        self.habit_streak = streak
        self.relapse_tendency = tendency


def probe_relapse(cfg: dict) -> Dict[str, float]:
    set_mechanism_config(cfg)
    stub = _RelapseStub(
        discipline=cfg["simulation"]["subject"].get("self_discipline", "medium"),
        addiction=cfg["simulation"]["subject"].get("addiction_level", "moderate"),
        streak=10,
        tendency=0.2,
    )
    p0 = stub.calculate_relapse_probability(True, 0)
    p9 = stub.calculate_relapse_probability(True, 9)
    return {"relapse_p_day0": round(p0, 4), "relapse_p_day9": round(p9, 4)}


def _fixed_day_events(days: int, seed: int) -> List[Tuple[bool, int, bool, int]]:
    """(had_violation, intervention_count, intervention_success, unblocked)."""
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


def probe_health(cfg: dict, days: int = 30, seed: int = 7) -> Dict[str, float]:
    set_mechanism_config(cfg)
    disc = cfg["simulation"]["subject"].get("self_discipline", "medium")
    init = float(cfg["simulation"]["subject"].get("initial_health", 75))
    scorer = NonlinearHealthScorer(
        initial_score=init, discipline_level=disc, random_seed=seed, floor_score=0.0
    )
    scores = []
    for had, ic, ok, ub in _fixed_day_events(days, seed):
        change, bd = scorer.calculate_daily_change(
            {},
            had_violation=had,
            intervention_count=ic,
            intervention_success=ok,
            unblocked_violation_count=ub,
        )
        scores.append(scorer.current_score)
    warning = float(
        cfg["simulation"]["health"]["nonlinear"].get(
            "warning_line", cfg["simulation"]["health"].get("warning_line", 30)
        )
    )
    return {
        "health_final": round(scores[-1], 3),
        "health_mean": round(sum(scores) / len(scores), 3),
        "health_min": round(min(scores), 3),
        "days_below_warning": float(sum(1 for s in scores if s < warning)),
    }


def probe_mood(cfg: dict) -> Dict[str, float]:
    set_mechanism_config(cfg)
    actions = [{"level": 1}, {"level": 2}, {"level": 2}]
    score, _ = Scorer.calculate_mood_score_with_discipline(
        actions,
        day=10,
        discipline_level=cfg["simulation"]["subject"].get("self_discipline", "medium"),
        health_score=45,
        cumulative_health={"in_plateau": True},
        habit_streak=5,
    )
    return {"mood_under_pressure": round(float(score), 3)}


def probe_satisfaction(cfg: dict) -> Dict[str, float]:
    set_mechanism_config(cfg)
    actions = [
        {"level": 2, "reason": "unnecessary"},
        {"level": 1, "reason": "reasonable"},
        {"level": 3, "reason": "preventive"},
    ]
    # reasonability keys may be inferred inside scorer; pass list of dicts
    score, _ = Scorer.calculate_satisfaction_score(
        actions, day=25, habit_streak=10, health_score=8.0
    )
    return {"satisfaction": round(float(score), 3)}


def probe_compliance(cfg: dict) -> Dict[str, float]:
    set_mechanism_config(cfg)
    disc = cfg["simulation"]["subject"].get("self_discipline", "medium")
    addict = cfg["simulation"]["subject"].get("addiction_level", "moderate")
    accept = cfg["simulation"]["compliance"]["discipline_accept_rate"].get(disc, 0.55)
    add_m = cfg["simulation"]["compliance"]["addiction_resistance_mod"].get(addict, 0.0)
    disc_m = cfg["simulation"]["compliance"]["discipline_resistance_mod"].get(disc, 0.0)
    base_r = float(cfg["simulation"]["subject"].get("resistance_to_persuasion", 0.5))
    eff = max(0.0, min(1.0, base_r + add_m + disc_m))
    return {
        "accept_rate": round(float(accept), 4),
        "effective_resistance": round(eff, 4),
    }


def probe_behavior(cfg: dict) -> Dict[str, float]:
    set_mechanism_config(cfg)
    out: Dict[str, float] = {}
    bs = cfg["simulation"]["behavior_scores"]

    def walk(obj: Any, prefix: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, f"{prefix}.{k}" if prefix else k)
        elif isinstance(obj, (int, float)):
            out[prefix.replace(".", "__")] = float(obj)

    walk(bs, "bs")
    food = Scorer._food_type_scores()
    out["food_high_sugar_diabetes"] = float(food["high_sugar_fat"]["diabetes"])
    return out


def probe_habit_streak_effect(cfg: dict) -> Dict[str, float]:
    set_mechanism_config(cfg)
    good = int(cfg["simulation"]["habit"]["streak_good_delta"])
    bad_reset = int(cfg["simulation"]["habit"]["streak_bad_reset"])
    streak = 0
    for _ in range(5):
        streak += good
    after_good = streak
    streak = bad_reset
    stub = _RelapseStub(streak=after_good, tendency=0.0)
    p_good = stub.calculate_relapse_probability(True, 3)
    stub2 = _RelapseStub(streak=streak, tendency=0.3)
    # apply tendency deltas conceptually
    tend = 0.0 + float(cfg["simulation"]["habit"]["tendency_delta_bad"])
    stub2.relapse_tendency = tend
    p_bad = stub2.calculate_relapse_probability(True, 3)
    return {
        "streak_after_5_good": float(after_good),
        "relapse_p_after_streak": round(p_good, 4),
        "relapse_p_after_bad_tendency": round(p_bad, 4),
    }


def probe_tidal(cfg: dict, days: int = 30) -> Dict[str, float]:
    set_mechanism_config(cfg)
    sm = StrategyManager(scenario="diabetes")
    # synthetic health: alternate blocks of good/bad
    levels, trusts, relax_day = [], [], None
    for d in range(1, days + 1):
        if d <= 8:
            h = 8.0
            ic = 1
        elif d <= 14:
            h = 3.0
            ic = 3
        else:
            h = 8.5
            ic = 0
        sm.update_state(d, h, ic)
        lvl, _ = sm.get_recommended_level(d)
        sm.current_level = lvl
        levels.append(lvl)
        trusts.append(sm.trust_level)
        if relax_day is None and sm.is_relaxed:
            relax_day = d
    return {
        "tidal_mean_level": round(sum(levels) / len(levels), 3),
        "tidal_mean_trust": round(sum(trusts) / len(trusts), 3),
        "tidal_first_relax_day": float(relax_day or -1),
        "tidal_final_level": float(levels[-1]),
    }


def probe_trust_capital(cfg: dict) -> Dict[str, float]:
    set_mechanism_config(cfg)
    tc = TrustCapital()
    daily = cfg["management"]["trust_capital"]["daily"]
    for _ in range(10):
        tc.earn(float(daily["good_earn"]), "good")
    for _ in range(2):
        tc.lose(float(daily["bad_loss"]), "bad")
    return {
        "trust_capital": round(float(tc.capital), 3),
        "autonomy": 1.0 if tc.get_autonomy_level() == "high" else (
            0.5 if tc.get_autonomy_level() == "medium" else 0.0
        ),
    }


def probe_habit_consolidation(cfg: dict) -> Dict[str, float]:
    set_mechanism_config(cfg)
    hc = HabitConsolidation()
    for d in range(1, 15):
        hc.record_opportunity(
            d, intervention_level=0, complied=True, was_proactive=True, emotion_positive=True
        )
        hc.record_relax_resistance(d, resisted_temptation=True)
    stage = hc.get_internalization_stage()
    stage_score = {"none": 0, "compliant": 1, "internalized": 2, "autonomous": 3}.get(
        stage, 0
    )
    return {"habit_stage_score": float(stage_score), "habit_stage_name_ord": float(stage_score)}


def probe_manager_learning(cfg: dict) -> Dict[str, float]:
    set_mechanism_config(cfg)
    ml = ManagerLearning()
    for d in range(1, 20):
        ml.record_intervention(
            d,
            level=1 if d % 3 else 2,
            success=d % 4 != 0,
            health_before=6.0,
            health_after=7.0 if d % 4 != 0 else 5.5,
        )
    s = ml.get_summary()
    return {
        "mgr_understanding": round(float(s.get("understanding_level", 0)), 4),
        "mgr_efficiency": round(float(s.get("intervention_efficiency", 0)), 4),
    }


def probe_over_intervention(cfg: dict) -> Dict[str, float]:
    set_mechanism_config(cfg)
    lts = LongTermStrategyManager(scenario="diabetes")
    # drive low emotion consecutive days
    oi = cfg["management"]["over_intervention"]
    triggers = 0
    for d in range(1, 12):
        lts.set_emotion_context(float(oi["emotion_critical_threshold"]) - 0.2, d)
        lts._update_intervention_tracking(3, d)
        forced, _ = lts._check_over_intervention_protection(d, health_score=7.0)
        if forced:
            triggers += 1
    return {"over_interv_force_hits": float(triggers)}


def probe_composite(cfg: dict) -> Dict[str, float]:
    set_mechanism_config(cfg)
    result = Scorer.calculate_composite_score(
        health_score=7.0, satisfaction_score=6.0, effectiveness_score=7.0
    )
    if isinstance(result, tuple) and len(result) >= 1:
        score = float(result[0])
        rating = result[1] if len(result) > 1 else ""
        if isinstance(rating, dict):
            rating = rating.get("rating", "")
        elif len(result) > 2 and isinstance(result[2], dict):
            rating = result[2].get("rating", rating)
    else:
        score = float(result)
        rating = ""
    return {
        "composite": round(score, 3),
        "rating_ord": float(
            {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}.get(str(rating), 2)
        ),
    }


def probe_subject_enums(cfg: dict) -> Dict[str, float]:
    """Combine health+relapse sensitivity to subject enums."""
    h = probe_health(cfg, days=20, seed=3)
    r = probe_relapse(cfg)
    c = probe_compliance(cfg)
    return {**h, **r, **c}


PRIMARY_METRIC = {
    probe_relapse: "relapse_p_day9",
    probe_health: "health_mean",
    probe_mood: "mood_under_pressure",
    probe_satisfaction: "satisfaction",
    probe_compliance: "effective_resistance",
    probe_behavior: "food_high_sugar_diabetes",
    probe_habit_streak_effect: "relapse_p_after_streak",
    probe_tidal: "tidal_mean_level",
    probe_trust_capital: "trust_capital",
    probe_habit_consolidation: "habit_stage_score",
    probe_manager_learning: "mgr_understanding",
    probe_over_intervention: "over_interv_force_hits",
    probe_composite: "composite",
    probe_subject_enums: "health_mean",
}


PROBE_BY_PREFIX: List[Tuple[str, Callable[[dict], Dict[str, float]]]] = [
    ("simulation.subject.", probe_subject_enums),
    ("simulation.relapse.", probe_relapse),
    ("simulation.health.", probe_health),
    ("simulation.mood.", probe_mood),
    ("simulation.satisfaction.", probe_satisfaction),
    ("simulation.compliance.", probe_compliance),
    ("simulation.behavior_scores.", probe_behavior),
    ("simulation.habit.", probe_habit_streak_effect),
    ("simulation.composite.", probe_composite),
    ("management.tidal.", probe_tidal),
    ("management.trust_capital.", probe_trust_capital),
    ("management.habit_consolidation.", probe_habit_consolidation),
    ("management.manager_learning.", probe_manager_learning),
    ("management.over_intervention.", probe_over_intervention),
    ("management.relationship_phases.", probe_tidal),  # modifier affects long-term; tidal approx
    ("management.reflection.", probe_tidal),
    ("management.intervention.", probe_tidal),
]


def select_probe(path: str) -> Callable[[dict], Dict[str, float]]:
    for prefix, fn in PROBE_BY_PREFIX:
        if path.startswith(prefix):
            return fn
    return probe_health


def subject_hi_lo(path: str, value: str) -> Optional[Tuple[str, str]]:
    maps = {
        "simulation.subject.self_discipline": ("high", "low"),
        "simulation.subject.addiction_level": ("severe", "none"),
        "simulation.subject.habit_formation_speed": ("normal", "slow"),
    }
    return maps.get(path)


@dataclass
class SweepRow:
    path: str
    baseline: Any
    high: Any
    low: Any
    probe: str
    metric: str
    baseline_metrics: Dict[str, float]
    high_metrics: Dict[str, float]
    low_metrics: Dict[str, float]
    delta_high: float
    delta_low: float
    effect_when_up: str
    effect_when_down: str
    verified: bool = True
    skip_reason: Optional[str] = None


def effect_label(delta: float, eps: float = 1e-4) -> str:
    if abs(delta) < eps:
        return "无明显变化"
    return "指标上升" if delta > 0 else "指标下降"


def pick_metric_and_deltas(
    probe_fn: Callable,
    path: str,
    m0: Dict[str, float],
    mh: Dict[str, float],
    ml: Dict[str, float],
) -> Tuple[str, float, float]:
    preferred = PRIMARY_METRIC.get(probe_fn)
    # behavior leaf: prefer metric key matching path
    if path.startswith("simulation.behavior_scores."):
        leaf_key = "bs__" + path[len("simulation.behavior_scores.") :].replace(".", "__")
        # walk used "bs." prefix with "." -> "__"
        leaf_key = "bs__" + path.split("behavior_scores.", 1)[1].replace(".", "__")
        if leaf_key in m0:
            preferred = leaf_key
    keys = list(m0.keys())
    best_key = preferred if preferred in m0 else keys[0]
    best_score = -1.0
    best_dh = best_dl = 0.0
    for k in keys:
        dh = float(mh.get(k, 0)) - float(m0.get(k, 0))
        dl = float(ml.get(k, 0)) - float(m0.get(k, 0))
        score = abs(dh) + abs(dl)
        if preferred and k == preferred:
            score += 1e-6
        if score > best_score:
            best_score, best_key, best_dh, best_dl = score, k, dh, dl
    return best_key, best_dh, best_dl


def align_cfg_for_path(cfg: dict, path: str) -> dict:
    for level in ("high", "medium", "low"):
        if f".discipline_params.{level}." in path:
            cfg["simulation"]["subject"]["self_discipline"] = level
            break
    return cfg


def run_sweep(
    days_health: int = 30,
    config_path: Optional[str | Path] = None,
    ui_only: bool = True,
) -> Tuple[List[SweepRow], List[dict], dict]:
    """Sweep ↑/↓ for every leaf in the given mechanism JSON (default: active.json)."""
    del days_health  # reserved; health probe uses its own default
    reset_mechanism_config()
    cfg_path = Path(config_path) if config_path else DEFAULT_ACTIVE_PATH
    base = load_mechanism_config(str(cfg_path))
    source_meta = {
        "config_path": str(cfg_path),
        "version_id": (base.get("meta") or {}).get("version_id"),
        "name": (base.get("meta") or {}).get("name"),
    }
    leaves = flatten_leaves(base)
    rows: List[SweepRow] = []
    skipped: List[dict] = []

    for path, value in leaves:
        if not path.startswith(("simulation.", "management.")):
            continue
        if ui_only and path not in UI_TUNABLE_JSON_PATHS:
            skipped.append({"path": path, "baseline": value, "reason": "非界面22项白名单"})
            continue
        reason = should_skip(path, value)
        if reason:
            skipped.append({"path": path, "baseline": value, "reason": reason})
            continue

        probe_fn = select_probe(path)
        probe_name = probe_fn.__name__

        if isinstance(value, str):
            pair = subject_hi_lo(path, value)
            if not pair:
                skipped.append({"path": path, "baseline": value, "reason": "无枚举升降"})
                continue
            hi_v, lo_v = pair
        else:
            pair = algebraic_hi_lo(value)
            if not pair:
                skipped.append({"path": path, "baseline": value, "reason": "无法升降"})
                continue
            hi_v, lo_v = pair

        cfg0 = align_cfg_for_path(copy.deepcopy(base), path)
        cfg_hi = align_cfg_for_path(copy.deepcopy(base), path)
        cfg_lo = align_cfg_for_path(copy.deepcopy(base), path)
        try:
            set_by_path(cfg_hi, path, hi_v)
            set_by_path(cfg_lo, path, lo_v)
        except Exception as e:
            skipped.append({"path": path, "baseline": value, "reason": f"写入失败: {e}"})
            continue

        try:
            m0 = probe_fn(cfg0)
            mh = probe_fn(cfg_hi)
            ml = probe_fn(cfg_lo)
        except Exception as e:
            skipped.append({"path": path, "baseline": value, "reason": f"探针失败: {e}"})
            reset_mechanism_config()
            continue

        metric, dh, dl = pick_metric_and_deltas(probe_fn, path, m0, mh, ml)
        rows.append(
            SweepRow(
                path=path,
                baseline=value,
                high=hi_v,
                low=lo_v,
                probe=probe_name,
                metric=metric,
                baseline_metrics=m0,
                high_metrics=mh,
                low_metrics=ml,
                delta_high=round(dh, 4),
                delta_low=round(dl, 4),
                effect_when_up=effect_label(dh),
                effect_when_down=effect_label(dl),
            )
        )
        reset_mechanism_config()

    reset_mechanism_config()
    return rows, skipped, source_meta



MODULE_TITLES = {
    "simulation.subject": "主体属性",
    "simulation.health": "健康分",
    "simulation.relapse": "复发",
    "simulation.mood": "心情",
    "simulation.compliance": "遵从/抵抗",
    "simulation.behavior_scores": "行为分项",
    "simulation.habit": "习惯 streak",
    "simulation.satisfaction": "满意度",
    "simulation.composite": "综合评估",
    "management.intervention": "干预等级",
    "management.tidal": "潮汐松紧",
    "management.relationship_phases": "关系阶段",
    "management.trust_capital": "信任资本",
    "management.habit_consolidation": "习惯巩固",
    "management.manager_learning": "管理者学习",
    "management.over_intervention": "过管保护",
    "management.reflection": "反思周期",
}


def _module_key(path: str) -> str:
    parts = path.split(".")
    return ".".join(parts[:2])


METRIC_ZH = {
    "health_mean": "健康分日均",
    "health_final": "期末健康分",
    "health_min": "期间最低健康分",
    "days_below_warning": "低于警戒线天数",
    "relapse_p_day0": "刚放松时复发概率",
    "relapse_p_day9": "放松第9天复发概率",
    "mood_under_pressure": "高压干预下心情分",
    "satisfaction": "满意度",
    "accept_rate": "劝说接受率",
    "effective_resistance": "有效抵抗程度",
    "tidal_mean_level": "平均干预等级",
    "tidal_mean_trust": "平均信任度",
    "tidal_first_relax_day": "首次进入放松的天数",
    "tidal_final_level": "期末干预等级",
    "trust_capital": "信任资本余额",
    "autonomy": "自主档位（数值化）",
    "habit_stage_score": "习惯内化阶段",
    "habit_stage_name_ord": "习惯内化阶段",
    "streak_after_5_good": "连续好天后的 streak",
    "relapse_p_after_streak": "有 streak 时的复发概率",
    "relapse_p_after_bad_tendency": "坏倾向下的复发概率",
    "mgr_understanding": "管理者理解度",
    "mgr_efficiency": "管理者干预效率",
    "over_interv_force_hits": "触发强制松管次数",
    "composite": "综合评分",
    "rating_ord": "综合评级档位",
    "food_high_sugar_diabetes": "高糖饮食·糖尿病分项",
}


SIM_MEANING = {
    "health_mean": ("健康轨迹整体更好", "健康轨迹整体更差"),
    "health_final": ("期末更健康", "期末更差"),
    "health_min": ("最差那天仍更高（更抗砸）", "谷底更深（更易崩）"),
    "days_below_warning": ("更多天处于危险区", "更少天处于危险区"),
    "relapse_p_day0": ("一放松就更容易复发", "一放松也不易复发"),
    "relapse_p_day9": ("放松越久越容易复发", "长时间放松也较稳"),
    "mood_under_pressure": ("被强管时心情更好", "被强管时心情更差"),
    "satisfaction": ("对管理更满意", "对管理更不满"),
    "accept_rate": ("更听劝", "更不听劝"),
    "effective_resistance": ("更难被说服/移除", "更容易被说服/移除"),
    "tidal_mean_level": ("整体管得更严", "整体管得更松"),
    "tidal_mean_trust": ("信任积累更高", "信任更低"),
    "tidal_first_relax_day": ("更晚才放手", "更早放手"),
    "tidal_final_level": ("期末仍更严", "期末更松"),
    "trust_capital": ("信任资本更高（更敢给自主）", "信任资本更低（更易严管）"),
    "autonomy": ("自主档更高", "自主档更低"),
    "habit_stage_score": ("内化阶段更高", "内化阶段更低"),
    "streak_after_5_good": ("习惯连续天数涨得更快", "习惯连续天数涨得更慢"),
    "relapse_p_after_streak": ("即便有习惯仍更易复发", "习惯更能压住复发"),
    "mgr_understanding": ("管理者学得更快/更懂", "管理者更慢理解对方"),
    "mgr_efficiency": ("干预效率更高", "干预效率更低"),
    "over_interv_force_hits": ("更容易触发强制松管", "更难触发强制松管"),
    "composite": ("卷面综合分更高", "卷面综合分更低"),
    "rating_ord": ("评级档位更高", "评级档位更低"),
}


def metric_label(metric: str) -> str:
    if metric in METRIC_ZH:
        return METRIC_ZH[metric]
    if metric.startswith("bs__"):
        return "行为分项「" + metric.replace("bs__", "").replace("__", ".") + "」"
    return metric


def impact_on_sim(metric: str, delta: float, baseline: Any, new_val: Any) -> str:
    """Human-readable: what happens to the simulation side when param moves."""
    label = metric_label(metric)
    if abs(delta) < 1e-4:
        return f"对「{label}」几乎无影响（本探针下）"
    meaning = SIM_MEANING.get(metric)
    if metric.startswith("bs__"):
        # 行为分项：分数代数升高=该项记分更宽；降低=更严
        if delta > 0:
            return f"该类行为记分变宽（分项 {baseline}→{new_val}，Δ{delta:+}）→ 同类行为对健康叙事更「便宜」"
        return f"该类行为记分变严（分项 {baseline}→{new_val}，Δ{delta:+}）→ 同类行为扣/加更狠"
    if delta > 0:
        gloss = meaning[0] if meaning else f"「{label}」升高"
        return f"{gloss}（{label} {baseline}→{new_val}，Δ{delta:+}）"
    gloss = meaning[1] if meaning else f"「{label}」降低"
    return f"{gloss}（{label} {baseline}→{new_val}，Δ{delta:+}）"


def rows_to_jsonable(rows: List[SweepRow]) -> List[dict]:
    out = []
    for r in rows:
        b = r.baseline_metrics.get(r.metric)
        h = r.high_metrics.get(r.metric)
        lo = r.low_metrics.get(r.metric)
        up_txt = impact_on_sim(r.metric, r.delta_high, b, h)
        down_txt = impact_on_sim(r.metric, r.delta_low, b, lo)
        out.append(
            {
                "path": r.path,
                "baseline": r.baseline,
                "high": r.high,
                "low": r.low,
                "probe": r.probe,
                "metric": r.metric,
                "metric_zh": metric_label(r.metric),
                "baseline_value": b,
                "high_value": h,
                "low_value": lo,
                "delta_high": r.delta_high,
                "delta_low": r.delta_low,
                "effect_when_up": r.effect_when_up,
                "effect_when_down": r.effect_when_down,
                "impact_up": up_txt,
                "impact_down": down_txt,
                "name_zh": describe_param(r.path)[0],
                "explain": describe_param(r.path)[1],
                "verified": r.verified,
                "all_metrics_baseline": r.baseline_metrics,
                "all_metrics_high": r.high_metrics,
                "all_metrics_low": r.low_metrics,
            }
        )
    return out


def render_presentation_md(rows: List[SweepRow], skipped: List[dict], meta: dict) -> str:
    """逐参数：升高/降低后对模拟的影响（不强调「显著个数」）。"""
    lines: List[str] = []
    lines.append("# 机制参数对模拟的影响（逐项实测）")
    lines.append("")
    lines.append(
        "> **读法**：下面不是「哪些参数显著」，而是 **每一个参数** 升高或降低后，"
        "仿真里对应侧面会怎样变。数据来自 `tools/param_impact_sweep.py`（机制层对照，无 LLM）。"
    )
    lines.append("")
    lines.append("## 怎么读每一行")
    lines.append("")
    lines.append("| 列 | 含义 |")
    lines.append("|----|------|")
    lines.append("| 参数 | JSON 路径 |")
    lines.append("| 观察侧面 | 探针盯住的模拟量（健康/复发/心情/潮汐等） |")
    lines.append("| 升高时 | 把该参数代数调大后，模拟如何变 |")
    lines.append("| 降低时 | 把该参数代数调小后，模拟如何变 |")
    lines.append("")
    lines.append(
        f"共实测 **{meta['verified_count']}** 个可升降叶子；"
        f"跳过 {meta['skipped_count']} 个非数值项；"
        f"健康探针 {meta['health_days']} 天；"
        f"生成于 {meta['generated_at']}；"
        f"原始数据 [`{meta['json_path']}`](./param_impact/sweep_results.json)。"
    )
    lines.append("")

    groups: Dict[str, List[SweepRow]] = {}
    for r in rows:
        groups.setdefault(_module_key(r.path), []).append(r)

    MODULE_ORDER = [
        "simulation.subject",
        "simulation.health",
        "simulation.relapse",
        "simulation.mood",
        "simulation.compliance",
        "simulation.habit",
        "simulation.satisfaction",
        "simulation.behavior_scores",
        "simulation.composite",
        "management.intervention",
        "management.tidal",
        "management.relationship_phases",
        "management.trust_capital",
        "management.habit_consolidation",
        "management.manager_learning",
        "management.over_intervention",
        "management.reflection",
    ]

    def _sort_key(k: str) -> tuple:
        try:
            return (0, MODULE_ORDER.index(k))
        except ValueError:
            return (1, k)

    for key in sorted(groups.keys(), key=_sort_key):
        title = MODULE_TITLES.get(key, key)
        chunk = groups[key]
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| 参数 | 观察侧面 | 升高时对模拟的影响 | 降低时对模拟的影响 |")
        lines.append("|------|----------|--------------------|--------------------|")
        for r in chunk:
            b = r.baseline_metrics.get(r.metric)
            h = r.high_metrics.get(r.metric)
            lo = r.low_metrics.get(r.metric)
            up_txt = impact_on_sim(r.metric, r.delta_high, b, h)
            down_txt = impact_on_sim(r.metric, r.delta_low, b, lo)
            lines.append(
                f"| `{r.path}` | {metric_label(r.metric)} | {up_txt} | {down_txt} |"
            )
        lines.append("")

    if skipped:
        lines.append("## 未做升降的项")
        lines.append("")
        lines.append("| 路径 | 原因 |")
        lines.append("|------|------|")
        for s in skipped:
            lines.append(f"| `{s['path']}` | {s['reason']} |")
        lines.append("")

    lines.append("## 复现")
    lines.append("")
    lines.append("```bash")
    lines.append("cd generative_agents")
    lines.append("python3 tools/param_impact_sweep.py --out-dir ../docs/mechanism/param_impact")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _short(v: Any, n: int = 48) -> str:
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= n else s[: n - 1] + "…"


def write_canvas_tsx(results: List[dict], meta: dict, canvas_path: Path) -> None:
    """Embed full per-param impact tables into a Cursor canvas."""
    MODULE_ORDER = [
        "simulation.subject",
        "simulation.health",
        "simulation.relapse",
        "simulation.mood",
        "simulation.compliance",
        "simulation.habit",
        "simulation.satisfaction",
        "simulation.behavior_scores",
        "simulation.composite",
        "management.intervention",
        "management.tidal",
        "management.relationship_phases",
        "management.trust_capital",
        "management.habit_consolidation",
        "management.manager_learning",
        "management.over_intervention",
        "management.reflection",
    ]
    groups: Dict[str, List[dict]] = {}
    for r in results:
        groups.setdefault(_module_key(r["path"]), []).append(r)

    modules_js = []
    for key in MODULE_ORDER:
        if key not in groups:
            continue
        title = MODULE_TITLES.get(key, key)
        rows_js = []
        for r in groups[key]:
            name_zh, explain = describe_param(r["path"])
            rows_js.append(
                {
                    "path": r["path"],
                    "nameZh": name_zh,
                    "explain": explain,
                    "side": r.get("metric_zh") or metric_label(r["metric"]),
                    "up": r.get("impact_up") or "",
                    "down": r.get("impact_down") or "",
                }
            )
        modules_js.append({"id": key, "title": f"{title}（{len(rows_js)}）", "rows": rows_js})

    for key, chunk in groups.items():
        if key in MODULE_ORDER:
            continue
        rows_js = []
        for r in chunk:
            name_zh, explain = describe_param(r["path"])
            rows_js.append(
                {
                    "path": r["path"],
                    "nameZh": name_zh,
                    "explain": explain,
                    "side": r.get("metric_zh") or metric_label(r["metric"]),
                    "up": r.get("impact_up") or "",
                    "down": r.get("impact_down") or "",
                }
            )
        modules_js.append(
            {
                "id": key,
                "title": f"{MODULE_TITLES.get(key, key)}（{len(rows_js)}）",
                "rows": rows_js,
            }
        )

    data_literal = json.dumps(modules_js, ensure_ascii=False, indent=2)
    meta_literal = json.dumps(
        {
            "source": meta.get("config_path", "active.json"),
            "version_id": meta.get("version_id"),
            "verified": meta.get("verified_count"),
            "skipped": meta.get("skipped_count"),
            "health_days": meta.get("health_days"),
            "generated_at": meta.get("generated_at"),
        },
        ensure_ascii=False,
        indent=2,
    )

    tsx = f"""import {{
  Callout,
  Card,
  CardBody,
  CardHeader,
  H1,
  Select,
  Stack,
  Table,
  Text,
  useCanvasState,
}} from "cursor/canvas";

/**
 * Auto-generated by tools/param_impact_sweep.py — do not hand-edit.
 * Source: active.json full ↑/↓ mechanism-layer sims.
 */

type ImpactRow = {{ path: string; nameZh: string; explain: string; side: string; up: string; down: string }};
type Module = {{ id: string; title: string; rows: ImpactRow[] }};

const META = {meta_literal} as const;

const MODULES: Module[] = {data_literal};

export default function ParamImpactActiveJson() {{
  const [mod, setMod] = useCanvasState("module", MODULES[0]?.id ?? "");
  const current = MODULES.find((m) => m.id === mod) ?? MODULES[0];

  return (
    <Stack gap={{20}}>
      <Stack gap={{6}}>
        <H1>active.json 参数对模拟的影响</H1>
        <Text tone="secondary">
          配置 {{META.source}} · version {{META.version_id ?? "—"}} · 实测 {{META.verified}} 项 ·
          跳过 {{META.skipped}} · 健康探针 {{META.health_days}} 天 · {{META.generated_at}}
        </Text>
      </Stack>

      <Callout tone="info" title="读法">
        每行含中文名与含义说明；右侧为升高/降低后仿真如何变。覆盖 active.json 全部可升降叶子。
      </Callout>

      <Select
        value={{mod}}
        onChange={{setMod}}
        options={{MODULES.map((m) => ({{ label: m.title, value: m.id }}))}}
      />

      <Card>
        <CardHeader>{{current?.title}}</CardHeader>
        <CardBody>
          <Table
            headers={{["中文名", "参数", "说明", "观察侧面", "升高时", "降低时"]}}
            rows={{(current?.rows ?? []).map((r) => [
              r.nameZh,
              r.path,
              r.explain,
              r.side,
              r.up,
              r.down,
            ])}}
          />
        </CardBody>
      </Card>

      <Text tone="secondary" size="small">
        复现：cd generative_agents && python3 tools/param_impact_sweep.py --config data/mechanism/active.json
      </Text>
    </Stack>
  );
}}
"""
    canvas_path.parent.mkdir(parents=True, exist_ok=True)
    canvas_path.write_text(tsx, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        default=str(ROOT.parent / "docs" / "mechanism" / "param_impact"),
    )
    parser.add_argument("--health-days", type=int, default=30)
    parser.add_argument(
        "--config",
        default=str(DEFAULT_ACTIVE_PATH),
        help="Mechanism JSON to sweep (default: active.json)",
    )
    parser.add_argument(
        "--all-params",
        action="store_true",
        help="扫 active.json 全部叶子（默认仅界面可调 22 项映射路径）",
    )
    parser.add_argument(
        "--canvas",
        default=str(
            Path.home()
            / ".cursor"
            / "projects"
            / "Users-dongtingxiao-Desktop-generative-agent-visualize"
            / "canvases"
            / "param-impact-sweep.canvas.tsx"
        ),
    )
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running parameter impact sweep on {args.config} …")
    rows, skipped, source_meta = run_sweep(
        days_health=args.health_days,
        config_path=args.config,
        ui_only=not args.all_params,
    )
    from datetime import datetime, timezone

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    results = rows_to_jsonable(rows)
    payload = {
        "meta": {
            "health_days": args.health_days,
            "verified_count": len(rows),
            "skipped_count": len(skipped),
            "note": "mechanism-layer simulation; no LLM",
            "config_path": source_meta.get("config_path"),
            "version_id": source_meta.get("version_id"),
            "name": source_meta.get("name"),
            "generated_at": generated_at,
        },
        "results": results,
        "skipped": skipped,
    }
    json_path = out_dir / "sweep_results.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    meta = {
        "verified_count": len(rows),
        "skipped_count": len(skipped),
        "health_days": args.health_days,
        "generated_at": generated_at,
        "json_path": "docs/mechanism/param_impact/sweep_results.json",
        "config_path": source_meta.get("config_path"),
        "version_id": source_meta.get("version_id"),
    }

    md = render_presentation_md(rows, skipped, meta)
    # prepend active.json note
    md = md.replace(
        "# 机制参数对模拟的影响（逐项实测）",
        "# 机制参数对模拟的影响（逐项实测 · active.json）",
        1,
    )
    docs_path = ROOT.parent / "docs" / "mechanism" / "机制参数升降影响手册.md"
    docs_path.write_text(md, encoding="utf-8")

    canvas_path = Path(args.canvas)
    write_canvas_tsx(results, meta, canvas_path)

    print(f"OK verified={len(rows)} skipped={len(skipped)} source={source_meta.get('config_path')}")
    print(f"JSON: {json_path}")
    print(f"DOC:  {docs_path}")
    print(f"CANVAS: {canvas_path}")



if __name__ == "__main__":
    main()
