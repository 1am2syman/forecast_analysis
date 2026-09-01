# Gates: revision chart accessibility and action export

OWNS: dashboard/adapter.py, dashboard/server.py, dashboard/app.js, dashboard/styles.css, dashboard/index.html, scripts/validate_dashboard_functionality.mjs, tests/test_static_dashboard_adapter.py, validation-artifacts/revision-chart-accessibility/**

Scope: add a fullscreen Vintage revisions scatter, enlarge its standard-view labels and legend, make the full harmful-revision action queue scrollable with material descriptions, and provide a CSV download containing the evidence behind each flag while preserving TM/ML source isolation.

- [x] G1: adapter tests prove the full source-scoped harmful action dataset includes material descriptions and supporting forecast/error fields for TM and ML
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter && echo 'REVISION ACCESSIBILITY ADAPTER TESTS PASSED'
  EXPECT: REVISION ACCESSIBILITY ADAPTER TESTS PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 14 tests in 5.481s | OK

- [x] G2: dashboard JavaScript and validation JavaScript parse successfully
  CHECK: node --check dashboard/app.js && node --check scripts/validate_dashboard_functionality.mjs && echo 'REVISION ACCESSIBILITY JAVASCRIPT CHECK PASSED'
  EXPECT: REVISION ACCESSIBILITY JAVASCRIPT CHECK PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=REVISION ACCESSIBILITY JAVASCRIPT CHECK PASSED

- [x] G3: real-browser validation proves fullscreen rendering, readable standard labels, scrollable complete queue, material descriptions, CSV download, and source isolation
  CHECK: node scripts/validate_dashboard_functionality.mjs --output validation-artifacts/revision-chart-accessibility && echo 'REVISION ACCESSIBILITY BROWSER VALIDATION PASSED'
  EXPECT: REVISION ACCESSIBILITY BROWSER VALIDATION PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=EXHAUSTIVE DASHBOARD FUNCTIONALITY VALIDATION PASSED | REVISION ACCESSIBILITY BROWSER VALIDATION PASSED

- [x] G4: edited files contain no whitespace errors and no blocking diagnostics
  CHECK: git diff --check -- dashboard/adapter.py dashboard/server.py dashboard/app.js dashboard/styles.css dashboard/index.html scripts/validate_dashboard_functionality.mjs tests/test_static_dashboard_adapter.py && echo 'REVISION ACCESSIBILITY DIFF CHECK PASSED'
  EXPECT: REVISION ACCESSIBILITY DIFF CHECK PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=REVISION ACCESSIBILITY DIFF CHECK PASSED
