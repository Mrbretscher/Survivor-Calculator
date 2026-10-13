from pathlib import Path
import unittest

from survivor_calculator.baseline import build_predictions, resolve_model_name
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

    def test_model_name_aliases_keep_baseline_default_readable(self) -> None:
        self.assertEqual(resolve_model_name("historical-rate-baseline"), "historical_rate_baseline")
        self.assertEqual(resolve_model_name("experimental-next-boot"), "experimental_next_boot")

    def test_experimental_model_reports_missing_optional_dependency(self) -> None:
        try:
            import sklearn  # noqa: F401
        except ModuleNotFoundError:
            features = build_features(minimal_core_tables())
            with self.assertRaisesRegex(RuntimeError, "requires scikit-learn"):
                build_predictions(features, Path("fixture.xlsx"), model_name="experimental-next-boot")
        else:
            self.skipTest("scikit-learn is installed; missing-optional-dependency path is not active")


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

