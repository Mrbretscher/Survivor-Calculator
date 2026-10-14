"""Build backend analytics datasets from Survivor workbook tables."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from survivor_calculator.features import to_float, to_int
from survivor_calculator.soc import build_soc_mapping

ANALYTICS_PLAYER_SEASON_COLUMNS = (
    "version",
    "version_season",
    "season",
    "castaway_id",
    "castaway",
    "age",
    "age_bucket",
    "gender",
    "occupation",
    "soc_code",
    "soc_title",
    "soc_major_group",
    "soc_confidence",
    "soc_review_required",
    "final_place",
    "result",
    "jury",
    "finalist",
    "winner",
    "challenge_appearances_total",
    "challenge_wins_total",
    "team_challenge_appearances_total",
    "team_challenge_wins_total",
    "individual_immunity_appearances_total",
    "individual_immunity_wins_total",
    "votes_received_total",
    "votes_cast_total",
    "confessionals_total",
    "confessional_time_total",
)


def build_player_season_rows(tables: dict[str, list[dict[str, str | None]]]) -> list[dict[str, object]]:
    """Return one analytics row per castaway-season.

    The dataset keeps only season-level facts and cumulative metrics so charts do
    not overcount players who survived into later episode-state rows.
    """

    castaways = tables["Castaways"]
    details = tables["Castaway Details"]
    challenge_results = tables["Challenge Results"]
    confessionals = tables["Confessionals"]
    vote_history = tables["Vote History"]
    season_summary = tables["Season Summary"]

    detail_by_id = {row.get("castaway_id"): row for row in details}
    soc_by_occupation = {
        mapping.occupation: mapping
        for mapping in build_soc_mapping({row.get("occupation") for row in details})
    }
    winner_ids = {
        _season_key(row): row.get("winner_id")
        for row in season_summary
        if row.get("winner_id") and to_int(row.get("season")) is not None
    }

    challenge_appearances: dict[tuple[str, str, int, str], int] = defaultdict(int)
    challenge_wins: dict[tuple[str, str, int, str], int] = defaultdict(int)
    team_challenge_appearances: dict[tuple[str, str, int, str], int] = defaultdict(int)
    team_challenge_wins: dict[tuple[str, str, int, str], int] = defaultdict(int)
    individual_immunity_appearances: dict[tuple[str, str, int, str], int] = defaultdict(int)
    individual_immunity_wins: dict[tuple[str, str, int, str], int] = defaultdict(int)
    for row in challenge_results:
        key = _player_key(row)
        if key is None or row.get("sit_out") == "1":
            continue
        challenge_appearances[key] += 1
        if row.get("won") == "1":
            challenge_wins[key] += 1
        if _is_team_challenge_row(row):
            team_challenge_appearances[key] += 1
            if _won_team_challenge(row):
                team_challenge_wins[key] += 1
        if _is_individual_immunity_row(row):
            individual_immunity_appearances[key] += 1
        if row.get("won_individual_immunity") == "1":
            individual_immunity_wins[key] += 1

    votes_received: dict[tuple[str, str, int, str], int] = defaultdict(int)
    votes_cast: dict[tuple[str, str, int, str], int] = defaultdict(int)
    for row in vote_history:
        season_key = _season_key(row)
        season = season_key[2]
        if season is None:
            continue
        voter_id = row.get("castaway_id")
        vote_id = row.get("vote_id")
        if voter_id and vote_id:
            votes_cast[(*season_key, voter_id)] += 1
        if vote_id and row.get("nullified") != "1":
            votes_received[(*season_key, vote_id)] += 1

    confessionals_total: dict[tuple[str, str, int, str], float] = defaultdict(float)
    confessional_time_total: dict[tuple[str, str, int, str], float] = defaultdict(float)
    for row in confessionals:
        key = _player_key(row)
        if key is None:
            continue
        confessionals_total[key] += to_float(row.get("confessional_count"))
        confessional_time_total[key] += to_float(row.get("confessional_time"))

    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, int, str]] = set()
    for castaway in castaways:
        key = _player_key(castaway)
        if key is None or key in seen:
            continue
        seen.add(key)
        version, version_season, season, castaway_id = key
        detail = detail_by_id.get(castaway_id, {})
        occupation = detail.get("occupation") or ""
        soc = soc_by_occupation.get(occupation)
        age = to_int(castaway.get("age"))
        season_key = (version, version_season, season)
        rows.append(
            {
                "version": version,
                "version_season": version_season,
                "season": season,
                "castaway_id": castaway_id,
                "castaway": castaway.get("castaway") or "",
                "age": age,
                "age_bucket": age_bucket(age),
                "gender": detail.get("gender") or "Unknown",
                "occupation": occupation,
                "soc_code": soc.soc_code if soc else "",
                "soc_title": soc.soc_title if soc else "",
                "soc_major_group": soc.soc_major_group if soc else "",
                "soc_confidence": soc.confidence if soc else "none",
                "soc_review_required": soc.review_required if soc else True,
                "final_place": to_int(castaway.get("place")),
                "result": castaway.get("result") or "",
                "jury": _to_bool(castaway.get("jury")),
                "finalist": _to_bool(castaway.get("finalist")),
                "winner": _to_bool(castaway.get("winner")) or winner_ids.get(season_key) == castaway_id,
                "challenge_appearances_total": challenge_appearances[key],
                "challenge_wins_total": challenge_wins[key],
                "team_challenge_appearances_total": team_challenge_appearances[key],
                "team_challenge_wins_total": team_challenge_wins[key],
                "individual_immunity_appearances_total": individual_immunity_appearances[key],
                "individual_immunity_wins_total": individual_immunity_wins[key],
                "votes_received_total": votes_received[key],
                "votes_cast_total": votes_cast[key],
                "confessionals_total": confessionals_total[key],
                "confessional_time_total": confessional_time_total[key],
            }
        )

    return sorted(rows, key=lambda row: (str(row["version"]), int(row["season"]), str(row["castaway_id"])))


def export_player_season_rows(rows: list[dict[str, object]], output_path: str | Path) -> Path:
    """Write the player-season analytics dataset with a stable schema."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ANALYTICS_PLAYER_SEASON_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return path


def age_bucket(age: int | None) -> str:
    if age is None:
        return "unknown"
    if age < 25:
        return "under_25"
    if age < 35:
        return "25_34"
    if age < 45:
        return "35_44"
    return "45_plus"


def _player_key(row: dict[str, str | None]) -> tuple[str, str, int, str] | None:
    season_key = _season_key(row)
    season = season_key[2]
    castaway_id = row.get("castaway_id")
    if season is None or not castaway_id:
        return None
    return (*season_key, castaway_id)


def _season_key(row: dict[str, str | None]) -> tuple[str, str, int | None]:
    return (
        row.get("version") or "",
        row.get("version_season") or "",
        to_int(row.get("season")),
    )


def _is_individual_immunity_row(row: dict[str, str | None]) -> bool:
    challenge_type = (row.get("challenge_type") or "").lower()
    outcome_type = (row.get("outcome_type") or "").lower()
    return (
        row.get("won_individual_immunity") == "1"
        or ("immunity" in challenge_type and "individual" in outcome_type)
    )


def _is_team_challenge_row(row: dict[str, str | None]) -> bool:
    outcome_type = (row.get("outcome_type") or "").lower()
    return "tribal" in outcome_type or "team" in outcome_type


def _won_team_challenge(row: dict[str, str | None]) -> bool:
    return (
        row.get("won_tribal_reward") == "1"
        or row.get("won_tribal_immunity") == "1"
        or row.get("won_team_reward") == "1"
        or row.get("won_team_immunity") == "1"
        or row.get("won") == "1"
    )


def _to_bool(value: str | None) -> bool:
    return value == "1" or (value or "").lower() == "true"
