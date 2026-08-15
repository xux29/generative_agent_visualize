"""Environment block checks (kitchen lock / food / phone removed)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def check_env_blocked(
    target_location: Optional[str],
    env_state: Dict[str, Any],
) -> Tuple[bool, Optional[str], Optional[str]]:
    """检查目标位置是否被环境状态阻止。

    Returns:
        (is_blocked, block_reason, blocked_at_location)
    """
    if not target_location:
        return False, None, None

    if target_location == "kitchen" and env_state.get("kitchen_locked", False):
        return True, "厨房门被锁了", "kitchen_door"

    if target_location == "kitchen" and env_state.get("food_removed", False):
        return True, "厨房里没有可吃的东西", "kitchen"

    if target_location == "phone_area" and env_state.get("phone_removed", False):
        return True, "手机已被没收", "phone_area"

    return False, None, None


def describe_env_constraints(env_state: Dict[str, Any]) -> str:
    """环境约束中文摘要（供折返 prompt 使用）。"""
    constraints = []
    if env_state.get("kitchen_locked"):
        constraints.append("厨房已被锁定")
    if env_state.get("food_removed"):
        constraints.append("厨房食物已被移除")
    if env_state.get("phone_removed"):
        constraints.append("手机已被没收")
    return "；".join(constraints) if constraints else "无"
