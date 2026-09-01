# Gates: rolling SKU class filter

OWNS: forecast_analysis/sku_classification.py, forecast_analysis/actuals.py, forecast_analysis/analysis_frame.py, forecast_analysis/contracts.py, forecast_analysis/filters.py, forecast_analysis/vintages.py, forecast_analysis/dashboard.py, forecast_analysis/comparison.py, forecast_analysis/__init__.py, dashboard/adapter.py, dashboard/app.js, dashboard/index.html, docs/forecast-analysis-dashboard-spec.md, tests/test_sku_classification.py, tests/test_forecast_analysis_population.py, tests/test_forecast_analysis_dashboard.py, tests/test_static_dashboard_adapter.py, tests/test_static_dashboard_server.py, tests/test_forecast_analysis_dashboard_ui.py

Scope: Add a national parent-level monthly SKU Class filter using the preceding six completed months of actuals and 70/20/10 cumulative contribution bands.

- [x] G1: SKU classification uses six completed months, deterministic threshold crossing, 70/20/10 bands, carry-forward, and unclassified handling
  CHECK: cd ../.. && uv run python -m unittest tests.test_sku_classification && echo SKU_CLASS_UNIT_PASSED
  EXPECT: SKU_CLASS_UNIT_PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis/.unlazy/sku-class; path=cda89a5385a8/24 entries; output=Ran 6 tests in 0.039s | OK

- [x] G2: The canonical analysis dataset and shared forecast/actual filters apply SKU Class consistently
  CHECK: cd ../.. && uv run python -m unittest tests.test_forecast_analysis_population tests.test_forecast_analysis_dashboard && echo SKU_CLASS_PIPELINE_PASSED
  EXPECT: SKU_CLASS_PIPELINE_PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis/.unlazy/sku-class; path=cda89a5385a8/24 entries; output=Ran 62 tests in 14.861s | OK

- [x] G3: Browser request, options, cache-normalized view, and filter UI expose SKU Class end-to-end
  CHECK: cd ../.. && uv run python -m unittest tests.test_static_dashboard_adapter tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests && node --check dashboard/app.js && echo SKU_CLASS_UI_API_PASSED
  EXPECT: SKU_CLASS_UI_API_PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis/.unlazy/sku-class; path=cda89a5385a8/24 entries; output=Ran 26 tests in 6.363s | OK

- [x] G4: Relevant dashboard, history ETL, quality, release, and server regression suites have no regressions
  CHECK: cd ../.. && uv run python -m unittest tests.test_sku_classification tests.test_forecast_analysis_population tests.test_forecast_analysis_dashboard tests.test_forecast_analysis_quality tests.test_forecast_analysis_release tests.test_forecast_history_etl tests.test_static_dashboard_adapter tests.test_static_dashboard_server && echo SKU_CLASS_REGRESSION_SUITE_PASSED
  EXPECT: SKU_CLASS_REGRESSION_SUITE_PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis/.unlazy/sku-class; path=cda89a5385a8/24 entries; output=Ran 139 tests in 29.473s | OK

- [x] G5: Edited Python and JavaScript files have no blocking language diagnostics
  EVIDENCE: lsp_diagnostics primary scan checked 13 edited Python/JavaScript files with 0 diagnostics; lens_diagnostics mode=all reported no issues across the cached edited-file set.

Note: `python -m unittest discover -s tests` was attempted separately but terminated after more than six minutes while the pre-existing UI artifact screenshot recomputation test was still running. G4 therefore uses the explicit relevant regression suites as the bounded completion oracle.
