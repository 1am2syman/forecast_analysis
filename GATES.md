# Gates: implement forecast history review fixes

OWNS: forecast_history_pipeline.py, forecast_history_etl.py, scripts/**, tests/**, artifacts/forecast_history/consolidated/forecast_history_waterfall.csv

Scope: enforce source-family invariants, preserve atomic-output permissions, expose validation status, and verify TM oracle blob provenance with adversarial tests.

- [x] G1: focused tests cover every review finding and their failure modes
  CHECK: uv run python -m unittest discover -s tests -p 'test_*.py' && echo 'FORECAST HISTORY REVIEW TESTS PASSED'
  EXPECT: FORECAST HISTORY REVIEW TESTS PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 36 tests in 1.429s | OK

- [x] G2: the current source snapshot still matches the immutable TM oracle and regression manifest
  CHECK: uv run python scripts/verify_forecast_history_output.py --current-input-regression
  EXPECT: FORECAST HISTORY CURRENT REGRESSION VERIFIED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=FORECAST HISTORY CURRENT REGRESSION VERIFIED | Could not determine dtype for column 14, falling back to string

- [x] G3: the generated artifact satisfies the consolidated six-column contract and both-source requirement
  CHECK: uv run python scripts/verify_forecast_history_output.py --output artifacts/forecast_history/consolidated/forecast_history_waterfall.csv && echo 'FORECAST HISTORY OUTPUT CONTRACT PASSED'
  EXPECT: FORECAST HISTORY OUTPUT CONTRACT PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=FORECAST HISTORY OUTPUT VERIFIED rows=16035 columns=6 | FORECAST HISTORY OUTPUT CONTRACT PASSED

- [x] G4: safe generation validates and atomically publishes the current deterministic output
  CHECK: uv run python scripts/generate_forecast_history_output.py && echo 'SAFE FORECAST HISTORY GENERATION PASSED'
  EXPECT: SAFE FORECAST HISTORY GENERATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=SAFE FORECAST HISTORY GENERATION PASSED | Could not determine dtype for column 14, falling back to string

- [x] G5: all touched Python modules compile and the Marimo report validates
  CHECK: uv run python -m py_compile forecast_history_pipeline.py forecast_history_etl.py scripts/generate_forecast_history_output.py scripts/verify_forecast_history_output.py tests/test_forecast_history_etl.py && uv run marimo check forecast_history_etl.py && echo 'FORECAST HISTORY PYTHON AND MARIMO CHECKS PASSED'
  EXPECT: FORECAST HISTORY PYTHON AND MARIMO CHECKS PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=FORECAST HISTORY PYTHON AND MARIMO CHECKS PASSED

- [x] G6: changed files contain no whitespace errors
  CHECK: git diff --check && echo 'FORECAST HISTORY DIFF CHECK PASSED'
  EXPECT: FORECAST HISTORY DIFF CHECK PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=FORECAST HISTORY DIFF CHECK PASSED

- [x] G7: the final output retains the documented default permissions
  CHECK: mode=$(stat -c '%a' artifacts/forecast_history/consolidated/forecast_history_waterfall.csv) && test "$mode" = 644 && echo 'FORECAST HISTORY OUTPUT MODE PASSED'
  EXPECT: FORECAST HISTORY OUTPUT MODE PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=FORECAST HISTORY OUTPUT MODE PASSED
