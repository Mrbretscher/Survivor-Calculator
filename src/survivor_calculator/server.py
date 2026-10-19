"""Small standard-library API server for local development."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from survivor_calculator.api import (
    DEFAULT_ANALYTICS,
    DEFAULT_PREDICTIONS,
    DEFAULT_WORKBOOK,
    AnalyticsQueryInvalid,
    PredictionApiError,
    analytics_presets_payload,
    analytics_query_payload,
    analytics_schema_payload,
    current_season_payload,
    error_payload,
    prediction_payload,
    player_profile_payload,
)


class SurvivorApiHandler(BaseHTTPRequestHandler):
    """Serve the same prediction contract as the optional FastAPI app."""

    def do_OPTIONS(self) -> None:
        self._send_json({}, HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/health":
                self._send_json({"status": "ok"})
                return
            if path == "/api/predictions/current":
                self._send_json(prediction_payload(DEFAULT_WORKBOOK, DEFAULT_PREDICTIONS))
                return
            if path == "/api/current-season":
                payload = prediction_payload(DEFAULT_WORKBOOK, DEFAULT_PREDICTIONS)
                self._send_json(current_season_payload(payload))
                return
            if path.startswith("/api/players/"):
                self._send_json(player_profile_payload(
                    path.removeprefix("/api/players/"), DEFAULT_PREDICTIONS, DEFAULT_ANALYTICS,
                ))
                return
            if path == "/api/analytics/schema":
                self._send_json(analytics_schema_payload(DEFAULT_ANALYTICS))
                return
            if path == "/api/analytics/presets":
                self._send_json(analytics_presets_payload())
                return
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except PredictionApiError as exc:
            self._send_json(error_payload(exc), exc.status_code)
        except Exception:  # pragma: no cover - defensive server boundary
            self._send_json({"error": "Internal server error"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/analytics/query":
                self._send_json(analytics_query_payload(self._read_json_body(), DEFAULT_ANALYTICS))
                return
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except PredictionApiError as exc:
            self._send_json(error_payload(exc), exc.status_code)
        except Exception:  # pragma: no cover - defensive server boundary
            self._send_json({"error": "Internal server error"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json_body(self) -> object:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise AnalyticsQueryInvalid("Request body must be valid JSON.") from exc
        if content_length <= 0:
            raise AnalyticsQueryInvalid("Request body must be valid JSON.")
        body = self.rfile.read(content_length)
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AnalyticsQueryInvalid("Request body must be valid JSON.") from exc

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = b"" if status == HTTPStatus.NO_CONTENT else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    predictions_path = Path(DEFAULT_PREDICTIONS)
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), SurvivorApiHandler)
    print(f"Serving Survivor Calculator API at http://{host}:{port}")
    server.serve_forever()

