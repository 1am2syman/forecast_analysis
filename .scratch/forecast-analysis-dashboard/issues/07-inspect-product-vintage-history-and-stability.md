# 07 — Inspect product vintage history and stability

**What to build:** Give users a product-level view of chronological forecast development, actual outcomes, revisions, and stability, with TM and ML shown as separate series when comparison mode is active.

**Blocked by:** 04 — Measure revision effectiveness; 06 — Compare TM and ML as separate chart series.

**Status:** closed

- [x] Users can search for and select a parent product by code or description and choose a target month.
- [x] The detail chart shows chronological forecast vintages and an actual-volume reference for the selected product-target month.
- [x] Standard mode displays the filtered source; comparison mode displays TM and ML as separate legend series.
- [x] Every point exposes calculation month, horizon, forecast quantity, actual quantity, and error.
- [x] A revision table shows consecutive source-specific changes and their direction.
- [x] Forecast range, population standard deviation, revision count, and maximum absolute revision are calculated independently by source.
- [x] Products with fewer than two vintages show an explicit insufficient-history state.
- [x] Stability and consecutive-revision calculations are tested with ordered, unordered, and incomplete vintage histories.
