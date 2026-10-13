"""Optional FastAPI surface for prediction results."""

from __future__ import annotations

import os
from pathlib import Path

from survivor_calculator.baseline import build_predictions, save_predictions
from survivor_calculator.features import build_features
from survivor_calculator.ingest import load_core_tables

try:
    from fastapi import FastAPI
except ModuleNotFoundError:  # pragma: no cover - exercised only without optional dependency
    FastAPI = None  # type: ignore[assignment]

DEFAULT_WORKBOOK = Path(os.environ.get("SURVIVOR_WORKBOOK_PATH", "survivoR.xlsx"))
DEFAULT_PREDICTIONS = Path(os.environ.get("SURVIVOR_PREDICTIONS_PATH", "data/processed/current_predictions.json"))


def prediction_payload(workbook_path: Path = DEFAULT_WORKBOOK, predictions_path: Path = DEFAULT_PREDICTIONS) -> dict[str, object]:
    if predictions_path.exists():
        import json

        return json.loads(predictions_path.read_text(encoding="utf-8"))
    tables = load_core_tables(workbook_path)
    features = build_features(tables)
    bundle = build_predictions(features, workbook_path)
    save_predictions(bundle, predictions_path)
    return bundle.to_dict()


def create_app():
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Install with: pip install -e \".[api]\"")

    app = FastAPI(title="Survivor Calculator API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/current-season")
    def current_season() -> dict[str, object]:
        payload = prediction_payload()
        metadata = payload["metadata"]
        return {
            "current_season": metadata["current_season"],
            "latest_episode": metadata["latest_episode"],
            "latest_final_n": metadata["latest_final_n"],
            "active_players": metadata["active_players"],
        }

    @app.get("/api/predictions/current")
    def current_predictions() -> dict[str, object]:
        return prediction_payload()

    return app


app = create_app() if FastAPI is not None else None

