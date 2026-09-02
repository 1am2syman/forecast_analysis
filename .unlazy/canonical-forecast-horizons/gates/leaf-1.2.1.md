# Gates: exact analytical vintage rules

OWNS: forecast_analysis/vintage_accuracy.py, dashboard/adapter.py, tests/test_common_vintage_accuracy.py, tests/test_static_dashboard_adapter.py

Scope: accuracy comparisons resolve Oldest as exact M5 and Latest as exact M1 while retaining common-cohort eligibility

- [ ] G1: adversarial common-cohort tests prove exact endpoint selection and no fallback
  CHECK: uv run python -m unittest tests.test_common_vintage_accuracy tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintage_request_defaults_and_validation tests.test_static_dashboard_adapter.StaticDashboardAdapterTests.test_accuracy_vintages_use_common_cohort_without_changing_global_metrics
  EXPECT: OK
  EVIDENCE: pending

- [ ] G2: independent canonical horizon oracle proves Oldest/Latest identity
  CHECK: uv run python scripts/verify_canonical_horizons.py --stage accuracy
  EXPECT: ACCURACY HORIZONS VERIFIED
  EVIDENCE: pending
