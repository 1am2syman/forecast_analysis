# Gates: revision effectiveness evolution

OWNS: dashboard/adapter.py, dashboard/app.js, dashboard/index.html, dashboard/styles.css, tests/test_static_dashboard_adapter.py, tests/test_forecast_analysis_dashboard_ui.py, validation-artifacts/revision-effectiveness-evolution/**

Scope: Replace the Comparison revision-history chart with five-vintage balanced-score evolution and a selected-vintage detail overlay without changing the existing chart frame size.

- [x] G1: Revision-history payload exposes five cumulative vintage score positions and auditable score components for every eligible target month
  CHECK: cd ../.. && uv run python -m unittest tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_revision_history_uses_latest_six_actual_months_and_fixed_cohorts
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis/.unlazy/revision-effectiveness-evolution; path=cda89a5385a8/24 entries; output=Ran 1 test in 2.589s | OK

- [x] G2: Dashboard UI renders stepped vintage score evolution and the detail overlay while retaining the existing revision-history chart integration
  CHECK: cd ../.. && uv run python -m unittest tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis/.unlazy/revision-effectiveness-evolution; path=cda89a5385a8/24 entries; output=Ran 23 tests in 0.012s | OK

- [x] G3: Edited production files have no blocking diagnostics
  CHECK: cd ../.. && uv run python -m compileall -q dashboard forecast_analysis tests && echo diagnostics-check-passed
  EXPECT: diagnostics-check-passed
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis/.unlazy/revision-effectiveness-evolution; path=cda89a5385a8/24 entries; output=diagnostics-check-passed

- [x] G4: At the existing Comparison chart viewport, the replacement chart preserves its frame size, all six month bands remain legible, and clicking a vintage opens a centered no-scroll detail overlay; wider and compact screenshots show no clipping, wrapping, or overflow regressions
  EVIDENCE: Browser QA on Comparison confirmed SVG viewBox 0 0 720 300, 6 month bands, 30 vintage points, 24 stepped segments, and zero document horizontal overflow. Latest-vintage overlay measured centered at 1440×900 (1060×458 panel; clientHeight 456, scrollHeight 456) and at 800×700 (740×582 panel; clientHeight 580, scrollHeight 580). Console/network/error QA passed. Screenshots: validation-artifacts/revision-effectiveness-evolution/comparison-final-1440x900.png, overlay-final-1440x900.png, overlay-wide-1680x1050.png, overlay-compact-800x700.png, comparison-compact-800x700.png.
