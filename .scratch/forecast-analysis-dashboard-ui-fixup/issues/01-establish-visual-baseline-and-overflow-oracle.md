# 01 — Establish the visual baseline and overflow oracle

**What to build:** Make the current dashboard geometry reproducible and measurable so every later UI change can be judged against the same analytical state, full-page capture method, and objective overflow rules.

**Blocked by:** None — can start immediately.

**Status:** closed

- [x] The existing expanded full-page screenshot remains preserved as the immutable before-state, with its dimensions and capture date recorded.
- [x] A repeatable browser workflow records viewport, document, and Marimo application client/scroll dimensions for a named dashboard state.
- [x] The workflow captures the dashboard's default analytical state deterministically, including source, target range, product, horizon, vintage, performance, and quality selections.
- [x] The Marimo full-page normalization step produces a genuine full-content screenshot rather than a viewport-only image.
- [x] Overflow evaluation uses a two-pixel tolerance and can report document and application overflow independently without requiring the current broken UI to pass.
- [x] Baseline measurements explicitly record the current horizontal-overflow failure and the dimensions of the captured screenshot.
- [x] Automated tests cover the measurement and pass/fail evaluation logic without adding a permanently failing release test.
- [x] Existing analytical validation and dashboard behavior remain unchanged.
