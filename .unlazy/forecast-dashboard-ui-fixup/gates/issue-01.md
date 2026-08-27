# Gates: issue 01 visual baseline and overflow oracle

OWNS: scripts/capture_forecast_analysis_dashboard_ui.py, scripts/validate_forecast_analysis_dashboard_ui.py, tests/test_forecast_analysis_dashboard_ui.py, validation-artifacts/forecast-analysis-dashboard-long-full.png, validation-artifacts/forecast-analysis-dashboard-default.png, validation-artifacts/forecast-analysis-dashboard-expanded.png, validation-artifacts/forecast-analysis-dashboard-ui-baseline.json, validation-artifacts/forecast-analysis-dashboard-ui-normalization-default.json, validation-artifacts/forecast-analysis-dashboard-ui-normalization-expanded.json, validation-artifacts/forecast-analysis-dashboard-ui-raw-default.json, validation-artifacts/forecast-analysis-dashboard-ui-raw-expanded.json, validation-artifacts/forecast-analysis-dashboard-ui-validation.md

Scope: establish a deterministic dashboard capture contract, genuine Marimo full-content normalization, and independent two-pixel document/application overflow evidence without changing dashboard analysis behavior.

- [x] G1: immutable expanded baseline is preserved and its recorded metadata matches the checked-in artifact
  CHECK: uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-baseline --root . --artifact validation-artifacts/forecast-analysis-dashboard-long-full.png --expected-width 6650 --expected-height 11082
  EXPECT: baseline verification passed
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=baseline verification passed: 6650x11082 px, SHA256 29cd5651eadfec811b1c0671786f4a807dc846e1c59f9b5bddfab17e7261dfdd

- [x] G2: deterministic default analytical state and browser dimensions are recorded in a named baseline artifact
  CHECK: uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-capture --root . --artifact validation-artifacts/forecast-analysis-dashboard-ui-baseline.json
  EXPECT: capture verification passed
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; output=capture verification passed; pre-normalization overflow: document=no, application=yes; normalized capture overflow: document=yes, application=no; full-page screenshot: 6650x11186 px; disclosure state difference: 1.0000 sampled-pixel ratio

- [x] G3: the Marimo normalization contract proves a full-content capture rather than a viewport-only capture
  CHECK: uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-capture --root . --artifact validation-artifacts/forecast-analysis-dashboard-ui-baseline.json --require-normalized
  EXPECT: capture verification passed
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; output=capture verification passed; pre-normalization overflow: document=no, application=yes; normalized capture overflow: document=yes, application=no; full-page screenshot: 6650x11186 px; disclosure state difference: 1.0000 sampled-pixel ratio

- [x] G4: measurement and overflow evaluation logic passes deterministic tests, including an overflowing positive control and independent document/application results
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard_ui
  EXPECT: UI validation logic tests passed
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; output=Ran 7 tests in 442.095s | OK; UI validation logic tests passed

- [x] G5: existing analytical and Marimo contracts remain green without adding a permanently failing release test
  CHECK: uv run marimo check forecast_accuracy_app.py && uv run python -m unittest tests.test_forecast_analysis_dashboard tests.test_forecast_analysis_population tests.test_forecast_analysis_quality tests.test_forecast_analysis_release && uv run python scripts/validate_forecast_analysis_dashboard.py
  EXPECT: DASHBOARD RELEASE VALIDATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; output=79-test analytical suite OK; DASHBOARD RELEASE VALIDATION PASSED; measured 16,035 forecast rows, 1,679 actual rows, and 143 parent products | Could not determine dtype for column 137, falling back to string

- [x] G6: captured baseline artifacts were inspected for state, clipping, and full-content evidence
  EVIDENCE: reviewed `validation-artifacts/forecast-analysis-dashboard-default.png`, `validation-artifacts/forecast-analysis-dashboard-expanded.png`, and immutable `validation-artifacts/forecast-analysis-dashboard-long-full.png`; default is 6650x11082, expanded is 6650x11186 with the Data-quality filters region open, immutable is 6650x11082, and the captures reach the lower exception/data-quality sections without a viewport-only cutoff
