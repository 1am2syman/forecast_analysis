# Gates: integrated canonical data pipeline

OWNS: forecast_history_pipeline.py, tests/test_forecast_history_etl.py, scripts/verify_canonical_horizons.py, artifacts/forecast_history/consolidated/forecast_history_waterfall.csv, artifacts/forecast_history/consolidated/source_summary.csv, artifacts/forecast_history/consolidated/validation_status.csv, artifacts/forecast_history/consolidated/tm_validation.csv, artifacts/forecast_history/consolidated/ml_validation.csv

Scope: TM provenance and cross-source M1–M5 waterfall validation compose without row loss or reconciliation regressions

- [ ] G1: ETL regression suite passes against regenerated artifacts
  CHECK: uv run python -m unittest tests.test_forecast_history_etl
  EXPECT: OK
  EVIDENCE: pending

- [ ] G2: canonical TM provenance and waterfall checks pass together
  CHECK: uv run python scripts/verify_canonical_horizons.py --stage tm-provenance && uv run python scripts/verify_canonical_horizons.py --stage waterfall
  EXPECT: WATERFALL HORIZONS VERIFIED
  EVIDENCE: pending
