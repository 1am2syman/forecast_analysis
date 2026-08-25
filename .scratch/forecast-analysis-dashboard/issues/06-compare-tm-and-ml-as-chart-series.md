# 06 — Compare TM and ML as separate chart series

**What to build:** Add an explicit comparison feature that calculates TM and ML independently over a like-for-like population and displays the two sources as legend series in compatible metrics and charts.

**Blocked by:** 02 — Deliver the single-source performance dashboard; 03 — Analyze performance by forecast horizon.

**Status:** closed

- [x] Standard source-filter behavior remains unchanged when comparison mode is off.
- [x] Comparison mode activates TM and ML together as separate metric groups and chart legend series.
- [x] Source metrics are calculated independently; TM and ML forecast quantities are never combined into one forecast.
- [x] The default comparison uses a common exact horizon available to both sources, preferring one month ahead when available.
- [x] The dashboard prevents or prominently warns about comparisons using mismatched horizons or vintage rules.
- [x] Comparison KPIs show TM, ML, and clearly labeled deltas for accuracy, bias, absolute error, and coverage.
- [x] Monthly and horizon charts display TM and ML with stable, distinct legend colors.
- [x] Common-population, TM-only, and ML-only counts and actual volumes remain visible.
- [x] A paired comparison classifies each common product-target observation as TM better, ML better, or tied by absolute error.
- [x] Tests prove that comparison results use aligned populations and remain invariant to source row ordering.
