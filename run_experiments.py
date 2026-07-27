# Quick test to verify the scorer is working correctly
import sys
sys.path.insert(0, 'E:/data/pythoncode/GenerativeAgentsCN/generative_agents')

from modules.scorer_nonlinear import NonlinearHealthScorer

# Test 1: 30 consecutive violations - score should stay above 30
print("=" * 60)
print("Test 1: 30 consecutive violations (LOW discipline, initial=90)")
print("=" * 60)
scorer = NonlinearHealthScorer(initial_score=90, discipline_level='low', random_seed=42)
min_score = scorer.current_score
for day in range(1, 31):
    _, breakdown = scorer.calculate_daily_change(
        agent_data={'action': 'test'},
        had_violation=True,
        intervention_count=0,
        intervention_success=False,
        unblocked_violation_count=1
    )
    min_score = min(min_score, scorer.current_score)
print(f"Start: 90.00, Min: {min_score:.2f}, Final: {scorer.current_score:.2f}")
print(f"Score stayed above 30: {'PASS' if min_score >= 30 else 'FAIL'}")

# Test 2: Discipline improvement - LOW -> MEDIUM after 14 good days
print()
print("=" * 60)
print("Test 2: Discipline improvement (LOW -> MEDIUM after 14 days)")
print("=" * 60)
scorer2 = NonlinearHealthScorer(initial_score=90, discipline_level='low', random_seed=42)
for day in range(1, 15):
    _, breakdown = scorer2.calculate_daily_change(
        agent_data={'action': 'test'},
        had_violation=False,
        intervention_count=0,
        intervention_success=False,
        unblocked_violation_count=0
    )
print(f"Final discipline: {scorer2.discipline_level.value}")
print(f"Discipline improved: {'PASS' if scorer2.discipline_improved else 'FAIL'}")

# Test 3: Mixed scenario - 5 good days, 1 violation, repeat
print()
print("=" * 60)
print("Test 3: Mixed scenario (5 good days + 1 violation, LOW discipline)")
print("=" * 60)
scorer3 = NonlinearHealthScorer(initial_score=75, discipline_level='low', random_seed=42)
for cycle in range(1, 7):  # 6 cycles = 36 days
    # 5 good days
    for _ in range(5):
        scorer3.calculate_daily_change(
            agent_data={'action': 'test'},
            had_violation=False,
            intervention_count=0,
            intervention_success=False,
            unblocked_violation_count=0
        )
    # 1 violation day
    scorer3.calculate_daily_change(
        agent_data={'action': 'test'},
        had_violation=True,
        intervention_count=0,
        intervention_success=False,
        unblocked_violation_count=1
    )
    print(f"  Cycle {cycle}: score={scorer3.current_score:.2f}")
print(f"Score after 36 days: {scorer3.current_score:.2f}")

print()
print("All tests completed!")