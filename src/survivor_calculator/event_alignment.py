"""Source-validated forecast rosters and chronological exit cutoffs.

n_boots is a net-removal feature, not an event identifier. Alignment uses only
current/past roster evidence; later rosters never repair an earlier snapshot.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace

from survivor_calculator.council_events import Council, integer, season_key

ACTIVE_STATUSES = {"In the game", "Returned", "Exile Island"}


@dataclass(frozen=True)
class Exit:
    """A chronological source identity, including non-voting exits/placements."""
    index: int
    record: dict[str, str | None]

    @property
    def episode(self) -> int:
        return integer(self.record.get("episode")) or 0

    @property
    def player(self) -> str:
        return str(self.record.get("castaway_id") or "")

    @property
    def eligible(self) -> bool:
        result = str(self.record.get("result") or "").lower()
        # Empty results support the existing small, legacy fixtures only.
        return "voted out" in result or (not result and not self.episode)


@dataclass(frozen=True)
class AlignedState:
    season: int
    episode: int
    stage: int
    n_boots: int
    completed_exit_order: int
    roster: dict[str, dict[str, str | None]]
    next_exit: Exit | None
    audit: dict[str, object]


def align_events(
    tables: dict[str, list[dict[str, str | None]]], councils: list[Council],
) -> tuple[list[AlignedState], list[Council], list[dict[str, object]]]:
    """Match each complete roster to exactly one chronological exit prefix.

    Exit identity uses season/episode/day/eliminated ID, independent of source
    order numbers. Within a day, Boot Order's source order breaks ties. A council
    with conflicting identities is unavailable. Incomplete rosters, missing
    counts, chronological conflicts and non-voting next exits remain explicit
    exclusions. No later eligible vote is substituted for a non-voting exit.
    """
    by_season: dict[str, list[dict[str, str | None]]] = defaultdict(list)
    for row in tables["Boot Order"]:
        by_season[season_key(row)].append(row)
    timelines: dict[str, list[Exit]] = {}
    ambiguous_sequences: set[str] = set()
    for season, records in by_season.items():
        # Exact duplicate records are not additional exits.
        unique = {tuple(sorted(r.items())): r for r in records}
        ordered = sorted(unique.values(), key=lambda r: (
            integer(r.get("episode")) or 0, integer(r.get("day")) or 0,
            integer(r.get("order")) or 0, str(r.get("castaway_id") or "")))
        keys = [(integer(r.get("episode")), integer(r.get("day")), integer(r.get("order")))
                for r in ordered]
        if len(keys) != len(set(keys)):
            ambiguous_sequences.add(season)
        timelines[season] = [Exit(i, r) for i, r in enumerate(ordered, 1)]

    aligned_councils: list[Council] = []
    supported: set[tuple[str, int]] = set()
    council_issues: list[dict[str, object]] = []
    for council in councils:
        timeline = timelines.get(council.season, [])
        if not council.eliminated_ids:
            # Legacy records cannot establish a same-episode source identity.
            aligned_councils.append(council if not any(e.episode for e in timeline)
                                    else replace(council, order=None))
            continue
        matches = [e for e in timeline if e.episode == council.episode
                   and e.player in council.eliminated_ids
                   and (council.day is None or integer(e.record.get("day")) == council.day)]
        if len(matches) != 1 or len(council.eliminated_ids) != 1:
            council_issues.append({"council_id": council.id, "status": "excluded_council",
                                   "reason": "ambiguous_council_exit_identity"})
            continue
        exit_event = matches[0]
        aligned_councils.append(replace(council, order=exit_event.index))
        supported.add((council.season, exit_event.index))
        if integer(exit_event.record.get("order")) != council.order:
            council_issues.append({"council_id": council.id, "status": "source_order_disagreement",
                                   "reason": "matched_by_episode_day_eliminated_id",
                                   "boot_order": integer(exit_event.record.get("order")),
                                   "vote_history_order": council.order, "exit_index": exit_event.index})

    council_counts: dict[tuple[str, int], int] = defaultdict(int)
    for council in aligned_councils:
        if council.order is not None:
            council_counts[council.season, council.order] += 1
    repeated = {key for key, count in council_counts.items() if count > 1}
    for council in aligned_councils:
        if (council.season, council.order) in repeated:
            council_issues.append({"council_id": council.id, "status": "excluded_council",
                                   "reason": "multiple_councils_for_exit_identity"})
    aligned_councils = [c for c in aligned_councils if (c.season, c.order) not in repeated]
    supported.difference_update(repeated)

    pools: dict[str, set[str]] = defaultdict(set)
    for row in tables["Castaways"]:
        if row.get("castaway_id"):
            pools[season_key(row)].add(str(row["castaway_id"]))
    stages: dict[tuple[str, int, int], list[dict[str, str | None]]] = defaultdict(list)
    for row in tables["Boot Mapping"]:
        episode = integer(row.get("episode"))
        stage = integer(row.get("sog_id"))
        if episode is None or not row.get("castaway_id"):
            continue
        if stage is None:
            stage = integer(row.get("n_boots"))
        if stage is not None:
            stages[season_key(row), episode, stage].append(row)

    states, audit = [], []
    cleared: dict[str, dict[str, int]] = defaultdict(dict)
    last_roster: dict[str, set[str]] = {}
    last_cutoff: dict[str, int] = {}
    inactive: dict[str, set[str]] = defaultdict(set)
    for (season_key_value, episode, stage), records in sorted(stages.items()):
        season = integer(records[0].get("season"))
        timeline = timelines.get(season_key_value, [])
        active = [r for r in records if r.get("game_status") in ACTIVE_STATUSES]
        inactive[season_key_value].update(str(r["castaway_id"]) for r in records
                                           if r.get("game_status") not in ACTIVE_STATUSES)
        counts = {integer(r.get("n_boots")) for r in active}
        finals = {integer(r.get("final_n")) for r in active}
        entry: dict[str, object] = {"season": season, "episode": episode, "stage": stage,
                                   "source_n_boots": sorted(v for v in counts if v is not None),
                                   "source_orders": sorted({integer(r.get("order")) for r in active
                                                            if integer(r.get("order")) is not None}),
                                   "status": "excluded", "reason": "missing_state_counts"}
        audit.append(entry)
        if season_key_value in ambiguous_sequences:
            entry["reason"] = "ambiguous_exit_sequence"
            continue
        if not active or None in counts or None in finals or len(finals) != 1:
            continue
        n_boots = min(counts)
        roster = {}
        conflict = False
        for row in active:
            player = str(row["castaway_id"])
            normalized = {**row, "n_boots": str(n_boots)}
            if player in roster and roster[player] != normalized:
                conflict = True
            roster[player] = normalized
        entry.update(roster=sorted(roster), roster_size=len(roster), final_n=next(iter(finals)),
                     reconciled_rows=sum(integer(r.get("n_boots")) != n_boots for r in active))
        if conflict or len(roster) != next(iter(finals)):
            entry["reason"] = "conflicting_or_incomplete_roster"
            continue
        legacy = not any(e.episode for e in timeline)
        if legacy:
            # Old fixtures without event dates retain their explicit count contract.
            cutoffs = [n_boots]
        else:
            source_orders = entry["source_orders"]
            boundary = max(source_orders, default=-1)
            reentries = []
            proposed_cleared = dict(cleared[season_key_value])
            previous = last_roster.get(season_key_value, set(roster))
            for player, row in roster.items():
                if (row.get("game_status") == "Returned" or player in inactive[season_key_value]
                        or player not in previous):
                    earlier = [e.index for e in timeline if e.player == player
                               and e.episode <= episode and e.index <= boundary]
                    if earlier:
                        proposed_cleared[player] = max(earlier)
                        reentries.append(player)
            never_started = {str(r["castaway_id"]) for r in records if r.get("game_status") == "Never started"}
            pool = pools[season_key_value] - never_started
            lower = sum(e.episode < episode for e in timeline)
            upper = sum(e.episode <= episode for e in timeline)
            cutoffs = []
            for cutoff in range(lower, upper + 1):
                removed = {e.player for e in timeline[:cutoff]
                           if e.index > proposed_cleared.get(e.player, 0)}
                if pool - removed == set(roster):
                    cutoffs.append(cutoff)
            entry.update(reentries=sorted(reentries), possible_cutoffs=cutoffs)
        if len(cutoffs) != 1:
            entry["reason"] = "no_unique_chronological_roster_match"
            continue
        cutoff = cutoffs[0]
        if (cutoff < last_cutoff.get(season_key_value, 0)
                or (not legacy and cutoff < max(proposed_cleared.values(), default=0))):
            entry["reason"] = "non_monotone_or_pre_return_cutoff"
            continue
        last_cutoff[season_key_value] = cutoff
        if not legacy:
            cleared[season_key_value] = proposed_cleared
            inactive[season_key_value].difference_update(roster)
            last_roster[season_key_value] = set(roster)
        next_exit = next((e for e in timeline if e.index == cutoff + 1), None)
        entry.update(completed_exit_order=cutoff,
                     next_exit_index=next_exit.index if next_exit else None,
                     next_exit_id=next_exit.player if next_exit else None,
                     next_exit_episode=next_exit.episode if next_exit else None,
                     next_exit_source_order=integer(next_exit.record.get("order")) if next_exit else None)
        if next_exit is None:
            reason = "no_next_exit"
        elif not next_exit.eligible:
            reason = "next_exit_is_non_voting_or_terminal"
        elif next_exit.player not in roster:
            reason = "next_exit_absent_from_roster"
        elif not legacy and (season_key_value, next_exit.index) not in supported:
            reason = "next_exit_has_no_unique_council_identity"
        else:
            reason = "aligned"
        entry.update(status="included" if reason == "aligned" else "excluded", reason=reason)
        states.append(AlignedState(season, episode, stage, n_boots, cutoff, roster, next_exit, entry))
    # Only the latest source roster at the same episode/cutoff represents a forecast.
    unique_states: dict[tuple[int, int, int], AlignedState] = {}
    for state in states:
        key = (state.season, state.episode, state.completed_exit_order)
        if key in unique_states:
            unique_states[key].audit.update(status="excluded", reason="superseded_same_cutoff")
        unique_states[key] = state
    return list(unique_states.values()), aligned_councils, audit + council_issues
