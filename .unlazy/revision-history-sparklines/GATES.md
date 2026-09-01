# Gates: comparison revision history sparklines

OWNS: dashboard/adapter.py, dashboard/app.js, dashboard/styles.css, tests/test_static_dashboard_adapter.py, tests/test_forecast_analysis_dashboard_ui.py, scripts/validate_dashboard_functionality.mjs, docs/forecast-analysis-dashboard-spec.md, validation-artifacts/revision-history-sparklines/**

Scope: replace the redundant revision-outcomes table with six target-month bands containing angular forecast-revision paths on one shared delta-percent axis, color each revision by FA outcome, and support full-screen analysis with tooltips.

- [x] G1: the exceptions module exposes request-filtered, fixed-cohort revision histories for the latest six target months ending at the maximum selected actual month
  CHECK: cd ../.. && uv run python -m unittest tests.test_static_dashboard_adapter
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis/.unlazy/revision-history-sparklines; path=cda89a5385a8/24 entries; output=Ran 16 tests in 6.740s | OK

- [x] G2: the browser source contract renders independent month bands, a shared percentage axis, angular FA-outcome segments, endpoint-only rectangular markers, and a full-screen trigger
  CHECK: cd ../.. && uv run python -m unittest tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests
  EXPECT: OK
  EVIDENCE: exit=0; output=Ran 15 tests in 0.005s | OK

- [x] G3: the real Chromium dashboard interaction suite validates the chart, tooltips, source switching, responsive layout, and existing comparison workflows
  CHECK: cd ../.. && node scripts/validate_dashboard_functionality.mjs --output validation-artifacts/revision-history-sparklines
  EXPECT: EXHAUSTIVE DASHBOARD FUNCTIONALITY VALIDATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis/.unlazy/revision-history-sparklines; path=cda89a5385a8/24 entries; output=EXHAUSTIVE DASHBOARD FUNCTIONALITY VALIDATION PASSED

- [x] G4: the Comparison revision panel and full-screen chart are visually reviewed, with six month bands readable, no cross-band connector, and segment/endpoint tooltips working
  EVIDENCE: `validation-artifacts/revision-history-sparklines/live-revision-history-fullscreen.png` shows the full-screen Mar–Aug 2026 chart with green/red FA-outcome segments and the segment tooltip; endpoint tooltip also exposes net FA vs oldest.
