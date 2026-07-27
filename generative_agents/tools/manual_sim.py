import json
import sys
from pathlib import Path

# 将 generative_agents 目录加入 sys.path，确保可直接导入 modules
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.scorer_nonlinear import NonlinearHealthScorer


def run_manual_sim(days=90, seed=42):
    scorer = NonlinearHealthScorer(initial_score=60, discipline_level='low', random_seed=seed, floor_score=0.0)

    results = []
    for day in range(1, days + 1):
        # 固定的手动模拟规则：
        # - 每天都有 2 次未被拦截的违规
        # - 每天还有 1 次被拦截的情况（用于反映干预存在）
        had_violation = True
        intervention_count = 1
        intervention_success = True

        change, breakdown = scorer.calculate_daily_change(
            agent_data={},
            had_violation=had_violation,
            intervention_count=intervention_count,
            intervention_success=intervention_success,
            unblocked_violation_count=2,
        )
        # keep concise output
        out = {
            "day": breakdown["day"],
            "had_violation": had_violation,
            "intervention_count": intervention_count,
            "intervention_success": intervention_success,
            "initial_score": round(breakdown["initial_score"], 3),
            "change": round(breakdown["change"], 3),
            "new_score": round(breakdown["new_score"], 3),
            "floor_protection": breakdown["components"].get("floor_protection"),
            "base_boost": breakdown["components"].get("recovery_components", {}).get("base_boost"),
            "compliance_scale": breakdown["components"].get("compliance_scale"),
            "natural_recovery": breakdown["components"].get("natural_recovery"),
            "compliance_bonus": breakdown["components"].get("compliance_bonus"),
            "recovery_scale": breakdown["components"].get("recovery_scale"),
        }
        results.append(out)
        print(json.dumps(out, ensure_ascii=False))

    # write summary file
    with open("simulation_90_manual.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    run_manual_sim(90, seed=42)
