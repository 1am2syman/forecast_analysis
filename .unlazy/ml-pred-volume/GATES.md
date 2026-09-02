# Gates: use PRED_VOLUME as the ML forecast value

OWNS: forecast_history_pipeline.py, tests/test_forecast_history_etl.py, tests/test_static_dashboard_adapter.py, ML_FORECAST_HISTORY_IMPLEMENTATION_PLAN.md, artifacts/forecast_history/consolidated/forecast_history_waterfall.csv, .unlazy/ml-pred-volume/**

Scope: make PRED_VOLUME the authoritative ML forecast quantity, retain Cal_forecast only as optional reference validation, and regenerate the consolidated forecast-history artifact without changing the TM history.

- [x] G1: focused automated tests prove PRED_VOLUME maps to qty and Cal_forecast can be absent or blank
  CHECK: uv run python -m unittest tests.test_forecast_history_etl.MlHistoryNormalizationTests && echo 'ML PRED VOLUME UNIT TESTS PASSED'
  EXPECT: ML PRED VOLUME UNIT TESTS PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 18 tests in 0.270s | OK

- [x] G2: the full forecast-history test suite passes, including current-workbook row-level PRED_VOLUME reconciliation and unchanged TM oracle output
  CHECK: uv run python -m unittest tests.test_forecast_history_etl && echo 'ML PRED VOLUME REGRESSION TESTS PASSED'
  EXPECT: ML PRED VOLUME REGRESSION TESTS PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 41 tests in 1.705s | OK

- [x] G3: safe generation publishes the consolidated output and the verifier accepts its contract
  CHECK: uv run python scripts/generate_forecast_history_output.py && uv run python scripts/verify_forecast_history_output.py --output artifacts/forecast_history/consolidated/forecast_history_waterfall.csv && echo 'ML PRED VOLUME OUTPUT VERIFIED'
  EXPECT: ML PRED VOLUME OUTPUT VERIFIED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=ML PRED VOLUME OUTPUT VERIFIED | Could not determine dtype for column 14, falling back to string

- [x] G4: the complete Python test suite passes after the forecast-value change
  CHECK: uv run python -m unittest discover -s tests -p 'test_*.py' && echo 'FORECAST ANALYSIS FULL TEST SUITE PASSED'
  EXPECT: FORECAST ANALYSIS FULL TEST SUITE PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 202 tests in 481.547s | OK

- [x] G5: touched Python modules compile, Marimo validates, and changed files have no whitespace errors
  CHECK: uv run python -m py_compile forecast_history_pipeline.py tests/test_forecast_history_etl.py && uv run marimo check forecast_history_etl.py && git diff --check && echo 'ML PRED VOLUME STATIC CHECKS PASSED'
  EXPECT: ML PRED VOLUME STATIC CHECKS PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=ML PRED VOLUME STATIC CHECKS PASSED

- [x] G6: documentation states PRED_VOLUME is authoritative and Cal_forecast is optional reference data
  CHECK: uv run python -c 'from pathlib import Path; text=Path("ML_FORECAST_HISTORY_IMPLEMENTATION_PLAN.md").read_text(); assert "Use `PRED_VOLUME` as the ML `qty` value." in text; assert "`Cal_forecast` | Optional validation/reference only; not written" in text; print("ML PRED VOLUME DOCUMENTATION VERIFIED")'
  EXPECT: ML PRED VOLUME DOCUMENTATION VERIFIED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=ML PRED VOLUME DOCUMENTATION VERIFIED
