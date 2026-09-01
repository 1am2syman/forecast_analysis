# Gates: revision outcome drill-down integration

OWNS: dashboard/adapter.py, dashboard/app.js, dashboard/styles.css, tests/test_static_dashboard_adapter.py, scripts/validate_revision_drilldown.mjs, scripts/validate_dashboard_functionality.mjs, .unlazy/revision-outcome-drilldown/**

Scope: add outcome-card parent-code drill-down with canonical multi-parent filtering across KPIs and both revision charts

- [x] N1: backend and UI leaf ledgers pass independently after re-verification
  CHECK: node /root/.pi/agent/skills/unlazy/scripts/gate-check.mjs --root . --cwd . --reverify .unlazy/revision-outcome-drilldown/gates/leaf-1.1.md .unlazy/revision-outcome-drilldown/gates/leaf-1.2.md && echo 'REVISION DRILLDOWN LEAVES REVERIFIED'
  EXPECT: REVISION DRILLDOWN LEAVES REVERIFIED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=ALL MET (6 met, reran: 5, previously met reverified: 5) | REVISION DRILLDOWN LEAVES REVERIFIED

- [x] N2: focused backend and browser integration checks pass together
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter && node scripts/validate_revision_drilldown.mjs && echo 'REVISION DRILLDOWN INTEGRATION PASSED'
  EXPECT: REVISION DRILLDOWN INTEGRATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 19 tests in 7.177s | OK

- [x] N3: touched files have no whitespace errors
  CHECK: git diff --check -- dashboard/adapter.py dashboard/app.js dashboard/styles.css tests/test_static_dashboard_adapter.py scripts/validate_revision_drilldown.mjs scripts/validate_dashboard_functionality.mjs .unlazy/revision-outcome-drilldown && echo 'REVISION DRILLDOWN DIFF CHECK PASSED'
  EXPECT: REVISION DRILLDOWN DIFF CHECK PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=REVISION DRILLDOWN DIFF CHECK PASSED

- [x] N4: user-facing behavior is visually reviewed in a real browser at the Comparison → Revision subpanel
  EVIDENCE: reviewed /tmp/revision-drilldown-desktop.png and /tmp/revision-drilldown-selected.png at 1440x1000; confirmed compact top-20 presentation, selection state, KPI update, left revision chart redraw, right scatter filtering, and Clear affordance. Focused Python/JavaScript diagnostics and syntax checks were also run.
