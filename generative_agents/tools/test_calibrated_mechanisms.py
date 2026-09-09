import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modules.mechanism_config import get_mechanism_config, set_mechanism_config, reset_mechanism_config
from modules.mechanism_config.ui_tunable import write_ui_param
from modules.health_mechanisms.scoring.nonlinear import NonlinearHealthScorer, Scorer
from modules.health_mechanisms.management.strategy import LongTermStrategyManager


class CalibrationTests(unittest.TestCase):
    def tearDown(self):
        reset_mechanism_config()

    def reward(self, value):
        cfg = write_ui_param(get_mechanism_config(), "complianceBonus", value)
        set_mechanism_config(cfg)
        scorer = NonlinearHealthScorer(initial_score=75, discipline_level="medium", random_seed=91)
        scorer.current_score = 60
        _, breakdown = scorer.calculate_daily_change({}, False, 0, True, 0)
        return breakdown["components"]["compliance_bonus"]

    def test_autonomous_compliance_recovers_and_slider_works(self):
        low = self.reward(.5)
        high = self.reward(2.5)
        self.assertGreater(low, 0)
        self.assertAlmostEqual(high / low, 5)

    def test_high_intervention_streak_counts_days(self):
        manager = LongTermStrategyManager()
        for level in (2, 3, 0, 2):
            manager._update_intervention_tracking(level, 1)
        self.assertEqual(manager._intervention_protection["consecutive_high_intervention_days"], 1)
        manager._update_intervention_tracking(2, 2)
        self.assertEqual(manager._intervention_protection["consecutive_high_intervention_days"], 2)
        manager._update_intervention_tracking(0, 3)
        self.assertEqual(manager._intervention_protection["consecutive_high_intervention_days"], 0)

    def test_compliance_bonus_does_not_exceed_start_score(self):
        scorer = NonlinearHealthScorer(initial_score=60, random_seed=42)
        scorer.current_score = 59.99
        self.assertLessEqual(scorer._calculate_compliance_bonus(59.99, 60, 0), .010000001)

    def test_compliant_noise_does_not_cross_initial_baseline(self):
        scorer = NonlinearHealthScorer(initial_score=60, random_seed=2)
        scorer.current_score = 59.99
        scorer.calculate_daily_change({}, False, 0, True, 0)
        self.assertLessEqual(scorer.current_score, 60)

    def test_successful_interventions_mitigate_mixed_day_penalty(self):
        a = NonlinearHealthScorer(initial_score=90, discipline_level="low", random_seed=19)
        b = NonlinearHealthScorer(initial_score=90, discipline_level="low", random_seed=19)
        raw, _ = a.calculate_daily_change({}, True, 0, False, 3)
        managed, detail = b.calculate_daily_change({}, True, 2, True, 3)
        self.assertGreater(managed, raw)
        self.assertIn("intervention_mitigation", detail["components"])

    def test_satisfaction_sliders_drive_runtime_mood(self):
        low = get_mechanism_config()
        low = write_ui_param(low, "baseSatisfaction", 4)
        low = write_ui_param(low, "frequencyPenalty", .8)
        set_mechanism_config(low)
        low_score, _ = Scorer.calculate_mood_score_with_discipline(
            [{"level": 2, "reasonability": "reasonable"}], 2, "medium", 70
        )
        high = write_ui_param(low, "baseSatisfaction", 8)
        high = write_ui_param(high, "frequencyPenalty", .1)
        set_mechanism_config(high)
        high_score, _ = Scorer.calculate_mood_score_with_discipline(
            [{"level": 2, "reasonability": "reasonable"}], 2, "medium", 70
        )
        self.assertGreater(high_score, low_score)


if __name__ == "__main__":
    unittest.main()
