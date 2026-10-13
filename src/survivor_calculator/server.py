"""Small standard-library API server for local development."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from survivor_calculator.api import DEFAULT_PREDICTIONS, DEFAULT_WORKBOOK, prediction_payload


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
                metadata = payload["metadata"]
                self._send_json(
                    {
                        "current_season": metadata["current_season"],
                        "latest_episode": metadata["latest_episode"],
                        "latest_final_n": metadata["latest_final_n"],
                        "active_players": metadata["active_players"],
                    }
                )
                return
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:  # pragma: no cover - defensive server boundary
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = b"" if status == HTTPStatus.NO_CONTENT else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
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

