# Gates: canonical horizon end-to-end proof

OWNS: scripts/verify_canonical_horizons.py, scripts/validate_vintage_selector.mjs, validation-artifacts/vintage-selector/**

Scope: live dashboard behavior and responsive screenshots expose the deterministic M5/M1 model

- [x] G1: feature-scoped Python and UI contract suites pass
  CHECK: uv run python -m unittest tests.test_common_vintage_accuracy tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintage_request_defaults_and_validation tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintages_use_common_cohort_without_changing_global_metrics tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_invalid_requests_fail_with_field_specific_errors tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 29 tests in 2.879s | OK

- [x] G2: live browser validator passes and refreshes reviewed artifacts
  CHECK: node scripts/validate_vintage_selector.mjs --output validation-artifacts/vintage-selector
  EXPECT: VINTAGE SELECTOR VALIDATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=VINTAGE SELECTOR VALIDATION PASSED

- [x] G3: screenshots at desktop, wide, and compact viewports are manually reviewed for labels, alignment, overflow, and chart clipping
  EVIDENCE: Reviewed desktop-open.png, desktop-multi.png, wide.png, compact.png, fullscreen-latest-only.png, and fullscreen-selector-open.png after the final browser run. Selector remains left of Full screen; exact M5/M4/M3/M2 and fixed M1 labels are legible; controls, popover, chart paths, and legends remain contained with no clipping. validation-report.json records pageOverflow=0, pathsContained=true, actionsContained=true, and fullscreen menu insideViewport=true.
