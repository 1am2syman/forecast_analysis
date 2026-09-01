# Gates: Phase 2 service API and caching

OWNS: dashboard/adapter.py, dashboard/server.py, tests/test_static_dashboard_adapter.py, tests/test_static_dashboard_server.py, scripts/benchmark_dashboard_performance.py

Scope: Add a compact modular dashboard service boundary, immutable-data caches/prewarm, and preserve compatibility and exports.

- [x] G1: adapter and HTTP service focused tests pass
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter tests.test_static_dashboard_server && echo 'PHASE2 SERVICE TESTS PASSED'
  EXPECT: PHASE2 SERVICE TESTS PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 12 tests in 7.380s | OK

- [x] G2: exact cached default response is below 100 ms and compact startup payload is below 150 KiB
  CHECK: uv run python scripts/benchmark_dashboard_performance.py --assert-cache-hit-ms 100 --assert-bootstrap-kib 150 && echo 'PHASE2 SERVICE PERFORMANCE PASSED'
  EXPECT: PHASE2 SERVICE PERFORMANCE PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Could not determine dtype for column 136, falling back to string | Could not determine dtype for column 137, falling back to string

- [x] G3: modified Python service files compile and have no whitespace errors
  CHECK: uv run python -m py_compile dashboard/adapter.py dashboard/server.py scripts/benchmark_dashboard_performance.py && git diff --check && echo 'PHASE2 STATIC CHECKS PASSED'
  EXPECT: PHASE2 STATIC CHECKS PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=PHASE2 STATIC CHECKS PASSED
