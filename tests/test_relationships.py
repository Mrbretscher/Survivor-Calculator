from __future__ import annotations

import unittest
from copy import deepcopy

from survivor_calculator.council_events import normalize_councils
from survivor_calculator.relationships import build_relationship_snapshot, social_features


def vote(exit_order: int, voter: str, target: str | None, **extra: str) -> dict[str, str | None]:
    return {"version": "US", "season": "1", "episode": str(exit_order), "order": str(exit_order),
            "day": str(exit_order * 3), "sog_id": str(exit_order), "tribe": "Old", "vote_order": "1",
            "castaway_id": voter, "vote_id": target, "nullified": "0", **extra}


def players(ids: tuple[str, ...] = ("1a", "1b", "1c", "1d", "2a", "2b"),
            episode: int = 4, n_boots: int = 3) -> list[dict[str, object]]:
    return [{"version": "US", "season": 1, "episode": episode, "n_boots": n_boots,
             "castaway_id": i, "castaway": i, "tribe": "Swapped",
             "original_tribe": i[0]} for i in ids]


def swap_votes() -> list[dict[str, str | None]]:
    rows = []
    for order in (1, 2, 3):
        rows.extend([vote(order, "1a", "1c", nullified="1"), vote(order, "1b", "1c", nullified="1"),
                     vote(order, "1c", f"X{order}"), vote(order, "1d", f"X{order}" if order < 3 else "1c")])
    return rows


def matrix(rows: list[dict[str, str | None]], roster: list[dict[str, object]] | None = None):
    snapshot = build_relationship_snapshot(normalize_councils(rows), roster or players())
    return snapshot, {(p["player_id"], p["other_id"]): p for p in snapshot["pairs"]}


class RelationshipTests(unittest.TestCase):
    def test_swap_fracture_and_protective_opposition(self) -> None:
        snapshot, pairs = matrix(swap_votes())
        self.assertEqual(pairs["1a", "1b"]["coordinated_councils"], 3)
        self.assertEqual(pairs["1c", "1d"]["coordinated_councils"], 2)
        self.assertEqual(pairs["1a", "1d"]["coordinated_councils"], 1)
        self.assertGreater(pairs["1c", "1d"]["coordination_strength"], pairs["1a", "1d"]["coordination_strength"])
        self.assertEqual(pairs["1a", "1c"]["targeting_councils"], 3)
        self.assertEqual(pairs["1a", "1d"]["targeting_councils"], 0)
        self.assertGreater(pairs["1d", "1a"]["protective_opposition"], 0)
        self.assertTrue(any(e["ally_id"] == "1c" for e in pairs["1d", "1a"]["protective_evidence"]))
        self.assertIsNone(pairs["1c", "2a"]["coordination_strength"])
        self.assertIsNone(pairs["2a", "2b"]["coordination_strength"])
        self.assertGreater(social_features(snapshot)["1a"]["social_protective_opposition_received"], 0)

    def test_removing_partner_evidence_removes_inferred_protection(self) -> None:
        rows = [r for r in swap_votes() if r["castaway_id"] != "1d"]
        _, pairs = matrix(rows)
        self.assertIsNone(pairs["1d", "1a"]["protective_opposition"])

    def test_future_votes_cannot_change_a_snapshot(self) -> None:
        rows = swap_votes()
        before, _ = matrix(rows)
        rows.extend([vote(4, "2a", "1a"), vote(4, "2b", "1a")])
        self.assertEqual(before, matrix(rows)[0])

    def test_same_episode_later_council_is_excluded_by_exit_order(self) -> None:
        rows = [vote(1, "1a", "1c", episode="1"), vote(2, "1b", "1c", episode="1")]
        snapshot, pairs = matrix(rows, players(episode=1, n_boots=1))
        self.assertEqual(len(snapshot["councils"]), 1)
        self.assertEqual(pairs["1b", "1c"]["targeting_councils"], 0)

    def test_no_vote_is_not_hostility_or_shared_opportunity(self) -> None:
        _, pairs = matrix([vote(1, "1a", None, vote_event="Lost vote"), vote(1, "1b", "1c")])
        self.assertEqual(pairs["1a", "1b"]["shared_councils"], 0)
        self.assertIsNone(pairs["1a", "1b"]["targeting_rate"])

    def test_nullification_preserves_targeting(self) -> None:
        _, pairs = matrix([vote(1, "1a", "1c", nullified="1")])
        self.assertEqual(pairs["1a", "1c"]["targeting_councils"], 1)

    def test_extra_ballots_do_not_multiply_shared_councils(self) -> None:
        rows = [vote(1, "1a", "X", vote_event="Extra vote"), vote(1, "1b", "X"), vote(1, "1c", "Y")]
        _, base = matrix(rows)
        rows.append(deepcopy(rows[0]))
        _, repeated = matrix(rows)
        self.assertEqual(repeated["1a", "1b"]["coordination_strength"], base["1a", "1b"]["coordination_strength"])
        self.assertEqual(repeated["1a", "1b"]["shared_councils"], 1)

    def test_duplicate_ordinary_record_removed_and_reported(self) -> None:
        row = vote(1, "1a", "X")
        councils = normalize_councils([row, deepcopy(row)])
        self.assertEqual(len(councils[0].rounds[1]), 1)
        self.assertIn("Exact duplicate ordinary record removed.", councils[0].warnings)

    def test_revote_is_not_a_new_coalition_observation(self) -> None:
        _, pairs = matrix([vote(1, "1a", "X"), vote(1, "1b", "Y"),
                           vote(1, "1a", "X", vote_order="2"), vote(1, "1b", "X", vote_order="2")])
        self.assertEqual(pairs["1a", "1b"]["shared_councils"], 1)
        self.assertEqual(pairs["1a", "1b"]["coordinated_councils"], 0)

    def test_documented_split_is_not_assumed_for_unannotated_split(self) -> None:
        rows = [vote(1, "1a", "X"), vote(1, "1b", "Y")]
        self.assertEqual(matrix(rows)[1]["1a", "1b"]["coordinated_councils"], 0)
        rows[0]["split_vote"], rows[1]["split_vote"] = "X, Y", "Y, X"
        self.assertEqual(matrix(rows)[1]["1a", "1b"]["coordinated_councils"], 1)

    def test_incomplete_split_annotation_does_not_invent_coordination(self) -> None:
        rows = [vote(1, "1a", "X", split_vote="X"), vote(1, "1b", "Y", split_vote="X")]
        self.assertEqual(matrix(rows)[1]["1a", "1b"]["coordinated_councils"], 0)

    def test_unanimous_agreement_has_less_distinguishing_weight(self) -> None:
        rows = [vote(1, "1a", "X"), vote(1, "1b", "X"), vote(1, "1c", "X")]
        unanimous = matrix(rows)[1]["1a", "1b"]["coordination_strength"]
        rows[2]["vote_id"] = "Y"
        contested = matrix(rows)[1]["1a", "1b"]["coordination_strength"]
        self.assertLess(unanimous, contested)

    def test_franchise_and_season_isolation(self) -> None:
        rows = swap_votes()
        before, _ = matrix(rows)
        rows.extend([vote(1, "2a", "1a", version="AU"), vote(1, "2b", "1a", season="2")])
        self.assertEqual(before, matrix(rows)[0])

    def test_joint_council_not_fragmented_by_original_tribe(self) -> None:
        rows = [vote(1, "1a", "X", tribe="One"), vote(1, "2a", "X", tribe="Two")]
        self.assertEqual(len(normalize_councils(rows)), 1)
        self.assertEqual(matrix(rows)[1]["1a", "2a"]["shared_councils"], 1)

    def test_current_tribe_limits_actionable_protection(self) -> None:
        roster = players()
        next(p for p in roster if p["castaway_id"] == "1c")["tribe"] = "Elsewhere"
        self.assertIsNone(matrix(swap_votes(), roster)[1]["1d", "1a"]["protective_opposition"])

    def test_permuting_source_and_players_preserves_evidence(self) -> None:
        self.assertEqual(matrix(swap_votes())[0], matrix(list(reversed(swap_votes())), list(reversed(players())))[0])

    def test_rock_and_fire_results_are_not_votes(self) -> None:
        rows = [vote(1, "1a", "1c", vote_event="Rock draw"),
                vote(1, "1b", "1c", vote_event="Fire challenge (f4)")]
        _, pairs = matrix(rows)
        self.assertEqual(pairs["1a", "1c"]["targeting_councils"], 0)
        self.assertEqual(pairs["1b", "1c"]["targeting_councils"], 0)

    def test_missing_order_only_allows_prior_episodes(self) -> None:
        rows = [vote(1, "1a", "1c", order="")]
        self.assertEqual(len(matrix(rows, players(episode=1))[0]["councils"]), 0)
        self.assertEqual(len(matrix(rows, players(episode=2))[0]["councils"]), 1)


if __name__ == "__main__":
    unittest.main()
