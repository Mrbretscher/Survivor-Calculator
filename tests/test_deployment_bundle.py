from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fixtures import minimal_core_tables
from survivor_calculator.analytics import build_player_season_rows, export_player_season_rows
from survivor_calculator.baseline import build_predictions, save_predictions
from survivor_calculator.deployment_bundle import prepare_bundle
from survivor_calculator.features import build_features


class DeploymentBundleTests(unittest.TestCase):
    def test_bundle_contains_valid_snapshot_and_excludes_local_private_files(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "input"
            data.mkdir()
            tables = minimal_core_tables()
            export_player_season_rows(build_player_season_rows(tables), data / "analytics_player_season.csv")
            save_predictions(build_predictions(build_features(tables), Path("fixture.xlsx")), data / "current_predictions.json")
            (data / ".env").write_text("SECRET=private", encoding="utf-8")
            output = root / "bundle"
            manifest = json.loads(prepare_bundle(repository, data, output).read_text(encoding="utf-8"))
            self.assertEqual(manifest["analytics_rows"], 4)
            self.assertEqual(manifest["players"], 2)
            for name, checksum in manifest["files"].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), checksum)
            self.assertFalse(any(path.name in {".env", "survivoR.xlsx", "node_modules"} for path in output.rglob("*")))
            self.assertEqual((output / ".python-version").read_text().strip(), "3.12")
            with self.assertRaises(FileExistsError):
                prepare_bundle(repository, data, output)

    def test_missing_data_does_not_create_partial_bundle(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle"
            with self.assertRaises(RuntimeError):
                prepare_bundle(repository, Path(directory), output)
            self.assertFalse(output.exists())
