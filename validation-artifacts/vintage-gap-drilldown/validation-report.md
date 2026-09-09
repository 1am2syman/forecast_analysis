# Monthly vintage gap drill-down validation

## Viewport/state matrix

| State | 1280×720 | 1920×1080 |
| --- | --- | --- |
| Overview, overlay closed | `1280-overview-closed.png` | `1920-overview-closed.png` |
| Inline chart → Gap creators | `1280-inline-creators.png` | `1920-inline-creators.png` |
| Inline overlay → Latest regressions | `1280-inline-regressions.png` | `1920-inline-regressions.png` |
| Inline overlay → Show all + populated search | `1280-inline-show-all-search.png` | `1920-inline-show-all-search.png` |
| Accuracy chart fullscreen, overlay closed | `1280-fullscreen-closed.png` | `1920-fullscreen-closed.png` |
| Fullscreen chart → Gap creators | `1280-fullscreen-creators.png` | `1920-fullscreen-creators.png` |
| Latest-only selection guidance | `1280-latest-only-guidance.png` | `1920-latest-only-guidance.png` |
| Parent SKU → Product history handoff | `1280-product-history-handoff.png` | `1920-product-history-handoff.png` |

All paths are relative to this directory.

## Browser assertions

At both desktop targets:

- Drill-down panel bounds remain inside the viewport.
- The document does not gain page-level overflow while the overlay is open.
- The overlay body fits its fixed panel.
- Brand and parent evidence panes use internal `overflow-y: auto` scrolling.
- Brand and parent columns do not overlap.
- Month hit regions expose button semantics and historical-selection guidance.
- Product history handoff reached `#history`, selected parent `706088`, and rendered `SKU post-mortem` without console, page, or network errors.

Measured overlay geometry:

- 1280×720: panel inside viewport; document overflow `false`; body fits `true`; brand pane 553/449 px scroll/client height; parent pane 349/349 px; columns non-overlapping.
- 1920×1080: panel 1540×900 at `(190, 90)`; document overflow `false`; body fits `true`; brand pane 641/588 px; parent pane 478/478 px; columns non-overlapping.

## Whole-screen judgment

### Improved

- The chart keeps its compact aggregate hover while adding a clear click-to-investigate action.
- The overlay establishes a strong audit hierarchy: baseline/latest WAPE, net change, gross fixes, regressions, brand contributors, then parent-SKU evidence.
- Gap creators use teal and regressions use red consistently in totals, tabs, bars, and row contributions.
- The 1280 layout remains dense but readable; the 1920 layout is centered and uses the additional space without stretching the evidence table excessively.
- Show all and separate brand/parent searches are visible only when needed and preserve the selected evidence context.
- Product history handoff lands on the selected parent and target month with the post-mortem context visible.

### Regressed

None observed.

### Out of place

None observed.

## Result

The complete required desktop matrix passed visual inspection and geometry assertions. No blocker remains for this feature.
