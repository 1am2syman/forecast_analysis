# Gates: issue 05 product history and exception exploration

OWNS: forecast_accuracy_app.py, .scratch/forecast-analysis-dashboard-ui-fixup/issues/05-deliver-product-history-and-exception-exploration.md

Scope: move product history after the main story and contain exception/audit tables without changing filtered rows or downloads.

- [ ] G1: Marimo syntax and cell dependency checks pass after product-history/table composition changes
  CHECK: uv run marimo check forecast_accuracy_app.py
  EXPECT: no errors found
  EVIDENCE: pending

- [ ] G2: product-history, exception, and download regression tests remain green
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard tests.test_forecast_analysis_population tests.test_forecast_analysis_quality tests.test_forecast_analysis_release
  EXPECT: OK
  EVIDENCE: pending

- [ ] G3: product-history and exception states pass the responsive overflow oracle
  CHECK: uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-responsive --root . --url <http://127.0.0.1:8765> --widths 390,768,1280,1440,1920
  EXPECT: responsive overflow verification passed
  EVIDENCE: pending

- [ ] G4: product identity, history evidence, bounded local table scrolling, discoverable search/sort/pagination/download, and empty history states are visually reviewable
  EVIDENCE: pending
