# 02 — Deliver the responsive shell and filter workbench

**What to build:** Give users a bounded, clearly identified dashboard whose navigation, primary filters, advanced filters, active population, warnings, and reset behavior remain understandable and usable across desktop, tablet, and mobile widths.

**Blocked by:** 01 — Establish the visual baseline and overflow oracle.

**Status:** ready-for-agent

- [ ] The dashboard has a visible title, concise purpose statement, refresh metadata, active mode/source status, and working in-page section navigation.
- [ ] The application is centered within a constrained content width with responsive padding and no document-level or Marimo-application horizontal overflow in the default state.
- [ ] Primary scope controls are arranged in a responsive grid rather than one unbounded equal-width row.
- [ ] Vintage comparison, performance, and data-quality controls are grouped by task and use compact progressive disclosure.
- [ ] Exact vintage month or horizon controls are shown or enabled only when the selected rule requires them.
- [ ] Related Vintage A/B controls read as paired inputs, and unavailable comparison-mode controls are replaced by one concise explanation.
- [ ] A compact active-population panel exposes source/mode, date range, products, observations, comparable pairs, actual volume, and coverage, while detailed formulas remain available on demand.
- [ ] Coverage and population mismatch warnings are visually prominent and retain their exact evidence.
- [ ] Reset all filters is discoverable and restores the existing default analytical state.
- [ ] Existing accessible labels and all filter, population, empty-state, and download semantics remain compatible with the current regression suite.
- [ ] The layout passes the overflow oracle at desktop, tablet, and mobile widths with advanced filter groups opened and closed.
