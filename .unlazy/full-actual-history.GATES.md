# Gates: Full actual-sales history for SKU History

OWNS: forecast_analysis/actuals.py, forecast_analysis/analysis_frame.py, tests/test_forecast_analysis_population.py, docs/forecast-analysis-dashboard-spec.md, .unlazy/full-actual-history.GATES.md, validation-artifacts/full-actual-history/**

Scope: Load all actual-sales months for SKU History, clip negative actual volumes to zero, and preserve forecast-target scoping for dashboard accuracy calculations.

- [x] G1: Actual normalization clips negative row values to zero before aggregation while still rejecting non-finite values.
  CHECK: .venv/bin/python -m unittest tests.test_forecast_analysis_population.ActualNormalizationTests && echo FULL_ACTUAL_HISTORY_NORMALIZATION_OK
  EXPECT: FULL_ACTUAL_HISTORY_NORMALIZATION_OK
  CWD: ..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=4fe78384d2b3/18 entries; output=Ran 6 tests in 0.031s | OK

- [x] G2: Canonical input loading retains the full 66-month actual-sales history from 2021 through 2026 while dashboard-comparable actuals remain forecast-target scoped.
  CHECK: .venv/bin/python -m unittest tests.test_forecast_analysis_population.CurrentConsolidatedArtifactTests && echo FULL_ACTUAL_HISTORY_PIPELINE_OK
  EXPECT: FULL_ACTUAL_HISTORY_PIPELINE_OK
  CWD: ..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=4fe78384d2b3/18 entries; output=Ran 2 tests in 1.910s | OK

- [x] G3: Forecast-analysis, product-history, and year-overlay regression tests pass.
  CHECK: .venv/bin/python -m unittest tests.test_forecast_analysis_population tests.test_product_postmortem tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_product_detail_exposes_auditable_postmortem_projection tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_year_overlay_is_target_independent_and_source_specific && echo FULL_ACTUAL_HISTORY_REGRESSION_OK
  EXPECT: FULL_ACTUAL_HISTORY_REGRESSION_OK
  CWD: ..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=4fe78384d2b3/18 entries; output=Ran 29 tests in 7.062s | OK

- [x] G4: Product-history payload exposes full retained actual history without expanding KPI actual population beyond forecast target months.
  CHECK: .venv/bin/python -c "from pathlib import Path; from dashboard.adapter import DashboardDataService; from forecast_analysis import load_analysis_inputs; paths=(Path('artifacts/forecast_history/consolidated/forecast_history_waterfall.csv'),Path('artifacts/ph/PH_FG.xlsx'),Path('artifacts/secondary_sales')); x=load_analysis_inputs(*paths); h=x.actual_history; assert h is not None; months=h.get_column('snop_month').unique().sort(); comparable=x.actuals.get_column('snop_month').unique().sort(); assert str(months.min())=='2021-04-01' and str(months.max())=='2026-09-01' and len(months)==66; assert str(comparable.min())=='2025-05-01' and str(comparable.max())=='2026-09-01' and len(comparable)==17; assert h.get_column('actual_kl').min() >= 0; s=DashboardDataService.from_paths(*paths); r=s.default_request(); r['product_parent_code']=706059; p=s.product_detail(r); rows=p['year_overlay']['points']['rows']; assert rows[0]['snop_month']=='2021-04-01'; print('FULL_ACTUAL_HISTORY_RUNTIME_OK')"
  EXPECT: FULL_ACTUAL_HISTORY_RUNTIME_OK
  CWD: ..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=4fe78384d2b3/18 entries; output=Could not determine dtype for column 136, falling back to string | Could not determine dtype for column 137, falling back to string

- [x] G5: History tab is browser-validated at 1280x720 and 1920x1080 with complete artifacts, assertions, and Improved/Regressed/Out of place classifications.
  EVIDENCE: Luna/max verified all 8 required PNG cells under validation-artifacts/full-actual-history/; api-assertions.json all_passed=true; history begins 2021-04-01, no negative actual_kl, September 2026 actual excluded, FY2022-FY2027 rendered; Improved=None observed (no before baseline), Regressed=None observed, Out of place=None observed. Detailed evidence: validation-artifacts/full-actual-history/validation-report.md. Known caveat: four 1280 cells lack dedicated per-cell state JSON and exact 720px runtime geometry was not independently asserted.
