# Gates: comparison scatter focus behavior

OWNS: dashboard/**, scripts/validate_revision_drilldown.mjs, tests/**, validation-artifacts/screenshots/**

Scope: keep all comparison scatter bubbles visible while focusing selected SKUs and increase the default bubble size by 50%, with automated and screenshot-based regression protection.

- [x] G1: focused source contracts protect the full-population focus logic and 50% radius increase
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests.test_revision_selection_focuses_the_full_scatter_population tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests.test_revision_scatter_has_local_sku_class_filter_and_full_default_viewbox && echo 'COMPARISON FOCUS TESTS PASSED'
  EXPECT: COMPARISON FOCUS TESTS PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 2 tests in 0.002s | OK

- [x] G2: browser validation proves single and multi-selection focus without removing context bubbles
  CHECK: node scripts/validate_revision_drilldown.mjs && echo 'REVISION DRILLDOWN VALIDATION PASSED'
  EXPECT: REVISION DRILLDOWN VALIDATION PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=REVISION DRILLDOWN BROWSER VALIDATION PASSED | REVISION DRILLDOWN VALIDATION PASSED

- [x] G3: exact reproduction screenshot shows selected SKU focus, faint context bubbles, and larger default bubbles at the comparison drill-down state
  EVIDENCE: validation-artifacts/screenshots/comparison-drilldown-focus-800x700.png; browser oracle measured 54 total bubbles, 2 selected, 52 pale context bubbles, and uniform radius 7.2 (up from 4.8).

- [x] G4: wider and compact viewport screenshots show no clipping, overlap, wrapping, or control-visibility regressions
  EVIDENCE: validation-artifacts/screenshots/comparison-drilldown-focus-1440x900.png and comparison-drilldown-focus-640x700.png; browser oracle verified zero document overflow, popover within viewport, and scatter chart within its frame at both widths. Existing scrollable toolbar/popover overflow remains contained.

- [x] G5: changed files contain no whitespace errors
  CHECK: git diff --check && echo 'COMPARISON DIFF CHECK PASSED'
  EXPECT: COMPARISON DIFF CHECK PASSED
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=COMPARISON DIFF CHECK PASSED
