# 05 — Drill into brand and target-month performance

**What to build:** Enable users to move from total source performance into cleaned brand and target-month performance, while preserving hierarchy-quality groups and volume context.

**Blocked by:** 02 — Deliver the single-source performance dashboard.

**Status:** closed

- [x] The brand filter uses the cleaned hierarchy and includes explicit Unmapped and Hierarchy conflict groups when present.
- [x] A brand-by-target-month heatmap supports forecast accuracy, bias, absolute error, Vintage A accuracy, Vintage B accuracy, accuracy delta, and revision effectiveness where applicable.
- [x] Signed metrics use a diverging scale with a visible zero point; magnitude metrics use an appropriate sequential scale.
- [x] Brand rows can be sorted by the selected performance metric, with an All brands summary available.
- [x] Heatmap tooltips include source, brand, target month, metric value, actual volume, and eligible observation count.
- [x] Brand and target-month interactions update KPI cards, charts, exception rows, coverage counts, and downloads from the same population.
- [x] Tests verify that cleaned hierarchy duplicates do not multiply forecast or actual volume during brand aggregation.
