# Gates: integrated canonical forecast horizons

OWNS: forecast_history_pipeline.py, forecast_analysis/vintage_accuracy.py, dashboard/adapter.py, tests/test_forecast_history_etl.py, tests/test_common_vintage_accuracy.py, tests/test_static_dashboard_adapter.py, tests/test_forecast_analysis_dashboard_ui.py, scripts/verify_canonical_horizons.py, scripts/validate_vintage_selector.mjs, artifacts/forecast_history/consolidated/forecast_history_waterfall.csv, artifacts/forecast_history/consolidated/source_summary.csv, artifacts/forecast_history/consolidated/validation_status.csv, artifacts/forecast_history/consolidated/tm_validation.csv, artifacts/forecast_history/consolidated/ml_validation.csv, validation-artifacts/vintage-selector/**

Scope: canonical source provenance, exact M1–M5 output, deterministic M5/M1 accuracy, and responsive dashboard behavior are complete

- [ ] G1: all feature-scoped regression suites pass together
  CHECK: uv run python -m unittest tests.test_forecast_history_etl tests.test_common_vintage_accuracy tests.test_static_dashboard_adapter tests.test_forecast_analysis_dashboard_ui
  EXPECT: OK
  EVIDENCE: pending

- [ ] G2: all three independent canonical-horizon stages pass
  CHECK: uv run python scripts/verify_canonical_horizons.py --stage all
  EXPECT: CANONICAL HORIZONS VERIFIED
  EVIDENCE: pending

- [ ] G3: live browser validation passes against the regenerated dataset
  CHECK: node scripts/validate_vintage_selector.mjs --output validation-artifacts/vintage-selector
  EXPECT: VINTAGE SELECTOR VALIDATION PASSED
  EVIDENCE: pending

- [ ] G4: changed files have no whitespace errors
  CHECK: git diff --check
  EXPECT: <no output>
  EVIDENCE: pending

- [ ] G5: final diagnostics and responsive screenshot review show no blocking regression
  EVIDENCE: pending
