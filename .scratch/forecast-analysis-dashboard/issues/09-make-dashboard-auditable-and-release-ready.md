# 09 — Make the complete dashboard auditable and release-ready

**What to build:** Finish the dashboard as one coherent analytical product whose views, downloads, formulas, empty states, and comparison populations can be independently verified and safely released.

**Blocked by:** 04 — Measure revision effectiveness; 05 — Drill into brand and target-month performance; 06 — Compare TM and ML as separate chart series; 07 — Inspect product vintage history and stability; 08 — Investigate data-quality exclusions.

**Status:** closed

- [x] One shared filter state drives KPI cards, charts, heatmaps, detail views, exception tables, quality counts, and downloads.
- [x] A visible population summary states mode, source or sources, target range, horizons, products, actual volume, eligible observations, comparable pairs, and coverage.
- [x] Filtered downloads contain exactly the rows represented by the active source mode, filters, and vintage rules.
- [x] Every KPI and chart exposes its unit, eligible observation count, and enough numerator or denominator context to audit the result.
- [x] Empty selections, zero denominators, missing common horizons, and incomplete comparisons render explanatory states without tracebacks.
- [x] Source and vintage colors, labels, legends, and signed zero references are consistent across all views.
- [x] Hand-calculated fixtures cover core metrics, revision metrics, source comparisons, stability, and coverage.
- [x] End-to-end tests cover standard TM mode, standard ML mode, comparison mode, filtering, quality inspection, and download fidelity.
- [x] Python diagnostics and the dashboard validation command pass.
- [x] The implemented behavior satisfies every acceptance criterion in the approved dashboard specification.
