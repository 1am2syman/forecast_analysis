# 04 — Measure revision effectiveness

**What to build:** Let users compare two vintages within the selected source and determine whether forecast revisions moved up or down and improved, worsened, or did not materially change forecast error.

**Blocked by:** 02 — Deliver the single-source performance dashboard.

**Status:** closed

- [x] Vintage A and Vintage B support oldest available, latest available, exact calculation month, and exact horizon rules.
- [x] Vintage pairs are constructed within one source and retain complete, missing-A, missing-B, missing-both, missing-actual, and zero-actual statuses.
- [x] Revision amount, revision percentage, error improvement, accuracy delta, and revision effectiveness match hand-calculated fixtures.
- [x] Revision direction and outcome use a documented configurable tolerance.
- [x] KPI cards show accuracy delta, revision effectiveness, and total error improvement when a valid pair comparison is active.
- [x] Users can filter by revision direction and revision outcome.
- [x] A revision diagnostic view shows improved, worsened, neutral, and unchanged populations and relates revision amount to error improvement.
- [x] A sortable exception table exposes the selected vintages, actuals, errors, revision values, outcomes, and pair status.
- [x] Incomplete pairs remain visible in coverage counts but do not enter revision-effectiveness denominators.
