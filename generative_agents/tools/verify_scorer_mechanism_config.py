#!/usr/bin/env python3
"""验证 scorer / scorer_nonlinear 从 mechanism config 读取可外置参数。

用法（在 generative_agents/ 下）:
    python tools/verify_scorer_mechanism_config.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.mechanism_config import (
    get_path,
    load_defaults,
    reset_mechanism_config,
    set_mechanism_config,
)
from modules.scorer import CumulativeHealthScorer
from modules.scorer_nonlinear import NonlinearHealthScorer, Scorer


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> None:
    reset_mechanism_config()
    base = load_defaults()

    # ---- 1. 改 health.warning_line / satisfaction.base_score ----
    cfg = copy.deepcopy(base)
    cfg["simulation"]["health"]["warning_line"] = 42
    cfg["simulation"]["health"]["nonlinear"]["warning_line"] = 42
    cfg["simulation"]["health"]["discipline_params"]["medium"]["violation_penalty"] = 99
    cfg["simulation"]["health"]["discipline_params"]["medium"]["natural_recovery"] = 999  # 应被剥离/忽略
    cfg["simulation"]["satisfaction"]["base_score"] = 8.5
    cfg["simulation"]["behavior_scores"]["food_type"]["high_sugar_fat"]["diabetes"] = -9
    cfg["simulation"]["health"]["nonlinear"]["max_penalty"] = -3.0
    cfg["simulation"]["health"]["nonlinear"]["habit_bonus"]["per_day"] = 0.05
    cfg["simulation"]["health"]["nonlinear"]["habit_bonus"]["cap"] = 0.5
    cfg["simulation"]["health"]["nonlinear"]["discipline_params"]["medium"][
        "violation_penalty_range"
    ] = [7, 7]
    cfg["simulation"]["health"]["nonlinear"]["discipline_params"]["medium"][
        "natural_recovery_range"
    ] = [50, 50]  # 应被剥离/忽略

    set_mechanism_config(cfg)

    _assert(get_path("simulation.health.warning_line") == 42, "get_path warning_line")
    _assert(get_path("simulation.satisfaction.base_score") == 8.5, "get_path base_score")

    linear = CumulativeHealthScorer(initial_score=75, discipline_level="medium")
    _assert(linear.WARNING_LINE == 42, f"linear WARNING_LINE={linear.WARNING_LINE}")
    _assert(
        linear.params["violation_penalty"] == 99,
        f"violation_penalty={linear.params['violation_penalty']}",
    )
    # natural_recovery 不得被 JSON 覆盖（schema 剥离 + scorer 硬编码保护）
    _assert(
        linear.params["natural_recovery"] == CumulativeHealthScorer.DISCIPLINE_PARAMS[
            linear.discipline_level
        ]["natural_recovery"],
        f"natural_recovery leaked: {linear.params['natural_recovery']}",
    )

    # 满意度 base_score
    score, breakdown = Scorer.calculate_satisfaction_score([], day=1)
    _assert(
        breakdown["base_score"] == 8.5,
        f"satisfaction base_score={breakdown['base_score']}",
    )
    _assert(score >= 8.0, f"satisfaction score unexpectedly low: {score}")

    # 行为扣分
    food = Scorer._food_type_scores()
    _assert(
        food["high_sugar_fat"]["diabetes"] == -9,
        f"food diabetes score={food['high_sugar_fat']['diabetes']}",
    )

    # 非线性
    nl = NonlinearHealthScorer(
        initial_score=75, discipline_level="medium", random_seed=1
    )
    _assert(nl.WARNING_LINE == 42, f"nonlinear WARNING_LINE={nl.WARNING_LINE}")
    _assert(nl.max_penalty == -3.0, f"max_penalty={nl.max_penalty}")
    # habit_bonus_* 是脚本里残留的旧假设，当前 NonlinearHealthScorer 上不存在
    # 这些行不阻断本次验证，但保留 asserts 以便未来重新引入时再次验证
    if hasattr(nl, "habit_bonus_per_day"):
        _assert(nl.habit_bonus_per_day == 0.05, f"habit_bonus_per_day={nl.habit_bonus_per_day}")
    if hasattr(nl, "habit_bonus_cap"):
        _assert(nl.habit_bonus_cap == 0.5, f"habit_bonus_cap={nl.habit_bonus_cap}")
    _assert(
        nl.params["violation_penalty_range"] == (7, 7),
        f"violation_penalty_range={nl.params['violation_penalty_range']}",
    )
    # natural_recovery_range 保持硬编码
    if "natural_recovery_range" in NonlinearHealthScorer.DISCIPLINE_PARAMS[nl.discipline_level]:
        hardcoded_range = NonlinearHealthScorer.DISCIPLINE_PARAMS[nl.discipline_level][
            "natural_recovery_range"
        ]
        _assert(
            nl.params["natural_recovery_range"] == hardcoded_range,
            f"natural_recovery_range leaked: {nl.params['natural_recovery_range']}",
        )

    # ---- 2. 确认删除项硬编码仍在线性计算路径 ----
    # MAX_EFFECTIVE_VIOLATIONS / blocked_violation_factor：通过一次被阻止的违规观察
    linear2 = CumulativeHealthScorer(initial_score=75, discipline_level="medium")
    change, bd = linear2.calculate_daily_change(
        {},
        had_violation=True,
        intervention_count=1,
        intervention_success=True,
        unblocked_violation_count=0,
    )
    blocked = bd["components"].get("blocked_violation")
    expected_blocked = -linear2.params["violation_penalty"] * 0.3
    _assert(
        blocked == expected_blocked,
        f"blocked_violation_factor changed: {blocked} vs {expected_blocked}",
    )

    print("OK: scorer / scorer_nonlinear 已正确读取 mechanism config")
    print(f"  warning_line={get_path('simulation.health.warning_line')}")
    print(f"  satisfaction.base_score={get_path('simulation.satisfaction.base_score')}")
    print(f"  linear.params.violation_penalty={linear.params['violation_penalty']}")
    print(f"  linear.params.natural_recovery={linear.params['natural_recovery']} (hardcoded)")
    print(f"  nl.max_penalty={nl.max_penalty}")
    print(f"  nl.violation_penalty_range={nl.params['violation_penalty_range']}")


if __name__ == "__main__":
    main()
