# Gates: canonical common-cohort calculation

OWNS: forecast_analysis/vintage_accuracy.py, forecast_analysis/__init__.py, tests/test_common_vintage_accuracy.py

Scope: canonical forecast-analysis code calculates all vintage FA/WAPE series from one common cohort per target month

- [x] G1: adversarial fixture excludes a parent missing any selected vintage from every plotted line
  CHECK: uv run python -m unittest tests.test_common_vintage_accuracy.CommonVintageAccuracyTests.test_missing_selected_vintage_is_excluded_from_every_series
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 1 test in 0.027s | OK

- [x] G2: every series row shares eligible count and actual denominator while retaining independently checked FA numerators
  CHECK: uv run python -m unittest tests.test_common_vintage_accuracy.CommonVintageAccuracyTests.test_series_share_common_denominator_and_worked_fa_values
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 1 test in 0.018s | OK

- [x] G3: empty historical selection computes fixed latest alone and invalid duplicate rules fail deterministically
  CHECK: uv run python -m unittest tests.test_common_vintage_accuracy.CommonVintageAccuracyTests.test_latest_only_and_duplicate_rule_contract
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 1 test in 0.032s | OK

- [x] G4: complete canonical cohort test module passes
  CHECK: uv run python -m unittest tests.test_common_vintage_accuracy
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 3 tests in 0.047s | OK
