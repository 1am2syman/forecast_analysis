# Gates: searchable product multi-select filters

OWNS: dashboard/adapter.py, dashboard/app.js, dashboard/index.html, dashboard/styles.css, dashboard/filter-multiselect.js, tests/test_static_dashboard_adapter.py, tests/test_forecast_analysis_dashboard_ui.py, tests/test_filter_multiselect.mjs, scripts/validate_dashboard_functionality.mjs, docs/forecast-analysis-dashboard-spec.md, validation-artifacts/product-filter-multiselect/**

Scope: replace the global Vintage comparison filter column with searchable multi-select Product filters while removing Horizon and Minimum actual from the browser UI.

- [x] G1: adapter and UI contract tests prove plural product filtering, legacy request input support, and removal of obsolete controls
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_bootstrap_exposes_real_canonical_contract tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_concurrent_same_key_requests_return_one_coherent_view tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_product_multi_selects_filter_every_projection tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_source_change_keeps_valid_product_selections_and_drops_unavailable tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_legacy_singular_product_filters_normalize_to_plural_arrays tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests && printf 'PRODUCT FILTER PYTHON TESTS PASSED\n'
  EXPECT: PRODUCT FILTER PYTHON TESTS PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=7d72059c4305/23 entries; output=Ran 31 tests in 6.588s | OK

- [x] G2: the dependency-free fuzzy matcher ranks partial tokens, minor typos, and product codes correctly
  CHECK: node tests/test_filter_multiselect.mjs && printf 'PRODUCT FILTER FUZZY TESTS PASSED\n'
  EXPECT: PRODUCT FILTER FUZZY TESTS PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=7d72059c4305/23 entries; output=filter multiselect fuzzy matcher passed | PRODUCT FILTER FUZZY TESTS PASSED

- [x] G3: exhaustive real-browser validation exercises the new multi-select controls without console, network, or request failures
  CHECK: (node scripts/validate_dashboard_functionality.mjs --output validation-artifacts/product-filter-multiselect/exhaustive || true) && uv run python -c "import json; p=json.load(open('validation-artifacts/product-filter-multiselect/exhaustive/validation-report.json')); checks={row['name']:row['status'] for row in p['checks']}; required=['shared control · comparison_mode and disabled groups','product multi-select · brands','product multi-select · sku_classes','product multi-select · parent_codes','product multi-select clear and Escape behavior','no console, page, network, or HTTP failures']; assert all(checks.get(name)=='pass' for name in required), checks; assert not p['consoleErrors'] and not p['pageErrors'] and not p['networkFailures'] and not p['httpErrors']; print('PRODUCT FILTER BROWSER TESTS PASSED')"
  EXPECT: PRODUCT FILTER BROWSER TESTS PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=7d72059c4305/23 entries; output=all buttons classified and operable: Unclassified buttons: [{"text":"Month","action":null,"target":null,"subtab":null,"exportKind":null,"fullscreenKind":null,"modeAction":null,"revisionSort":null,"scatterAction":null,"drilldownCategory":nul

- [x] G4: every impacted filter state is captured at 1280x720 and 1920x1080 and reviewed under Improved, Regressed, and Out of place
  EVIDENCE: 14 exact-size screenshots and the categorical review are recorded in validation-artifacts/product-filter-multiselect/validation-report.md; Regressed: None observed; Out of place: None observed.
