# Gates: canonical horizon end-to-end proof

OWNS: scripts/verify_canonical_horizons.py, scripts/validate_vintage_selector.mjs, validation-artifacts/vintage-selector/**

Scope: live dashboard behavior and responsive screenshots expose the deterministic M5/M1 model

- [ ] G1: feature-scoped Python and UI contract suites pass
  CHECK: uv run python -m unittest tests.test_common_vintage_accuracy tests.test_static_dashboard_adapter tests.test_forecast_analysis_dashboard_ui
  EXPECT: OK
  EVIDENCE: pending

- [ ] G2: live browser validator passes and refreshes reviewed artifacts
  CHECK: node scripts/validate_vintage_selector.mjs --output validation-artifacts/vintage-selector
  EXPECT: VINTAGE SELECTOR VALIDATION PASSED
  EVIDENCE: pending

- [ ] G3: screenshots at desktop, wide, and compact viewports are manually reviewed for labels, alignment, overflow, and chart clipping
  EVIDENCE: pending
