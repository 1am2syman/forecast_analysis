---
name: "validate-dashboard-screenshot"
description: "Validate forecast dashboard UI changes with viewport-matched screenshots and explicit regression judgment."
---

# Validate dashboard screenshots

Use this after every forecast-dashboard visual or responsive change.

1. Reproduce the reported state at the same viewport, tab, subtab, filters, and fullscreen mode. Capture a before screenshot when available.
2. Add a browser assertion for the reported defect and the visual relationships affected by the proposed layout change. Check geometry such as overlap, alignment edges, ordering, overflow, and computed styles.
3. Apply the smallest scoped change and run the assertion until it passes.
4. Capture an after screenshot at the exact reproduction viewport. Inspect the whole changed component and its immediate surrounding layout—not only the original symptom.
5. Explicitly judge regressions in alignment, spacing, hierarchy, wrapping/truncation, control visibility, borders/backgrounds, chart/table clipping, and neighboring content. Compare before/after when both exist.
6. If visual inspection reveals a regression, add it to the browser assertion, fix it, and recapture. Repeat until both the assertion and screenshot judgment pass.
7. Validate at one wider viewport and one compact viewport when responsive CSS or shared component styles changed.
8. Report the viewport/state, screenshot artifact paths, assertions run, and any known unverified visual states. Do not claim success from DOM assertions alone.
