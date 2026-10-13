from pathlib import Path
import unittest

from survivor_calculator.features import FEATURE_COLUMNS, assert_no_leakage_columns, build_features
from survivor_calculator.ingest import load_core_tables


WORKBOOK = Path("survivoR.xlsx")


class FeatureBuildTests(unittest.TestCase):
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

