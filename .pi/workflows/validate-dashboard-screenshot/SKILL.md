---
name: "validate-dashboard-screenshot"
description: "Validate forecast dashboard UI changes across every impacted page and overlay state with desktop screenshots and categorical regression judgment."
---

# Validate dashboard screenshots

Use this after every forecast-dashboard visual or responsive change.

1. Before editing, enumerate every visible step/state the change can affect: the trigger in its normal page context, opened menus/popovers, each selection/action result, and every dialog/fullscreen variant. This list is the required screenshot matrix.
2. Reproduce the reported state at the same viewport, tab, subtab, filters, selection, and fullscreen mode. Capture a before screenshot when available.
3. Add browser assertions for the reported defect and affected visual relationships. Check geometry such as overlap, alignment edges, ordering, overflow, computed styles, and whether visually-hidden/accessibility text is actually hidden.
4. Apply the smallest scoped change and run the assertions until they pass.
5. Literally capture an after screenshot for every state in the matrix; do not substitute DOM assertions or one representative screenshot for an impacted state.
6. Inspect each screenshot as a whole and record a categorical judgment under **Improved**, **Regressed**, and **Out of place**. Assess alignment, spacing, hierarchy, wrapping/truncation, control visibility, borders/backgrounds, chart/table clipping, and neighboring content. Write `None observed` for an empty category rather than omitting it.
7. Treat any regression or out-of-place element as a failed validation. Add it to the browser assertion, fix it, and recapture every state affected by that fix.
8. Validate the complete screenshot matrix at both supported desktop targets: 1280×720 and 1920×1080. Skip tablet/mobile and other compact viewports unless the user explicitly requests them.
9. Report the viewport/state matrix, screenshot artifact paths, assertions run, the three categorical judgments, and any known unverified state. Do not claim success while any matrix cell lacks a screenshot.
