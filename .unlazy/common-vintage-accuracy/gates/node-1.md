# Gates: integrated common-cohort vintage accuracy

OWNS: forecast_analysis/vintage_accuracy.py, forecast_analysis/__init__.py, dashboard/adapter.py, dashboard/app.js, tests/test_common_vintage_accuracy.py, tests/test_static_dashboard_adapter.py, tests/test_forecast_analysis_dashboard_ui.py, scripts/verify_common_vintage_accuracy.py, scripts/validate_vintage_selector.mjs, validation-artifacts/vintage-selector/**

Scope: selected historical and fixed latest accuracy lines are analytically comparable, auditable, request-driven, and visually sound

- [x] G1: all feature-scoped suites pass together
  CHECK: uv run python -m unittest tests.test_common_vintage_accuracy tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintage_request_defaults_and_validation tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintages_use_common_cohort_without_changing_global_metrics tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_invalid_requests_fail_with_field_specific_errors tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 29 tests in 2.987s | OK

- [x] G2: independent analytical oracle and live browser oracle both pass
  CHECK: uv run python scripts/verify_common_vintage_accuracy.py && node scripts/validate_vintage_selector.mjs --output validation-artifacts/vintage-selector
  EXPECT: VINTAGE SELECTOR VALIDATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=COMMON VINTAGE ACCURACY VERIFIED | VINTAGE SELECTOR VALIDATION PASSED

- [x] G3: LSP, syntax, diff, and session diagnostics contain no new blocking findings
  EVIDENCE: `uv run pyright` over the changed Python implementation/tests reported 0 errors and 0 warnings; `node --check` passed for `dashboard/app.js` and the Chromium validator; `git diff --check` passed. Primary language-server checks were clean. Session diagnostics contain only nonblocking generic cross-language-method warnings plus three pre-existing CSS `!important` warnings absent from this diff; the auxiliary LSP index also retained stale missing-import findings for the newly added module despite command-line Pyright resolving it cleanly.

- [x] G4: branch ledgers are independently reverified and final artifacts reviewed with no abandonment
  EVIDENCE: Reverified every runnable gate in both depth-3 branches after the concurrent forecast-history artifact update. Re-read `validation-report.json` and reviewed all six regenerated desktop, wide, compact, multi-series, latest-only full-screen, and selector-open full-screen screenshots; selector ordering, containment, alignment, wrapping, chart clipping, and responsive behavior remain sound. No gate was abandoned.
