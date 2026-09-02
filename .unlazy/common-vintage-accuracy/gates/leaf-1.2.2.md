# Gates: live common-cohort and visual proof

OWNS: scripts/validate_vintage_selector.mjs, validation-artifacts/vintage-selector/**

Scope: fresh-server Chromium proves request-driven multi-selection, common-cohort evidence, latest-only behavior, and responsive presentation

- [x] G1: Chromium intercepts selection requests and verifies identical cohort evidence across plotted lines
  CHECK: node scripts/validate_vintage_selector.mjs --output validation-artifacts/vintage-selector
  EXPECT: VINTAGE SELECTOR VALIDATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=VINTAGE SELECTOR VALIDATION PASSED

- [x] G2: desktop, multi-series, compact, wide, latest-only full-screen, and open full-screen selector screenshots have no visual regression
  EVIDENCE: Manually reviewed the six final PNGs after the last Chromium run. The selector remains left of Full screen, all controls/popovers stay inside their frame and viewport, no text or chart is clipped, latest is clearly marked fixed, the multi-series palette remains distinguishable, and desktop/wide/800×700/full-screen layouts retain clean alignment and spacing.
