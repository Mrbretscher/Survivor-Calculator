from __future__ import annotations

import copy
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fixtures import minimal_core_tables
from survivor_calculator.cli import build_from_tables, main
from survivor_calculator.api import prediction_payload
from survivor_calculator.deployment_bundle import prepare_bundle
from survivor_calculator.refresh import COMMIT_URL, normalize_table, refresh


class RefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.stdout = contextlib.redirect_stdout(io.StringIO())
        self.stdout.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)
        self.output = Path(self.temporary.name) / "processed"
        self.commit = "a" * 40
        self.tables = minimal_core_tables()
        for name, rows in self.tables.items():
            if name != "Castaway Details":
                for row in rows:
                    row["version"] = "US"
        self.tables["Episodes"] = [{"version": "US", "season": 2, "episode": 2}]
        self.fetch = patch("survivor_calculator.refresh.fetch_json", side_effect=self.fetch_json).start()
        self.addCleanup(patch.stopall)

    def fetch_json(self, url: str) -> object:
        if url == COMMIT_URL:
            return {"sha": self.commit}
        self.assertIn(f"/{self.commit}/dev/json/", url)
        name = Path(url).stem.replace("_", " ").title()
        return copy.deepcopy(self.tables[name])

    def test_real_pipeline_provenance_and_no_change_skip(self) -> None:
        with patch("survivor_calculator.cli.build_from_tables", wraps=build_from_tables) as build:
            self.assertTrue(refresh(self.output))
            before = (self.output / "current_predictions.json").read_bytes()
            self.assertFalse(refresh(self.output))
            self.assertEqual(build.call_count, 1)
        self.assertEqual(self.fetch.call_count, 12)  # Commit + ten tables, then commit only.
        payload = json.loads(before)
        self.assertEqual(payload["metadata"]["source_data"]["commit"], self.commit)
        self.assertEqual(payload["metadata"]["evaluation_strategy"], "chronological")
        self.assertEqual(payload["metadata"]["source_workbook"], "upstream-json (no workbook)")
        served = prediction_payload(predictions_path=self.output / "current_predictions.json")
        self.assertEqual(served["metadata"]["source_data"]["commit"], self.commit)
        self.assertEqual(len(payload["players"]), 2)
        self.assertEqual((self.output / "current_predictions.json").read_bytes(), before)

    def test_changed_data_retrains_and_updates_manifest(self) -> None:
        refresh(self.output)
        self.commit = "b" * 40
        self.tables["Confessionals"][0]["confessional_count"] = "9"
        with patch("survivor_calculator.cli.build_from_tables", wraps=build_from_tables) as build:
            self.assertTrue(refresh(self.output))
            build.assert_called_once()
        manifest = json.loads((self.output / "refresh_manifest.json").read_text())
        self.assertEqual(manifest["commit"], self.commit)

    def test_refreshed_data_builds_deployable_bundle(self) -> None:
        refresh(self.output)
        repository = Path(__file__).resolve().parents[1]
        manifest = prepare_bundle(repository, self.output, Path(self.temporary.name) / "bundle")
        self.assertEqual(json.loads(manifest.read_text())["players"], 2)

    def test_documentation_only_commit_skips_training(self) -> None:
        refresh(self.output)
        self.commit = "b" * 40
        with patch("survivor_calculator.cli.build_from_tables") as build:
            self.assertFalse(refresh(self.output))
            build.assert_not_called()

    def test_schema_failure_preserves_previous_outputs_and_retries(self) -> None:
        refresh(self.output)
        before = {path.name: path.read_bytes() for path in self.output.glob("*") if path.is_file()}
        self.commit = "b" * 40
        saved = self.tables["Confessionals"]
        self.tables["Confessionals"] = [{"version": "US", "season": "2"}]
        with self.assertRaisesRegex(ValueError, "missing columns"):
            refresh(self.output)
        for name, contents in before.items():
            self.assertEqual((self.output / name).read_bytes(), contents)
        self.tables["Confessionals"] = saved
        self.tables["Confessionals"][0]["confessional_count"] = "9"
        self.assertTrue(refresh(self.output))

    def test_training_failure_preserves_previous_outputs(self) -> None:
        refresh(self.output)
        before = (self.output / "current_predictions.json").read_bytes()
        manifest = (self.output / "refresh_manifest.json").read_bytes()
        with patch("survivor_calculator.cli.build_from_tables", side_effect=RuntimeError("training failed")):
            with self.assertRaisesRegex(RuntimeError, "training failed"):
                refresh(self.output, force=True)
        self.assertEqual((self.output / "current_predictions.json").read_bytes(), before)
        self.assertEqual((self.output / "refresh_manifest.json").read_bytes(), manifest)

    def test_download_failure_has_no_output_and_releases_lock(self) -> None:
        self.fetch.side_effect = RuntimeError("network down")
        with self.assertRaisesRegex(RuntimeError, "network down"):
            refresh(self.output)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.with_name(".processed.refresh.lock").exists())

    def test_missing_or_corrupted_output_forces_rebuild(self) -> None:
        refresh(self.output)
        (self.output / "analytics_player_season.csv").unlink()
        self.assertTrue(refresh(self.output))
        (self.output / "current_predictions.json").write_text("{}")
        self.assertTrue(refresh(self.output))

    def test_force_and_code_changes_rebuild(self) -> None:
        refresh(self.output)
        self.assertTrue(refresh(self.output, force=True))
        with patch("survivor_calculator.refresh._code_digest", return_value="new code"):
            self.assertTrue(refresh(self.output))

    def test_rejects_invalid_commit_and_overlapping_refresh(self) -> None:
        self.commit = "../../master"
        with self.assertRaisesRegex(ValueError, "commit SHA"):
            refresh(self.output)
        lock = self.output.with_name(".processed.refresh.lock")
        lock.touch()
        with self.assertRaisesRegex(RuntimeError, "Another refresh"):
            refresh(self.output)
        self.assertTrue(lock.exists())

    def test_boolean_normalization_and_us_filter(self) -> None:
        rows = normalize_table("Castaways", [
            {"version": "US", "season": 1, "castaway_id": "A", "castaway": "A", "winner": True},
            {"version": "AU", "season": 99, "castaway_id": "B", "castaway": "B", "winner": False},
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["winner"], "1")
        self.assertEqual(rows[0]["season"], "1")
        self.assertEqual(normalize_table("Castaway Details", [{
            "castaway_id": "A", "gender": None, "occupation": "Teacher", "flag": False,
        }])[0]["flag"], "0")

    def test_rejects_invalid_payloads(self) -> None:
        for payload in ([], {}, ["bad"], [{"field": []}]):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                normalize_table("Castaways", payload)

    def test_cli_refresh_reports_failure(self) -> None:
        with patch("survivor_calculator.refresh.refresh", side_effect=RuntimeError("failed")):
            self.assertEqual(main(["refresh", "--output-dir", str(self.output)]), 2)


if __name__ == "__main__":
    unittest.main()
