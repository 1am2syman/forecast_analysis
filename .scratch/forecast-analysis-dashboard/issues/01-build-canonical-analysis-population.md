# 01 — Build a trustworthy canonical analysis population

**What to build:** Create the end-to-end data foundation that loads consolidated forecast history, cleans the product hierarchy, aggregates secondary-sales actuals, and produces one validated source-aware analysis population with visible quality diagnostics.

**Blocked by:** None — can start immediately.

**Status:** closed

- [x] Consolidated history is normalized to typed calculation month, target month, parent product, forecast quantity, description, and source fields.
- [x] Forecast identity includes source, so overlapping TM and ML records remain separate while duplicates within a source fail clearly.
- [x] Forecast horizon is derived as the whole-month distance between calculation month and target month.
- [x] Product-hierarchy duplicates with agreeing brand mappings collapse to one parent-product mapping.
- [x] Missing and conflicting hierarchy mappings remain visible through explicit statuses and diagnostics.
- [x] Secondary-sales rows are normalized and aggregated to one actual value per parent product and target month.
- [x] The canonical analysis population preserves forecasts with missing or zero actuals and assigns explicit actual statuses.
- [x] Population diagnostics report row counts, products, sources, hierarchy status, actual status, and source coverage.
- [x] Pure transformation tests cover successful normalization and every blocking or non-blocking data-quality rule.
