from __future__ import annotations

import csv
import io
import json
from threading import Thread
from typing import Any
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dashboard.adapter import DashboardDataService  # pyright: ignore[reportMissingImports]
from dashboard.server import DashboardHTTPServer  # pyright: ignore[reportMissingImports]


class StaticDashboardServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = DashboardDataService.from_paths(cache_size=8)
        cls.server = DashboardHTTPServer(("127.0.0.1", 0), cls.service)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()

    def request_json(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        body = None
        method = "GET"
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
            method = "POST"
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=30) as response:
                status = response.status
                decoded = json.loads(response.read())
        except HTTPError as error:
            status = error.code
            decoded = json.loads(error.read())
        self.assertIsInstance(decoded, dict)
        return status, decoded

    def test_bootstrap_compact_view_and_module_routes(self) -> None:
        status, bootstrap = self.request_json("/api/bootstrap")
        self.assertEqual(status, 200)
        defaults = bootstrap["defaults"]
        self.assertNotIn("quality", bootstrap)
        self.assertLess(
            len(json.dumps(bootstrap, separators=(",", ":")).encode("utf-8")),
            150 * 1024,
        )

        status, compact = self.request_json("/api/view/compact", defaults)
        self.assertEqual(status, 200)
        self.assertEqual(compact["request"], defaults)
        self.assertEqual(
            compact["meta"]["dataset_version"],
            bootstrap["meta"]["dataset_version"],
        )

        status, trends = self.request_json("/api/module/trends", defaults)
        self.assertEqual(status, 200)
        self.assertEqual(trends["module"], "trends")
        self.assertEqual(trends["request"], defaults)
        self.assertEqual(trends["contract"]["merge"], "shallow-root")
        self.assertEqual(
            set(trends["data"]),
            {
                "monthly_performance",
                "monthly_audit",
                "horizon_performance",
                "horizon_audit",
            },
        )

    def test_legacy_full_view_product_and_invalid_module_routes(self) -> None:
        defaults = self.service.default_request()
        status, full = self.request_json("/api/view", defaults)
        self.assertEqual(status, 200)
        self.assertIn("quality", full)
        self.assertIn("exceptions", full)
        self.assertIn("product_detail", full)

        product_request = dict(defaults)
        product_request["product_parent_code"] = full["options"]["parent_products"][-1][
            "parent_code"
        ]
        status, product = self.request_json("/api/module/product", product_request)
        self.assertEqual(status, 200)
        self.assertEqual(
            product["data"]["product_detail"]["parent_code"],
            product_request["product_parent_code"],
        )
        status, legacy_product = self.request_json("/api/product", product_request)
        self.assertEqual(status, 200)
        self.assertEqual(
            legacy_product["product_detail"]["parent_code"],
            product_request["product_parent_code"],
        )

        export_request = dict(defaults)
        export_request.update(
            {
                "parent_code": 703584,
                "horizon": 4,
                "vintage_a": {"kind": "specific_horizon", "value": 4},
                "vintage_b": {"kind": "specific_horizon", "value": 4},
            }
        )
        body = json.dumps(
            {"request": export_request, "kind": "vintages", "category": None}
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/export",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            rows = list(
                csv.DictReader(io.StringIO(response.read().decode("utf-8")))
            )
            self.assertIn(
                "forecast_ml_filtered_vintages.csv",
                response.headers["Content-Disposition"],
            )
        self.assertTrue(rows)
        self.assertTrue(all(row["parent_code"] == "703584" for row in rows))

        status, error = self.request_json("/api/module/unknown", defaults)
        self.assertEqual(status, 400)
        self.assertIn("unsupported dashboard module", error["error"])


if __name__ == "__main__":
    unittest.main()
