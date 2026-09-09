# Gates: Overview vintage provenance

OWNS: dashboard/app.js, dashboard/index.html, scripts/validate_vintage_selector.mjs, scripts/validate_overview_vintage_provenance.mjs, tests/test_overview_vintage_provenance.mjs, validation-artifacts/overview-vintage-provenance/**

Scope: Preserve existing work, align Overview bias with primary common-cohort vintage, and show every selected forecast with consistent colors.

- [ ] G1: Bias and forecast-line regression tests pass, including unchanged Trends behavior.
  CHECK: node --test tests/test_overview_vintage_provenance.mjs
  EXPECT: # fail 0
  EVIDENCE: pending
- [ ] G2: Before and after screenshots cover five selections, page/popover/two fullscreens at both desktop sizes; changed guides also captured. Browser data and geometry assertions pass.
  CHECK: node scripts/validate_overview_vintage_provenance.mjs after
  EXPECT: OVERVIEW PROVENANCE VALIDATION PASSED
  EVIDENCE: pending
- [ ] G3: Each screenshot inspected; Improved, Regressed and Out of place recorded, with regressions resolved.
  EVIDENCE: pending
- [ ] G4: Proactive LSP, relevant Python tests and session diagnostics reviewed; dashboard restarted and shared preview route verified.
  EVIDENCE: pending
