# Gates: canonical waterfall horizons

OWNS: forecast_history_pipeline.py, tests/test_forecast_history_etl.py, scripts/verify_canonical_horizons.py, artifacts/forecast_history/consolidated/forecast_history_waterfall.csv, artifacts/forecast_history/consolidated/source_summary.csv, artifacts/forecast_history/consolidated/validation_status.csv, artifacts/forecast_history/consolidated/tm_validation.csv, artifacts/forecast_history/consolidated/ml_validation.csv

Scope: both source families publish only M1 through M5 rows through the six-column waterfall contract

- [x] G1: waterfall rows derive only horizons 1 through 5 for ML and TM
  CHECK: uv run python scripts/verify_canonical_horizons.py --stage waterfall
  EXPECT: WATERFALL HORIZONS VERIFIED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=WATERFALL HORIZONS VERIFIED

- [x] G2: safe generation and current output verification pass
  CHECK: uv run python scripts/generate_forecast_history_output.py && uv run python scripts/verify_forecast_history_output.py --output artifacts/forecast_history/consolidated/forecast_history_waterfall.csv
  EXPECT: FORECAST HISTORY OUTPUT VERIFIED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=FORECAST HISTORY OUTPUT VERIFIED rows=16035 columns=6 | Could not determine dtype for column 14, falling back to string
