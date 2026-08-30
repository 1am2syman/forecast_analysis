# Plan: Exhaustive browser functionality and collapsible navigation

1. Inventory every interactive element and map it to expected state, API, accessibility, and layout effects.
2. Build a deterministic real-Chromium harness that fails on each broken control independently and records screenshots/report evidence.
3. Run the harness against the current UI to establish failures before changing behavior.
4. Implement a persistent, keyboard-accessible collapsed rail with graceful responsive behavior and full-width dashboard recovery.
5. Diagnose and repair every failure found by the exhaustive harness; add regression assertions at the browser seam.
6. Re-run exhaustive, existing browser, adapter, HTTP, syntax, diagnostics, and visual checks.
7. Publish the updated live app and validation gallery through the existing shared preview route.
