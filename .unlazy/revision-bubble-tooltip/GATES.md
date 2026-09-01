# Gates: revision bubble sizing and tooltip cleanup

OWNS: forecast_analysis/metrics.py, dashboard/app.js, dashboard/styles.css, scripts/validate_dashboard_functionality.mjs, tests/test_forecast_analysis_dashboard.py, validation-artifacts/revision-bubble-tooltip/**

Scope: make revision bubble area visibly reflect actual volume across the skewed data range, remove native SVG title tooltips from revision points, enrich the designed tooltip with material, forecast, error, direction, and volume evidence, and add client-side filtering and sortable columns to the full action queue while preserving source isolation.

- [x] G1: metric tests prove revision scatter rows expose the forecast and error fields required by the enriched tooltip
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard && echo 'REVISION TOOLTIP METRIC TESTS PASSED'
  EXPECT: REVISION TOOLTIP METRIC TESTS PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 46 tests in 10.923s | OK

- [x] G2: dashboard JavaScript and browser validation JavaScript parse successfully
  CHECK: node --check dashboard/app.js && node --check scripts/validate_dashboard_functionality.mjs && echo 'REVISION TOOLTIP JAVASCRIPT CHECK PASSED'
  EXPECT: REVISION TOOLTIP JAVASCRIPT CHECK PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=REVISION TOOLTIP JAVASCRIPT CHECK PASSED

- [x] G3: real-browser validation proves varied bubble radii, zero native point titles, one enriched designed tooltip, action-queue filtering and sorting, and source isolation
  CHECK: node scripts/validate_dashboard_functionality.mjs --output validation-artifacts/revision-bubble-tooltip && echo 'REVISION TOOLTIP BROWSER VALIDATION PASSED'
  EXPECT: REVISION TOOLTIP BROWSER VALIDATION PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=EXHAUSTIVE DASHBOARD FUNCTIONALITY VALIDATION PASSED | REVISION TOOLTIP BROWSER VALIDATION PASSED

- [x] G4: edited files contain no whitespace errors
  CHECK: git diff --check -- forecast_analysis/metrics.py dashboard/app.js dashboard/styles.css scripts/validate_dashboard_functionality.mjs tests/test_forecast_analysis_dashboard.py && echo 'REVISION TOOLTIP DIFF CHECK PASSED'
  EXPECT: REVISION TOOLTIP DIFF CHECK PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=REVISION TOOLTIP DIFF CHECK PASSED
