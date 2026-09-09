"""Build a stable, front-end friendly violation/intervention log."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Callable


def normalize_display_log(day_log: dict, is_violation: Callable) -> list[dict]:
    """Annotate raw intentions and extract only meaningful violation events."""
    interventions = {
        item.get("time"): item
        for item in day_log.get("interventions", [])
        if item.get("time") and item.get("level", 0) > 0
    }
    display_events = []

    for event in day_log.get("events", []):
        if event.get("type") != "intention":
            continue
        intention = SimpleNamespace(
            activity=event.get("content", ""),
            compliance_threshold=event.get("compliance_threshold", 0),
            target_location=event.get("target_location"),
        )
        violation = bool(is_violation(intention, event.get("target_location")))
        event["is_violation"] = violation
        event["behavior_type"] = "normal"
        if not violation:
            continue

        intervention = interventions.get(event.get("time"))
        prevented = bool(event.get("blocked")) or bool(
            intervention and intervention.get("succeeded", False)
        )
        behavior_type = "violation_attempt" if prevented else "violation_completed"
        event["behavior_type"] = behavior_type

        if event.get("blocked"):
            outcome = event.get("block_reason") or "违规尝试被环境限制阻止"
        elif prevented:
            outcome = "管理者及时干预，违规行为未实际完成"
        else:
            outcome = "违规行为已发生"

        display_events.append({
            "time": event.get("time"),
            "behavior": event.get("content", ""),
            "behavior_type": behavior_type,
            "inner_monologue": event.get("inner_monologue", ""),
            "target_location": event.get("target_location"),
            "intervention": {
                "level": max(0, min(3, int(intervention.get("level", 0)))),
                "action": intervention.get("action", ""),
                "reason": intervention.get("reason", ""),
                "succeeded": bool(intervention.get("succeeded", False)),
            } if intervention else None,
            "outcome": outcome,
        })

    day_log["display_events"] = display_events
    day_log["has_displayable_event"] = bool(display_events)
    day_log["display_event_count"] = len(display_events)
    return display_events
