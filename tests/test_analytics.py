from __future__ import annotations

import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fixtures import minimal_core_tables
from survivor_calculator.analytics import (
    ANALYTICS_PLAYER_SEASON_COLUMNS,
    build_player_season_rows,
    export_player_season_rows,
)


class PlayerSeasonAnalyticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = build_player_season_rows(minimal_core_tables())
        cls.rows_by_id = {row["castaway_id"]: row for row in cls.rows}

    def test_builds_one_row_per_castaway_season(self) -> None:
        self.assertEqual(len(self.rows), 4)
        self.assertEqual({row["castaway_id"] for row in self.rows}, {"S1-A", "S1-B", "S2-C", "S2-D"})

    def test_includes_demographic_and_soc_fields(self) -> None:
        cam = self.rows_by_id["S2-C"]

        self.assertEqual(cam["age"], 35)
        self.assertEqual(cam["age_bucket"], "35_44")
        self.assertEqual(cam["gender"], "Female")
        self.assertEqual(cam["occupation"], "Nurse")
        self.assertEqual(cam["soc_code"], "29-1141")
        self.assertEqual(cam["soc_title"], "Registered Nurses")
        self.assertEqual(cam["soc_major_group"], "Healthcare Practitioners and Technical Occupations")
        self.assertEqual(cam["soc_confidence"], "medium")
        self.assertFalse(cam["soc_review_required"])

    def test_includes_placement_and_winner_outcomes(self) -> None:
        ari = self.rows_by_id["S1-A"]
        bea = self.rows_by_id["S1-B"]

        self.assertFalse(ari["winner"])
        self.assertTrue(bea["winner"])
        self.assertIsNone(ari["final_place"])
        self.assertEqual(ari["result"], "")

    def test_aggregates_supported_performance_metrics(self) -> None:
        ari = self.rows_by_id["S1-A"]
        bea = self.rows_by_id["S1-B"]
        cam = self.rows_by_id["S2-C"]
        dee = self.rows_by_id["S2-D"]

        self.assertEqual(ari["votes_received_total"], 1)
        self.assertEqual(ari["votes_cast_total"], 0)
        self.assertEqual(ari["confessionals_total"], 2.0)
        self.assertEqual(ari["confessional_time_total"], 15.5)

        self.assertEqual(bea["challenge_appearances_total"], 1)
        self.assertEqual(bea["challenge_wins_total"], 1)
        self.assertEqual(bea["votes_cast_total"], 1)

        self.assertEqual(cam["challenge_appearances_total"], 1)
        self.assertEqual(cam["challenge_wins_total"], 1)
        self.assertEqual(cam["individual_immunity_appearances_total"], 1)
        self.assertEqual(cam["individual_immunity_wins_total"], 1)
        self.assertEqual(cam["votes_received_total"], 1)
        self.assertEqual(cam["confessionals_total"], 3.0)
        self.assertEqual(cam["confessional_time_total"], 42.0)

        self.assertEqual(dee["age_bucket"], "under_25")
        self.assertEqual(dee["votes_cast_total"], 1)

    def test_export_writes_stable_header(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = export_player_season_rows(self.rows, Path(temp_dir) / "analytics_player_season.csv")
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                exported_rows = list(reader)

        self.assertEqual(reader.fieldnames, list(ANALYTICS_PLAYER_SEASON_COLUMNS))
        self.assertEqual(len(exported_rows), 4)
        self.assertEqual(exported_rows[0]["castaway_id"], "S1-A")


if __name__ == "__main__":
    unittest.main()
