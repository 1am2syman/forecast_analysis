# Gates: issue 02 responsive shell and filter workbench

OWNS: forecast_accuracy_app.py, tests/e2e/test_forecast_analysis_dashboard.py, .scratch/forecast-analysis-dashboard-ui-fixup/issues/02-deliver-responsive-shell-and-filter-workbench.md

Scope: contain the dashboard shell, expose a responsive filter workbench, and preserve the shared analytical population and control contracts.

- [ ] G1: Marimo syntax and cell dependency checks pass after the shell/filter composition changes
  CHECK: uv run marimo check forecast_accuracy_app.py
  EXPECT: no errors found
  EVIDENCE: pending

- [ ] G2: existing dashboard analytical and browser contracts remain green
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard tests.test_forecast_analysis_population tests.test_forecast_analysis_quality tests.test_forecast_analysis_release
  EXPECT: OK
  EVIDENCE: pending

- [ ] G3: the responsive shell and filter workbench have no page-level horizontal overflow at supported widths
  CHECK: uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-responsive --root . --url <http://127.0.0.1:8765> --widths 390,768,1280,1440,1920
  EXPECT: responsive overflow verification passed
  EVIDENCE: pending

- [ ] G4: title, purpose, navigation, reset action, grouped filters, and active-population status are visually reviewable in the browser
  EVIDENCE: pending
