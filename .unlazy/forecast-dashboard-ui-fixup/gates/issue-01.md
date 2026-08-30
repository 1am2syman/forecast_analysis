# Gates: issue 01 visual baseline and overflow oracle

OWNS: scripts/capture_forecast_analysis_dashboard_ui.py, scripts/validate_forecast_analysis_dashboard_ui.py, tests/test_forecast_analysis_dashboard_ui.py, validation-artifacts/forecast-analysis-dashboard-long-full.png, validation-artifacts/forecast-analysis-dashboard-default.png, validation-artifacts/forecast-analysis-dashboard-expanded.png, validation-artifacts/forecast-analysis-dashboard-ui-baseline.json, validation-artifacts/forecast-analysis-dashboard-ui-normalization-default.json, validation-artifacts/forecast-analysis-dashboard-ui-normalization-expanded.json, validation-artifacts/forecast-analysis-dashboard-ui-raw-default.json, validation-artifacts/forecast-analysis-dashboard-ui-raw-expanded.json, validation-artifacts/forecast-analysis-dashboard-ui-validation.md

Scope: establish a deterministic dashboard capture contract, genuine Marimo full-content normalization, independent two-pixel document/application overflow evidence, and content-addressed screenshot provenance without changing dashboard analysis behavior.

- [x] G1: immutable expanded baseline is preserved and its recorded metadata matches the checked-in artifact
  CHECK: uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-baseline --root . --artifact validation-artifacts/forecast-analysis-dashboard-long-full.png --expected-width 6650 --expected-height 11082
  EXPECT: baseline verification passed
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=baseline verification passed: 6650x11082 px, SHA256 29cd5651eadfec811b1c0671786f4a807dc846e1c59f9b5bddfab17e7261dfdd

- [x] G2: deterministic default analytical state and browser dimensions are recorded in a named baseline artifact by trusted live recapture
  CHECK: uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-capture --live-recapture --root . --artifact validation-artifacts/forecast-analysis-dashboard-ui-baseline.json --require-normalized --url http://127.0.0.1:8765/
  EXPECT: live recapture verification passed
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; output=live recapture verification passed; fresh two-state browser capture matched the checked-in analytical, raw rendered-control, disclosure, geometry, normalization, and screenshot contract; pre-normalization overflow: document=no, application=yes; normalized capture overflow: document=yes, application=no; full-page screenshot: 6650x11186 px; disclosure state difference: 0.0963 sampled-pixel ratio

- [x] G3: the Marimo normalization contract proves a full-content capture rather than a viewport-only capture by trusted live recapture
  CHECK: uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-capture --live-recapture --root . --artifact validation-artifacts/forecast-analysis-dashboard-ui-baseline.json --require-normalized --url http://127.0.0.1:8765/
  EXPECT: live recapture verification passed
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; output=live recapture verification passed; fresh two-state browser capture matched the checked-in analytical, raw rendered-control, disclosure, geometry, normalization, and screenshot contract; pre-normalization overflow: document=no, application=yes; normalized capture overflow: document=yes, application=no; full-page screenshot: 6650x11186 px; disclosure state difference: 0.0963 sampled-pixel ratio

- [x] G4: measurement and overflow evaluation logic passes deterministic tests, including an overflowing positive control and independent document/application results
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard_ui
  EXPECT: UI validation logic tests passed
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; output=Ran 13 tests in 439.259s | OK; UI validation logic tests passed

- [x] G5: existing analytical and Marimo contracts remain green without adding a permanently failing release test
  CHECK: uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-capture --live-recapture --root . --artifact validation-artifacts/forecast-analysis-dashboard-ui-baseline.json --require-normalized --url http://127.0.0.1:8765/ && uv run marimo check forecast_accuracy_app.py && uv run python -m unittest tests.test_forecast_analysis_dashboard tests.test_forecast_analysis_population tests.test_forecast_analysis_quality tests.test_forecast_analysis_release && uv run python scripts/validate_forecast_analysis_dashboard.py
  EXPECT: DASHBOARD RELEASE VALIDATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; output=79-test analytical suite OK; DASHBOARD RELEASE VALIDATION PASSED; measured 16,035 forecast rows, 1,679 actual rows, and 143 parent products | Could not determine dtype for column 137, falling back to string

- [x] G6: captured baseline artifacts were inspected for state, clipping, and full-content evidence
  EVIDENCE: reviewed `validation-artifacts/forecast-analysis-dashboard-default.png`, `validation-artifacts/forecast-analysis-dashboard-expanded.png`, and immutable `validation-artifacts/forecast-analysis-dashboard-long-full.png`; default is 6650x11082, expanded is 6650x11186 with the Data-quality filters region open, immutable is 6650x11082, and the captures reach the lower exception/data-quality sections without a viewport-only cutoff

- [x] G7: padded default screenshots cannot substitute for the expanded state
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard_ui.DashboardUiOverflowTests.test_padded_closed_screenshot_is_not_an_expanded_state
  EXPECT: OK
  EVIDENCE: exit=0; the negative regression creates a taller PNG with identical overlapping rows, verifies `overlap_difference_ratio=0.0`, and confirms `validate_state_transition` rejects it; the preserved capture also passes with overlapping-state difference `0.0963`.

- [x] G8: full-artifact screenshot substitutions are rejected even after screenshot records, bindings, and cross-state digests are recomputed
  CHECK: `uv run python -m unittest tests.test_forecast_analysis_dashboard_ui.DashboardUiArtifactTests.test_viewport_only_expanded_substitution_is_rejected_by_full_artifact tests.test_forecast_analysis_dashboard_ui.DashboardUiArtifactTests.test_padded_default_expanded_substitution_is_rejected_by_full_artifact tests.test_forecast_analysis_dashboard_ui.DashboardUiArtifactTests.test_wrong_state_expanded_substitution_is_rejected_by_full_artifact tests.test_forecast_analysis_dashboard_ui.DashboardUiArtifactTests.test_independent_meaningful_expanded_substitution_is_rejected_by_full_artifact tests.test_forecast_analysis_dashboard_ui.DashboardUiArtifactTests.test_immutable_baseline_padded_expanded_substitution_is_rejected_by_full_artifact`
  EXPECT: five tests pass
  EVIDENCE: exit=0; `Ran 5 tests in 6.521s | OK`; the viewport-only, padded-default, wrong-state, and independently meaningful fixtures retain the existing static negative coverage; the padded immutable-baseline fixture recomputes the screenshot output receipt, binding, normalization digest, and capture-anchor digest, passes the payload-only unit seam, and is rejected by the injected trusted live-recapture comparison.
