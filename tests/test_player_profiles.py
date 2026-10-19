from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from fixtures import minimal_core_tables
from survivor_calculator import api, server
from survivor_calculator.analytics import build_player_season_rows, export_player_season_rows
from survivor_calculator.baseline import build_predictions, save_predictions
from survivor_calculator.features import build_features


class PlayerProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.predictions = Path(self.directory.name) / "predictions.json"
        self.analytics = Path(self.directory.name) / "analytics.csv"
        tables = minimal_core_tables()
        save_predictions(build_predictions(build_features(tables), Path("fixture.xlsx")), self.predictions)
        self.rows = build_player_season_rows(tables)
        self.write_rows()

    def write_rows(self) -> None:
        export_player_season_rows(self.rows, self.analytics)

    def profile(self, castaway_id: str = "S2-C") -> dict[str, object]:
        return api.player_profile_payload(castaway_id, self.predictions, self.analytics)

    def test_profile_exposes_observed_totals_and_forecast_separately(self) -> None:
        profile = self.profile()
        self.assertEqual(profile["metadata"]["current_season"], 2)
        self.assertEqual(profile["player"]["castaway_id"], "S2-C")
        self.assertEqual(profile["stats_status"], "available")
        self.assertEqual(profile["stats"]["challenge_wins_total"], 1)
        self.assertEqual(profile["stats"]["votes_received_total"], 1)
        self.assertEqual(profile["stats"]["votes_cast_total"], 0)
        self.assertEqual(profile["stats"]["confessionals_total"], 3)
        self.assertNotIn("source_workbook", profile["metadata"])
        self.assertNotIn("final_place", profile["stats"])

    def test_current_us_season_and_exact_identity_are_required(self) -> None:
        base = next(row for row in self.rows if row["castaway_id"] == "S2-C")
        self.rows += [
            {**base, "season": 1, "votes_received_total": 999},
            {**base, "version": "AU", "version_season": "AU2", "votes_received_total": 999},
            {**base, "version": "", "version_season": "AU2", "votes_received_total": 999},
            {**base, "castaway_id": "someone-else", "votes_received_total": 999},
        ]
        self.write_rows()
        self.assertEqual(self.profile()["stats"]["votes_received_total"], 1)

    def test_duplicate_matches_are_unknown_instead_of_double_counted(self) -> None:
        self.rows += [next(row for row in self.rows if row["castaway_id"] == "S2-C")]
        self.write_rows()
        profile = self.profile()
        self.assertEqual(profile["stats_status"], "unavailable")
        self.assertTrue(all(value is None for value in profile["stats"].values()))

    def test_missing_invalid_and_nonfinite_stats_remain_unknown(self) -> None:
        for row in self.rows:
            if row["castaway_id"] == "S2-C":
                row.update(age="", votes_received_total="NaN", votes_cast_total="-1", confessionals_total="bad", confessional_time_total="inf")
        self.write_rows()
        stats = self.profile()["stats"]
        for field in ("age", "votes_received_total", "votes_cast_total", "confessionals_total", "confessional_time_total"):
            self.assertIsNone(stats[field])
        self.assertEqual(stats["challenge_wins_total"], 1)

    def test_missing_analytics_preserves_forecast_without_inventing_zeros(self) -> None:
        self.analytics.unlink()
        profile = self.profile()
        self.assertEqual(profile["stats_status"], "unavailable")
        self.assertEqual(profile["player"]["castaway_id"], "S2-C")
        self.assertIsNone(profile["stats"]["challenge_wins_total"])

    def test_unknown_and_invalid_ids_return_sanitized_404(self) -> None:
        for identifier in ("unknown", "../private", "S2-C/extra", "x" * 100):
            with self.subTest(identifier=identifier), self.assertRaises(api.PlayerNotFound) as raised:
                self.profile(identifier)
            self.assertEqual(raised.exception.status_code, 404)
            self.assertNotIn(self.directory.name, raised.exception.message)

    def test_standard_library_profile_endpoint(self) -> None:
        with patch.object(server, "DEFAULT_PREDICTIONS", self.predictions), patch.object(server, "DEFAULT_ANALYTICS", self.analytics):
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.SurvivorApiHandler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{httpd.server_address[1]}"
                with urlopen(base + "/api/players/S2-C", timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(json.load(response)["stats"]["votes_received_total"], 1)
                with self.assertRaises(HTTPError) as raised:
                    urlopen(base + "/api/players/missing", timeout=5)
                self.assertEqual(raised.exception.code, 404)
            finally:
                httpd.shutdown()
                thread.join(timeout=5)
                httpd.server_close()

    @unittest.skipIf(api.FastAPI is None, "Install existing API extras to test FastAPI.")
    def test_fastapi_profile_route_and_missing_player(self) -> None:
        original = api.player_profile_payload
        with patch.object(api, "player_profile_payload", side_effect=lambda identifier: original(identifier, self.predictions, self.analytics)):
            app = api.create_app()
            for identifier, expected in (("S2-C", 200), ("missing", 404)):
                messages: list[dict] = []

                async def run() -> None:
                    async def receive() -> dict:
                        return {"type": "http.request", "body": b"", "more_body": False}

                    async def send(message: dict) -> None:
                        messages.append(message)

                    await app({
                        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                        "method": "GET", "scheme": "http", "path": f"/api/players/{identifier}",
                        "query_string": b"", "root_path": "", "headers": [],
                        "server": ("test", 80), "client": ("test", 123),
                    }, receive, send)

                asyncio.run(run())
                start = next(message for message in messages if message["type"] == "http.response.start")
                self.assertEqual(start["status"], expected)


if __name__ == "__main__":
    unittest.main()
