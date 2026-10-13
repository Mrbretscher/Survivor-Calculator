from pathlib import Path
import unittest

from survivor_calculator.features import FEATURE_COLUMNS, assert_no_leakage_columns, build_features
from survivor_calculator.ingest import load_core_tables

from fixtures import minimal_core_tables


WORKBOOK = Path("survivoR.xlsx")


class FeatureBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tables = minimal_core_tables()
        cls.features = build_features(cls.tables)

    def test_feature_build_identifies_current_fixture_state(self) -> None:
        self.assertEqual(self.features.current_season, 2)
        self.assertEqual(self.features.latest_episode, 2)
        self.assertEqual(len(self.features.current_rows), 2)
        self.assertEqual(self.features.latest_final_n, 2)

    def test_feature_build_creates_historical_targets(self) -> None:
        targets = {
            (row["season"], row["episode"], row["castaway_id"]): row["target_next_boot"]
            for row in self.features.historical_rows
        }

        self.assertEqual(targets[(1, 1, "S1-A")], 1)
        self.assertEqual(targets[(1, 1, "S1-B")], 0)
        self.assertEqual(targets[(1, 2, "S1-B")], 1)

    def test_feature_build_carries_event_counts_forward(self) -> None:
        current_by_id = {row["castaway_id"]: row for row in self.features.current_rows}

        self.assertEqual(current_by_id["S2-C"]["challenge_wins_to_date"], 1)
        self.assertEqual(current_by_id["S2-C"]["individual_immunity_wins_to_date"], 1)
        self.assertEqual(current_by_id["S2-C"]["votes_received_to_date"], 1)
        self.assertEqual(current_by_id["S2-C"]["confessionals_to_date"], 3.0)
        self.assertEqual(current_by_id["S2-D"]["votes_cast_to_date"], 1)
        self.assertEqual(current_by_id["S2-D"]["advantages_held_to_date"], 1)

    def test_feature_build_derives_player_facing_tribe_status(self) -> None:
        current_by_id = {row["castaway_id"]: row for row in self.features.current_rows}

        self.assertEqual(current_by_id["S2-C"]["original_tribe"], "Luma")
        self.assertEqual(current_by_id["S2-C"]["tribe"], "Luma")
        self.assertEqual(current_by_id["S2-C"]["tribe_status_display"], "Original")
        self.assertEqual(current_by_id["S2-D"]["original_tribe"], "Luma")
        self.assertEqual(current_by_id["S2-D"]["tribe"], "Koru")
        self.assertEqual(current_by_id["S2-D"]["tribe_status_display"], "Swapped")

    def test_feature_build_marks_every_current_player_merged_after_merge(self) -> None:
        tables = minimal_core_tables()
        for row in tables["Boot Mapping"]:
            if row["season"] == "2" and row["episode"] == "2":
                row["tribe"] = "Merged Tribe"
                row["tribe_status"] = "Merged"

        features = build_features(tables)

        self.assertEqual(
            {row["tribe_status_display"] for row in features.current_rows},
            {"Merged"},
        )

    def test_feature_columns_do_not_include_known_leakage_targets(self) -> None:
        assert_no_leakage_columns(FEATURE_COLUMNS)

    def test_leakage_guard_rejects_target_columns(self) -> None:
        with self.assertRaisesRegex(ValueError, "Potential leakage columns"):
            assert_no_leakage_columns((*FEATURE_COLUMNS, "target_next_boot"))

    def test_soc_mapping_covers_every_distinct_fixture_occupation(self) -> None:
        occupations = {
            (row.get("occupation") or "").strip()
            for row in self.tables["Castaway Details"]
        }

        self.assertEqual(len(self.features.soc_mappings), len(occupations))

    def test_feature_build_includes_detailed_soc_fields(self) -> None:
        current_by_id = {row["castaway_id"]: row for row in self.features.current_rows}

        self.assertEqual(current_by_id["S2-C"]["soc_code"], "29-1141")
        self.assertEqual(current_by_id["S2-C"]["soc_title"], "Registered Nurses")
        self.assertEqual(
            current_by_id["S2-C"]["soc_major_group"],
            "Healthcare Practitioners and Technical Occupations",
        )


@unittest.skipUnless(WORKBOOK.exists(), "Integration coverage requires survivoR.xlsx")
class FeatureBuildIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tables = load_core_tables(WORKBOOK)
        cls.features = build_features(cls.tables)

    def test_feature_build_identifies_current_season_state(self) -> None:
        self.assertEqual(self.features.current_season, 51)
        self.assertEqual(self.features.latest_episode, 4)
        self.assertEqual(len(self.features.current_rows), 17)
        self.assertEqual(self.features.latest_final_n, 17)

    def test_feature_columns_do_not_include_known_leakage_targets(self) -> None:
        assert_no_leakage_columns(FEATURE_COLUMNS)

    def test_soc_mapping_covers_every_distinct_occupation(self) -> None:
        occupations = {
            (row.get("occupation") or "").strip()
            for row in self.tables["Castaway Details"]
        }

        self.assertEqual(len(self.features.soc_mappings), len(occupations))


if __name__ == "__main__":
    unittest.main()

