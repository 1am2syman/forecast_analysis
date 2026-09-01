#!/usr/bin/env python3
"""Dependency-light HTTP server for the real-data static dashboard."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import posixpath
import sys
from typing import Any, cast
from urllib.parse import unquote, urlparse

from .adapter import (  # pyright: ignore[reportMissingImports]
    DEFAULT_ACTUALS,
    DEFAULT_FORECAST_HISTORY,
    DEFAULT_HIERARCHY,
    DashboardDataService,
    DashboardRequestError,
)

STATIC_ROOT = Path(__file__).resolve().parent
MAX_REQUEST_BYTES = 1_048_576


class DashboardHTTPServer(ThreadingHTTPServer):
    """HTTP server carrying the immutable dashboard data adapter."""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        service: DashboardDataService,
    ) -> None:
        self.service = service
        super().__init__(server_address, DashboardHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    @property
    def dashboard_server(self) -> DashboardHTTPServer:
        return cast(DashboardHTTPServer, self.server)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler interface
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json(
                {
                    "status": "ok",
                    "dataset_rows": self.dashboard_server.service.dataset.frame.height,
                    "actual_population_rows": self.dashboard_server.service.dataset.actual_population.height,
                    "refresh_timestamp": self.dashboard_server.service.refresh_timestamp,
                }
            )
            return
        if path == "/api/bootstrap":
            self._handle_json_call(self.dashboard_server.service.bootstrap)
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler interface
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/view":
                self._send_json(self.dashboard_server.service.view(payload))
                return
            if path == "/api/view/compact":
                self._send_json(self.dashboard_server.service.compact_view(payload))
                return
            if path.startswith("/api/module/"):
                module_name = path.removeprefix("/api/module/")
                if not module_name or "/" in module_name:
                    raise DashboardRequestError("dashboard module name is required")
                self._send_json(
                    self.dashboard_server.service.module(module_name, payload)
                )
                return
            if path == "/api/product":
                self._send_json({"product_detail": self.dashboard_server.service.product_detail(payload)})
                return
            if path == "/api/export":
                request = payload.get("request")
                if not isinstance(request, dict):
                    raise DashboardRequestError("export request must contain a request object")
                kind = payload.get("kind")
                if kind not in {
                    "vintages",
                    "revision_actions",
                    "quality",
                    "scope_exclusions",
                }:
                    raise DashboardRequestError("unsupported export kind")
                category = payload.get("category")
                if category is not None and not isinstance(category, str):
                    raise DashboardRequestError("export category must be a string or null")
                filename, csv_text = self.dashboard_server.service.export_csv(
                    request,
                    kind=kind,
                    category=category,
                )
                self._send_bytes(
                    csv_text.encode("utf-8"),
                    content_type="text/csv; charset=utf-8",
                    headers={
                        "Content-Disposition": f'attachment; filename="{filename}"',
                        "Cache-Control": "no-store",
                    },
                )
                return
            self._send_error_json(HTTPStatus.NOT_FOUND, "unknown API endpoint")
        except DashboardRequestError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except json.JSONDecodeError:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "request body must be valid JSON")
        except Exception as exc:  # app edge: preserve a structured HTTP failure
            self.log_error("unhandled API error: %s", exc)
            self._send_error_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "dashboard computation failed; inspect the server log",
            )

    def _handle_json_call(self, call: Any) -> None:
        try:
            self._send_json(call())
        except DashboardRequestError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # app edge: preserve a structured HTTP failure
            self.log_error("unhandled API error: %s", exc)
            self._send_error_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "dashboard computation failed; inspect the server log",
            )

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise DashboardRequestError("Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise DashboardRequestError("Content-Length must be an integer") from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise DashboardRequestError(
                f"request body must be between 0 and {MAX_REQUEST_BYTES} bytes"
            )
        body = self.rfile.read(length)
        try:
            decoded = body.decode("utf-8")
            payload = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DashboardRequestError("request body must be valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise DashboardRequestError("request body must be a JSON object")
        return payload

    def _serve_static(self, request_path: str) -> None:
        decoded = unquote(request_path)
        relative = posixpath.normpath(decoded).lstrip("/")
        if relative in {"", "."}:
            relative = "index.html"
        candidate = (STATIC_ROOT / relative).resolve()
        if STATIC_ROOT not in candidate.parents and candidate != STATIC_ROOT:
            self._send_error_json(HTTPStatus.NOT_FOUND, "static asset not found")
            return
        if not candidate.is_file():
            candidate = STATIC_ROOT / "index.html"
        content_type, _ = mimetypes.guess_type(candidate.name)
        self._send_bytes(
            candidate.read_bytes(),
            content_type=content_type or "application/octet-stream",
            headers={"Cache-Control": "no-cache"},
        )

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send_bytes(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            ),
            status=status,
            content_type="application/json; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message, "status": status.value}, status=status)

    def _send_bytes(
        self,
        body: bytes,
        *,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(
            f"{self.address_string()} - {self.log_date_time_string()} - {format % args}\n"
        )


def _environment_port(default: int = 8766) -> int:
    raw = os.environ.get("PORT", str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise SystemExit(f"fatal: PORT must be an integer, got {raw!r}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=_environment_port(),
    )
    parser.add_argument(
        "--forecast-history",
        type=Path,
        default=Path(
            os.environ.get("FORECAST_HISTORY_PATH") or str(DEFAULT_FORECAST_HISTORY)
        ),
    )
    parser.add_argument(
        "--hierarchy",
        type=Path,
        default=Path(os.environ.get("HIERARCHY_PATH") or str(DEFAULT_HIERARCHY)),
    )
    parser.add_argument(
        "--actuals",
        type=Path,
        default=Path(os.environ.get("ACTUALS_PATH") or str(DEFAULT_ACTUALS)),
    )
    parser.add_argument("--cache-size", type=int, default=32)
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        service = DashboardDataService.from_paths(
            args.forecast_history,
            args.hierarchy,
            args.actuals,
            cache_size=args.cache_size,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"fatal: canonical dashboard inputs could not be loaded: {exc}") from exc
    server = DashboardHTTPServer((args.host, args.port), service)
    print(
        f"Forecast dashboard ready at http://{args.host}:{server.server_port} "
        f"({service.dataset.frame.height:,} forecast rows)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Forecast dashboard stopping", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
