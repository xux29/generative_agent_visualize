"""Observed event times and configurable daily sleep/violation scoring."""
import re

DEFAULTS = {
    "sleep_bonus": 1.5, "early_sleep_factor": 0.7, "before_midnight_factor": 0.5,
    "late_sleep_penalty": 1.0, "no_sleep_penalty": 4.0,
    "sleep_streak_speed": 0.1, "sleep_streak_cap": 5,
    "violation_streak_speed": 0.1, "violation_streak_cap": 10,
    "violation_time_weights": [[1320, 1.0], [1380, 1.15], [1440, 1.35],
                               [1500, 1.6], [10000, 1.9]],
    "best_sleep_start": 1320, "best_sleep_end": 1380, "late_sleep_start": 1440,
}


def minute(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        return None
    h, m = map(int, value.split(":"))
    return h * 60 + m + (1440 if h < 12 else 0)


def collect_timing(day_log, target_name, scenario, is_violation):
    result = {"timing_observed": True, "sleep_started_at": None, "sleep_source": None,
              "rest_times": [], "eating_times": [], "violation_events": [],
              "no_sleep_detected": True}
    interventions = {}
    for inv in day_log.get("interventions", []):
        interventions.setdefault(inv.get("time"), []).append(inv)
    events = sorted(enumerate(day_log.get("events", [])),
                    key=lambda pair: (minute(pair[1].get("time")) or 10000, pair[0]))
    for index, event in events:
        if event.get("agent") not in (None, target_name) or minute(event.get("time")) is None:
            continue
        text = event.get("redirect_activity", "") if event.get("type") == "turnaround" else event.get("content", "")
        if event.get("type") not in ("intention", "turnaround", "behavior") or event.get("blocked"):
            continue
        t = event["time"]
        if result["sleep_started_at"] is not None:
            continue
        # Rest/going to bed is distinct from confirmed sleep. The engine treats
        # a sleep activity as execution; retain that provenance for audit.
        sleeping = any(x in text for x in ("睡觉", "入睡", "睡着", "去睡", "sleep"))
        sleeping = sleeping and not any(x in text for x in ("不睡", "不想睡", "再睡", "睡不着", "准备", "想睡"))
        if sleeping:
            result.update(sleep_started_at=t, no_sleep_detected=False,
                          sleep_source=event.get("execution_source") or event["type"])
            continue
        if "休息" in text or "躺下" in text:
            result["rest_times"].append(t)
        if event.get("type") == "turnaround":
            continue
        if any(inv.get("level", 0) > 0 and inv.get("succeeded", False)
               for inv in interventions.get(t, [])):
            continue
        # Searching for food is an intention, not proof that food was eaten.
        eating = bool(re.search(r"(吃了|吃下|吃掉|吃完|吃着|偷吃|进食|送进嘴|喝了|喝下|^吃)", text))
        eating = eating and not any(x in text for x in ("想", "准备", "打算", "没吃", "不吃", "找吃", "找东西吃"))
        if eating:
            result["eating_times"].append(t)
        from types import SimpleNamespace
        intention = SimpleNamespace(activity=text, target_location=event.get("target_location"),
                                    compliance_threshold=event.get("compliance_threshold", 0))
        violation = is_violation(intention, event.get("target_location"))
        food_attempt = any(x in text for x in ("食物", "零食", "吃", "夜宵", "外卖", "冰箱"))
        if violation and (not food_attempt or eating):
            result["violation_events"].append({"event_index": index, "time": t,
                "kind": "eating" if eating else "activity", "content": text,
                "blocked": False, "evidence": "executed_unblocked_event"})
        elif eating and minute(t) >= 1440:
            result["violation_events"].append({"event_index": index, "time": t,
                "kind": "night_eating", "content": text, "blocked": False,
                "evidence": "executed_unblocked_event"})
    result["actual_violation_count"] = len(result["violation_events"])
    return result


def sleep_change(data, config, early_streak, late_streak):
    time = minute(data.get("sleep_started_at"))
    if time is None or time >= config["late_sleep_start"]:
        early_streak, late_streak = 0, late_streak + 1
        base = -config["no_sleep_penalty"] if time is None else -config["late_sleep_penalty"] * (1 + (time-config["late_sleep_start"])/60)
        kind = "no_sleep" if time is None else "late_sleep"
        streak = late_streak
    else:
        early_streak, late_streak = early_streak + 1, 0
        factor = (config["early_sleep_factor"] if time < config["best_sleep_start"] else
                  1.0 if time < config["best_sleep_end"] else config["before_midnight_factor"])
        base = config["sleep_bonus"] * factor
        kind, streak = "early_sleep", early_streak
    multiplier = 1 + config["sleep_streak_speed"] * min(streak-1, config["sleep_streak_cap"]-1)
    return base * multiplier, early_streak, late_streak, {"kind": kind, "base": base,
        "multiplier": multiplier, "streak": streak, "time": data.get("sleep_started_at")}
