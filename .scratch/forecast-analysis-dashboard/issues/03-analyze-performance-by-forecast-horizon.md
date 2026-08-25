# 03 — Analyze performance by forecast horizon

**What to build:** Let users filter and evaluate the selected source at consistent planning horizons, showing how accuracy, bias, error, volume, and coverage change as the target month approaches.

**Blocked by:** 02 — Deliver the single-source performance dashboard.

**Status:** closed

- [x] Horizon controls are populated from horizons actually available for the selected source.
- [x] Users can select an exact horizon without silently substituting another vintage.
- [x] Missing product-target observations at the selected horizon remain represented in coverage diagnostics.
- [x] A horizon chart shows source-specific forecast accuracy or bias with actual volume and observation counts in tooltips.
- [x] The horizon view clearly orders and labels long-range through near-term forecasts.
- [x] Horizon filtering updates KPI cards, monthly charts, population summaries, tables, and downloads consistently.
- [x] Year-boundary horizon calculations and incomplete horizon histories are covered by tests.
