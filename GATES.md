# Gates: Overview explainer overlays

OWNS: dashboard/app.js, dashboard/index.html, dashboard/styles.css, tests/test_forecast_analysis_dashboard_ui.py, validation-artifacts/overview-explainers/**

Scope: Replace Overview KPI help popovers and add chart question controls with eight intuitive, no-scroll, full-canvas explainers matching or exceeding the Comparison overlays.

- [x] G1: All six Overview KPI cards and both Overview charts expose dialog question-mark triggers, including both chart fullscreen states
  CHECK: python -m unittest tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests
  EXPECT: OK
  EVIDENCE: met — DashboardUiSourceContractTests OK; test_overview_kpis_and_charts_use_full_canvas_explainers covers all 8 guide keys, dialog id, open/close actions, fullscreen title wiring

- [x] G2: JavaScript syntax and dashboard UI regression tests pass
  CHECK: node --check dashboard/app.js && python -m unittest tests.test_forecast_analysis_dashboard_ui.DashboardUiOverflowTests
  EXPECT: OK
  EVIDENCE: met — node --check clean; 30 tests OK

- [x] G3: Browser assertions confirm every Overview explainer opens, fits within 90% of the viewport, has no internal/document scroll, closes with Escape, and restores focus at 1280x720 and 1920x1080
  EVIDENCE: met — eval assertions: panel 1152x648 = 90% of 1280x720; panel/body/section/doc scrollHeight==clientHeight all true; Escape closes dialog, restores focus to trigger, body scroll-lock class removed; fullscreen variants verified at both viewports

- [x] G4: A complete two-viewport screenshot matrix exists for the Overview trigger state, six KPI overlays, two chart overlays, and both chart fullscreen overlay variants
  EVIDENCE: met — 22 PNGs in validation-artifacts/overview-explainers/ (11 states x 2 viewports), all verified at exact 1280x720 / 1920x1080 dimensions, recaptured after the validator-driven fix pass

- [x] G5: Independent SOL-medium subagent assessments find every explainer naturally understandable for planners, visually intuitive, and at least equal in quality to the Comparison overlays, with no unresolved regression or out-of-place finding
  EVIDENCE: met — four max-effort glm-5.3-flash validators: all 8 overlays PASS WITH NOTES (fullscreen variants PASS), planner-understandability 8/10 across the board, no FAIL verdicts; every ranked defect from the first review round was fixed and the full matrix recaptured (bar-truth errors, missing band tints, clipped/strikethrough SVG labels, label wraps, jargon, cross-tab pointer, dot legend, whisker caps, SVG text size)

- [x] G6: Edited files have no blocking diagnostics or whitespace errors
  CHECK: git diff --check -- dashboard/app.js dashboard/index.html dashboard/styles.css tests/test_forecast_analysis_dashboard_ui.py && echo diff-check-passed
  EXPECT: diff-check-passed
  EVIDENCE: met — diff-check-passed; pi-lens delta: no issues
