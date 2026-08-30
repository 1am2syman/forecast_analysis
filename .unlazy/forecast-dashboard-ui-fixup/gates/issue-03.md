# Gates: issue 03 single-source performance overview

OWNS: forecast_accuracy_app.py, .scratch/forecast-analysis-dashboard-ui-fixup/issues/03-deliver-single-source-performance-overview.md

Scope: present single-source KPIs and performance charts as bounded, readable overview sections without changing metric values.

- [ ] G1: Marimo syntax and cell dependency checks pass after KPI/chart composition changes
  CHECK: uv run marimo check forecast_accuracy_app.py
  EXPECT: no errors found
  EVIDENCE: pending

- [ ] G2: analytical metric and dashboard regression suites remain green
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard tests.test_forecast_analysis_population tests.test_forecast_analysis_quality tests.test_forecast_analysis_release
  EXPECT: OK
  EVIDENCE: pending

- [ ] G3: single-source KPI and chart states pass the responsive overflow oracle
  CHECK: uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-responsive --root . --url <http://127.0.0.1:8765> --widths 390,768,1280,1440,1920
  EXPECT: responsive overflow verification passed
  EVIDENCE: pending

- [ ] G4: headline/supporting KPI hierarchy, chart sizing, heatmap order, labels, and empty states are visually reviewable
  EVIDENCE: pending
