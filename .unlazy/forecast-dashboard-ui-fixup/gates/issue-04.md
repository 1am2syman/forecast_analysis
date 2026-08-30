# Gates: issue 04 revision and source comparison

OWNS: forecast_accuracy_app.py, .scratch/forecast-analysis-dashboard-ui-fixup/issues/04-deliver-revision-and-source-comparison-experience.md

Scope: group revision and TM-versus-ML comparison evidence while preserving source isolation, pair alignment, formulas, and downloads.

- [ ] G1: Marimo syntax and cell dependency checks pass after comparison/revision composition changes
  CHECK: uv run marimo check forecast_accuracy_app.py
  EXPECT: no errors found
  EVIDENCE: pending

- [ ] G2: comparison, revision, and download regression tests remain green
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard tests.test_forecast_analysis_population tests.test_forecast_analysis_quality tests.test_forecast_analysis_release
  EXPECT: OK
  EVIDENCE: pending

- [ ] G3: revision and comparison states pass the responsive overflow oracle
  CHECK: uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-responsive --root . --url <http://127.0.0.1:8765> --widths 390,768,1280,1440,1920
  EXPECT: responsive overflow verification passed
  EVIDENCE: pending

- [ ] G4: source groups, deltas, warnings, outcome counts, zero references, and bounded comparison tables are visually reviewable
  EVIDENCE: pending
