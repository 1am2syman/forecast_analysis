# Gates: issue 06 progressive data-quality diagnostics

OWNS: forecast_accuracy_app.py, .scratch/forecast-analysis-dashboard-ui-fixup/issues/06-deliver-progressive-data-quality-diagnostics.md

Scope: make data-quality summaries prominent and diagnostic evidence independently expandable while preserving statuses, counts, rows, and downloads.

- [ ] G1: Marimo syntax and cell dependency checks pass after data-quality composition changes
  CHECK: uv run marimo check forecast_accuracy_app.py
  EXPECT: no errors found
  EVIDENCE: pending

- [ ] G2: quality, filtering, empty-state, and download regression tests remain green
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard tests.test_forecast_analysis_population tests.test_forecast_analysis_quality tests.test_forecast_analysis_release
  EXPECT: OK
  EVIDENCE: pending

- [ ] G3: default and fully-expanded quality states pass the responsive overflow oracle
  CHECK: uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-responsive --root . --url <http://127.0.0.1:8765> --widths 390,768,1280,1440,1920
  EXPECT: responsive overflow verification passed
  EVIDENCE: pending

- [ ] G4: summary severity/count evidence, blocking errors, collapsed raw tables, and independent diagnostic downloads are visually reviewable
  EVIDENCE: pending
