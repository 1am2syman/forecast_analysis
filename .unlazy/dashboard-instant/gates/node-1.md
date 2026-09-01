# Gates: Dashboard instantaneous integration

OWNS: dashboard/**, forecast_analysis/**, tests/**, scripts/**

Scope: Verify analytical, service, and browser phases compose into a correct and materially faster dashboard.

- [x] G1: focused analytical, service, and UI interaction regression suites pass
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard tests.test_static_dashboard_adapter tests.test_static_dashboard_server tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests && echo 'INTEGRATION PYTHON TESTS PASSED'
  EXPECT: INTEGRATION PYTHON TESTS PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 61 tests in 17.733s | OK

- [x] G2: performance budgets hold for cold views, bootstrap, and cache hits
  CHECK: uv run python scripts/benchmark_dashboard_performance.py --assert-default-ms 1500 --assert-comparison-ms 1500 --assert-cache-hit-ms 100 --assert-bootstrap-kib 150 && echo 'INTEGRATION PERFORMANCE PASSED'
  EXPECT: INTEGRATION PERFORMANCE PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Could not determine dtype for column 136, falling back to string | Could not determine dtype for column 137, falling back to string

- [x] G3: real Chromium behavior passes and changed files are syntactically clean
  CHECK: node --check dashboard/app.js && node scripts/validate_dashboard_functionality.mjs --output validation-artifacts/dashboard-instant-functional && git diff --check && echo 'INTEGRATION BROWSER PASSED'
  EXPECT: INTEGRATION BROWSER PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=EXHAUSTIVE DASHBOARD FUNCTIONALITY VALIDATION PASSED | INTEGRATION BROWSER PASSED
