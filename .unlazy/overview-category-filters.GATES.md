# Gates: Overview category filters

OWNS: dashboard/filter-multiselect.js, dashboard/app.js, dashboard/styles.css, forecast_analysis/sku_classification.py, forecast_analysis/filters.py, tests/test_filter_multiselect.mjs, tests/test_forecast_analysis_dashboard.py, tests/test_static_dashboard_adapter.py, tests/test_forecast_analysis_dashboard_ui.py, validation-artifacts/overview-category-filters/**

Scope: Hide Unclassified from user-facing SKU-class options, keep SKU-class option order static after selection, and narrow the Overview SKU-class popover without implementing Seasonal/NPD.

- [x] G1: User-facing backend option lists expose only A, B, and C
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard.DashboardPopulationTests.test_sku_class_filter_recomputes_forecast_and_actual_populations_together tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_bootstrap_exposes_real_canonical_contract tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests && echo __PI_FOCUSED_BACKEND_OK__
  EXPECT: __PI_FOCUSED_BACKEND_OK__
  EVIDENCE: monitor_3; the broader legacy module run remains blocked by one unrelated pre-existing empty-state assertion.

- [x] G2: Static ordering helper and dashboard JavaScript pass syntax/regression checks
  CHECK: node --check dashboard/app.js && node --check dashboard/filter-multiselect.js && node tests/test_filter_multiselect.mjs && echo __PI_JS_OK__
  EXPECT: __PI_JS_OK__
  EVIDENCE: monitor_4.

- [x] G3: Desktop browser validation captures every impacted Overview state at both supported viewports
  EVIDENCE: validation-artifacts/overview-category-filters/visual-test-report.md; 12 PNG screenshots at 1280x720 and 1920x1080, native agent_browser QA by cliproxyapi/gpt-5.6-luna.

- [x] G4: Changed files have no whitespace errors
  CHECK: git diff --check -- dashboard/filter-multiselect.js dashboard/app.js dashboard/styles.css forecast_analysis/sku_classification.py forecast_analysis/filters.py tests/test_filter_multiselect.mjs tests/test_forecast_analysis_dashboard.py tests/test_static_dashboard_adapter.py tests/test_forecast_analysis_dashboard_ui.py && echo __PI_DIFF_OK__
  EXPECT: __PI_DIFF_OK__
  EVIDENCE: monitor_5.
