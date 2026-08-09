"""短验证：agent_health 的 relapse.base_prob 可被 mechanism config 覆盖。

用法（在 generative_agents/ 下）::

    PYTHONPATH=. python3 tools/verify_agent_health_mechanism.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.mechanism_config import (
    get_path,
    load_defaults,
    reset_mechanism_config,
    set_mechanism_config,
)
from modules.agent_health import HealthAgentMixin


class _Stub(HealthAgentMixin):
    def __init__(self):
        self.self_discipline = "medium"
        self.addiction_level = "moderate"
        self.habit_streak = 0
        self.relapse_tendency = 0.0


def _prob():
    return _Stub().calculate_relapse_probability(is_relaxed=True, days_relaxed=0)


def main():
    reset_mechanism_config()
    set_mechanism_config(load_defaults())
    baseline = get_path("simulation.relapse.base_prob")
    p0 = _prob()
    assert abs(baseline - 0.15) < 1e-9, baseline
    assert abs(p0 - 0.15) < 1e-9, p0

    cfg = load_defaults()
    cfg["simulation"]["relapse"]["base_prob"] = 0.42
    set_mechanism_config(cfg)
    p1 = _prob()
    assert abs(p1 - 0.42) < 1e-9, p1

    del cfg["simulation"]["relapse"]["base_prob"]
    set_mechanism_config(cfg)
    p2 = _prob()
    assert abs(p2 - 0.15) < 1e-9, p2

    print("OK: relapse base_prob override works")
    print(f"  baseline={p0}, override=0.42 -> {p1}, missing_fallback={p2}")
    reset_mechanism_config()


if __name__ == "__main__":
    main()
