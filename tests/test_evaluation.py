import itertools
import math
import unittest

from survivor_calculator.baseline import HistoricalRateModel
from survivor_calculator.evaluation import (
    PRIMARY_MODEL_NAME,
    RANKING_METRIC_VERSION,
    _score_events,
    expected_top_k_hit,
    evaluate_relationship_diagnostics,
    assert_chronological_split,
    evaluate_chronological,
    evaluate_pooled_random_holdout,
)


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

    def test_pooled_random_holdout_uses_seeded_validation_seasons(self) -> None:
        rows = _evaluation_rows(seasons=10)

        evaluation = evaluate_pooled_random_holdout(
            rows,
            HistoricalRateModel,
            pool_size=5,
            holdout_seasons_per_pool=1,
            random_seed=42,
        )

        self.assertEqual(evaluation["status"], "ok")
        self.assertEqual(evaluation["split"]["strategy"], "pooled_random_holdout_by_season")
        self.assertEqual(evaluation["split"]["season_pools"], [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]])
        self.assertEqual(evaluation["split"]["holdout_seasons"], [1, 6])
        self.assertEqual(evaluation["split"]["training_seasons"], [2, 3, 4, 5, 7, 8, 9, 10])
        self.assertEqual(evaluation["metrics"]["event_count"], 2)
        self.assertEqual(evaluation["top1_accuracy"], 1.0)

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


class FairRankingTests(unittest.TestCase):
    def test_uniform_scores_give_inverse_cohort_credit_for_every_outcome(self) -> None:
        for size in range(1, 9):
            for actual in range(size):
                for k in (0, 1, 3, size, size + 2):
                    with self.subTest(size=size, actual=actual, k=k):
                        self.assertEqual(expected_top_k_hit([1.0] * size, actual, k), min(k, size) / size)

    def test_partial_top_tie_and_untied_scores(self) -> None:
        self.assertEqual(expected_top_k_hit([9.0, 9.0, 6.0, 3.0], 0, 1), 0.5)
        self.assertEqual(expected_top_k_hit([9.0, 9.0, 6.0, 3.0], 2, 3), 1.0)
        self.assertEqual(expected_top_k_hit([9.0, 8.0, 6.0, 3.0], 1, 1), 0.0)
        self.assertEqual(expected_top_k_hit([9.0, 8.0, 6.0, 3.0], 3, 3), 0.0)

    def test_ties_crossing_top_three_boundary_receive_fractional_credit(self) -> None:
        self.assertEqual(expected_top_k_hit([9.0, 5.0, 5.0, 5.0, 1.0], 2, 3), 2 / 3)
        self.assertEqual(expected_top_k_hit([9.0, 8.0, 5.0, 5.0, 5.0], 2, 3), 1 / 3)
        self.assertEqual(expected_top_k_hit([5.0, 5.0, 5.0, 5.0, 1.0], 2, 3), 3 / 4)
        self.assertEqual(expected_top_k_hit([9.0, 8.0, 7.0, 5.0, 5.0], 3, 3), 0.0)

    def test_distinct_close_scores_are_not_rounded_into_ties(self) -> None:
        scores = [1.0, 1.0 - 5e-13, 0.5]
        self.assertEqual(expected_top_k_hit(scores, 0, 1), 1.0)
        self.assertEqual(expected_top_k_hit(scores, 1, 1), 0.0)

    def test_fractional_credit_matches_enumerated_random_tie_orders(self) -> None:
        scores = [9.0, 5.0, 5.0, 5.0, 1.0]
        orders = [[0, *tie_order, 4] for tie_order in itertools.permutations((1, 2, 3))]
        for actual in range(len(scores)):
            for k in range(len(scores) + 2):
                oracle = sum(actual in order[:k] for order in orders) / len(orders)
                self.assertEqual(expected_top_k_hit(scores, actual, k), oracle)

    def test_scored_metrics_are_invariant_to_every_contestant_permutation(self) -> None:
        for scores, actual in [([9.0, 5.0, 5.0, 5.0, 1.0], 2), ([4.0, 4.0, 1.0, 1.0], 0),
                               ([4.0, 4.0, 1.0, 1.0], 2)]:
            candidates = [{**_row(1, str(i), int(i == actual), 0), "score": score}
                          for i, score in enumerate(scores)]
            expected = _score_events("test", lambda r: r["score"], {(1, 1, 0): candidates})
            for permuted in itertools.permutations(candidates):
                result = _score_events("test", lambda r: r["score"], {(1, 1, 0): list(permuted)})
                for metric in ("top1_accuracy", "top3_recall", "log_loss", "brier_score"):
                    self.assertAlmostEqual(result[metric], expected[metric])

    def test_probability_metrics_retain_their_independently_computed_values(self) -> None:
        candidates = [{**_row(1, str(i), int(i == 1), 0), "score": score}
                      for i, score in enumerate((5.0, 3.0, 1.0, 1.0))]
        result = _score_events("test", lambda r: r["score"], {(1, 1, 0): candidates})
        self.assertEqual([r["probability"] for r in result["predictions"]], [0.5, 0.3, 0.1, 0.1])
        self.assertEqual(result["log_loss"], -math.log(0.3))
        self.assertAlmostEqual(result["brier_score"], (0.5**2 + (0.3-1)**2 + 0.1**2 + 0.1**2) / 4)

    def test_uniform_credit_is_averaged_per_event_with_different_cohort_sizes(self) -> None:
        groups = {(1, 1, 0): [_row(1, str(i), int(i == 0), 0) for i in range(4)],
                  (2, 1, 0): [_row(2, str(i), int(i == 0), 0) for i in range(2)]}
        result = _score_events("uniform", lambda _: 1.0, groups)
        self.assertEqual(result["top1_accuracy"], (1/4 + 1/2) / 2)
        self.assertEqual(result["top3_recall"], (3/4 + 1) / 2)
        self.assertEqual(result["log_loss"], (math.log(4) + math.log(2)) / 2)
        self.assertAlmostEqual(result["brier_score"], (0.75 + 0.5) / 6)

    def test_public_summaries_comparisons_and_slices_share_fair_metrics(self) -> None:
        evaluation = evaluate_chronological(_evaluation_rows(), ConstantRiskModel, holdout_seasons=2,
                                             model_name="constant_test_model")
        self.assertEqual(evaluation["ranking_metric_version"], RANKING_METRIC_VERSION)
        self.assertEqual(evaluation["metrics"]["ranking"]["tie_handling"], RANKING_METRIC_VERSION)
        self.assertEqual(evaluation["top1_accuracy"], 1/3)
        self.assertEqual(evaluation["metrics"]["ranking"]["top1_accuracy"], 1/3)
        self.assertEqual(evaluation["top3_recall"], 1)
        for row in evaluation["baseline_comparisons"]:
            if row["name"] in {"constant_test_model", "uniform_random"}:
                self.assertEqual(row["top1_accuracy"], 1/3)
        diagnostics = evaluate_relationship_diagnostics(_evaluation_rows(), ConstantRiskModel,
            model_name="constant_test_model", comparison_model_factories={}, holdout_seasons=[5, 6])
        for report in [*diagnostics["per_season"].values(),
                       diagnostics["slices"]["sparse_relationship_history"]]:
            for row in report["baseline_comparisons"]:
                if row["name"] in {"constant_test_model", "uniform_random"}:
                    self.assertEqual(row["top1_accuracy"], 1/3)
                    self.assertEqual(row["top3_recall"], 1)

    def test_invalid_ranking_inputs_fail_clearly(self) -> None:
        for scores, actual, k in [([], 0, 1), ([1.0], 1, 1), ([1.0], -1, 1), ([1.0], 0, -1),
                                  ([1.0], 0, 1.5), ([float("nan")], 0, 1), ([float("inf")], 0, 1)]:
            with self.subTest(scores=scores, actual=actual, k=k), self.assertRaises(ValueError):
                expected_top_k_hit(scores, actual, k)

    def test_multiple_actual_boots_are_rejected_instead_of_using_row_order(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one actual boot"):
            _score_events("invalid", lambda _: 1.0,
                          {(1, 1, 0): [_row(1, "A", 1, 0), _row(1, "B", 1, 0)]})


if __name__ == "__main__":
    unittest.main()
