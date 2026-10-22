"""Optional FastAPI surface for prediction results."""

from __future__ import annotations

import csv
import json
import math
import os
import re
from http import HTTPStatus
from pathlib import Path
from typing import Literal, TypedDict

from survivor_calculator.analytics import ANALYTICS_PLAYER_SEASON_COLUMNS
from survivor_calculator.analytics_query import (
    DIMENSIONS,
    METRICS,
    SUPPORTED_FILTER_FIELDS,
    AnalyticsQueryError,
    preset_configs,
    run_chart_query,
)

try:
    from fastapi import Body, FastAPI
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover - exercised only without optional dependency
    Body = None  # type: ignore[assignment]
    FastAPI = None  # type: ignore[assignment]
    JSONResponse = None  # type: ignore[assignment]

try:
    from pydantic import BaseModel
except ModuleNotFoundError:  # pragma: no cover - FastAPI depends on pydantic
    BaseModel = object  # type: ignore[assignment,misc]

DEFAULT_WORKBOOK = Path(os.environ.get("SURVIVOR_WORKBOOK_PATH", "survivoR.xlsx"))
DEFAULT_PREDICTIONS = Path(os.environ.get("SURVIVOR_PREDICTIONS_PATH", "data/processed/current_predictions.json"))
DEFAULT_ANALYTICS = Path(os.environ.get("SURVIVOR_ANALYTICS_PATH", "data/processed/analytics_player_season.csv"))


class HealthPayload(TypedDict):
    status: Literal["ok"]


class CurrentSeasonPayload(TypedDict):
    current_season: int
    latest_episode: int
    latest_final_n: int
    active_players: int


class ErrorPayload(TypedDict):
    error: str


class PredictionPayload(TypedDict):
    metadata: dict[str, object]
    players: list[dict[str, object]]
    projected_boot_order: list[dict[str, object]]
    evaluation: dict[str, object]


class AnalyticsSchemaPayload(TypedDict):
    dataset: dict[str, object]
    dimensions: list[dict[str, object]]
    metrics: list[dict[str, object]]
    filters: list[dict[str, object]]
    chart_types: list[str]


class AnalyticsPresetsPayload(TypedDict):
    presets: list[dict[str, object]]


class AnalyticsQueryPayload(TypedDict):
    metadata: dict[str, object]
    rows: list[dict[str, object]]


class HealthResponse(BaseModel):  # type: ignore[misc]
    status: Literal["ok"]


class CurrentSeasonResponse(BaseModel):  # type: ignore[misc]
    current_season: int
    latest_episode: int
    latest_final_n: int
    active_players: int


class PlayerResponse(BaseModel):  # type: ignore[misc]
    castaway_id: str
    castaway: str
    tribe: str
    original_tribe: str
    tribe_status: str
    tribe_status_display: str
    occupation: str
    soc_code: str
    soc_title: str
    soc_major_group: str
    raw_next_boot_risk: float
    next_boot_probability: float
    winner_probability: float
    explanation: list[str]


class ProjectedBootResponse(BaseModel):  # type: ignore[misc]
    projected_order: int
    projected_final_n_before_boot: int
    castaway_id: str
    castaway: str
    projected_boot_probability: float


class PredictionMetadataResponse(BaseModel):  # type: ignore[misc]
    generated_at: str
    model_name: str
    model_selection_policy: str
    source_workbook: str
    source_data: dict[str, object] | None = None
    current_season: int
    latest_episode: int
    latest_final_n: int
    active_players: int
    disclaimer: str
    training_seasons: list[int] | None = None
    training_policy: str | None = None


class PredictionResponse(BaseModel):  # type: ignore[misc]
    metadata: PredictionMetadataResponse
    players: list[PlayerResponse]
    projected_boot_order: list[ProjectedBootResponse]
    evaluation: dict[str, object]


class PredictionApiError(RuntimeError):
    """A client-safe prediction API error."""

    def __init__(self, message: str, status_code: HTTPStatus) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class PredictionDataUnavailable(PredictionApiError):
    def __init__(self) -> None:
        super().__init__(
            "Prediction data is not available. Run `survivor-calculator build` before serving the API.",
            HTTPStatus.SERVICE_UNAVAILABLE,
        )


class PredictionDataInvalid(PredictionApiError):
    def __init__(self) -> None:
        super().__init__(
            "Prediction data is invalid. Rebuild predictions before serving the API.",
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )


class AnalyticsDataUnavailable(PredictionApiError):
    def __init__(self) -> None:
        super().__init__(
            "Analytics data is not available. Run `survivor-calculator build` before serving the API.",
            HTTPStatus.SERVICE_UNAVAILABLE,
        )


class AnalyticsDataInvalid(PredictionApiError):
    def __init__(self) -> None:
        super().__init__(
            "Analytics data is invalid. Rebuild analytics data before serving the API.",
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )


class AnalyticsQueryInvalid(PredictionApiError):
    def __init__(self, message: str = "Analytics query config is invalid.") -> None:
        super().__init__(message, HTTPStatus.BAD_REQUEST)


class PlayerNotFound(PredictionApiError):
    def __init__(self) -> None:
        super().__init__("Contestant is not on the current prediction board.", HTTPStatus.NOT_FOUND)


PROFILE_STAT_FIELDS = (
    "age", "challenge_appearances_total", "challenge_wins_total",
    "team_challenge_appearances_total", "team_challenge_wins_total",
    "individual_immunity_appearances_total", "individual_immunity_wins_total",
    "votes_received_total", "votes_cast_total", "confessionals_total", "confessional_time_total",
)


def player_profile_payload(
    castaway_id: str,
    predictions_path: str | Path = DEFAULT_PREDICTIONS,
    analytics_path: str | Path = DEFAULT_ANALYTICS,
) -> dict[str, object]:
    """Join an active player's forecast to recorded current-US-season totals.

    No data is generated on request. Missing or malformed counts stay unknown;
    totals cover available snapshot records, including recorded voting rounds.
    Analytics failures leave the validated forecast usable with an explicit status.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", castaway_id):
        raise PlayerNotFound()
    predictions = prediction_payload(predictions_path=predictions_path)
    player = next((row for row in predictions["players"] if row["castaway_id"] == castaway_id), None)
    if player is None:
        raise PlayerNotFound()
    season = predictions["metadata"]["current_season"]
    try:
        matches = [
            row for row in analytics_rows(analytics_path)
            if row.get("castaway_id") == castaway_id
            and str(row.get("season")) == str(season)
            and (row.get("version") or "US") == "US"
            and (row.get("version_season") or f"US{season}") == f"US{season}"
        ]
    except (AnalyticsDataUnavailable, AnalyticsDataInvalid):
        matches = []
    # Duplicate identities are ambiguous: do not pick or sum an arbitrary row.
    row = matches[0] if len(matches) == 1 else None
    return {
        "metadata": {key: predictions["metadata"][key] for key in (
            "current_season", "latest_episode", "generated_at", "disclaimer",
        )},
        "player": player,
        "stats_status": "available" if row is not None else "unavailable",
        "stats": {field: _profile_number(row.get(field)) if row is not None else None for field in PROFILE_STAT_FIELDS},
        "notes": [
            "Observed totals describe available records in this saved snapshot; missing source coverage can affect totals.",
            "Votes cast include recorded voting rounds; votes received exclude votes recorded as nullified.",
            "Confessionals describe edited screen time, not social influence or jury support.",
        ],
    }


def _profile_number(value: object) -> float | None:
    """Preserve absent, invalid and negative statistics as unknown."""
    if value is None or isinstance(value, bool) or str(value).strip() == "":
        return None
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def prediction_payload(
    workbook_path: str | Path = DEFAULT_WORKBOOK,
    predictions_path: str | Path = DEFAULT_PREDICTIONS,
) -> PredictionPayload:
    """Load and validate the current prediction API payload.

    The API serves a previously generated predictions file. It deliberately does
    not build predictions on request so missing or invalid files fail with a
    clear, sanitized response rather than leaking local filesystem details.
    """

    del workbook_path  # Retained for backward-compatible callers.
    path = Path(predictions_path)
    if not path.exists():
        raise PredictionDataUnavailable()
    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PredictionDataInvalid() from exc
    except OSError as exc:
        raise PredictionDataUnavailable() from exc
    return validate_prediction_payload(raw_payload)


def timeline_payload(
    predictions_path: str | Path = DEFAULT_PREDICTIONS,
    *,
    season: int | None = None,
    episode: int | None = None,
    checkpoint: int | None = None,
) -> dict[str, object]:
    """Read prepared unseen-season checkpoints; never train or read raw tables.

    The index omits full player distributions. A detail request must identify
    an exact checkpoint; missing/unavailable states return 404, never a fallback.
    """
    try:
        raw = json.loads(Path(predictions_path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise PredictionDataUnavailable() from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PredictionDataInvalid() from exc
    current = validate_prediction_payload(raw)
    timeline = raw.get("timeline")
    if timeline is None:
        raise PredictionApiError("Timeline is unavailable. Rebuild predictions to enable it.", HTTPStatus.SERVICE_UNAVAILABLE)
    try:
        timeline = _required_mapping(timeline, "timeline")
        if timeline.get("version") != 1:
            raise ValueError("Unsupported Timeline version")
        note = _required_string(timeline, "note")
        metadata = current["metadata"]
        training = metadata.get("training_seasons")
        if not isinstance(training, list):
            raise ValueError("Missing training provenance")
        last_training = max(training, default=0)
        states = []
        seen = set()
        for item in _required_list(timeline.get("states"), "timeline.states"):
            item = _required_mapping(item, "state")
            state = {field: _required_int(item, field) for field in (
                "season", "episode", "checkpoint", "final_n", "active_players",
            )}
            key = (state["season"], state["episode"], state["checkpoint"])
            if (key in seen or not last_training < state["season"] <= metadata["current_season"]
                    or state["episode"] < 1 or state["checkpoint"] < 0
                    or state["active_players"] < 1 or state["final_n"] != state["active_players"]
                    or (state["season"] == metadata["current_season"] and state["episode"] > metadata["latest_episode"])):
                raise ValueError("Invalid or ineligible Timeline state")
            seen.add(key)
            board = validate_prediction_payload({
                "metadata": {**metadata, "current_season": state["season"], "latest_episode": state["episode"],
                             "latest_final_n": state["final_n"], "active_players": state["active_players"]},
                "players": item.get("players"), "projected_boot_order": item.get("projected_boot_order"),
                "evaluation": current["evaluation"],
            })
            ids = [player["castaway_id"] for player in board["players"]]
            order_ids = [player["castaway_id"] for player in board["projected_boot_order"]]
            if len(set(ids)) != len(ids) or set(ids) != set(order_ids) or not all(
                math.isclose(sum(player[field] for player in board["players"]), 1.0, abs_tol=1e-6)
                for field in ("next_boot_probability", "winner_probability")
            ):
                raise ValueError("Invalid Timeline distribution")
            states.append((state, board))
        available = {(state["season"], state["episode"]) for state, _board in states}
        episodes = []
        episode_keys = set()
        for item in _required_list(timeline.get("episodes", [
            {"season": season, "episode": episode, "available": True} for season, episode in sorted(available)
        ]), "timeline.episodes"):
            item = _required_mapping(item, "episode")
            season_value, episode_value = _required_int(item, "season"), _required_int(item, "episode")
            key = (season_value, episode_value)
            if (key in episode_keys or not last_training < season_value <= metadata["current_season"]
                    or episode_value < 1 or (season_value == metadata["current_season"] and episode_value > metadata["latest_episode"])
                    or not isinstance(item.get("available"), bool) or item["available"] != (key in available)):
                raise ValueError("Invalid Timeline episode coverage")
            episode_keys.add(key)
            episodes.append({"season": season_value, "episode": episode_value, "available": item["available"]})
        if not available.issubset(episode_keys):
            raise ValueError("Missing Timeline episode coverage")
    except (TypeError, ValueError) as exc:
        raise PredictionDataInvalid() from exc
    if season is not None or episode is not None or checkpoint is not None:
        match = next(((state, board) for state, board in states if (
            state["season"], state["episode"], state["checkpoint"]
        ) == (season, episode, checkpoint)), None)
        if match is None:
            raise PredictionApiError("Timeline checkpoint is unavailable or was used for training.", HTTPStatus.NOT_FOUND)
        state, board = match
        return {**board, "timeline_context": {**state, "note": note}}
    return {"metadata": metadata, "note": note, "states": [state for state, _board in states], "episodes": episodes}


def analytics_schema_payload(analytics_path: str | Path = DEFAULT_ANALYTICS) -> AnalyticsSchemaPayload:
    rows = analytics_rows(analytics_path)
    return {
        "dataset": {
            "id": "analytics_player_season",
            "grain": "one row per castaway per season",
            "row_count": len(rows),
        },
        "dimensions": [
            {
                "id": dimension.id,
                "label": dimension.label,
                "column": dimension.column,
                "labels": dimension.labels or {},
            }
            for dimension in DIMENSIONS.values()
        ],
        "metrics": [
            {
                "id": metric.id,
                "label": metric.label,
                "format": metric.format,
                "minimum_sample_size": metric.minimum_sample_size,
                "proxy": metric.proxy,
                "description": metric.description,
                "warning": metric.warning,
            }
            for metric in METRICS.values()
        ],
        "filters": [
            {
                "field": field,
                "operators": ["equals", "not_equals", "in", "not_in", "range", "is_true", "is_false"],
            }
            for field in sorted(SUPPORTED_FILTER_FIELDS)
        ],
        "chart_types": ["bar", "horizontal_bar", "table"],
    }


def analytics_presets_payload() -> AnalyticsPresetsPayload:
    return {"presets": preset_configs()}


def analytics_query_payload(
    config: object,
    analytics_path: str | Path = DEFAULT_ANALYTICS,
) -> AnalyticsQueryPayload:
    if not isinstance(config, dict):
        raise AnalyticsQueryInvalid("Analytics query config must be an object.")
    try:
        return run_chart_query(analytics_rows(analytics_path), config)
    except AnalyticsQueryError as exc:
        raise AnalyticsQueryInvalid(str(exc)) from exc


def analytics_rows(analytics_path: str | Path = DEFAULT_ANALYTICS) -> list[dict[str, object]]:
    path = Path(analytics_path)
    if not path.exists():
        raise AnalyticsDataUnavailable()
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fieldnames = set(reader.fieldnames or [])
            if not set(ANALYTICS_PLAYER_SEASON_COLUMNS).issubset(fieldnames):
                raise AnalyticsDataInvalid()
            return list(reader)
    except csv.Error as exc:
        raise AnalyticsDataInvalid() from exc
    except OSError as exc:
        raise AnalyticsDataUnavailable() from exc


def current_season_payload(payload: PredictionPayload | None = None) -> CurrentSeasonPayload:
    payload = payload or prediction_payload()
    metadata = payload["metadata"]
    return {
        "current_season": _required_int(metadata, "current_season"),
        "latest_episode": _required_int(metadata, "latest_episode"),
        "latest_final_n": _required_int(metadata, "latest_final_n"),
        "active_players": _required_int(metadata, "active_players"),
    }


def error_payload(exc: PredictionApiError) -> ErrorPayload:
    return {"error": exc.message}


def validate_prediction_payload(value: object) -> PredictionPayload:
    try:
        payload = _required_mapping(value, "prediction payload")
        metadata = _validate_metadata(payload.get("metadata"))
        players = [
            _validate_player(player, f"players[{index}]")
            for index, player in enumerate(_required_list(payload.get("players"), "players"))
        ]
        projected_boot_order = [
            _validate_projected_boot(row, f"projected_boot_order[{index}]")
            for index, row in enumerate(_required_list(payload.get("projected_boot_order"), "projected_boot_order"))
        ]
        evaluation = dict(_required_mapping(payload.get("evaluation"), "evaluation"))
        if metadata["active_players"] != len(players):
            raise ValueError("metadata.active_players does not match players length")
        if len(projected_boot_order) != len(players):
            raise ValueError("projected_boot_order length does not match players length")
        return {
            "metadata": metadata,
            "players": players,
            "projected_boot_order": projected_boot_order,
            "evaluation": evaluation,
        }
    except (TypeError, ValueError) as exc:
        raise PredictionDataInvalid() from exc


def _validate_metadata(value: object) -> dict[str, object]:
    metadata = _required_mapping(value, "metadata")
    validated: dict[str, object] = {
        "generated_at": _required_string(metadata, "generated_at"),
        "model_name": _required_string(metadata, "model_name"),
        "model_selection_policy": _required_string(metadata, "model_selection_policy"),
        "source_workbook": _required_string(metadata, "source_workbook"),
        "current_season": _required_int(metadata, "current_season"),
        "latest_episode": _required_int(metadata, "latest_episode"),
        "latest_final_n": _required_int(metadata, "latest_final_n"),
        "active_players": _required_int(metadata, "active_players"),
        "disclaimer": _required_string(metadata, "disclaimer"),
    }
    if metadata.get("source_data") is not None:
        validated["source_data"] = dict(_required_mapping(metadata["source_data"], "metadata.source_data"))
    if metadata.get("training_seasons") is not None:
        training = _required_list(metadata["training_seasons"], "training_seasons")
        if any(isinstance(season, bool) or not isinstance(season, int) or season < 1 for season in training):
            raise ValueError("Invalid training seasons")
        validated["training_seasons"] = training
        validated["training_policy"] = _required_string(metadata, "training_policy")
    return validated


def _validate_player(value: object, field: str) -> dict[str, object]:
    player = _required_mapping(value, field)
    return {
        "castaway_id": _required_string(player, "castaway_id"),
        "castaway": _required_string(player, "castaway"),
        "tribe": _required_string(player, "tribe"),
        "original_tribe": _required_string(player, "original_tribe"),
        "tribe_status": _required_string(player, "tribe_status"),
        "tribe_status_display": _required_string(player, "tribe_status_display"),
        "occupation": _required_string(player, "occupation"),
        "soc_code": _required_string(player, "soc_code"),
        "soc_title": _required_string(player, "soc_title"),
        "soc_major_group": _required_string(player, "soc_major_group"),
        "raw_next_boot_risk": _required_float(player, "raw_next_boot_risk"),
        "next_boot_probability": _required_probability(player, "next_boot_probability"),
        "winner_probability": _required_probability(player, "winner_probability"),
        "explanation": [
            _required_string({"explanation": item}, "explanation")
            for item in _required_list(player.get("explanation"), "explanation")
        ],
    }


def _validate_projected_boot(value: object, field: str) -> dict[str, object]:
    row = _required_mapping(value, field)
    return {
        "projected_order": _required_int(row, "projected_order"),
        "projected_final_n_before_boot": _required_int(row, "projected_final_n_before_boot"),
        "castaway_id": _required_string(row, "castaway_id"),
        "castaway": _required_string(row, "castaway"),
        "projected_boot_probability": _required_probability(row, "projected_boot_probability"),
    }


def _required_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{field} must be an object")
    return value


def _required_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"{field} must be a list")
    return value


def _required_string(mapping: dict[str, object], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _required_int(mapping: dict[str, object], field: str) -> int:
    value = mapping.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer")
    return value


def _required_float(mapping: dict[str, object], field: str) -> float:
    value = mapping.get(field)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field} must be numeric")
    return float(value)


def _required_probability(mapping: dict[str, object], field: str) -> float:
    value = _required_float(mapping, field)
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise ValueError(f"{field} must be between 0 and 1")
    return value


def create_app():
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Install with: pip install -e \".[api]\"")

    app = FastAPI(title="Survivor Calculator API", version="0.1.0")

    @app.exception_handler(PredictionApiError)
    def prediction_api_error_handler(_request: object, exc: PredictionApiError):
        return JSONResponse(status_code=int(exc.status_code), content=error_payload(exc))

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthPayload:
        return {"status": "ok"}

    @app.get("/api/current-season", response_model=CurrentSeasonResponse)
    def current_season() -> CurrentSeasonPayload:
        return current_season_payload()

    @app.get("/api/predictions/current", response_model=PredictionResponse)
    def current_predictions() -> PredictionPayload:
        return prediction_payload()

    @app.get("/api/predictions/timeline", response_model=None)
    def prediction_timeline() -> dict[str, object]:
        return timeline_payload(DEFAULT_PREDICTIONS)

    @app.get("/api/predictions/timeline/{season}/{episode}/{checkpoint}", response_model=None)
    def prediction_checkpoint(season: int, episode: int, checkpoint: int) -> dict[str, object]:
        return timeline_payload(DEFAULT_PREDICTIONS, season=season, episode=episode, checkpoint=checkpoint)

    @app.get("/api/players/{castaway_id}", response_model=None)
    def player_profile(castaway_id: str) -> dict[str, object]:
        return player_profile_payload(castaway_id)

    # Payload functions validate these dictionaries. Disable inferred response
    # models because Python 3.11 typing.TypedDict is unsupported by Pydantic v2.
    @app.get("/api/analytics/schema", response_model=None)
    def analytics_schema() -> AnalyticsSchemaPayload:
        return analytics_schema_payload()

    @app.get("/api/analytics/presets", response_model=None)
    def analytics_presets() -> AnalyticsPresetsPayload:
        return analytics_presets_payload()

    @app.post("/api/analytics/query", response_model=None)
    def analytics_query(config: object = Body(...)) -> AnalyticsQueryPayload:
        return analytics_query_payload(config)

    return app


app = create_app() if FastAPI is not None else None

