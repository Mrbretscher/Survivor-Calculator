"""Optional FastAPI surface for prediction results."""

from __future__ import annotations

import csv
import json
import os
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
    current_season: int
    latest_episode: int
    latest_final_n: int
    active_players: int
    disclaimer: str


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
    return {
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
    if value < 0.0 or value > 1.0:
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

