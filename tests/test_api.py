from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request
from urllib.request import urlopen

from fixtures import minimal_core_tables
from survivor_calculator import server as api_server
from survivor_calculator.analytics import build_player_season_rows, export_player_season_rows
from survivor_calculator.baseline import build_predictions, save_predictions
from survivor_calculator.features import build_features


class ApiEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.predictions_path = Path(self.temp_dir.name) / "current_predictions.json"
        self.analytics_path = Path(self.temp_dir.name) / "analytics_player_season.csv"
        tables = minimal_core_tables()
        export_player_season_rows(build_player_season_rows(tables), self.analytics_path)
        features = build_features(tables)
        bundle = build_predictions(features, Path("fixture.xlsx"))
        save_predictions(bundle, self.predictions_path)

        self.old_predictions_path = api_server.DEFAULT_PREDICTIONS
        self.old_analytics_path = api_server.DEFAULT_ANALYTICS
        api_server.DEFAULT_PREDICTIONS = self.predictions_path
        api_server.DEFAULT_ANALYTICS = self.analytics_path
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), api_server.SurvivorApiHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.thread.join(timeout=5)
        self.httpd.server_close()
        api_server.DEFAULT_PREDICTIONS = self.old_predictions_path
        api_server.DEFAULT_ANALYTICS = self.old_analytics_path
        self.temp_dir.cleanup()

    def test_health_endpoint_reports_ok(self) -> None:
        status, payload = self._get_json("/health")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload, {"status": "ok"})

    def test_timeline_index_and_exact_checkpoint(self) -> None:
        status, payload = self._get_json("/api/predictions/timeline")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["states"][0]["season"], 2)
        status, payload = self._get_json("/api/predictions/timeline/2/2/0")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["metadata"]["latest_episode"], 2)
        self.assertEqual(payload["timeline_context"]["checkpoint"], 0)
        status, _ = self._get_json("/api/predictions/timeline/1/1/0")
        self.assertEqual(status, HTTPStatus.NOT_FOUND)

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

    def test_analytics_schema_endpoint_returns_available_contract(self) -> None:
        status, payload = self._get_json("/api/analytics/schema")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["dataset"]["id"], "analytics_player_season")
        self.assertEqual(payload["dataset"]["row_count"], 4)
        self.assertIn("occupation", {dimension["id"] for dimension in payload["dimensions"]})
        self.assertIn("social_proxy_no_votes_rate", {metric["id"] for metric in payload["metrics"]})

    def test_analytics_presets_endpoint_returns_preset_configs(self) -> None:
        status, payload = self._get_json("/api/analytics/presets")

        self.assertEqual(status, HTTPStatus.OK)
        preset_ids = {preset["id"] for preset in payload["presets"]}
        self.assertEqual(len(preset_ids), 10)
        self.assertIn("occupations_cast_most_often", preset_ids)
        self.assertIn("age_buckets_most_winners", preset_ids)

    def test_analytics_query_endpoint_returns_chart_rows(self) -> None:
        status, payload = self._post_json(
            "/api/analytics/query",
            {
                "dimension": "age_bucket",
                "metric": "contestant_count",
                "filters": [{"field": "season", "operator": "equals", "value": "1"}],
                "sort": {"field": "label", "direction": "asc"},
            },
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["metadata"]["filtered_row_count"], 2)
        self.assertEqual(
            [(row["label"], row["value"], row["count"]) for row in payload["rows"]],
            [("25-34", 1, 1), ("35-44", 1, 1)],
        )

    def test_invalid_analytics_query_returns_sanitized_client_error(self) -> None:
        status, payload = self._post_json(
            "/api/analytics/query",
            {"dimension": "not_real", "metric": "contestant_count"},
        )

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload, {"error": "Unsupported dimension: not_real"})
        self.assertNotIn(str(self.analytics_path), payload["error"])
        self.assertNotIn(self.temp_dir.name, payload["error"])

    def test_missing_analytics_file_returns_clear_sanitized_error(self) -> None:
        missing_path = Path(self.temp_dir.name) / "private" / "missing_analytics.csv"
        api_server.DEFAULT_ANALYTICS = missing_path

        status, payload = self._get_json("/api/analytics/schema")

        self.assertEqual(status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(
            payload,
            {"error": "Analytics data is not available. Run `survivor-calculator build` before serving the API."},
        )
        self.assertNotIn(str(missing_path), payload["error"])
        self.assertNotIn(self.temp_dir.name, payload["error"])

    def _get_json(self, path: str) -> tuple[int, dict[str, object]]:
        port = self.httpd.server_address[1]
        url = f"http://127.0.0.1:{port}{path}"
        try:
            with urlopen(url, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        port = self.httpd.server_address[1]
        url = f"http://127.0.0.1:{port}{path}"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
