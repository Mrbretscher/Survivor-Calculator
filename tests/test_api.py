from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from fixtures import minimal_core_tables
from survivor_calculator import server as api_server
from survivor_calculator.baseline import build_predictions, save_predictions
from survivor_calculator.features import build_features


class ApiEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.predictions_path = Path(self.temp_dir.name) / "current_predictions.json"
        features = build_features(minimal_core_tables())
        bundle = build_predictions(features, Path("fixture.xlsx"))
        save_predictions(bundle, self.predictions_path)

        self.old_predictions_path = api_server.DEFAULT_PREDICTIONS
        api_server.DEFAULT_PREDICTIONS = self.predictions_path
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), api_server.SurvivorApiHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.thread.join(timeout=5)
        self.httpd.server_close()
        api_server.DEFAULT_PREDICTIONS = self.old_predictions_path
        self.temp_dir.cleanup()

    def test_health_endpoint_reports_ok(self) -> None:
        status, payload = self._get_json("/health")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload, {"status": "ok"})

    def test_current_season_endpoint_returns_validated_summary(self) -> None:
        status, payload = self._get_json("/api/current-season")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(
            payload,
            {
                "current_season": 2,
                "latest_episode": 2,
                "latest_final_n": 2,
                "active_players": 2,
            },
        )

    def test_current_predictions_endpoint_returns_validated_contract(self) -> None:
        status, payload = self._get_json("/api/predictions/current")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["metadata"]["current_season"], 2)
        self.assertEqual(payload["metadata"]["active_players"], 2)
        self.assertEqual(len(payload["players"]), 2)
        self.assertEqual(len(payload["projected_boot_order"]), 2)
        self.assertEqual(payload["evaluation"]["status"], "skipped")
        self.assertIn("next_boot_probability", payload["players"][0])
        self.assertIn("original_tribe", payload["players"][0])
        self.assertIn("tribe_status_display", payload["players"][0])
        self.assertIn("soc_code", payload["players"][0])
        self.assertIn("soc_title", payload["players"][0])
        self.assertIn("projected_boot_probability", payload["projected_boot_order"][0])

    def test_missing_predictions_file_returns_clear_sanitized_error(self) -> None:
        missing_path = Path(self.temp_dir.name) / "private" / "missing_predictions.json"
        api_server.DEFAULT_PREDICTIONS = missing_path

        status, payload = self._get_json("/api/predictions/current")

        self.assertEqual(status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(
            payload,
            {"error": "Prediction data is not available. Run `survivor-calculator build` before serving the API."},
        )
        self.assertNotIn(str(missing_path), payload["error"])
        self.assertNotIn(self.temp_dir.name, payload["error"])

    def test_invalid_predictions_file_returns_sanitized_error(self) -> None:
        self.predictions_path.write_text(
            json.dumps({"metadata": {"source_workbook": str(Path.home())}}),
            encoding="utf-8",
        )

        status, payload = self._get_json("/api/current-season")

        self.assertEqual(status, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertEqual(payload, {"error": "Prediction data is invalid. Rebuild predictions before serving the API."})
        self.assertNotIn(str(self.predictions_path), payload["error"])
        self.assertNotIn(str(Path.home()), payload["error"])

    def _get_json(self, path: str) -> tuple[int, dict[str, object]]:
        port = self.httpd.server_address[1]
        url = f"http://127.0.0.1:{port}{path}"
        try:
            with urlopen(url, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
