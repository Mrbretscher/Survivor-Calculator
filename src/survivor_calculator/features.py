"""Episode-state features with completed-council and prior-episode cutoffs."""
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from survivor_calculator.council_events import integer, normalize_councils, season_key
from survivor_calculator.event_alignment import align_events
from survivor_calculator.relationships import SOCIAL_FEATURE_COLUMNS, build_relationship_snapshot, social_features
from survivor_calculator.soc import SocMapping, build_soc_mapping

TARGET_COLUMNS = {"winner", "place", "result", "order", "next_boot", "target_next_boot", "target_winner"}
FEATURE_TIMING_VERSION = "validated_exit_prefix_prior_episode_v2"
FEATURE_COLUMNS = (
    "season", "episode", "n_boots", "final_n", "age", "gender", "occupation", "soc_major_group",
    "tribe_status", "tribe_size", "challenge_wins_to_date", "individual_immunity_wins_to_date",
    "votes_received_to_date", "votes_cast_to_date", "confessionals_to_date", "confessional_time_to_date",
    "advantages_held_to_date", *SOCIAL_FEATURE_COLUMNS,
)


@dataclass(frozen=True)
class FeatureBuildResult:
    historical_rows: list[dict[str, object]]
    current_rows: list[dict[str, object]]
    current_season: int
    latest_episode: int
    latest_final_n: int
    soc_mappings: list[SocMapping]
    current_relationships: dict[str, object] | None = None
    excluded_non_vote_states: int = 0
    reconciled_state_rows: int = 0
    excluded_unlabelable_states: int = 0
    alignment_audit: list[dict[str, object]] = field(default_factory=list)
    idol_assistance_audit: list[dict[str, object]] = field(default_factory=list)
    timeline_rows: list[dict[str, object]] = field(default_factory=list)
    timeline_episodes: list[tuple[int, int]] = field(default_factory=list)


def build_features(
    tables: dict[str, list[dict[str, str | None]]], *, include_idol_assistance: bool = False,
) -> FeatureBuildResult:
    """Replay US states using information available before their next elimination.

    Historical and current states use identical cutoffs. Council ballots require a
    completed exit order (or a strict prior-episode fallback for legacy records).
    Challenge/advantage/confessional data are conservatively lagged one episode.
    Non-voting exits and finalist placements do not supply next-vote labels.
    Idol assistance is an explicit experimental opt-in requiring optional source
    tables; the default feature schema and production predictions are unchanged.
    """
    selected = {name: rows if name == "Castaway Details" else [r for r in rows if season_key(r).startswith("US:")]
                for name, rows in tables.items()}
    castaways, details = selected["Castaways"], selected["Castaway Details"]
    all_seasons = [to_int(r.get("season")) for r in castaways if to_int(r.get("season")) is not None]
    if not all_seasons:
        raise ValueError("No US castaways with valid season numbers were found.")
    current_season = max(all_seasons)
    completed = {to_int(r.get("season")) for r in selected["Season Summary"] if r.get("winner_id")}
    detail_by_id = {r.get("castaway_id"): r for r in details}
    castaway_by_key = {(to_int(r.get("season")), r.get("castaway_id")): r for r in castaways}
    mappings = build_soc_mapping({r.get("occupation") for r in details})
    soc_by_occupation = {m.occupation: m for m in mappings}
    councils = normalize_councils(selected["Vote History"])
    aligned_states, councils, alignment_audit = align_events(selected, councils)
    idol_evidence = None
    if include_idol_assistance:
        from survivor_calculator.idol_assistance import normalize_idol_assistance
        idol_evidence = normalize_idol_assistance(selected, councils)
    councils_by_season = defaultdict(list)
    for council in councils:
        councils_by_season[council.season].append(council)
    sources = {
        "challenge_wins_to_date": _episode_index(selected["Challenge Results"], "won"),
        "individual_immunity_wins_to_date": _episode_index(selected["Challenge Results"], "won_individual_immunity"),
        "confessionals_to_date": _episode_index(selected["Confessionals"], "confessional_count"),
        "confessional_time_to_date": _episode_index(selected["Confessionals"], "confessional_time"),
        "advantages_held_to_date": _episode_index(selected["Advantage Timeline"], "holding", cumulative=False),
    }
    states = [r for r in selected["Boot Mapping"] if r.get("game_status") == "In the game"]
    originals = _original_tribes(states)
    current_states = [s for s in aligned_states if s.season == current_season]
    if not current_states:
        raise ValueError("No uniquely aligned active current-season state is available.")
    current_state = max(current_states, key=lambda s: (s.episode, s.stage))
    current_key = (current_state.season, current_state.episode, current_state.completed_exit_order)
    reconciled = sum(int(a.get("reconciled_rows", 0)) for a in alignment_audit)
    historical_rows, current_rows, timeline_rows = [], [], []
    current_snapshot = None
    for aligned in aligned_states:
        season, episode, n_boots = aligned.season, aligned.episode, aligned.n_boots
        by_id = aligned.roster
        is_current = aligned is current_state
        if not is_current and season not in completed and season != current_season:
            continue
        if not is_current and aligned.audit["status"] != "included":
            continue
        next_exit = aligned.next_exit.record if aligned.next_exit else {}
        tribe_sizes = defaultdict(int)
        for state in by_id.values():
            tribe_sizes[state.get("tribe") or ""] += 1
        visible_councils = [c for c in councils_by_season[f"US:{season}"] if c.completed_before({**next(iter(by_id.values())), "completed_exit_order": aligned.completed_exit_order})]
        votes_cast, votes_received = defaultdict(int), defaultdict(int)
        for council in visible_councils:
            for ballots in council.rounds.values():
                for ballot in ballots:
                    votes_cast[ballot.voter] += 1
                    if not ballot.nullified:
                        votes_received[ballot.target] += 1
        event_rows = []
        for player, state in sorted(by_id.items()):
            castaway = castaway_by_key.get((season, player), {})
            detail = detail_by_id.get(player, {})
            occupation = detail.get("occupation") or ""
            soc = soc_by_occupation.get(occupation)
            observed_original = originals.get((season, player))
            original = observed_original[2] if observed_original and observed_original[:2] <= (episode, n_boots) else ""
            row = {
                "version": "US", "season": season, "episode": episode, "n_boots": n_boots,
                "final_n": to_int(state.get("final_n")), "castaway_id": player,
                "completed_exit_order": aligned.completed_exit_order, "source_stage": aligned.stage,
                "castaway": state.get("castaway") or castaway.get("castaway") or "",
                "age": to_int(castaway.get("age")), "gender": detail.get("gender") or "Unknown",
                "occupation": occupation, "soc_code": soc.soc_code if soc else "",
                "soc_title": soc.soc_title if soc else "", "soc_major_group": soc.soc_major_group if soc else "",
                "tribe": state.get("tribe") or "", "original_tribe": original,
                "tribe_status": state.get("tribe_status") or "",
                "tribe_status_display": _tribe_status_display(state.get("tribe_status") or "", original, state.get("tribe") or ""),
                "tribe_size": tribe_sizes[state.get("tribe") or ""],
                **{name: _prior_episode_value(index, season, player, episode) for name, index in sources.items()},
                "votes_received_to_date": votes_received[player], "votes_cast_to_date": votes_cast[player],
                "target_next_boot": int(next_exit.get("castaway_id") == player),
                "target_winner": int(castaway.get("winner") == "1"),
            }
            event_rows.append(row)
        snapshot = build_relationship_snapshot(visible_councils, event_rows)
        summaries = social_features(snapshot)
        for row in event_rows:
            row.update(summaries[row["castaway_id"]])
        if idol_evidence is not None:
            from survivor_calculator.idol_assistance import idol_features, idol_snapshot
            assistance = idol_snapshot(idol_evidence, event_rows)
            snapshot["idol_assistance"] = assistance
            assistance_summaries = idol_features(assistance, event_rows)
            for row in event_rows:
                row.update(assistance_summaries[row["castaway_id"]])
        if is_current:
            current_rows, current_snapshot = event_rows, snapshot
        elif season in completed:
            historical_rows.extend(event_rows)
        timeline_rows.extend(event_rows)
    return FeatureBuildResult(historical_rows, current_rows, current_season, current_key[1],
                              max((int(r["final_n"]) for r in current_rows), default=0), mappings,
                              current_snapshot,
                              sum(a.get("reason") in {"no_next_exit", "next_exit_is_non_voting_or_terminal"}
                                  for a in alignment_audit if a.get("season") in completed),
                              reconciled,
                              sum(a.get("status") == "excluded" and a.get("reason") not in {
                                  "no_next_exit", "next_exit_is_non_voting_or_terminal", "superseded_same_cutoff"}
                                  for a in alignment_audit if a.get("season") in completed),
                              alignment_audit,
                              list(idol_evidence.audit) if idol_evidence is not None else [], timeline_rows,
                              sorted({(to_int(row.get("season")), to_int(row.get("episode")))
                                      for row in selected["Episodes"] + selected["Boot Mapping"]
                                      if to_int(row.get("season")) is not None and to_int(row.get("episode")) is not None
                                      and to_int(row.get("episode")) > 0
                                      and (to_int(row.get("season")) < current_season
                                           or to_int(row.get("episode")) <= current_key[1])}))


def assert_no_leakage_columns(columns: Iterable[str]) -> None:
    leaked = TARGET_COLUMNS.intersection(columns)
    if leaked:
        raise ValueError(f"Potential leakage columns in features: {sorted(leaked)}")


def to_int(value: object) -> int | None:
    return integer(value)


def to_float(value: object) -> float:
    try:
        return float(str(value)) if value not in (None, "") else 0.0
    except ValueError:
        return 0.0


def _episode_index(
    rows: list[dict[str, str | None]], value_column: str, *, cumulative: bool = True,
) -> dict[tuple[int, str], tuple[list[int], list[float]]]:
    values: dict[tuple[int, str], dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        season, episode, player = to_int(row.get("season")), to_int(row.get("episode")), row.get("castaway_id")
        if season is not None and episode is not None and player:
            values[season, player][episode] += to_float(row.get(value_column))
    result = {}
    for key, by_episode in values.items():
        episodes, totals, total = sorted(by_episode), [], 0.0
        for episode in episodes:
            total = total + by_episode[episode] if cumulative else by_episode[episode]
            totals.append(total)
        result[key] = (episodes, totals)
    return result


def _prior_episode_value(
    index: dict[tuple[int, str], tuple[list[int], list[float]]], season: int, player: str, episode: int,
) -> float:
    episodes, values = index.get((season, player), ([], []))
    position = bisect_left(episodes, episode) - 1
    return values[position] if position >= 0 else 0.0


def _original_tribes(rows: list[dict[str, str | None]]) -> dict[tuple[int, str], tuple[int, int, str]]:
    originals = {}
    for row in sorted(rows, key=lambda r: (to_int(r.get("episode")) or 0, to_int(r.get("n_boots")) or 0)):
        key = (to_int(row.get("season")), row.get("castaway_id"))
        if row.get("tribe") and row.get("tribe") != "No Tribe":
            originals.setdefault(key, (to_int(row.get("episode")) or 0, to_int(row.get("n_boots")) or 0, row["tribe"]))
    return originals


def _tribe_status_display(source_status: str, original_tribe: str, current_tribe: str) -> str:
    if source_status.lower().startswith("merge"):
        return "Merged"
    if original_tribe and current_tribe and original_tribe != current_tribe:
        return "Swapped"
    return "Original"
