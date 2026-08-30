# Gates: Static dashboard exhaustive browser functionality

OWNS: dashboard/**, scripts/validate_dashboard_functionality.mjs, scripts/validate_real_dashboard_ui.mjs, validation-artifacts/static-dashboard-browser-exhaustive/**, .unlazy/static-dashboard-browser-exhaustive/**

Scope: Exercise every interactive dashboard control in a real Chromium session, repair every reproducible failure, add a graceful collapsible navigation rail, and publish verified evidence.

- [x] G1: The exhaustive Chromium harness inventories and exercises every enabled button, tab, select, checkbox, date/number/search input, mode toggle, reset, export, keyboard navigation action, history action, and rail-collapse action without console, page, network, API, overflow, or state-contract failures.
  CHECK: node scripts/validate_dashboard_functionality.mjs --output validation-artifacts/static-dashboard-browser-exhaustive
  EXPECT: EXHAUSTIVE DASHBOARD FUNCTIONALITY VALIDATION PASSED
  EVIDENCE: Exit 0 on 2026-08-27; 43/43 checks passed, 27/27 shared controls exercised, five CSV export classes downloaded, four visual states captured, and zero console/page/network/HTTP failures recorded in validation-report.json.

- [x] G2: The existing real-data browser regression matrix still passes after all fixes.
  CHECK: node scripts/validate_real_dashboard_ui.mjs --output validation-artifacts/static-dashboard-real-data
  EXPECT: REAL DASHBOARD UI VALIDATION PASSED
  EVIDENCE: Exit 0 on 2026-08-27; all five tabs passed at 1440×900, 1440×720, and 800×700.

- [x] G3: Adapter and HTTP integration tests remain green.
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter && uv run python scripts/verify_static_dashboard_server.py
  EXPECT: STATIC DASHBOARD SERVER VERIFICATION PASSED
  EVIDENCE: Exit 0 on 2026-08-27; six adapter tests passed and the live HTTP verification emitted the expected success marker.

- [x] G4: JavaScript/Python syntax and edited-file diagnostics report no blocking errors.
  CHECK: uv run python -m compileall -q dashboard tests/test_static_dashboard_adapter.py scripts/verify_static_dashboard_server.py && node --check dashboard/app.js && node --check scripts/validate_dashboard_functionality.mjs && node --check scripts/validate_real_dashboard_ui.mjs && printf 'DASHBOARD DIAGNOSTIC CHECKS PASSED\n'
  EXPECT: DASHBOARD DIAGNOSTIC CHECKS PASSED
  EVIDENCE: Exit 0 on 2026-08-27; syntax marker printed, targeted source-file LSP scan found zero errors, and lens_diagnostics mode=all found no error issues.

- [x] G5: The collapsed rail is visually reviewed at desktop and narrow widths: labels hide, the restore control remains discoverable, content consumes released width, focus is visible, and fixed-viewport/no-document-scroll behavior remains intact.
  EVIDENCE: Reviewed desktop-expanded.png, desktop-collapsed.png, narrow-expanded.png, narrow-collapsed.png, and the live proxied screenshots. Desktop workspace expands from 1,208 px to 1,368 px while the rail contracts from 232 px to 72 px; the narrow layout remains fixed-viewport with no document scroll.

- [x] G6: The final live preview and validation gallery are republished and verified through the shared preview helper without creating a new Funnel.
  EVIDENCE: Published <https://sazzadvps.taildd3bd9.ts.net/forecast-dashboard-browser-exhaustive/> and refreshed <https://sazzadvps.taildd3bd9.ts.net/forecast-dashboard-real-data-validation/>; live app QA passed at <https://sazzadvps.taildd3bd9.ts.net/forecast-dashboard-real-data/> and tailscale serve status retained the existing shared Funnel/root configuration.
