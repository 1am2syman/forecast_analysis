# Gates: vintage accuracy data contract

OWNS: dashboard/adapter.py, tests/test_static_dashboard_adapter.py

Scope: expose auditable latest and historical monthly accuracy series without changing the shared KPI request contract

- [x] G1: adapter tests prove latest is fixed, oldest is the default option, and intermediate vintages have monthly accuracy rows
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintages_expose_fixed_latest_and_historical_options
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 1 test in 3.657s | OK

- [x] G2: the complete static adapter suite remains green
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 21 tests in 8.977s | OK
