# Gates: source-filtered revision action chart

OWNS: dashboard/adapter.py, dashboard/app.js, dashboard/styles.css, scripts/validate_dashboard_functionality.mjs, tests/test_static_dashboard_adapter.py, validation-artifacts/revision-action-chart/**

Scope: make the Vintage revisions view respect the selected TM or ML source and turn the revision scatter into an action-oriented planner view with source-scoped metrics, quadrants, tooltips, and a ranked action queue.

- [x] G1: adapter tests prove revision points, action summaries, and action rows contain only the selected source for both TM and ML
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter && echo 'REVISION ACTION ADAPTER TESTS PASSED'
  EXPECT: REVISION ACTION ADAPTER TESTS PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 13 tests in 5.832s | OK

- [x] G2: dashboard JavaScript parses successfully
  CHECK: node --check dashboard/app.js && echo 'REVISION ACTION JAVASCRIPT CHECK PASSED'
  EXPECT: REVISION ACTION JAVASCRIPT CHECK PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=REVISION ACTION JAVASCRIPT CHECK PASSED

- [x] G3: exhaustive real-browser dashboard validation passes with the revised comparison tab
  CHECK: node scripts/validate_dashboard_functionality.mjs --output validation-artifacts/revision-action-chart && echo 'REVISION ACTION BROWSER VALIDATION PASSED'
  EXPECT: REVISION ACTION BROWSER VALIDATION PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=EXHAUSTIVE DASHBOARD FUNCTIONALITY VALIDATION PASSED | REVISION ACTION BROWSER VALIDATION PASSED

- [x] G4: edited files contain no whitespace errors
  CHECK: git diff --check -- dashboard/adapter.py dashboard/app.js dashboard/styles.css scripts/validate_dashboard_functionality.mjs tests/test_static_dashboard_adapter.py && echo 'REVISION ACTION DIFF CHECK PASSED'
  EXPECT: REVISION ACTION DIFF CHECK PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=REVISION ACTION DIFF CHECK PASSED
