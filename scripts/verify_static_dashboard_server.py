#!/usr/bin/env python3
"""End-to-end HTTP verification for the canonical static dashboard server."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        address = sock.getsockname()
        if not isinstance(address, tuple) or len(address) < 2:
            raise RuntimeError("could not determine a local verification port")
        port = address[1]
        if not isinstance(port, int):
            raise RuntimeError("local verification port was not an integer")
        return port


def request(
    base_url: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 30,
) -> tuple[int, dict[str, str], bytes]:
    body = None
    headers: dict[str, str] = {"Accept": "application/json"}
    method = "GET"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    req = Request(f"{base_url}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def json_request(
    base_url: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    expected_status: int = 200,
    timeout: float = 30,
) -> dict[str, Any]:
    status, _, body = request(base_url, path, payload=payload, timeout=timeout)
    assert status == expected_status, f"{path}: expected {expected_status}, got {status}: {body[:500]!r}"
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{path}: response was not valid JSON") from exc
    assert isinstance(decoded, dict), f"{path}: expected JSON object"
    return decoded


def wait_for_server(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 75
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=2)
            raise AssertionError(
                f"dashboard server exited {process.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
            )
        try:
            health = json_request(base_url, "/api/health", timeout=2)
            if health.get("status") == "ok":
                return
        except (AssertionError, TimeoutError, URLError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise AssertionError(f"dashboard server did not become healthy: {last_error}")


def main() -> None:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            "uv",
            "run",
            "python",
            "-m",
            "dashboard.server",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--cache-size",
            "8",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_server(base_url, process)

        health = json_request(base_url, "/api/health")
        assert health["dataset_rows"] == 16_035
        assert health["actual_population_rows"] == 1_679

        status, headers, html = request(base_url, "/")
        assert status == 200
        assert headers["Content-Type"].startswith("text/html")
        assert b"Forecast performance" in html
        assert b"Live data" in html

        bootstrap = json_request(base_url, "/api/bootstrap", timeout=60)
        defaults = bootstrap["defaults"]
        assert not bootstrap["meta"]["synthetic"]
        assert bootstrap["metrics"]["eligible_observations"] == 1_203
        assert abs(bootstrap["metrics"]["forecast_accuracy_pct"] - 73.8876144) < 1e-5

        filtered_request = dict(defaults)
        filtered_request.update(
            {
                "parent_code": 703584,
                "horizon": 4,
                "minimum_actual_volume": 3.3,
                "vintage_a": {"kind": "specific_horizon", "value": 4},
                "vintage_b": {"kind": "specific_horizon", "value": 4},
                "hierarchy_status": "mapped",
                "actual_status": "matched_positive",
                "pair_status": "complete",
                "forecast_direction": "under",
                "revision_direction": "unchanged",
                "revision_outcome": "neutral",
                "minimum_absolute_error_kl": 1.0,
            }
        )
        filtered = json_request(
            base_url, "/api/view", payload=filtered_request, timeout=60
        )
        assert filtered["population_summary"]["forecast_rows"] == 1
        assert filtered["exceptions"]["total"] == 1
        assert filtered["exceptions"]["rows"][0]["parent_code"] == 703584
        assert filtered["product_detail"]["parent_code"] == 703584

        comparison_request = dict(defaults)
        comparison_request.update({"comparison_mode": True, "horizon": 1})
        comparison = json_request(
            base_url, "/api/view", payload=comparison_request, timeout=60
        )["comparison"]
        assert comparison["ready"]
        assert comparison["selected_horizon"] == 1
        assert comparison["comparable_pairs"] == 1_275

        product_request = dict(defaults)
        product_request["product_parent_code"] = 999173
        product = json_request(
            base_url, "/api/product", payload=product_request, timeout=60
        )["product_detail"]
        assert product["parent_code"] == 999173
        assert product["target_month"] == product["target_options"][-1]
        assert product["points"]["total"] > 0

        status, headers, csv_body = request(
            base_url,
            "/api/export",
            payload={"request": filtered_request, "kind": "vintages", "category": None},
            timeout=60,
        )
        assert status == 200
        assert headers["Content-Type"].startswith("text/csv")
        assert "forecast_tm_filtered_vintages.csv" in headers["Content-Disposition"]
        rows = list(csv.DictReader(io.StringIO(csv_body.decode("utf-8"))))
        assert len(rows) == filtered["exceptions"]["total"] == 1
        assert rows[0]["parent_code"] == "703584"

        invalid = json_request(
            base_url,
            "/api/view",
            payload={"source": "invalid"},
            expected_status=400,
        )
        assert "source must be one of" in invalid["error"]

        print("STATIC DASHBOARD SERVER VERIFICATION PASSED")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.returncode not in (0, -15):
            stdout, stderr = process.communicate()
            print(f"server stdout:\n{stdout}", file=sys.stderr)
            print(f"server stderr:\n{stderr}", file=sys.stderr)


if __name__ == "__main__":
    main()
