# Gates: backend drill-down contract

OWNS: dashboard/adapter.py, tests/test_static_dashboard_adapter.py

Scope: expose ranked outcome drill-down rows and canonical multi-parent module recomputation

- [x] G1: adapter tests prove four category payloads are top-20, correctly classified, and sorted by descending impact
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_revision_drilldown_ranks_top_parent_codes_by_category_impact && echo 'BACKEND DRILLDOWN RANKING PASSED'
  EXPECT: BACKEND DRILLDOWN RANKING PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 1 test in 2.567s | OK

- [x] G2: adapter tests prove a multi-parent exceptions request recomputes metrics, history, scatter, diagnostics, and actions only for selected parents
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_revision_drilldown_parent_selection_recomputes_exception_module && echo 'BACKEND DRILLDOWN SELECTION PASSED'
  EXPECT: BACKEND DRILLDOWN SELECTION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 1 test in 2.838s | OK

- [x] G3: adapter module contract and Python syntax remain valid
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter && uv run python -m py_compile dashboard/adapter.py tests/test_static_dashboard_adapter.py && echo 'BACKEND DRILLDOWN REGRESSION PASSED'
  EXPECT: BACKEND DRILLDOWN REGRESSION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 19 tests in 7.724s | OK
