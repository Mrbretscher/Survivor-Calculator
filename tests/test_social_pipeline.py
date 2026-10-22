from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from fixtures import minimal_core_tables
from survivor_calculator.baseline import DirectSocialRateModel, SocialRateModel, build_predictions, resolve_model_name
from survivor_calculator.cli import build_from_tables
from survivor_calculator.features import build_features


class TemporalFeatureTests(unittest.TestCase):
    def test_target_episode_votes_and_narrative_cannot_leak_into_training(self) -> None:
        tables = minimal_core_tables()
        before = build_features(tables).historical_rows
        first = next(r for r in before if r["episode"] == 1 and r["castaway_id"] == "S1-A")
        self.assertEqual(first["votes_received_to_date"], 0)
        self.assertEqual(first["confessionals_to_date"], 0)
        tables["Vote History"].append({"season": "1", "episode": "1", "order": "1",
                                      "castaway_id": "S1-A", "vote_id": "S1-B", "nullified": "1"})
        tables["Confessionals"][0]["confessional_count"] = "999"
        after = build_features(tables).historical_rows
        self.assertEqual([r for r in before if r["episode"] == 1], [r for r in after if r["episode"] == 1])

    def test_council_order_allows_earlier_councils_in_same_episode(self) -> None:
        tables = minimal_core_tables()
        for state in tables["Boot Mapping"]:
            if state["season"] == "1":
                state["episode"] = "1"
        tables["Vote History"][0]["order"] = "1"
        tables["Vote History"].append({"season": "1", "episode": "1", "order": "2",
                                      "castaway_id": "S1-B", "vote_id": "S1-A", "nullified": "0"})
        rows = build_features(tables).historical_rows
        self.assertTrue(all(r["votes_cast_to_date"] == 0 for r in rows if r["n_boots"] == 0))
        later = next(r for r in rows if r["n_boots"] == 1)
        self.assertEqual(later["votes_cast_to_date"], 1)

    def test_future_tribe_assignment_does_not_fill_earlier_unknown_origin(self) -> None:
        tables = minimal_core_tables()
        tables["Boot Mapping"][0]["tribe"] = "No Tribe"
        first = build_features(tables).historical_rows
        tables["Boot Mapping"].append({**tables["Boot Mapping"][0], "episode": "2", "tribe": "Future Tribe"})
        updated = build_features(tables).historical_rows
        self.assertEqual([r for r in first if r["episode"] == 1], [r for r in updated if r["episode"] == 1])

    def test_current_and_historical_use_same_prior_episode_rule(self) -> None:
        tables = minimal_core_tables()
        features = build_features(tables)
        cam = next(r for r in features.current_rows if r["castaway_id"] == "S2-C")
        tables["Confessionals"].append({"season": "2", "episode": "2", "castaway_id": "S2-C",
                                       "confessional_count": "100", "confessional_time": "100"})
        updated = next(r for r in build_features(tables).current_rows if r["castaway_id"] == "S2-C")
        self.assertEqual(cam, updated)

    def test_non_voting_exits_do_not_supply_training_labels(self) -> None:
        tables = minimal_core_tables()
        tables["Boot Order"][0]["result"] = "Quit"
        features = build_features(tables)
        self.assertFalse(any(r["n_boots"] == 0 for r in features.historical_rows))
        self.assertGreater(features.excluded_non_vote_states, 0)

    def test_stage_roster_reconciles_one_inconsistent_exit_count(self) -> None:
        tables = minimal_core_tables()
        for row in tables["Boot Mapping"]:
            if row["season"] == "1" and row["episode"] == "1":
                row["sog_id"] = "1"
                if row["castaway_id"] == "S1-B":
                    row["n_boots"] = "1"
        features = build_features(tables)
        self.assertEqual(features.reconciled_state_rows, 1)
        self.assertEqual(len([r for r in features.historical_rows if r["episode"] == 1]), 2)

    def test_workbook_feature_path_does_not_mix_franchises(self) -> None:
        tables = minimal_core_tables()
        for name, rows in list(tables.items()):
            if name != "Castaway Details":
                duplicates = [{**r, "version": "AU", "season": "99"} for r in deepcopy(rows)]
                rows.extend(duplicates)
        self.assertEqual(build_features(tables).current_season, 2)

    def test_current_state_uses_latest_completed_exit_within_episode(self) -> None:
        tables = minimal_core_tables()
        latest = {**tables["Boot Mapping"][-1], "n_boots": "1", "final_n": "1", "sog_id": "3"}
        tables["Boot Mapping"].append(latest)
        features = build_features(tables)
        self.assertEqual(len(features.current_rows), 1)
        self.assertEqual(features.current_rows[0]["castaway_id"], "S2-D")


class SocialPipelineTests(unittest.TestCase):
    def test_social_and_direct_model_flags_and_missing_evidence(self) -> None:
        self.assertEqual(resolve_model_name("social-rate-next-boot"), "social_rate_next_boot")
        row = {"social_strongest_partner": None}
        model = SocialRateModel()
        self.assertEqual(model._rate_features(row)["social_strongest_partner"], "unknown")
        self.assertNotIn("social_protective_opposition_received", DirectSocialRateModel()._rate_features(row))
        self.assertIn("social_protective_opposition_received", model._rate_features(row))

    def test_build_exports_separate_evidence_with_matching_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            build_from_tables(minimal_core_tables(), Path("fixture.xlsx"), output,
                              "social_rate_next_boot", "chronological")
            artifact = json.loads((output / "current_relationships.json").read_text(encoding="utf-8"))
            predictions = json.loads((output / "current_predictions.json").read_text(encoding="utf-8"))
            self.assertEqual(artifact["cutoff"]["episode"], predictions["metadata"]["latest_episode"])
            self.assertIn("feature_timing_version", artifact)
            self.assertEqual(len(artifact["pairs"]), 2)
            self.assertEqual(predictions["metadata"]["model_name"], "social_rate_next_boot")

    def test_chronological_social_comparison_has_direct_ablation(self) -> None:
        features = build_features(minimal_core_tables())
        # Replicate fixture seasons to exercise the real evaluator/model interface.
        rows = []
        for season in range(1, 8):
            rows.extend({**r, "season": season} for r in features.historical_rows)
        from dataclasses import replace
        expanded = replace(features, historical_rows=rows, current_season=8)
        bundle = build_predictions(expanded, "fixture.xlsx", model_name="social-rate-next-boot")
        names = {r["name"] for r in bundle.evaluation["baseline_comparisons"]}
        self.assertIn("social_direct_next_boot", names)
        self.assertIn("historical_rate_baseline", names)
        self.assertEqual(bundle.metadata["evaluation_strategy"], "chronological")
        diagnostics = bundle.evaluation["relationship_diagnostics"]
        self.assertEqual(diagnostics["season_block_bootstrap"]["samples"], 1000)
        self.assertIn("log_loss_delta_vs_baseline_95pct", diagnostics["season_block_bootstrap"]["intervals"])
        self.assertEqual(diagnostics["slices"]["sparse_relationship_history"]["candidates"], bundle.evaluation["split"]["evaluated_candidates"])


if __name__ == "__main__":
    unittest.main()
