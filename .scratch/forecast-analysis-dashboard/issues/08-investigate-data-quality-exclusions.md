# 08 — Investigate data-quality exclusions

**What to build:** Add a dedicated quality workflow that explains which records are included or excluded from analysis and lets users inspect and download hierarchy, actual, vintage-pair, and source-coverage exceptions.

**Blocked by:** 04 — Measure revision effectiveness; 05 — Drill into brand and target-month performance.

**Status:** closed

- [x] A quality panel reports mapped, unmapped, and conflicting hierarchy populations.
- [x] Missing actual, zero actual, positive actual, complete pair, and incomplete pair counts are visible.
- [x] Source availability distinguishes TM only, ML only, and both-source product-target populations.
- [x] Data-quality filters can include or isolate each supported quality status without corrupting metric denominators.
- [x] Blocking input errors remain distinct from non-blocking quality diagnostics.
- [x] Every diagnostic category provides a human-readable explanation and downloadable exception rows.
- [x] Quality counts respond consistently to target-month, brand, product, source, and comparison selections.
- [x] Tests verify that excluded metric rows remain represented in quality totals and cannot silently disappear.
