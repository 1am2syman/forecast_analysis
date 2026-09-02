# Gates: integrated deterministic forecast accuracy

OWNS: forecast_analysis/vintage_accuracy.py, dashboard/adapter.py, tests/test_common_vintage_accuracy.py, tests/test_static_dashboard_adapter.py, scripts/verify_canonical_horizons.py, scripts/validate_vintage_selector.mjs, validation-artifacts/vintage-selector/**

Scope: exact M5/M1 selection, common eligibility, adapter payloads, and browser rendering compose correctly

- [ ] G1: analytical and adapter regression tests pass together
  CHECK: uv run python -m unittest tests.test_common_vintage_accuracy tests.test_static_dashboard_adapter
  EXPECT: OK
  EVIDENCE: pending

- [ ] G2: independent data and browser oracles both pass
  CHECK: uv run python scripts/verify_canonical_horizons.py --stage accuracy && node scripts/validate_vintage_selector.mjs --output validation-artifacts/vintage-selector
  EXPECT: VINTAGE SELECTOR VALIDATION PASSED
  EVIDENCE: pending
