"""Hosted FastAPI entry point with browser origins and data readiness checks."""

from __future__ import annotations

import os
from http import HTTPStatus

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from survivor_calculator.api import (
    PredictionApiError,
    analytics_schema_payload,
    create_app,
    prediction_payload,
)


def create_deployment_app() -> FastAPI:
    """Create the hosted API without generating data or training on startup.

    SURVIVOR_ALLOWED_ORIGINS accepts comma-separated exact website origins.
    /health checks the process; /ready checks both prepared data files.
    """
    hosted_app = create_app()
    origins = [
        origin.strip()
        for origin in os.environ.get("SURVIVOR_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]
    hosted_app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @hosted_app.get("/ready", response_model=None)
    def ready() -> dict[str, str] | JSONResponse:
        try:
            predictions = prediction_payload()
            analytics = analytics_schema_payload()
        except PredictionApiError:
            return JSONResponse(
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                content={"status": "unavailable", "error": "Prepared data is unavailable or invalid."},
            )
        if not predictions["players"] or not analytics["dataset"]["row_count"]:
            return JSONResponse(
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                content={"status": "unavailable", "error": "Prepared data is empty."},
            )
        return {"status": "ready"}

    return hosted_app


app = create_deployment_app()
