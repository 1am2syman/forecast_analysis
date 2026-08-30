# 04 — Deliver the revision and source-comparison experience

**What to build:** Let users compare forecast vintages and TM versus ML through coherent controls, summary evidence, charts, warnings, and empty states that clearly distinguish common-population performance from source coverage.

**Blocked by:** 03 — Deliver the single-source performance overview.

**Status:** ready-for-agent

- [ ] Vintage A/B rules, tolerance, and comparison evidence are visually grouped and use the same responsive language as the single-source overview.
- [ ] Accuracy delta, revision effectiveness, and total error improvement appear in a dedicated revision summary rather than being mixed into an oversized KPI row.
- [ ] Revision outcome counts appear as compact evidence above a readable, appropriately sized scatter plot with visible signed-zero references.
- [ ] Revision chart legends or interactions remain usable when many brands are present and do not consume most of the plot area.
- [ ] TM-versus-ML mode presents TM and ML metrics as clearly labeled source groups and presents ML-minus-TM deltas separately.
- [ ] Common-population metrics and source-coverage metrics cannot be mistaken for one another.
- [ ] Aligned-horizon constraints, incomplete vintage pairs, coverage differences, and insufficient-history conditions produce concise, visible explanations.
- [ ] Revision and source-comparison tables are bounded, with summary evidence visible and row-level audit detail progressively disclosed.
- [ ] Existing Vintage A/B selection, pair alignment, tolerance, TM/ML isolation, comparison formulas, and download contracts remain unchanged.
- [ ] Standard TM, standard ML, comparison, warning, and empty comparison states pass analytical and browser regression tests.
- [ ] Every revision and comparison state passes the overflow oracle at supported viewport widths.
