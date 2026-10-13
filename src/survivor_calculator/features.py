"""Feature engineering for Survivor episode-state predictions."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from survivor_calculator.soc import SocMapping, build_soc_mapping

TARGET_COLUMNS = {"winner", "place", "result", "order", "next_boot", "target_next_boot", "target_winner"}

FEATURE_COLUMNS = (
    "season",
    "episode",
    "n_boots",
    "final_n",
    "age",
    "gender",
    "occupation",
    "soc_major_group",
    "tribe_status",
    "tribe_size",
    "challenge_wins_to_date",
    "individual_immunity_wins_to_date",
    "votes_received_to_date",
    "votes_cast_to_date",
    "confessionals_to_date",
    "confessional_time_to_date",
    "advantages_held_to_date",
)


@dataclass(frozen=True)
class FeatureBuildResult:
    historical_rows: list[dict[str, object]]
    current_rows: list[dict[str, object]]
    current_season: int
    latest_episode: int
    latest_final_n: int
    soc_mappings: list[SocMapping]


def build_features(tables: dict[str, list[dict[str, str | None]]]) -> FeatureBuildResult:
    castaways = tables["Castaways"]
    details = tables["Castaway Details"]
    boot_mapping = tables["Boot Mapping"]
    boot_order = tables["Boot Order"]
    challenge_results = tables["Challenge Results"]
    confessionals = tables["Confessionals"]
    vote_history = tables["Vote History"]
    advantage_timeline = tables["Advantage Timeline"]
    season_summary = tables["Season Summary"]

    detail_by_id = {row.get("castaway_id"): row for row in details}
    castaway_by_key = {(to_int(row.get("season")), row.get("castaway_id")): row for row in castaways}
    completed_seasons = {
        to_int(row.get("season"))
        for row in season_summary
        if row.get("winner_id") and to_int(row.get("season")) is not None
    }
    all_seasons = [to_int(row.get("season")) for row in castaways if to_int(row.get("season")) is not None]
    current_season = max(all_seasons)

    occupations = {row.get("occupation") for row in details}
    soc_mappings = build_soc_mapping(occupations)
    soc_by_occupation = {mapping.occupation: mapping for mapping in soc_mappings}

    next_boot_by_state: dict[tuple[int, int], str] = {}
    for row in boot_order:
        season = to_int(row.get("season"))
        order = to_int(row.get("order"))
        castaway_id = row.get("castaway_id")
        if season is not None and order is not None and castaway_id:
            next_boot_by_state[(season, order - 1)] = castaway_id

    challenge_wins = _cumulative_counts(
        challenge_results,
        id_column="castaway_id",
        season_column="season",
        episode_column="episode",
        predicate=lambda row: row.get("won") == "1",
    )
    immunity_wins = _cumulative_counts(
        challenge_results,
        id_column="castaway_id",
        season_column="season",
        episode_column="episode",
        predicate=lambda row: row.get("won_individual_immunity") == "1",
    )
    votes_received = _cumulative_counts(
        vote_history,
        id_column="vote_id",
        season_column="season",
        episode_column="episode",
        predicate=lambda row: bool(row.get("vote_id")) and row.get("nullified") != "1",
    )
    votes_cast = _cumulative_counts(
        vote_history,
        id_column="castaway_id",
        season_column="season",
        episode_column="episode",
        predicate=lambda row: bool(row.get("vote_id")),
    )
    confessional_count = _cumulative_sums(confessionals, "castaway_id", "season", "episode", "confessional_count")
    confessional_time = _cumulative_sums(confessionals, "castaway_id", "season", "episode", "confessional_time")
    advantages_held = _latest_advantage_holding(advantage_timeline)

    state_rows = [row for row in boot_mapping if row.get("game_status") == "In the game"]
    state_keys = _state_keys(state_rows)
    original_tribes = _original_tribes(state_rows)
    challenge_wins = _carry_forward_values(challenge_wins, state_keys)
    immunity_wins = _carry_forward_values(immunity_wins, state_keys)
    votes_received = _carry_forward_values(votes_received, state_keys)
    votes_cast = _carry_forward_values(votes_cast, state_keys)
    confessional_count = _carry_forward_values(confessional_count, state_keys)
    confessional_time = _carry_forward_values(confessional_time, state_keys)
    advantages_held = _carry_forward_values(advantages_held, state_keys)
    tribe_sizes = _tribe_sizes(state_rows)
    latest_episode = max(
        to_int(row.get("episode")) or 0 for row in state_rows if to_int(row.get("season")) == current_season
    )
    current_candidates = [
        row
        for row in state_rows
        if to_int(row.get("season")) == current_season and to_int(row.get("episode")) == latest_episode
    ]
    latest_final_n = max((to_int(row.get("final_n")) or 0 for row in current_candidates), default=0)

    historical_rows: list[dict[str, object]] = []
    current_rows: list[dict[str, object]] = []
    for state in state_rows:
        season = to_int(state.get("season"))
        episode = to_int(state.get("episode"))
        n_boots = to_int(state.get("n_boots"))
        final_n = to_int(state.get("final_n"))
        castaway_id = state.get("castaway_id")
        if None in (season, episode, n_boots, final_n) or not castaway_id:
            continue

        castaway = castaway_by_key.get((season, castaway_id), {})
        detail = detail_by_id.get(castaway_id, {})
        occupation = detail.get("occupation") or ""
        soc = soc_by_occupation.get(occupation)
        feature_row: dict[str, object] = {
            "season": season,
            "episode": episode,
            "n_boots": n_boots,
            "final_n": final_n,
            "castaway_id": castaway_id,
            "castaway": state.get("castaway") or castaway.get("castaway") or "",
            "age": to_int(castaway.get("age")),
            "gender": detail.get("gender") or "Unknown",
            "occupation": occupation,
            "soc_code": soc.soc_code if soc else "",
            "soc_title": soc.soc_title if soc else "",
            "soc_major_group": soc.soc_major_group if soc else "",
            "tribe": state.get("tribe") or "",
            "original_tribe": original_tribes.get((season, castaway_id), state.get("tribe") or ""),
            "tribe_status": state.get("tribe_status") or "",
            "tribe_status_display": _tribe_status_display(
                state.get("tribe_status") or "",
                original_tribes.get((season, castaway_id), state.get("tribe") or ""),
                state.get("tribe") or "",
            ),
            "tribe_size": tribe_sizes.get((season, episode, state.get("tribe") or ""), 0),
            "challenge_wins_to_date": challenge_wins.get((season, castaway_id, episode), 0),
            "individual_immunity_wins_to_date": immunity_wins.get((season, castaway_id, episode), 0),
            "votes_received_to_date": votes_received.get((season, castaway_id, episode), 0),
            "votes_cast_to_date": votes_cast.get((season, castaway_id, episode), 0),
            "confessionals_to_date": confessional_count.get((season, castaway_id, episode), 0.0),
            "confessional_time_to_date": confessional_time.get((season, castaway_id, episode), 0.0),
            "advantages_held_to_date": advantages_held.get((season, castaway_id, episode), 0),
            "target_next_boot": int(next_boot_by_state.get((season, n_boots)) == castaway_id),
            "target_winner": int(castaway.get("winner") == "1"),
        }

        if season == current_season and episode == latest_episode:
            current_rows.append(feature_row)
        elif season in completed_seasons:
            historical_rows.append(feature_row)

    return FeatureBuildResult(
        historical_rows=historical_rows,
        current_rows=current_rows,
        current_season=current_season,
        latest_episode=latest_episode,
        latest_final_n=latest_final_n,
        soc_mappings=soc_mappings,
    )


def assert_no_leakage_columns(columns: Iterable[str]) -> None:
    leaked = TARGET_COLUMNS.intersection(columns)
    if leaked:
        raise ValueError(f"Potential leakage columns in features: {sorted(leaked)}")


def to_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None


def to_float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value))
    except ValueError:
        return 0.0


def _cumulative_counts(
    rows: list[dict[str, str | None]],
    id_column: str,
    season_column: str,
    episode_column: str,
    predicate,
) -> dict[tuple[int, str, int], int]:
    events: dict[tuple[int, str], list[int]] = defaultdict(list)
    for row in rows:
        if not predicate(row):
            continue
        season = to_int(row.get(season_column))
        episode = to_int(row.get(episode_column))
        castaway_id = row.get(id_column)
        if season is None or episode is None or not castaway_id:
            continue
        events[(season, castaway_id)].append(episode)
    return _expand_cumulative(events)


def _cumulative_sums(
    rows: list[dict[str, str | None]],
    id_column: str,
    season_column: str,
    episode_column: str,
    value_column: str,
) -> dict[tuple[int, str, int], float]:
    events: dict[tuple[int, str], list[tuple[int, float]]] = defaultdict(list)
    for row in rows:
        season = to_int(row.get(season_column))
        episode = to_int(row.get(episode_column))
        castaway_id = row.get(id_column)
        if season is None or episode is None or not castaway_id:
            continue
        events[(season, castaway_id)].append((episode, to_float(row.get(value_column))))

    expanded: dict[tuple[int, str, int], float] = {}
    for (season, castaway_id), values in events.items():
        total = 0.0
        for episode, value in sorted(values):
            total += value
            expanded[(season, castaway_id, episode)] = total
    return expanded


def _expand_cumulative(events: dict[tuple[int, str], list[int]]) -> dict[tuple[int, str, int], int]:
    expanded: dict[tuple[int, str, int], int] = {}
    for (season, castaway_id), episodes in events.items():
        count = 0
        for episode in sorted(episodes):
            count += 1
            expanded[(season, castaway_id, episode)] = count
    return expanded


def _latest_advantage_holding(rows: list[dict[str, str | None]]) -> dict[tuple[int, str, int], int]:
    holdings: dict[tuple[int, str, int], int] = defaultdict(int)
    for row in rows:
        season = to_int(row.get("season"))
        episode = to_int(row.get("episode"))
        castaway_id = row.get("castaway_id")
        if season is None or episode is None or not castaway_id:
            continue
        holdings[(season, castaway_id, episode)] += to_int(row.get("holding")) or 0
    return dict(holdings)


def _tribe_sizes(rows: list[dict[str, str | None]]) -> dict[tuple[int, int, str], int]:
    sizes: dict[tuple[int, int, str], int] = defaultdict(int)
    for row in rows:
        season = to_int(row.get("season"))
        episode = to_int(row.get("episode"))
        tribe = row.get("tribe") or ""
        if season is None or episode is None:
            continue
        sizes[(season, episode, tribe)] += 1
    return dict(sizes)


def _original_tribes(rows: list[dict[str, str | None]]) -> dict[tuple[int, str], str]:
    originals: dict[tuple[int, str], tuple[int, int, str]] = {}
    for row in rows:
        season = to_int(row.get("season"))
        episode = to_int(row.get("episode"))
        n_boots = to_int(row.get("n_boots"))
        castaway_id = row.get("castaway_id")
        tribe = row.get("tribe") or ""
        if season is None or episode is None or n_boots is None or not castaway_id or not tribe:
            continue
        key = (season, castaway_id)
        candidate = (episode, n_boots, tribe)
        if key not in originals or candidate[:2] < originals[key][:2]:
            originals[key] = candidate
    return {key: value[2] for key, value in originals.items()}


def _tribe_status_display(source_status: str, original_tribe: str, current_tribe: str) -> str:
    if source_status.lower().startswith("merge"):
        return "Merged"
    if original_tribe and current_tribe and original_tribe != current_tribe:
        return "Swapped"
    return "Original"


def _state_keys(rows: list[dict[str, str | None]]) -> dict[tuple[int, str], list[int]]:
    keys: dict[tuple[int, str], set[int]] = defaultdict(set)
    for row in rows:
        season = to_int(row.get("season"))
        episode = to_int(row.get("episode"))
        castaway_id = row.get("castaway_id")
        if season is None or episode is None or not castaway_id:
            continue
        keys[(season, castaway_id)].add(episode)
    return {key: sorted(episodes) for key, episodes in keys.items()}


def _carry_forward_values(
    values: dict[tuple[int, str, int], int | float],
    state_keys: dict[tuple[int, str], list[int]],
) -> dict[tuple[int, str, int], int | float]:
    by_player: dict[tuple[int, str], dict[int, int | float]] = defaultdict(dict)
    for (season, castaway_id, episode), value in values.items():
        by_player[(season, castaway_id)][episode] = value

    carried: dict[tuple[int, str, int], int | float] = {}
    for key, episodes in state_keys.items():
        source = by_player.get(key, {})
        if not source:
            continue
        latest: int | float = 0
        source_episodes = sorted(source)
        source_index = 0
        for episode in episodes:
            while source_index < len(source_episodes) and source_episodes[source_index] <= episode:
                latest = source[source_episodes[source_index]]
                source_index += 1
            carried[(key[0], key[1], episode)] = latest
    return carried

