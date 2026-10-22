from __future__ import annotations

import unittest
from copy import deepcopy

from fixtures import minimal_core_tables
from survivor_calculator.council_events import normalize_councils
from survivor_calculator.evaluation import _group_events
from survivor_calculator.event_alignment import align_events
from survivor_calculator.features import build_features


def returning_tables() -> dict[str, list[dict[str, str | None]]]:
    """Three players, two completed exits, one explicitly observed return."""
    tables = minimal_core_tables()
    tables["Castaways"] = [r for r in tables["Castaways"] if r["season"] != "1"] + [
        {"season": "1", "castaway_id": p, "castaway": p, "age": "30"} for p in "ABC"]
    tables["Boot Mapping"] = [r for r in tables["Boot Mapping"] if r["season"] != "1"]
    for stage, episode, order, n_boots, players in [(1, 1, 0, 0, "ABC"), (2, 2, 1, 1, "BC"),
                                                   (3, 3, 2, 1, "AC"), (4, 4, 3, 2, "C")]:
        for p in players:
            tables["Boot Mapping"].append({"season": "1", "episode": str(episode), "order": str(order),
                "n_boots": str(n_boots), "final_n": str(len(players)), "sog_id": str(stage),
                "castaway_id": p, "castaway": p, "tribe": "T", "tribe_status": "Merged",
                "game_status": "Returned" if stage == 3 and p == "A" else "In the game"})
    tables["Boot Order"] = [{"season": "1", "episode": str(i), "day": str(3*i), "order": str(i),
                              "castaway_id": p, "result": "Voted out" if i < 4 else "Sole Survivor"}
                             for i, p in enumerate("ABAC", 1)]
    tables["Vote History"] = [r for r in tables["Vote History"] if r["season"] != "1"]
    for i, target in enumerate("ABA", 1):
        tables["Vote History"].append({"season": "1", "episode": str(i), "day": str(3*i),
            "order": str(i), "sog_id": str(i), "castaway_id": "C", "vote_id": target,
            "voted_out_id": target, "nullified": "0"})
    return tables


class EventAlignmentTests(unittest.TestCase):
    def test_returned_player_and_repeated_exit_use_chronological_cutoff(self) -> None:
        features = build_features(returning_tables())
        event = [r for r in features.historical_rows if r["episode"] == 3]
        self.assertEqual({r["castaway_id"] for r in event}, {"A", "C"})
        self.assertEqual({r["n_boots"] for r in event}, {1})
        self.assertEqual({r["completed_exit_order"] for r in event}, {2})
        self.assertEqual(next(r for r in event if r["castaway_id"] == "A")["target_next_boot"], 1)
        self.assertEqual(next(r for r in event if r["castaway_id"] == "C")["votes_cast_to_date"], 2)

    def test_identity_join_handles_source_order_disagreement_without_offset(self) -> None:
        tables = returning_tables()
        tables["Boot Order"][2]["order"] = "99"
        features = build_features(tables)
        event = [r for r in features.historical_rows if r["episode"] == 3]
        self.assertEqual(len(event), 2)
        disagreements = [a for a in features.alignment_audit if a["status"] == "source_order_disagreement"]
        self.assertEqual(disagreements[0]["boot_order"], 99)
        self.assertEqual(disagreements[0]["vote_history_order"], 3)

    def test_non_voting_exit_does_not_select_a_later_vote(self) -> None:
        tables = returning_tables()
        tables["Boot Order"][1]["result"] = "Quit"
        features = build_features(tables)
        self.assertFalse(any(r["episode"] == 2 for r in features.historical_rows))
        self.assertTrue(any(a.get("episode") == 2 and a["reason"] == "next_exit_is_non_voting_or_terminal"
                            for a in features.alignment_audit))

    def test_incomplete_roster_is_excluded_even_if_target_is_present(self) -> None:
        tables = returning_tables()
        tables["Boot Mapping"] = [r for r in tables["Boot Mapping"]
                                   if not (r["season"] == "1" and r["episode"] == "1" and r["castaway_id"] == "C")]
        features = build_features(tables)
        self.assertFalse(any(r["episode"] == 1 for r in features.historical_rows))
        self.assertTrue(any(a["reason"] == "conflicting_or_incomplete_roster" for a in features.alignment_audit))

    def test_future_roster_cannot_repair_an_earlier_missing_player(self) -> None:
        tables = returning_tables()
        tables["Boot Mapping"] = [r for r in tables["Boot Mapping"]
                                   if not (r["season"] == "1" and r["episode"] == "1" and r["castaway_id"] == "C")]
        for r in tables["Boot Mapping"]:
            if r["season"] == "1" and r["episode"] == "1":
                r["final_n"] = "2"
        before = build_features(tables)
        tables["Boot Mapping"].append({**tables["Boot Mapping"][-1], "episode": "9", "sog_id": "9"})
        after = build_features(tables)
        self.assertFalse(any(r["episode"] == 1 for r in after.historical_rows))
        self.assertEqual(before.historical_rows, after.historical_rows)

    def test_future_ballots_narrative_and_exits_do_not_change_earlier_features(self) -> None:
        tables = returning_tables()
        before = [r for r in build_features(tables).historical_rows if r["episode"] < 3]
        tables["Vote History"][-1]["vote_id"] = "C"
        tables["Confessionals"].append({"season": "1", "episode": "3", "castaway_id": "C",
                                        "confessional_count": "9999"})
        tables["Boot Order"].append({"season": "1", "episode": "9", "day": "99", "order": "9",
                                     "castaway_id": "Z", "result": "Voted out"})
        after = [r for r in build_features(tables).historical_rows if r["episode"] < 3]
        self.assertEqual(before, after)

    def test_same_episode_only_completed_council_is_visible(self) -> None:
        tables = returning_tables()
        for name in ("Boot Mapping", "Boot Order", "Vote History"):
            for row in tables[name]:
                if row.get("season") == "1" and row.get("episode") == "2":
                    row["episode"] = "1"
        before = build_features(tables)
        later = [r for r in before.historical_rows if r["completed_exit_order"] == 1]
        self.assertEqual(next(r for r in later if r["castaway_id"] == "C")["votes_cast_to_date"], 1)
        tables["Vote History"][-2]["vote_id"] = "C"
        after = build_features(tables)
        self.assertEqual([r for r in before.historical_rows if r["completed_exit_order"] <= 1],
                         [r for r in after.historical_rows if r["completed_exit_order"] <= 1])

    def test_day_conflict_keeps_target_excluded(self) -> None:
        tables = returning_tables()
        tables["Boot Order"][2]["day"] = "99"
        features = build_features(tables)
        self.assertFalse(any(r["episode"] == 3 for r in features.historical_rows))
        self.assertTrue(any(a["reason"] == "next_exit_has_no_unique_council_identity"
                            for a in features.alignment_audit))

    def test_temporary_exile_remains_an_active_candidate(self) -> None:
        tables = returning_tables()
        for row in tables["Boot Mapping"]:
            if row["season"] == "1" and row["episode"] == "1" and row["castaway_id"] == "C":
                row["game_status"] = "Exile Island"
        first = [r for r in build_features(tables).historical_rows if r["episode"] == 1]
        self.assertEqual({r["castaway_id"] for r in first}, set("ABC"))

    def test_ambiguous_exit_order_is_excluded_without_name_tiebreak(self) -> None:
        tables = returning_tables()
        tables["Boot Order"].append({**tables["Boot Order"][0], "castaway_id": "C"})
        features = build_features(tables)
        self.assertEqual(features.historical_rows, [])
        self.assertTrue(any(a["reason"] == "ambiguous_exit_sequence" for a in features.alignment_audit))

    def test_multiple_councils_for_one_exit_are_unavailable(self) -> None:
        tables = returning_tables()
        tables["Vote History"].append({**tables["Vote History"][-1], "sog_id": "99"})
        _, councils, audit = align_events(tables, normalize_councils(tables["Vote History"]))
        self.assertFalse(any(c.season == "US:1" and c.order == 3 for c in councils))
        self.assertTrue(any(a["reason"] == "multiple_councils_for_exit_identity" for a in audit))

    def test_input_row_order_does_not_change_alignment(self) -> None:
        tables = returning_tables()
        reversed_tables = {name: list(reversed(rows)) for name, rows in deepcopy(tables).items()}
        self.assertEqual(build_features(tables).historical_rows, build_features(reversed_tables).historical_rows)

    def test_later_stage_cannot_move_cutoff_back_or_replace_earlier_forecast(self) -> None:
        tables = returning_tables()
        for name in ("Boot Mapping", "Boot Order", "Vote History"):
            for row in tables[name]:
                if row.get("season") == "1" and row.get("episode") == "2":
                    row["episode"] = "1"
        before = build_features(tables)
        tables["Boot Mapping"].extend({**r, "sog_id": "99"} for r in list(tables["Boot Mapping"])
                                      if r["season"] == "1" and r["sog_id"] == "1")
        after = build_features(tables)
        self.assertEqual(before.historical_rows, after.historical_rows)
        self.assertTrue(any(a["reason"] == "non_monotone_or_pre_return_cutoff" for a in after.alignment_audit))

    def test_event_grouping_uses_cutoff_independent_of_net_boot_count(self) -> None:
        rows = [{"season": 1, "episode": 1, "n_boots": 0, "completed_exit_order": i} for i in (0, 1)]
        self.assertEqual(len(_group_events(rows)), 2)


if __name__ == "__main__":
    unittest.main()
