import unittest

from survivor_calculator.baseline import HistoricalRateModel
from survivor_calculator.evaluation import PRIMARY_MODEL_NAME, assert_chronological_split, evaluate_chronological


class EvaluationTests(unittest.TestCase):
    def test_chronological_evaluation_reports_metrics_baselines_and_calibration(self) -> None:
        rows = _evaluation_rows()

        evaluation = evaluate_chronological(rows, HistoricalRateModel, holdout_seasons=2)

        self.assertEqual(evaluation["status"], "ok")
        self.assertEqual(evaluation["split"]["holdout_seasons"], [5, 6])
        self.assertEqual(evaluation["split"]["training_seasons"], [1, 2, 3, 4])
        self.assertEqual(evaluation["metrics"]["event_count"], 2)
        self.assertEqual(evaluation["metrics"]["candidate_count"], 6)
        self.assertEqual(evaluation["metrics"]["ranking"]["top1_accuracy"], 1.0)
        self.assertEqual(evaluation["top1_accuracy"], 1.0)

        comparison_names = {row["name"] for row in evaluation["baseline_comparisons"]}
        self.assertEqual(
            comparison_names,
            {"historical_rate_baseline", "uniform_random", "prior_votes_heuristic"},
        )
        self.assertIn("expected_calibration_error", evaluation["calibration"])
        self.assertTrue(any(bucket["count"] > 0 for bucket in evaluation["calibration"]["bins"]))
        self.assertEqual(evaluation["probability_quality"]["recommendation"], "baseline_default")

    def test_chronological_evaluation_compares_candidate_to_historical_rate_baseline(self) -> None:
        rows = _evaluation_rows()

        evaluation = evaluate_chronological(
            rows,
            ConstantRiskModel,
            holdout_seasons=2,
            model_name="constant_test_model",
            comparison_model_factories={PRIMARY_MODEL_NAME: HistoricalRateModel},
        )

        comparison_names = [row["name"] for row in evaluation["baseline_comparisons"]]
        self.assertEqual(comparison_names[:2], ["constant_test_model", "historical_rate_baseline"])
        self.assertEqual(evaluation["primary_model"], "constant_test_model")
        self.assertEqual(evaluation["probability_quality"]["reference_model"], "historical_rate_baseline")
        self.assertIn("brier_score_delta_vs_baseline", evaluation["probability_quality"])

    def test_chronological_evaluation_skips_when_holdout_would_consume_all_seasons(self) -> None:
        evaluation = evaluate_chronological(_evaluation_rows(seasons=2), HistoricalRateModel, holdout_seasons=2)

        self.assertEqual(evaluation["status"], "skipped")
        self.assertIn("Not enough completed seasons", evaluation["reason"])

    def test_chronological_split_rejects_overlapping_seasons(self) -> None:
        row = _row(season=1, candidate="S1-risk", target=1, votes_received=2)

        with self.assertRaisesRegex(ValueError, "seasons appear in both train and holdout"):
            assert_chronological_split([row], [row])

    def test_chronological_split_rejects_future_training_season(self) -> None:
        train = [_row(season=4, candidate="S4-risk", target=1, votes_received=2)]
        test = [_row(season=3, candidate="S3-risk", target=1, votes_received=2)]

        with self.assertRaisesRegex(ValueError, "training seasons must all precede holdout seasons"):
            assert_chronological_split(train, test)


def _evaluation_rows(seasons: int = 6) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for season in range(1, seasons + 1):
        rows.extend(
            [
                _row(season, f"S{season}-risk", 1, votes_received=2),
                _row(season, f"S{season}-steady", 0, votes_received=0),
                _row(season, f"S{season}-quiet", 0, votes_received=0),
            ]
        )
    return rows


def _row(season: int, candidate: str, target: int, votes_received: int) -> dict[str, object]:
    return {
        "season": season,
        "episode": 1,
        "n_boots": 0,
        "final_n": 3,
        "castaway_id": candidate,
        "castaway": candidate,
        "age": 30,
        "gender": "Unknown",
        "occupation": "",
        "soc_major_group": "",
        "tribe": "Test",
        "tribe_status": "Tribal",
        "tribe_size": 3,
        "challenge_wins_to_date": 0,
        "individual_immunity_wins_to_date": 0,
        "votes_received_to_date": votes_received,
        "votes_cast_to_date": 0,
        "confessionals_to_date": 0.0,
        "confessional_time_to_date": 0.0,
        "advantages_held_to_date": 0,
        "target_next_boot": target,
        "target_winner": 0,
    }


class ConstantRiskModel:
    def fit(self, rows: list[dict[str, object]]) -> "ConstantRiskModel":
        return self

    def predict_risk(self, row: dict[str, object]) -> float:
        return 1.0


if __name__ == "__main__":
    unittest.main()
