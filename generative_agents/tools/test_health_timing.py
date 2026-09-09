import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modules.health_mechanisms.scoring.timing import collect_timing, sleep_change, DEFAULTS
from modules.health_mechanisms.scoring.nonlinear import NonlinearHealthScorer


def data(sleep="22:30", times=()):
    return {"timing_observed": True, "sleep_started_at": sleep,
            "violation_events": [{"time": t, "blocked": False} for t in times]}


def calculate(scorer, datum):
    with patch.object(scorer, "_add_daily_noise", return_value=0):
        return scorer.calculate_daily_change(datum, False, 0, False, 0)


def test_sleep_windows_and_streaks():
    best = sleep_change(data("22:30"), DEFAULTS, 0, 0)[0]
    assert best > sleep_change(data("23:30"), DEFAULTS, 0, 0)[0] > 0
    assert sleep_change(data("00:30"), DEFAULTS, 0, 0)[0] < 0
    assert sleep_change(data(None), DEFAULTS, 0, 0)[0] < 0
    assert sleep_change(data(), DEFAULTS, 3, 0)[0] > best


def test_sleep_replaces_generic_compliance_and_checkpoint():
    scorer = NonlinearHealthScorer(60, "medium", random_seed=10)
    first, report = calculate(scorer, data())
    assert first > 0 and "compliance_bonus" not in report["components"]
    restored = NonlinearHealthScorer.from_dict(scorer.to_dict())
    assert restored.early_sleep_streak == 1
    second, _ = calculate(restored, data())
    assert second > first
    late, report = calculate(restored, data("01:00"))
    assert late < 0 and restored.early_sleep_streak == 0
    assert restored.late_sleep_streak == 1


def test_later_more_and_consecutive_violations_cost_more():
    def penalty(times):
        s = NonlinearHealthScorer(90, "medium", random_seed=31)
        return calculate(s, data("02:00", times))[1]["components"]["violation"]
    assert penalty(["00:30"]) < penalty(["21:30"])
    assert penalty(["00:30", "01:10"]) < penalty(["00:30"])
    s = NonlinearHealthScorer(90, "medium", random_seed=31)
    calculate(s, data("02:00", ["00:30"]))
    _, report = calculate(s, data("02:00", ["00:30"]))
    assert report["components"]["violation_timing"]["streak_multiplier"] > 1


def test_execution_timing_excludes_blocked_search_and_rest():
    def event(time, content, **kwargs):
        return {"time": time, "content": content, "agent": "A", "type": "intention", **kwargs}
    log = {"events": [event("21:30", "去厨房找东西吃"),
                      event("22:00", "吃蛋糕", blocked=True),
                      event("23:00", "躺下休息"), event("00:30", "吃了蛋糕"),
                      event("02:00", "睡觉", execution_source="forced_02_00")],
           "interventions": []}
    result = collect_timing(log, "A", "diabetes", lambda i, l: "吃" in i.activity)
    assert result["actual_violation_count"] == 1
    assert result["eating_times"] == ["00:30"]
    assert result["sleep_started_at"] == "02:00"
    assert result["sleep_source"] == "forced_02_00"


def test_missing_sleep_is_not_defaulted_to_two_am():
    result = collect_timing({"events": []}, "A", "diabetes", lambda i, l: False)
    assert result["sleep_started_at"] is None and result["no_sleep_detected"]
