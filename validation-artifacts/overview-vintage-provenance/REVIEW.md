# Overview vintage provenance — visual review

## Scope and behavior

Overview KPI metrics already came from `accuracy_vintages.overview.metrics`, with microbars from `overviewPrimaryRows`. That behavior is preserved. The main and fullscreen accuracy strips now opt into primary-vintage monthly bias from those same rows. Historical accuracy comparison lines remain intact. Trends deliberately retains its existing monthly-performance bias source and axis geometry.

Volume plots now use all selected historical series plus fixed latest M1, with actual denominators from the shared common cohort. The monthly volume tooltip deliberately retains the latest-minus-actual comparison. Vintage colors are keyed to the canonical options list, not the selected-series position, and match selector, accuracy, volume and legends. Actual remains navy. The volume axis remains fixed at 1,600–4,500 KL; clipping outside that range is intentional.

## Screenshot matrix

Both **1280×720** and **1920×1080**, before and after:

| Selection | Primary | Captured states |
| --- | --- | --- |
| Default M5 | M5 | Overview, selector popover, normal volume context, accuracy fullscreen, volume fullscreen |
| M5 + M4 + M3 | M5 | Same five states |
| Deselect M5, retaining M4 + M3 | M4 | Same five states |
| Single M3 | M3 | Same five states |
| No historical selection | latest M1 | Same five states |
| Accuracy chart guide | n/a | Guide open |
| Volume chart guide | n/a | Guide open |

**54 before + 54 after PNGs**. Every image was inspected via the local image-reading tool, using 14 before/after contact sheets and additional full-resolution checks. No images were sent to the external image-analysis provider (its helper required consent).

- Original captures: `before/{viewport}-{state}.png`
- Final captures: `after/{viewport}-{state}.png`
- Payload/assertion evidence: `before/report.json`, `after/report.json`
- Side-by-side inspection sheets: `review/{viewport}-{selection-or-guide}.jpg`
- Per-image judgments and hashes: `visual-review.json`

## Improved

- M5/M4/M3 bias follows the KPI vintage, including promotion when M5 is deselected; latest-only uses latest M1's cohort rows.
- Multi-selection volume now contains the previously missing M4/M3 lines, rather than primary plus latest only.
- M4 stays blue and M3 stays purple after deselection; latest is teal in both charts, with matching legends and selector swatches.
- Extra volume legend entries have their own header row at 1920×1080, preserving the title and fullscreen control.
- Negative bias labels have reserved space above the month axis, in normal and fullscreen Overview.
- Both guides state the common-cohort and all-selected-vintage rules. The volume guide's A/B miniature is explicitly illustrative, not a claim that the live chart has only two forecasts.

## Regressed

**None remaining in the scoped changes.** The first after review found a squeezed volume title for multiple selections and bias labels touching the axis. Both were fixed, protected with geometry assertions, and the full matrix was recaptured and reviewed.

## Out of place

**None newly introduced in the scoped changes.** Existing compact-layout constraints remain visible: at 1280×720 the charts stack in an internal scroll area, the normal legends are hidden by the existing breakpoint, some KPI captions truncate, and the existing temporary “Shared population updated” toast can cover the lower-right of a normal-view capture. Normal volume-context captures prioritize its title/control; scroll is needed for the bottom of that chart. Both fullscreens show the complete chart, axes and legends. These neighboring/pre-existing behaviors were not redesigned.

## Browser assertions

For every selection, at both sizes and in both fullscreens:

- KPI Bias equals the primary common-cohort metric.
- Each monthly tooltip bias equals the primary series' raw `bias_pct`, not the separate monthly-performance value; actual visible tooltip text names that vintage.
- Every selected forecast and fixed latest occurs exactly once; actual occurs once.
- Forecast arrays equal each selected series' cohort-filtered `forecast_kl`; actual equals `actual_denominator_kl`.
- Selected series have identical target months, eligible-parent counts and actual denominators.
- Rendered volume strokes match accuracy strokes, legend swatches and selection swatches.
- No document horizontal overflow; visible overlays stay within the viewport.
- Volume title is at most two lines, fullscreen control stays inside the frame, legend does not crowd the title.
- Bias labels do not overlap month-axis labels.
- No browser runtime exceptions.

## Verification limits

No tablet/mobile widths were tested. The old `validate_vintage_selector.mjs` expectation was updated from primary-only to all-selected forecasts, but that legacy headless-browser harness was not run; the new visible-browser validation covers the requested matrix instead. CSS LSP timed out; the other six changed code files were confirmed clean, and the CSS behavior passed browser checks. See the final test logs/report for the unrelated adapter test outcome.
