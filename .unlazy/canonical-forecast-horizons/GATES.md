# Gates: canonical forecast horizons

OWNS: forecast_history_pipeline.py, forecast_analysis/vintage_accuracy.py, dashboard/adapter.py, tests/test_forecast_history_etl.py, tests/test_common_vintage_accuracy.py, tests/test_static_dashboard_adapter.py, scripts/verify_canonical_horizons.py, scripts/validate_vintage_selector.mjs, artifacts/forecast_history/consolidated/forecast_history_waterfall.csv, artifacts/forecast_history/consolidated/source_summary.csv, artifacts/forecast_history/consolidated/validation_status.csv, artifacts/forecast_history/consolidated/tm_validation.csv, artifacts/forecast_history/consolidated/ml_validation.csv, validation-artifacts/vintage-selector/**

Scope: canonicalize ML and TM forecast horizons in the data pipeline and consume exact M5/M1 vintages in forecast accuracy

- [ ] G1: TM workbook provenance maps the first target month to the preceding calculation month
  CHECK: uv run python scripts/verify_canonical_horizons.py --stage tm-provenance
  EXPECT: TM PROVENANCE VERIFIED
  EVIDENCE: pending

- [ ] G2: regenerated waterfall data contains only exact M1 through M5 horizons for both ML and TM
  CHECK: uv run python scripts/verify_canonical_horizons.py --stage waterfall
  EXPECT: WATERFALL HORIZONS VERIFIED
  EVIDENCE: pending

- [ ] G3: forecast accuracy resolves Oldest to exact M5 and Latest to exact M1, with no fallback
  CHECK: uv run python scripts/verify_canonical_horizons.py --stage accuracy
  EXPECT: ACCURACY HORIZONS VERIFIED
  EVIDENCE: pending

- [ ] G4: all feature-scoped regression suites pass
  CHECK: uv run python -m unittest tests.test_forecast_history_etl tests.test_common_vintage_accuracy tests.test_static_dashboard_adapter tests.test_forecast_analysis_dashboard_ui
  EXPECT: OK
  EVIDENCE: pending

- [ ] G5: independent browser and screenshot validation passes at wide and compact viewports
  CHECK: node scripts/validate_vintage_selector.mjs --output validation-artifacts/vintage-selector
  EXPECT: VINTAGE SELECTOR VALIDATION PASSED
  EVIDENCE: pending

- [ ] G6: implementation has no blocking diagnostics or whitespace errors
  CHECK: git diff --check
  EXPECT: <no output>
  EVIDENCE: pending

- [ ] G7: manual review confirms no chart-level horizon substitution or common-cohort mismatch
  EVIDENCE: pending

<!-- Root completion requires every gate to have current evidence. If a gate becomes impossible, add ABANDON with a reason; do not delete it. -->
