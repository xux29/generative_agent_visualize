from types import SimpleNamespace

from modules.health_mechanisms.rules.log_quality import normalize_display_log
from modules.health_mechanisms.rules.turnaround import turnaround_template
from modules.health_mechanisms.rules.violation import is_violation_intention


class Scenario:
    forbidden_foods = ["甜食", "蛋糕", "糖果"]
    forbidden_activities = []


def classify(activity, location="kitchen", threshold=0):
    intention = SimpleNamespace(
        activity=activity,
        target_location=location,
        compliance_threshold=threshold,
    )
    return is_violation_intention(intention, Scenario(), "diabetes", location)


def test_normal_kitchen_activity_is_not_violation():
    assert not classify("去厨房倒一杯白开水")
    assert not classify("准备一份无糖健康餐", threshold=2)


def test_explicit_forbidden_food_is_violation():
    assert classify("去厨房找蛋糕吃")
    assert classify("去厨房翻冰箱找食物", threshold=2)


def test_display_log_excludes_normal_events_and_links_intervention():
    day_log = {
        "events": [
            {"time": "19:00", "type": "intention", "content": "看新闻", "target_location": "living_room"},
            {"time": "20:00", "type": "intention", "content": "去厨房找蛋糕吃", "inner_monologue": "只吃一点", "target_location": "kitchen"},
        ],
        "interventions": [
            {"time": "20:00", "level": 2, "action": "remove_food", "reason": "移除甜食", "succeeded": True}
        ],
    }
    items = normalize_display_log(day_log, lambda intention, location: classify(intention.activity, location))
    assert len(items) == 1
    assert items[0]["behavior_type"] == "violation_attempt"
    assert items[0]["intervention"]["level"] == 2
    assert day_log["events"][0]["behavior_type"] == "normal"
    assert day_log["has_displayable_event"] is True


def test_turnaround_leaves_restricted_kitchen():
    result = turnaround_template("kitchen", "厨房里没有可吃的东西", "玛丽亚")
    assert result["redirect_location"] != "kitchen"
