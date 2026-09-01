# Gates: browser drill-down interaction

OWNS: dashboard/app.js, dashboard/styles.css, scripts/validate_revision_drilldown.mjs, scripts/validate_dashboard_functionality.mjs

Scope: add accessible outcome popovers and synchronize selected parent codes across KPIs and both revision charts

- [x] G1: dedicated real-Chromium oracle proves four drill icons, compact top-20 popover, single-click replacement, Shift additive selection, KPI/chart filtering, and clear restore
  CHECK: node scripts/validate_revision_drilldown.mjs
  EXPECT: REVISION DRILLDOWN BROWSER VALIDATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=REVISION DRILLDOWN BROWSER VALIDATION PASSED

- [x] G2: JavaScript syntax remains valid
  CHECK: node --check dashboard/app.js && node --check scripts/validate_revision_drilldown.mjs && echo 'REVISION DRILLDOWN JAVASCRIPT CHECK PASSED'
  EXPECT: REVISION DRILLDOWN JAVASCRIPT CHECK PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=REVISION DRILLDOWN JAVASCRIPT CHECK PASSED

- [x] G3: popover and selection are keyboard-accessible and visually reviewed at desktop width
  EVIDENCE: reviewed /tmp/revision-drilldown-desktop.png and /tmp/revision-drilldown-selected.png at 1440x1000; the four icon buttons, compact five-column popover, selected-row highlight, selection bar, KPI change, revision-history redraw, and filtered scatter were visible and readable. The Chromium oracle confirms native BUTTON triggers/rows and Escape dismissal.
