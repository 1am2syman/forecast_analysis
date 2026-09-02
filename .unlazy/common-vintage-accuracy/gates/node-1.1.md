# Gates: analytical pipeline integration

OWNS: forecast_analysis/vintage_accuracy.py, forecast_analysis/__init__.py, dashboard/adapter.py, tests/test_common_vintage_accuracy.py, tests/test_static_dashboard_adapter.py

Scope: canonical calculation and adapter compose into one request-faithful common-cohort data pipeline

- [x] G1: canonical and feature-scoped adapter suites pass together
  CHECK: uv run python -m unittest tests.test_common_vintage_accuracy tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintage_request_defaults_and_validation tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintages_use_common_cohort_without_changing_global_metrics tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_invalid_requests_fail_with_field_specific_errors
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 6 tests in 2.961s | OK

- [x] G2: independent oracle verifies same target-month denominator and eligible count for every returned selected series
  CHECK: uv run python scripts/verify_common_vintage_accuracy.py
  EXPECT: COMMON VINTAGE ACCURACY VERIFIED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=COMMON VINTAGE ACCURACY VERIFIED
