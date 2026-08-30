# 07 — Complete the responsive, accessible, and visual release gate

**What to build:** Prove that the redesigned dashboard is functionally unchanged, responsive, navigable, readable, and free from the baseline visual defects by validating real browser states and publishing equivalent after-state evidence.

**Blocked by:** 04 — Deliver the revision and source-comparison experience; 05 — Deliver product-history and exception exploration; 06 — Deliver progressive data-quality diagnostics.

**Status:** ready-for-agent

- [ ] Analytical unit tests, notebook checks, the dashboard release validator, and the complete browser regression suite pass without weakened assertions.
- [ ] Document and Marimo-application widths remain within the two-pixel overflow tolerance at 390, 768, 1280, 1440, and 1920 pixel viewport widths.
- [ ] Overflow checks pass with advanced filters, vintage comparison, performance filters, exception tables, product history, comparison mode, and every quality diagnostic expanded.
- [ ] Keyboard traversal follows visual order, focus remains visible, headings and section anchors are logical, and sticky navigation does not obscure focused content.
- [ ] Source, revision outcome, and quality state remain understandable without relying on color alone, and controlled text meets normal readability and contrast expectations.
- [ ] A default-state full-page screenshot is captured from the same analytical population using the verified Marimo normalization workflow.
- [ ] A fully expanded baseline-equivalent long screenshot is captured using the same normalization and evidence state as the preserved before-image.
- [ ] A labeled before-and-after comparison artifact records both image dimensions.
- [ ] A visual-diff artifact is produced, or an image-dimension limitation is explicitly recorded without treating pixel similarity as the pass criterion.
- [ ] Final full screenshots and focused header, filter, KPI, chart, table, quality, and mobile crops are directly inspected for clipping, spacing, overlap, readability, hierarchy, and containment.
- [ ] A written validation report records objective browser measurements and marks every planned issue Fixed, Partial, or Open with evidence.
- [ ] No high-priority issue remains Open; every Partial verdict has a specific follow-up task and rationale.
