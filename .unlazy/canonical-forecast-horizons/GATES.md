# Gates: canonical forecast horizons

OWNS: forecast_history_pipeline.py, forecast_analysis/vintage_accuracy.py, dashboard/adapter.py, tests/test_forecast_history_etl.py, tests/test_common_vintage_accuracy.py, tests/test_static_dashboard_adapter.py, scripts/verify_canonical_horizons.py, scripts/validate_vintage_selector.mjs, artifacts/forecast_history/consolidated/forecast_history_waterfall.csv, artifacts/forecast_history/consolidated/source_summary.csv, artifacts/forecast_history/consolidated/validation_status.csv, artifacts/forecast_history/consolidated/tm_validation.csv, artifacts/forecast_history/consolidated/ml_validation.csv, validation-artifacts/vintage-selector/**

Scope: canonicalize ML and TM forecast horizons in the data pipeline and consume exact M5/M1 vintages in forecast accuracy

- [x] G1: TM workbook provenance maps the first target month to the preceding calculation month
  CHECK: uv run python scripts/verify_canonical_horizons.py --stage tm-provenance
  EXPECT: TM PROVENANCE VERIFIED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=TM PROVENANCE VERIFIED

- [x] G2: regenerated waterfall data contains only exact M1 through M5 horizons for both ML and TM
  CHECK: uv run python scripts/verify_canonical_horizons.py --stage waterfall
  EXPECT: WATERFALL HORIZONS VERIFIED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=WATERFALL HORIZONS VERIFIED

- [x] G3: forecast accuracy resolves Oldest to exact M5 and Latest to exact M1, with no fallback
  CHECK: uv run python scripts/verify_canonical_horizons.py --stage accuracy
  EXPECT: ACCURACY HORIZONS VERIFIED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=ACCURACY HORIZONS VERIFIED

- [x] G4: all feature-scoped regression suites pass
  CHECK: uv run python -m unittest tests.test_forecast_history_etl tests.test_common_vintage_accuracy tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintage_request_defaults_and_validation tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintages_use_common_cohort_without_changing_global_metrics tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_invalid_requests_fail_with_field_specific_errors tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests tests.test_forecast_analysis_population.CurrentConsolidatedArtifactTests tests.test_forecast_analysis_dashboard.RealDashboardCoverageTests.test_real_comparison_coverage_includes_asymmetric_source_only_volume
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 75 tests in 8.542s | OK

- [x] G5: independent browser and screenshot validation passes at wide and compact viewports
  CHECK: node scripts/validate_vintage_selector.mjs --output validation-artifacts/vintage-selector
  EXPECT: VINTAGE SELECTOR VALIDATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=VINTAGE SELECTOR VALIDATION PASSED

- [x] G6: implementation has no blocking diagnostics or whitespace errors
  CHECK: git diff --check && echo 'DIFF CHECK PASSED'
  EXPECT: DIFF CHECK PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=DIFF CHECK PASSED

- [x] G7: manual review confirms no chart-level horizon substitution or common-cohort mismatch
  EVIDENCE: Independent adversarial oracle proves a parent with M4 but no M5 is excluded rather than substituted; the 75-test feature suite verifies exact endpoint and shared-cohort behavior; browser report shows every selected line has the same 17 target months (initial 2 series, multi 4 series, latest-only 1 series), with fixed Latest M1 and selectable Oldest M5/M4/M3/M2 identities.

<!-- Root completion requires every gate to have current evidence. If a gate becomes impossible, add ABANDON with a reason; do not delete it. -->
