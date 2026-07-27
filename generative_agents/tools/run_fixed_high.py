import json
import random
import sys
from pathlib import Path

# ensure generative_agents package path is importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.scorer_nonlinear import NonlinearHealthScorer


def main():
    seed = 321
    rng = random.Random(seed)
    seq = [(rng.randint(1, 4), rng.random() < 0.5) for _ in range(90)]
    Path(r'e:\data\pythoncode\GenerativeAgentsCN\fixed_sequence_seed321.json').write_text(
        json.dumps([{'unblocked': u, 'intervention_success': b} for u, b in seq], ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    for init in (90, 60):
        scorer = NonlinearHealthScorer(initial_score=init, discipline_level='high', random_seed=seed, floor_score=0.0)
        out = []
        for day, (u, b) in enumerate(seq, start=1):
            change, breakdown = scorer.calculate_daily_change(
                agent_data={},
                had_violation=True,
                intervention_count=1,
                intervention_success=b,
                unblocked_violation_count=u,
            )
            out.append({
                'day': day,
                'unblocked': u,
                'intervention_success': b,
                'initial_score': round(breakdown['initial_score'], 3),
                'change': round(breakdown['change'], 3),
                'new_score': round(breakdown['new_score'], 3),
                'floor_protection': breakdown['components'].get('floor_protection'),
                'natural_recovery': breakdown['components'].get('natural_recovery'),
                'compliance_bonus': breakdown['components'].get('compliance_bonus'),
            })

        p = Path(f'e:/data/pythoncode/GenerativeAgentsCN/fixed_seq_initial{init}_high_seed{seed}.json')
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
        scores = [d['new_score'] for d in out]
        print('INIT', init, 'final', round(scores[-1], 3), 'min', round(min(scores), 3), 'max', round(max(scores), 3), 'days_below_30', sum(1 for x in scores if x < 30), 'days_at_zero', sum(1 for x in scores if x == 0))


if __name__ == '__main__':
    main()
