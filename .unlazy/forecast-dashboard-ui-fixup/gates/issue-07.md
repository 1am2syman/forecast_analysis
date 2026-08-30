# Gates: issue 07 responsive accessible visual release

OWNS: forecast_accuracy_app.py, tests/e2e/test_forecast_analysis_dashboard.py, scripts/validate_forecast_analysis_dashboard_ui.py, validation-artifacts/**, .scratch/forecast-analysis-dashboard-ui-fixup/issues/07-complete-responsive-accessible-visual-release-gate.md

Scope: independently verify the finished dashboard through analytical, Marimo, browser, overflow, accessibility, and screenshot evidence.

- [ ] G1: analytical, notebook, release-validator, and browser regression suites pass without weakened assertions
  CHECK: uv run marimo check forecast_accuracy_app.py && uv run python -m unittest tests.test_forecast_analysis_dashboard tests.test_forecast_analysis_population tests.test_forecast_analysis_quality tests.test_forecast_analysis_release && uv run python scripts/validate_forecast_analysis_dashboard.py
  EXPECT: DASHBOARD RELEASE VALIDATION PASSED
  EVIDENCE: pending

- [ ] G2: document and application horizontal overflow stay within two pixels at every supported viewport and expanded state
  CHECK: uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-responsive --root . --url <http://127.0.0.1:8765> --widths 390,768,1280,1440,1920 --expand-all
  EXPECT: responsive overflow verification passed
  EVIDENCE: pending

- [ ] G3: final default and expanded screenshots, dimensions, before/after artifact, and visual-diff limitation/evidence are verified
  CHECK: uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-final-artifacts --root .
  EXPECT: final visual artifacts verification passed
  EVIDENCE: pending

- [ ] G4: keyboard order, focus visibility, heading/anchor structure, color-independent status text, and final issue verdicts are reviewed
  EVIDENCE: pending

- [ ] G5: no high-priority issue remains open in the final validation report
  EVIDENCE: pending
