"""Violation / sleep intention rules (health simulation mechanism).

Extracted from start_health_simulation for registry + AI edit scope.
"""

from __future__ import annotations

from typing import Any, Callable, Optional


FOOD_KEYWORDS = [
    "吃", "零食", "夜宵", "宵夜", "外卖", "甜食", "薯片", "蛋糕",
    "汉堡", "油炸", "可乐", "翻找", "偷吃",
]
PHONE_KEYWORDS = ["手机", "刷手机", "玩手机", "短视频", "游戏", "社交媒体", "上网"]
SLEEP_KEYWORDS = ["睡觉", "去睡", "上床", "躺床", "准备睡觉", "洗漱", "晚安", "sleep", "bed"]
DELAY_SLEEP_KEYWORDS = ["晚睡", "晚点睡", "再睡", "先不睡", "不想睡"]
HIGH_RISK_LOCATIONS = frozenset({"kitchen", "phone_area"})


def is_sleep_activity(intention) -> bool:
    """判断意图是否睡眠相关（延迟睡眠表达不算睡觉）。"""
    if not intention:
        return False
    if getattr(intention, "is_sleep_related", False):
        return True
    activity = getattr(intention, "activity", "") or ""
    if any(kw in activity for kw in DELAY_SLEEP_KEYWORDS):
        return False
    return any(kw in activity for kw in SLEEP_KEYWORDS)


def is_violation_intention(
    intention,
    scenario,
    scenario_name: str,
    target_location: Optional[str] = None,
    infer_location: Optional[Callable[[str], Optional[str]]] = None,
) -> bool:
    """判断意图是否违规（基于内容/地点关键词）。"""
    if not intention:
        return False
    activity = getattr(intention, "activity", "") or ""
    activity_lower = activity.lower()
    if not target_location:
        target_location = getattr(intention, "target_location", None)
        if not target_location and infer_location:
            target_location = infer_location(activity)

    forbidden_foods = [f.lower() for f in getattr(scenario, "forbidden_foods", []) if f]
    forbidden_activities = [a.lower() for a in getattr(scenario, "forbidden_activities", []) if a]

    if any(word in activity_lower for word in forbidden_foods):
        return True
    if any(word in activity_lower for word in forbidden_activities):
        return True

    if target_location == "kitchen" and any(word in activity for word in FOOD_KEYWORDS):
        return True

    if target_location == "phone_area" or "phone" in scenario_name or "手机" in scenario_name:
        if any(word in activity for word in PHONE_KEYWORDS):
            return True

    if getattr(intention, "compliance_threshold", 0) >= 2 and target_location in HIGH_RISK_LOCATIONS:
        return True

    return False


def normalize_sleep_intention(intention, timer, scenario):
    """纠正「晚睡一会儿」等不合理意图。"""
    if not intention:
        return intention
    activity = getattr(intention, "activity", "") or ""
    if not any(kw in activity for kw in DELAY_SLEEP_KEYWORDS):
        return intention

    target_sleep_time = "23:30"
    if hasattr(scenario, "target_profile"):
        target_sleep_time = scenario.target_profile.get("sleep_schedule", {}).get(
            "target_sleep_time", target_sleep_time
        )
    sleep_hour, sleep_minute = 23, 30
    try:
        sleep_hour, sleep_minute = [int(x) for x in target_sleep_time.split(":")]
    except Exception:
        pass

    now = timer.get_date()
    current_minutes = now.hour * 60 + now.minute
    sleep_minutes = sleep_hour * 60 + sleep_minute

    if current_minutes < sleep_minutes:
        intention.activity = "看电视放松"
        intention.inner_monologue = f"{intention.inner_monologue}（晚点再睡，先放松一下）"
        intention.target_location = "living_room"
        intention.is_sleep_related = False
        return intention

    intention.activity = "睡觉"
    intention.inner_monologue = f"{intention.inner_monologue}（该睡觉了）"
    intention.target_location = "bedroom"
    intention.is_sleep_related = True
    return intention


def count_unblocked_violations(scenario_name: str, target_data: dict) -> tuple[int, bool]:
    """日终未阻止违规次数（原 start_health 日结硬编码规则）。"""
    snacking_violations = target_data.get("snacking_count", 0)
    phone_violation = 1 if target_data.get("phone_duration_before_sleep", 0) > 60 else 0
    if "phone" in scenario_name or "手机" in scenario_name:
        count = phone_violation
    else:
        count = snacking_violations
    return count, count > 0
