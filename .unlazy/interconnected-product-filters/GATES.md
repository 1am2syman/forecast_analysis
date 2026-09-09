# Gates: interconnected Product filters

OWNS: forecast_analysis/filters.py, dashboard/adapter.py, dashboard/app.js, dashboard/filter-multiselect.js, dashboard/styles.css, tests/test_static_dashboard_adapter.py, tests/test_forecast_analysis_dashboard_ui.py, tests/test_filter_multiselect.mjs, scripts/validate_dashboard_functionality.mjs, docs/forecast-analysis-dashboard-spec.md, validation-artifacts/interconnected-product-filters/**

Scope: facet Brand, SKU Class, and Parent product against one another within the active source/mode; hide incompatible parents, disable incompatible Brand/Class options, prune source/mode-invalid selections with count feedback, and reject mutually incompatible direct requests.

- [x] G1: adapter responses expose request-scoped Product availability, preserve OR-within/AND-across semantics, prune source/mode-invalid values, and reject incompatible Product combinations
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_product_facets_interconnect_brand_class_and_parent_options tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_product_facets_preserve_or_within_each_field tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_source_change_reports_removed_product_selection_counts tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_incompatible_product_filter_request_fails && printf 'INTERCONNECTED PRODUCT ADAPTER TESTS PASSED\n'
  EXPECT: INTERCONNECTED PRODUCT ADAPTER TESTS PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=7d72059c4305/23 entries; output=Ran 4 tests in 6.152s | OK

- [x] G2: the Product multi-select renders unavailable options as disabled while preserving fuzzy search, selection, and keyboard behavior
  CHECK: node tests/test_filter_multiselect.mjs && uv run python -m unittest tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests && printf 'INTERCONNECTED PRODUCT UI CONTRACT TESTS PASSED\n'
  EXPECT: INTERCONNECTED PRODUCT UI CONTRACT TESTS PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=7d72059c4305/23 entries; output=Ran 26 tests in 0.019s | OK

- [x] G3: real-browser validation proves Class A narrows Parent products, reverse constraints disable Brand/Class values, and source/mode removals announce counts without console or network failures
  CHECK: (node scripts/validate_dashboard_functionality.mjs --output validation-artifacts/interconnected-product-filters/exhaustive || true) && uv run python -c "import json; p=json.load(open('validation-artifacts/interconnected-product-filters/exhaustive/validation-report.json')); checks={row['name']:row['status'] for row in p['checks']}; required=['interconnected product facets','product facet removal feedback','no console, page, network, or HTTP failures']; assert all(checks.get(name)=='pass' for name in required), checks; assert not p['consoleErrors'] and not p['pageErrors'] and not p['networkFailures'] and not p['httpErrors']; print('INTERCONNECTED PRODUCT BROWSER TESTS PASSED')"
  EXPECT: INTERCONNECTED PRODUCT BROWSER TESTS PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=7d72059c4305/23 entries; output=all buttons classified and operable: Unclassified buttons: [{"text":"Month","action":null,"target":null,"subtab":null,"exportKind":null,"fullscreenKind":null,"modeAction":null,"revisionSort":null,"scatterAction":null,"drilldownCategory":nul

- [x] G4: every impacted interconnected Product filter state is captured and reviewed at 1280x720 and 1920x1080 under Improved, Regressed, and Out of place
  EVIDENCE: 12 exact-size screenshots and categorical findings are recorded in validation-artifacts/interconnected-product-filters/validation-report.md; Regressed: None observed; Out of place: None observed.
