# 06 — Deliver progressive data-quality diagnostics

**What to build:** Let users understand data-health severity and affected populations at a glance, then expand only the hierarchy, actual, vintage-pair, source-availability, or baseline-exclusion evidence they need.

**Blocked by:** 02 — Deliver the responsive shell and filter workbench.

**Status:** ready-for-agent

- [ ] The default data-quality view starts with summary evidence for hierarchy mapping, actual availability, vintage pairs, and source availability.
- [ ] Each quality summary communicates healthy and warning/error counts, severity, and the affected product or observation population.
- [ ] Each category's explanation, count table, raw exceptions, and download are grouped in an independently expandable diagnostic section.
- [ ] Raw quality exception tables and baseline scope exclusions are collapsed in the default dashboard state.
- [ ] Baseline exclusions appear in a distinct final disclosure with an explanation of why otherwise healthy rows may be excluded.
- [ ] Blocking input errors remain immediately visible and are not hidden behind a collapsed section.
- [ ] All diagnostic and exception tables are bounded and use local horizontal scrolling without changing page width.
- [ ] Expanding every diagnostic section preserves readable hierarchy and passes the overflow oracle at supported desktop widths.
- [ ] Existing quality filters, counts, statuses, baseline-scope semantics, exception rows, and category-specific downloads remain unchanged.
- [ ] Browser tests cover default collapsed visibility, expanded visibility, filtering, download access, and empty quality states.
