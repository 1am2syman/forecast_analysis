# Gates: SKU post-mortem cockpit

OWNS: dashboard/**, forecast_analysis/**, tests/**, scripts/validate_sku_postmortem.mjs, validation-artifacts/sku-postmortem/**, .unlazy/sku-postmortem/**

Scope: Replace Product History with a planner-ready SKU post-mortem that preserves the forecast-dashboard visual language and derives auditable commentary, revision outcomes, peer context, and forward treatment from canonical data.

- [x] G1: Product-detail data exposes rolling SKU performance, monthly revision outcomes, brand and SKU-class peer benchmarks, categorized evidence commentary, and a deterministic forward-treatment recommendation.
  CHECK: .venv/bin/python -m unittest tests.test_product_postmortem tests.test_static_dashboard_adapter && printf 'sku postmortem backend verification passed\n'
  EXPECT: sku postmortem backend verification passed
  EVIDENCE: 28 tests passed on 2026-09-01; commentary includes evidence refs and treatment remains within the controlled action vocabulary.

- [x] G2: The Product History UI renders the decision summary, forecast/actual history, dashboard-style performance ledger, revision outcome sparkline, peer comparison, categorized commentary, issue callouts, and forward treatment without generic prototype styling.
  CHECK: .venv/bin/python -m unittest tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests.test_product_history_is_a_dashboard_native_sku_postmortem && printf 'sku postmortem UI contract verification passed\n'
  EXPECT: sku postmortem UI contract verification passed
  EVIDENCE: Source contract passed on 2026-09-01; markup and renderers use existing display/mono fonts, hairlines, frame hierarchy, severity lamps, and dashboard tokens.

- [x] G3: The real dashboard passes an end-to-end browser assertion at 1440x900 and 800x700, including no overflow, visible core sections, valid sparkline semantics, and dashboard typography/color tokens.
  CHECK: node scripts/validate_sku_postmortem.mjs
  EXPECT: sku postmortem browser validation passed
  EVIDENCE: Browser validation passed at 1440x900, 1680x1050 and 800x700; validation-artifacts/sku-postmortem/validation-report.json records zero horizontal overflow, zero overlap, six metrics, forecast/actual paths, revision zero baseline, commentary, three peer cohorts and forward treatment.

- [x] G4: Targeted Python regression suites pass without regression.
  CHECK: .venv/bin/python -m unittest tests.test_forecast_analysis_dashboard tests.test_static_dashboard_adapter tests.test_product_postmortem && printf 'sku postmortem regression verification passed\n'
  EXPECT: sku postmortem regression verification passed
  EVIDENCE: 75 domain, dashboard, adapter and post-mortem tests passed on 2026-09-01.

- [x] G5: Edited source files have no blocking diagnostics.
  CHECK: .venv/bin/python -m compileall -q dashboard forecast_analysis && node --check dashboard/app.js && node --check scripts/validate_sku_postmortem.mjs && node --check scripts/validate_dashboard_functionality.mjs && node --check scripts/validate_real_dashboard_ui.mjs && printf 'sku postmortem diagnostics passed\n'
  EXPECT: sku postmortem diagnostics passed
  EVIDENCE: Python compile, four Node syntax checks, targeted LSP diagnostics and git diff --check passed on 2026-09-01.

- [x] G6: Exact viewport screenshots are manually inspected for hierarchy, alignment, spacing, wrapping, clipping, dashboard visual inheritance, and compact usability.
  EVIDENCE: Inspected desktop-1440x900.png, desktop-1440x900-lower.png, wide-1680x1050.png, compact-800x700.png and compact-800x700-lower.png. No component overlap or horizontal clipping; decision and review-contract text wrap within bounded cells; frames, colors, typography and density inherit the dashboard. The compact viewport intentionally keeps paired panels side by side and scrolls vertically within the pane.
