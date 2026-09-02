# Gates: adapter common-cohort contract

OWNS: dashboard/adapter.py, tests/test_static_dashboard_adapter.py, scripts/verify_common_vintage_accuracy.py

Scope: browser requests select accuracy vintages and receive auditable canonical common-cohort rows

- [x] G1: adapter defaults to oldest and validates ordered unique supported IDs
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintage_request_defaults_and_validation
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 1 test in 3.031s | OK

- [x] G2: selected series rows expose identical per-month cohort counts and denominators and do not alter global KPIs
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintages_use_common_cohort_without_changing_global_metrics
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 1 test in 2.885s | OK

- [x] G3: feature-scoped adapter contract tests pass after the forecast-history artifact update
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintage_request_defaults_and_validation tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintages_use_common_cohort_without_changing_global_metrics tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_invalid_requests_fail_with_field_specific_errors
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 3 tests in 3.033s | OK
