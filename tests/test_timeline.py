from __future__ import annotations

import asyncio
import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fixtures import minimal_core_tables
from survivor_calculator.api import PredictionApiError, PredictionDataInvalid, create_app, timeline_payload
from survivor_calculator.baseline import HistoricalRateModel, build_predictions, save_predictions
from survivor_calculator.features import FeatureBuildResult, build_features


def timeline_features() -> FeatureBuildResult:
    """Six completed seasons, two earlier live states and two same-episode states."""
    base = build_features(minimal_core_tables())
    roster = [row for row in base.historical_rows if row["episode"] == 1]
    historical = [{**row, "season": season} for season in range(1, 7) for row in roster]
    current = [{**row, "season": 7, "episode": 3, "completed_exit_order": 1} for row in roster]
    early = [{**row, "season": 7, "episode": 1, "completed_exit_order": 0} for row in roster]
    same_episode = [{**row, "season": 7, "episode": 3, "completed_exit_order": 0} for row in roster]
    return replace(base, historical_rows=historical, current_rows=current, current_season=7,
                   latest_episode=3, latest_final_n=len(roster),
                   timeline_rows=historical + early + same_episode + current,
                   timeline_episodes=[(7, 1), (7, 2), (7, 3)])


class TimelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "predictions.json"
        self.features = timeline_features()
        self.bundle = build_predictions(self.features, "fixture.xlsx")
        save_predictions(self.bundle, self.path)

    def test_current_model_fits_only_recorded_training_seasons(self) -> None:
        self.assertEqual(self.bundle.metadata["training_seasons"], [1])
        self.assertEqual(self.bundle.evaluation["split"]["holdout_seasons"], [2, 3, 4, 5, 6])
        model = HistoricalRateModel().fit([row for row in self.features.historical_rows if row["season"] == 1])
        by_id = {row["castaway_id"]: row for row in self.features.current_rows}
        for player in self.bundle.players:
            self.assertEqual(player["raw_next_boot_risk"], model.predict_risk(by_id[player["castaway_id"]]))

    def test_heldout_outcomes_do_not_change_current_or_timeline_predictions(self) -> None:
        changed = copy.deepcopy(self.features)
        for row in changed.historical_rows:
            if row["season"] != 1:
                row["target_next_boot"] = 1 - row["target_next_boot"]
        other = build_predictions(changed, "fixture.xlsx")
        self.assertEqual(self.bundle.players, other.players)
        self.assertEqual(self.bundle.timeline, other.timeline)

    def test_index_excludes_training_seasons_and_keeps_live_and_multi_council_states(self) -> None:
        payload = timeline_payload(self.path)
        self.assertEqual({state["season"] for state in payload["states"]}, {2, 3, 4, 5, 6, 7})
        self.assertTrue(all("players" not in state for state in payload["states"]))
        self.assertEqual([state["checkpoint"] for state in payload["states"] if state["season"] == 7 and state["episode"] == 3], [0, 1])
        self.assertTrue(any(state["season"] == 7 and state["episode"] == 1 for state in payload["states"]))

    def test_detail_matches_current_board_and_normalizes_probabilities(self) -> None:
        payload = timeline_payload(self.path, season=7, episode=3, checkpoint=1)
        self.assertEqual(payload["players"], self.bundle.players)
        self.assertEqual(payload["projected_boot_order"], self.bundle.projected_boot_order)
        self.assertEqual(payload["timeline_context"]["checkpoint"], 1)
        for state in timeline_payload(self.path)["states"]:
            detail = timeline_payload(self.path, season=state["season"], episode=state["episode"], checkpoint=state["checkpoint"])
            for field in ("winner_probability", "next_boot_probability"):
                self.assertAlmostEqual(sum(row[field] for row in detail["players"]), 1.0)

    def test_known_episode_without_forecast_remains_in_coverage(self) -> None:
        coverage = timeline_payload(self.path)["episodes"]
        self.assertIn({"season": 7, "episode": 2, "available": False}, coverage)
        self.assertIn({"season": 7, "episode": 3, "available": True}, coverage)
        with self.assertRaises(PredictionApiError) as raised:
            timeline_payload(self.path, season=7, episode=2, checkpoint=0)
        self.assertEqual(raised.exception.status_code, 404)

    def test_unknown_future_and_training_requests_return_404(self) -> None:
        for season, episode, checkpoint in [(1, 1, 0), (8, 1, 0), (7, 3, 9), (7, 9, 0)]:
            with self.subTest(season=season, episode=episode, checkpoint=checkpoint), self.assertRaises(PredictionApiError) as raised:
                timeline_payload(self.path, season=season, episode=episode, checkpoint=checkpoint)
            self.assertEqual(raised.exception.status_code, 404)

    def test_corrupt_or_in_sample_artifacts_are_rejected(self) -> None:
        original = self.bundle.to_dict()
        for mutation in ("training", "duplicate", "nan", "normalization", "missing_provenance", "future"):
            payload = copy.deepcopy(original)
            state = payload["timeline"]["states"][0]
            if mutation == "training":
                state["season"] = 1
            elif mutation == "duplicate":
                payload["timeline"]["states"].append(copy.deepcopy(state))
            elif mutation == "nan":
                state["players"][0]["next_boot_probability"] = float("nan")
            elif mutation == "normalization":
                state["players"][0]["next_boot_probability"] = 0.0
            elif mutation == "missing_provenance":
                del payload["metadata"]["training_seasons"]
            else:
                state.update(season=7, episode=99)
            self.path.write_text(json.dumps(payload), encoding="utf-8")
            with self.subTest(mutation=mutation), self.assertRaises(PredictionDataInvalid):
                timeline_payload(self.path)

    def test_legacy_snapshot_reports_timeline_unavailable(self) -> None:
        payload = self.bundle.to_dict()
        del payload["timeline"]
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(PredictionApiError) as raised:
            timeline_payload(self.path)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn(str(self.path), raised.exception.message)

    def test_small_data_has_only_current_unseen_season(self) -> None:
        bundle = build_predictions(build_features(minimal_core_tables()), "fixture.xlsx")
        self.assertEqual(bundle.metadata["training_seasons"], [1])
        self.assertEqual({state["season"] for state in bundle.timeline["states"]}, {2})

    def test_pooled_split_never_replays_before_last_training_season(self) -> None:
        features = replace(self.features, historical_rows=[
            {**row, "season": season} for season in range(1, 11) for row in self.features.historical_rows[:2]
        ], current_season=11, current_rows=[{**row, "season": 11} for row in self.features.current_rows])
        features = replace(features, timeline_rows=features.historical_rows + features.current_rows)
        bundle = build_predictions(features, "fixture.xlsx", evaluation_strategy="pooled-random")
        last = max(bundle.metadata["training_seasons"])
        self.assertTrue(all(state["season"] > last for state in bundle.timeline["states"]))
        self.assertTrue(any(state["season"] == 11 for state in bundle.timeline["states"]))

    def test_feature_builder_retains_earlier_live_states_without_training_on_them(self) -> None:
        tables = minimal_core_tables()
        tables["Boot Order"].append({"season": "2", "order": "1", "castaway_id": "S2-C"})
        tables["Boot Mapping"] = [row for row in tables["Boot Mapping"] if not (row["season"] == "2" and row["episode"] == "2" and row["castaway_id"] == "S2-C")]
        for row in tables["Boot Mapping"]:
            if row["season"] == "2" and row["episode"] == "2":
                row.update(n_boots="1", final_n="1")
        features = build_features(tables)
        self.assertEqual({row["episode"] for row in features.timeline_rows if row["season"] == 2}, {1, 2})
        self.assertTrue(all(row["season"] == 1 for row in features.historical_rows))
        early = [row for row in features.timeline_rows if row["season"] == 2 and row["episode"] == 1]
        self.assertTrue(all(row["votes_cast_to_date"] == 0 and row["confessionals_to_date"] == 0 for row in early))

    def test_fastapi_serves_index_detail_and_unavailable_requests(self) -> None:
        try:
            app = create_app()
        except RuntimeError:
            self.skipTest("Existing [api] extras are not installed")

        async def request(path: str) -> tuple[int, dict]:
            messages = []
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}
            async def send(message):
                messages.append(message)
            await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                       "method": "GET", "scheme": "http", "path": path, "query_string": b"",
                       "root_path": "", "headers": [], "server": ("test", 80), "client": ("test", 1)}, receive, send)
            status = next(message["status"] for message in messages if message["type"] == "http.response.start")
            body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
            return status, json.loads(body)

        with patch("survivor_calculator.api.DEFAULT_PREDICTIONS", self.path):
            for route, status in [("", 200), ("/7/3/1", 200), ("/1/1/0", 404), ("/invalid/1/0", 422)]:
                actual, payload = asyncio.run(request("/api/predictions/timeline" + route))
                self.assertEqual(actual, status)
                self.assertNotIn(str(self.path), json.dumps(payload))
