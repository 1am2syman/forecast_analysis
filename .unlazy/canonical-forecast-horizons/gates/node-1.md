# Gates: integrated canonical forecast horizons

OWNS: forecast_history_pipeline.py, forecast_analysis/vintage_accuracy.py, dashboard/adapter.py, tests/test_forecast_history_etl.py, tests/test_common_vintage_accuracy.py, tests/test_static_dashboard_adapter.py, tests/test_forecast_analysis_dashboard_ui.py, scripts/verify_canonical_horizons.py, scripts/validate_vintage_selector.mjs, artifacts/forecast_history/consolidated/forecast_history_waterfall.csv, artifacts/forecast_history/consolidated/source_summary.csv, artifacts/forecast_history/consolidated/validation_status.csv, artifacts/forecast_history/consolidated/tm_validation.csv, artifacts/forecast_history/consolidated/ml_validation.csv, validation-artifacts/vintage-selector/**

Scope: canonical source provenance, exact M1–M5 output, deterministic M5/M1 accuracy, and responsive dashboard behavior are complete

- [x] G1: all feature-scoped regression suites pass together
  CHECK: uv run python -m unittest tests.test_forecast_history_etl tests.test_common_vintage_accuracy tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintage_request_defaults_and_validation tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintages_use_common_cohort_without_changing_global_metrics tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_invalid_requests_fail_with_field_specific_errors tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests tests.test_forecast_analysis_population.CurrentConsolidatedArtifactTests tests.test_forecast_analysis_dashboard.RealDashboardCoverageTests.test_real_comparison_coverage_includes_asymmetric_source_only_volume
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 75 tests in 8.678s | OK

- [x] G2: all three independent canonical-horizon stages pass
  CHECK: uv run python scripts/verify_canonical_horizons.py --stage all
  EXPECT: CANONICAL HORIZONS VERIFIED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=ACCURACY HORIZONS VERIFIED | CANONICAL HORIZONS VERIFIED

- [x] G3: live browser validation passes against the regenerated dataset
  CHECK: node scripts/validate_vintage_selector.mjs --output validation-artifacts/vintage-selector
  EXPECT: VINTAGE SELECTOR VALIDATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=VINTAGE SELECTOR VALIDATION PASSED

- [x] G4: changed files have no whitespace errors
  CHECK: git diff --check && echo 'DIFF CHECK PASSED'
  EXPECT: DIFF CHECK PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=DIFF CHECK PASSED

- [x] G5: final diagnostics and responsive screenshot review show no blocking regression
  EVIDENCE: Primary LSP diagnostics returned 0 findings across 9 changed Python files; lens_diagnostics reported no errors across cached edited files; desktop, wide, compact, and fullscreen screenshots were reviewed with no alignment, wrapping, overflow, or clipping regression. Browser report records pageOverflow=0 and contained paths/actions.
