from __future__ import annotations

import asyncio
import json
import os
import unittest
from http import HTTPStatus
from unittest.mock import patch

try:
    from survivor_calculator.deployment import create_deployment_app
except ModuleNotFoundError:
    create_deployment_app = None

from survivor_calculator.api import AnalyticsDataUnavailable, PredictionDataInvalid


@unittest.skipIf(create_deployment_app is None, "Install the existing [api] extras to test hosted FastAPI.")
class DeploymentTests(unittest.TestCase):
    def setUp(self) -> None:
        with patch.dict(os.environ, {"SURVIVOR_ALLOWED_ORIGINS": " https://example.netlify.app, http://localhost:3000 "}):
            self.app = create_deployment_app()

    def request(self, path: str, method: str = "GET", headers: list[tuple[bytes, bytes]] | None = None) -> tuple[int, dict[bytes, bytes], bytes]:
        """Exercise ASGI requests without adding a test-client dependency."""
        messages = []

        async def run() -> None:
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                messages.append(message)

            await self.app({
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": method, "scheme": "http", "path": path,
                "query_string": b"", "root_path": "", "headers": headers or [],
                "server": ("test", 80), "client": ("test", 123),
            }, receive, send)

        asyncio.run(run())
        start = next(message for message in messages if message["type"] == "http.response.start")
        body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
        return start["status"], dict(start["headers"]), body

    def test_allowed_browser_post_preflight(self) -> None:
        status, headers, _ = self.request("/api/analytics/query", "OPTIONS", [
            (b"origin", b"https://example.netlify.app"),
            (b"access-control-request-method", b"POST"),
            (b"access-control-request-headers", b"content-type"),
        ])
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(headers[b"access-control-allow-origin"], b"https://example.netlify.app")

    def test_unknown_browser_origin_is_not_allowed(self) -> None:
        status, headers, _ = self.request("/api/analytics/query", "OPTIONS", [
            (b"origin", b"https://untrusted.example"),
            (b"access-control-request-method", b"POST"),
        ])
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertNotIn(b"access-control-allow-origin", headers)

    def test_readiness_checks_both_datasets(self) -> None:
        with patch("survivor_calculator.deployment.prediction_payload", return_value={"players": [1]}), patch(
            "survivor_calculator.deployment.analytics_schema_payload", return_value={"dataset": {"row_count": 1}}
        ):
            status, _, body = self.request("/ready")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(json.loads(body), {"status": "ready"})

    def test_unavailable_or_invalid_data_fails_readiness_without_paths(self) -> None:
        for error in (AnalyticsDataUnavailable(), PredictionDataInvalid()):
            with self.subTest(error=type(error).__name__), patch("survivor_calculator.deployment.prediction_payload", side_effect=error):
                status, _, body = self.request("/ready")
                self.assertEqual(status, HTTPStatus.SERVICE_UNAVAILABLE)
                self.assertEqual(json.loads(body)["error"], "Prepared data is unavailable or invalid.")

    def test_empty_analytics_fails_readiness(self) -> None:
        with patch("survivor_calculator.deployment.prediction_payload", return_value={"players": [1]}), patch(
            "survivor_calculator.deployment.analytics_schema_payload", return_value={"dataset": {"row_count": 0}}
        ):
            status, _, _ = self.request("/ready")
        self.assertEqual(status, HTTPStatus.SERVICE_UNAVAILABLE)
