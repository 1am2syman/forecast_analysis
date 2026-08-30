# 03 — Deliver the single-source performance overview

**What to build:** Let a user in either TM or ML single-source mode understand headline forecast performance immediately through readable KPI cards and properly sized monthly, horizon, and brand-by-target-month visualizations.

**Blocked by:** 02 — Deliver the responsive shell and filter workbench.

**Status:** ready-for-agent

- [ ] Headline accuracy, bias, absolute error, and coverage metrics appear first in a responsive KPI grid with no more than four cards per desktop row.
- [ ] Actual volume, forecast volume, MAE, and eligible observations appear as a clearly secondary KPI group.
- [ ] Each KPI has a readable value, explicit unit, denominator or count context, and an available audit explanation without changing its formula.
- [ ] Undefined, negative, empty, and zero-denominator states remain explicit and are not visually clipped or silently normalized.
- [ ] Monthly performance and horizon performance share an overview grid on wide screens and stack cleanly at narrower widths.
- [ ] The brand-by-target-month heatmap receives full usable content width, chronological target-month ordering, worst-first brand ordering, and a legible nearby legend.
- [ ] Chart selectors, titles, explanations, and charts form coherent sections rather than detached notebook outputs.
- [ ] Chart labels and legends do not overlap at supported desktop widths, and concise axis labels retain full evidence in tooltips.
- [ ] Tooltips preserve source, observation count, numerator/denominator, and volume evidence where applicable.
- [ ] TM and ML single-source values, filtering behavior, chart evidence, and downloads remain unchanged under existing analytical and browser tests.
- [ ] KPI and chart sections pass the overflow oracle at desktop, tablet, and mobile widths.
