from __future__ import annotations

import unittest

from survivor_calculator.analytics_query import AnalyticsQueryError, preset_configs, run_chart_query


class AnalyticsQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            _row("Engineer", "25_34", True, 3, 2, 1, 1, 0),
            _row("Engineer", "25_34", False, 1, 1, 1, 0, 2),
            _row("Teacher", "35_44", False, 2, 2, 0, 0, 0),
            _row("Nurse", "under_25", True, 3, 0, 2, 1, 1),
            _row("Nurse", "35_44", False, 3, 3, 1, 1, 0),
        ]

    def test_computes_team_challenge_win_rate_by_dimension(self) -> None:
        result = run_chart_query(
            self.rows,
            {
                "dimension": "occupation",
                "metric": "team_challenge_win_rate",
                "minimum_sample_size": 1,
                "sort": {"field": "label", "direction": "asc"},
            },
        )

        by_label = {row["label"]: row for row in result["rows"]}
        self.assertAlmostEqual(by_label["Engineer"]["value"], 0.75)
        self.assertEqual(by_label["Engineer"]["sample_size"], 4)
        self.assertAlmostEqual(by_label["Nurse"]["value"], 0.5)
        self.assertAlmostEqual(by_label["Teacher"]["value"], 1.0)
        self.assertEqual(result["metadata"]["metric"]["label"], "Team Challenge Win Rate")

    def test_filters_rows_before_grouping(self) -> None:
        result = run_chart_query(
            self.rows,
            {
                "dimension": "occupation",
                "metric": "contestant_count",
                "filters": [{"field": "age_bucket", "operator": "equals", "value": "35_44"}],
                "sort": {"field": "label", "direction": "asc"},
            },
        )

        self.assertEqual(result["metadata"]["filtered_row_count"], 2)
        self.assertEqual(
            [(row["label"], row["value"], row["count"]) for row in result["rows"]],
            [("Nurse", 1, 1), ("Teacher", 1, 1)],
        )

    def test_sorts_and_limits_chart_rows(self) -> None:
        result = run_chart_query(
            self.rows,
            {
                "dimension": "occupation",
                "metric": "contestant_count",
                "sort": {"field": "value", "direction": "desc"},
                "limit": 2,
            },
        )

        self.assertEqual(result["metadata"]["returned_row_count"], 2)
        self.assertEqual([row["value"] for row in result["rows"]], [2, 2])

    def test_suppresses_rate_metrics_below_minimum_sample_size(self) -> None:
        result = run_chart_query(
            self.rows,
            {
                "dimension": "occupation",
                "metric": "social_proxy_no_votes_rate",
                "minimum_sample_size": 2,
                "sort": {"field": "value", "direction": "desc"},
            },
        )

        by_label = {row["label"]: row for row in result["rows"]}
        self.assertAlmostEqual(by_label["Engineer"]["value"], 0.5)
        self.assertIsNone(by_label["Teacher"]["value"])
        self.assertFalse(by_label["Teacher"]["eligible"])
        self.assertEqual(by_label["Teacher"]["suppressed_reason"], "Minimum sample size is 2.")
        self.assertEqual(result["metadata"]["suppressed_row_count"], 1)
        self.assertTrue(result["metadata"]["metric"]["proxy"])
        self.assertIn("does not measure relationships", result["metadata"]["warnings"][0])
        self.assertEqual(result["rows"][-1]["label"], "Teacher")

    def test_social_proxy_excludes_rows_without_recorded_vote_activity(self) -> None:
        rows = [
            _row("Engineer", "25_34", True, 3, 2, 1, 1, 0),
            _row("Engineer", "25_34", False, 1, 1, 1, 0, 2),
            {
                **_row("Engineer", "25_34", False, 1, 0, 0, 0, 0),
                "castaway_id": "Engineer-no-vote-activity",
                "votes_cast_total": 0,
            },
        ]

        result = run_chart_query(
            rows,
            {
                "dimension": "occupation",
                "metric": "social_proxy_no_votes_rate",
                "minimum_sample_size": 1,
            },
        )

        row = result["rows"][0]
        self.assertEqual(row["count"], 3)
        self.assertEqual(row["sample_size"], 2)
        self.assertAlmostEqual(row["value"], 0.5)

    def test_rate_metrics_explain_when_no_supported_observations_exist(self) -> None:
        result = run_chart_query(
            [{**_row("Engineer", "25_34", False, 0, 0, 0, 0, 0), "votes_cast_total": 0}],
            {
                "dimension": "occupation",
                "metric": "social_proxy_no_votes_rate",
                "minimum_sample_size": 1,
            },
        )

        self.assertEqual(result["rows"][0]["suppressed_reason"], "No supported observations for this metric.")

    def test_validates_unsupported_dimension(self) -> None:
        with self.assertRaisesRegex(AnalyticsQueryError, "Unsupported dimension"):
            run_chart_query(self.rows, {"dimension": "bad", "metric": "contestant_count"})

    def test_validates_filter_operator(self) -> None:
        with self.assertRaisesRegex(AnalyticsQueryError, "Unsupported filter operator"):
            run_chart_query(
                self.rows,
                {
                    "dimension": "occupation",
                    "metric": "contestant_count",
                    "filters": [{"field": "age_bucket", "operator": "contains", "value": "25"}],
                },
            )

    def test_preset_configs_include_requested_occupation_and_age_questions(self) -> None:
        preset_ids = {preset["id"] for preset in preset_configs()}

        self.assertEqual(
            preset_ids,
            {
                "occupations_cast_most_often",
                "occupations_best_team_challenge_win_rate",
                "occupations_best_individual_immunity_win_rate",
                "occupations_best_social_proxy",
                "occupations_most_winners",
                "age_buckets_cast_most_often",
                "age_buckets_best_team_challenge_win_rate",
                "age_buckets_best_individual_immunity_win_rate",
                "age_buckets_best_social_proxy",
                "age_buckets_most_winners",
            },
        )


def _row(
    occupation: str,
    age_bucket: str,
    winner: bool,
    team_appearances: int,
    team_wins: int,
    individual_appearances: int,
    individual_wins: int,
    votes_received: int,
) -> dict[str, object]:
    return {
        "version": "US",
        "version_season": "US01",
        "season": 1,
        "castaway_id": f"{occupation}-{age_bucket}-{votes_received}",
        "castaway": occupation,
        "age": 30,
        "age_bucket": age_bucket,
        "gender": "Unknown",
        "occupation": occupation,
        "soc_code": "",
        "soc_title": "",
        "soc_major_group": "",
        "soc_confidence": "none",
        "soc_review_required": False,
        "final_place": None,
        "result": "",
        "jury": False,
        "finalist": False,
        "winner": winner,
        "challenge_appearances_total": team_appearances + individual_appearances,
        "challenge_wins_total": team_wins + individual_wins,
        "team_challenge_appearances_total": team_appearances,
        "team_challenge_wins_total": team_wins,
        "individual_immunity_appearances_total": individual_appearances,
        "individual_immunity_wins_total": individual_wins,
        "votes_received_total": votes_received,
        "votes_cast_total": 1,
        "confessionals_total": 0.0,
        "confessional_time_total": 0.0,
    }


if __name__ == "__main__":
    unittest.main()
