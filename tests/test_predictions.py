from pathlib import Path
import unittest

from survivor_calculator.baseline import build_predictions
from survivor_calculator.features import build_features
from survivor_calculator.ingest import load_core_tables

from fixtures import minimal_core_tables


WORKBOOK = Path("survivoR.xlsx")


class PredictionTests(unittest.TestCase):
    def test_predictions_only_include_active_fixture_players(self) -> None:
        features = build_features(minimal_core_tables())
        bundle = build_predictions(features, Path("fixture.xlsx"))
        payload = bundle.to_dict()

        self.assertEqual(payload["metadata"]["current_season"], 2)
        self.assertEqual(payload["metadata"]["active_players"], 2)
        self.assertEqual(len(payload["players"]), 2)
        self.assertEqual(len(payload["projected_boot_order"]), 2)
        self.assertEqual(payload["evaluation"]["status"], "skipped")
        self.assertTrue(all(0.0 < player["next_boot_probability"] < 1.0 for player in payload["players"]))
        winner_total = sum(player["winner_probability"] for player in payload["players"])
        self.assertAlmostEqual(winner_total, 1.0, places=6)


@unittest.skipUnless(WORKBOOK.exists(), "Integration coverage requires survivoR.xlsx")
class PredictionIntegrationTests(unittest.TestCase):
    def test_predictions_only_include_active_current_players(self) -> None:
        features = build_features(load_core_tables(WORKBOOK))
        bundle = build_predictions(features, WORKBOOK)
        payload = bundle.to_dict()

        self.assertEqual(payload["metadata"]["current_season"], 51)
        self.assertEqual(payload["metadata"]["active_players"], 17)
        self.assertEqual(len(payload["players"]), 17)
        self.assertEqual(len(payload["projected_boot_order"]), 17)
        self.assertTrue(all(0.0 < player["next_boot_probability"] < 1.0 for player in payload["players"]))
        winner_total = sum(player["winner_probability"] for player in payload["players"])
        self.assertAlmostEqual(winner_total, 1.0, places=6)


if __name__ == "__main__":
    unittest.main()

