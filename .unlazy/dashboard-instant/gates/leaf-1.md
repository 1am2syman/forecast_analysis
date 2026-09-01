# Gates: Phase 1 analytical hot path

OWNS: forecast_analysis/metrics.py, forecast_analysis/dashboard.py, forecast_analysis/comparison.py, tests/test_forecast_analysis_dashboard.py, scripts/benchmark_dashboard_performance.py

Scope: Preserve analytical outputs while replacing repeated Python/DataFrame scans and duplicate computations with grouped vectorized work.

- [x] G1: focused analytical dashboard behavior remains correct
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard && echo 'PHASE1 ANALYTICS TESTS PASSED'
  EXPECT: PHASE1 ANALYTICS TESTS PASSED
  CWD: ../../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 45 tests in 11.610s | OK

- [x] G2: the reproducible real-data benchmark reports default and comparison cold views below 1500 ms after input loading
  CHECK: uv run python scripts/benchmark_dashboard_performance.py --assert-default-ms 1500 --assert-comparison-ms 1500 && echo 'PHASE1 PERFORMANCE PASSED'
  EXPECT: PHASE1 PERFORMANCE PASSED
  CWD: ../../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Could not determine dtype for column 136, falling back to string | Could not determine dtype for column 137, falling back to string

- [x] G3: modified Python files compile and have no whitespace errors
  CHECK: uv run python -m py_compile forecast_analysis/metrics.py forecast_analysis/dashboard.py forecast_analysis/comparison.py scripts/benchmark_dashboard_performance.py && git diff --check && echo 'PHASE1 STATIC CHECKS PASSED'
  EXPECT: PHASE1 STATIC CHECKS PASSED
  CWD: ../../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=PHASE1 STATIC CHECKS PASSED
