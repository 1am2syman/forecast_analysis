# Gates: monthly vintage WAPE gap drill-down

OWNS: forecast_analysis/vintage_accuracy.py, forecast_analysis/__init__.py, dashboard/adapter.py, dashboard/server.py, dashboard/app.js, dashboard/index.html, dashboard/styles.css, tests/test_common_vintage_accuracy.py, tests/test_static_dashboard_adapter.py, tests/test_forecast_analysis_dashboard_ui.py, validation-artifacts/vintage-gap-drilldown/**

Scope: Clicking an Overview accuracy-chart month opens an on-demand, auditable brand-to-parent-SKU drill-down that exactly reconciles the selected baseline vintage to fixed Latest M1 WAPE.

- [x] G1: Domain calculations use the chart's exact common cohort and parent plus brand contributions reconcile to the month WAPE gap, including fixes and regressions
  CHECK: uv run python -m unittest tests.test_common_vintage_accuracy
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=7d72059c4305/23 entries; output=Ran 6 tests in 0.296s | OK

- [x] G2: The browser adapter exposes a validated on-demand vintage-gap endpoint without inflating the compact Overview payload
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_vintage_gap_drilldown_reconciles_without_inflating_overview tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_vintage_gap_drilldown_validates_month_and_historical_selection tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_vintage_gap_uses_oldest_selected_rule_and_all_selected_cohort
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=7d72059c4305/23 entries; output=Ran 3 tests in 3.914s | OK

- [x] G3: The dashboard UI contract includes click and keyboard entry, creators/regressions views, top-plus-Other reconciliation, searchable Show all, focus-safe close, and Product history handoff
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=7d72059c4305/23 entries; output=Ran 27 tests in 0.024s | OK

- [x] G4: Browser validation covers inline and fullscreen chart entry, creators, regressions, expanded search, and latest-only guidance at 1280x720 and 1920x1080 with no regression or out-of-place finding
  EVIDENCE: Complete 16-screenshot matrix plus geometry assertions and categorical review recorded in validation-artifacts/vintage-gap-drilldown/validation-report.md; Regressed: None observed; Out of place: None observed.

- [x] G5: Edited source files have no blocking diagnostics or syntax errors
  CHECK: uv run python -m compileall -q forecast_analysis dashboard tests && node --check dashboard/app.js && echo vintage-gap-diagnostics-passed
  EXPECT: vintage-gap-diagnostics-passed
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=7d72059c4305/23 entries; output=vintage-gap-diagnostics-passed
