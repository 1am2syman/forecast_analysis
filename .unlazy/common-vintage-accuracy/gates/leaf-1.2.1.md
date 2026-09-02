# Gates: browser request integration

OWNS: dashboard/app.js, tests/test_forecast_analysis_dashboard_ui.py

Scope: selector changes request backend recomputation and render only returned common-cohort results

- [x] G1: source contract proves checkbox changes submit `accuracy_vintage_ids` and contain no browser-side WAPE/eligibility arithmetic
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests.test_accuracy_selector_requests_common_cohort_series
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 1 test in 0.002s | OK

- [x] G2: full UI source-contract suite passes
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 23 tests in 0.011s | OK
