# Gates: canonical TM provenance

OWNS: forecast_history_pipeline.py, tests/test_forecast_history_etl.py

Scope: TM workbook ranges use the month preceding the first target as calculation month

- [ ] G1: synthetic and real TM workbooks derive canonical calculation months
  CHECK: uv run python scripts/verify_canonical_horizons.py --stage tm-provenance
  EXPECT: TM PROVENANCE VERIFIED
  EVIDENCE: pending

- [ ] G2: ETL unit tests covering TM provenance pass
  CHECK: uv run python -m unittest tests.test_forecast_history_etl
  EXPECT: OK
  EVIDENCE: pending
