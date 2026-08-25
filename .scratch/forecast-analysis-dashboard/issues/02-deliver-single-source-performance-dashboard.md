# 02 — Deliver the single-source performance dashboard

**What to build:** Deliver a usable dashboard where the user selects either TM or ML as a source filter and every KPI, chart, filter result, population count, and table is recalculated exclusively from that source.

**Blocked by:** 01 — Build a trustworthy canonical analysis population.

**Status:** closed

- [x] The source filter offers TM and ML and defaults to TM.
- [x] Only one source contributes to metrics in standard mode; forecast quantities from different sources are never summed together.
- [x] The default comparison selects the oldest and latest available vintages independently for each parent product and target month within the selected source.
- [x] KPI cards show forecast accuracy, bias, absolute error, actual volume, forecast volume, coverage, and eligible observation count.
- [x] Forecast accuracy and bias use aggregate numerators and denominators rather than averaged subgroup percentages.
- [x] Target-month, brand, parent-product, and minimum-actual-volume filters update the entire dashboard from one shared population.
- [x] A monthly performance chart supports accuracy, bias, absolute error, and forecast-versus-actual volume views.
- [x] Negative forecast accuracy, zero denominators, empty selections, and missing vintage pairs render defined states rather than failing.
- [x] Tests demonstrate that switching the source filter recalculates all outputs and cannot leak rows from the other source.
