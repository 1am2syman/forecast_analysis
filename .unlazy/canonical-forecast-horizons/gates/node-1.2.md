# Gates: integrated deterministic forecast accuracy

OWNS: forecast_analysis/vintage_accuracy.py, dashboard/adapter.py, tests/test_common_vintage_accuracy.py, tests/test_static_dashboard_adapter.py, scripts/verify_canonical_horizons.py, scripts/validate_vintage_selector.mjs, validation-artifacts/vintage-selector/**

Scope: exact M5/M1 selection, common eligibility, adapter payloads, and browser rendering compose correctly

- [x] G1: analytical and adapter regression tests pass together
  CHECK: uv run python -m unittest tests.test_common_vintage_accuracy tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintage_request_defaults_and_validation tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintages_use_common_cohort_without_changing_global_metrics tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_invalid_requests_fail_with_field_specific_errors
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 6 tests in 2.803s | OK

- [x] G2: independent data and browser oracles both pass
  CHECK: uv run python scripts/verify_canonical_horizons.py --stage accuracy && node scripts/validate_vintage_selector.mjs --output validation-artifacts/vintage-selector
  EXPECT: VINTAGE SELECTOR VALIDATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=ACCURACY HORIZONS VERIFIED | VINTAGE SELECTOR VALIDATION PASSED
