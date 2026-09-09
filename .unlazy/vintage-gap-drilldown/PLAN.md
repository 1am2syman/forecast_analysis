# Plan: monthly vintage WAPE gap drill-down

## Accepted behavior

- Hover remains a compact monthly summary and advertises click-to-investigate.
- Click or Enter/Space on an accuracy-chart month opens the overlay.
- One selected historical vintage is compared with Latest M1.
- Multiple selected historical vintages use the oldest selected vintage as baseline while retaining the exact all-selected common cohort.
- No historical selection shows guidance instead of opening a meaningless latest-vs-latest overlay.
- Contributions are percentage-point shares of the chart's common-cohort WAPE gap, with supporting KL values.
- Positive fixes and latest-vintage regressions are separate views.
- Brand contribution bars drive a parent-SKU evidence table.
- Initial lists show top contributors plus an exact Other subtotal; Show all adds search.
- Parent rows offer a handoff to the existing Product history view.

## Screenshot matrix

At 1280x720 and 1920x1080:

1. Overview inline chart, overlay closed.
2. Inline chart → Gap creators overlay.
3. Inline overlay → Latest regressions.
4. Inline overlay → Show all with search populated.
5. Accuracy chart fullscreen, overlay closed.
6. Fullscreen chart → Gap creators overlay.
7. Latest-only selection → month activation guidance.
8. Parent SKU selection → Product history handoff.

## Implementation order

1. Extract reusable common-cohort assembly and add domain drill-down calculation.
2. Add adapter projection and on-demand HTTP endpoint.
3. Add overlay markup, styling, rendering, interactions, and Product history handoff.
4. Add domain, adapter, and UI source-contract tests.
5. Run diagnostics and tests.
6. Restart dashboard, execute screenshot matrix, inspect and fix.
