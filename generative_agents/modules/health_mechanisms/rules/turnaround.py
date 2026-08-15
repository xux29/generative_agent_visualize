"""Turnaround (折返) and same-day intervention level capping."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from modules.health_mechanisms.rules.env_block import describe_env_constraints

LOCATION_DESC_MAP = {
    "kitchen": "厨房",
    "kitchen_door": "厨房门口",
    "snacks_area": "零食柜",
    "phone_area": "手机放置处",
    "bedroom": "卧室",
    "living_room": "客厅",
}


def turnaround_template(
    target_location: str,
    block_reason: str,
    manager_name: str = "管理者",
) -> Dict[str, str]:
    """折返模板（LLM 失败时使用）。"""
    templates = {
        "kitchen_door": {
            "turnaround_monologue": (
                f"走到厨房门口发现{block_reason}，看来暂时进不去了。只能去客厅待会儿。"
            ),
            "redirect_activity": "去客厅看电视",
            "redirect_location": "living_room",
            "emotional_reaction": "resigned",
        },
        "kitchen": {
            "turnaround_monologue": (
                f"到厨房想找点吃的，结果{block_reason}。"
                f"估计是{manager_name}把食物拿走了，那就在厨房找找别的。"
            ),
            "redirect_activity": "在厨房找其他食物",
            "redirect_location": "kitchen",
            "emotional_reaction": "frustrated",
        },
        "phone_area": {
            "turnaround_monologue": (
                f"想玩会儿手机，找了半天发现{block_reason}。"
                f"肯定是{manager_name}把手机收走了，那就休息吧。"
            ),
            "redirect_activity": "躺下休息",
            "redirect_location": "bedroom",
            "emotional_reaction": "resigned",
        },
    }
    return templates.get(
        target_location,
        {
            "turnaround_monologue": f"想做的事被阻止了：{block_reason}。算了，去客厅待着吧。",
            "redirect_activity": "去客厅",
            "redirect_location": "living_room",
            "emotional_reaction": "resigned",
        },
    )


def generate_turnaround(
    intention,
    target_location: str,
    block_reason: str,
    env_state: dict,
    *,
    blocked_location: Optional[str] = None,
    manager_name: str = "管理者",
    self_discipline: str = "medium",
    completion_fn: Optional[Callable[..., Any]] = None,
    logger=None,
) -> Dict[str, str]:
    """生成折返独白与替代活动（优先 LLM，失败则模板）。"""
    location_key = blocked_location or target_location
    target_location_desc = LOCATION_DESC_MAP.get(location_key, location_key)
    env_constraints_str = describe_env_constraints(env_state)

    if completion_fn is None:
        return turnaround_template(location_key, block_reason, manager_name)

    try:
        output = completion_fn(
            "health_generate_turnaround",
            original_activity=intention.activity,
            target_location_desc=target_location_desc,
            block_reason=block_reason,
            environment_constraints=env_constraints_str,
            self_discipline=self_discipline,
        )
        if isinstance(output, dict):
            if "res" in output:
                return output["res"]
            return output
        return turnaround_template(location_key, block_reason, manager_name)
    except Exception as e:
        if logger is not None:
            logger.warning(f"折返生成失败: {e}，使用模板")
        return turnaround_template(location_key, block_reason, manager_name)


def adjust_intervention_for_day(strategy, level2_used: bool, level3_used: bool):
    """确保当天高阶干预不重复（L2/L3 用过后降级为劝说）。"""
    if not strategy:
        return strategy
    if level3_used and strategy.level >= 2:
        strategy.level = 1
        strategy.action = "persuade"
        strategy.reason = f"{strategy.reason}（当天已执行过L4，降级为劝说）"
        return strategy
    if level2_used and strategy.level == 2:
        strategy.level = 1
        strategy.action = "persuade"
        strategy.reason = f"{strategy.reason}（当天已执行过L3，降级为劝说）"
        return strategy
    return strategy
