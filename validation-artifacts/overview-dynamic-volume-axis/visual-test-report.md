# Overview dynamic volume-axis visual test report

## Run metadata

- Provider: `cliproxyapi` (primary)
- Model: `Luna`
- Reasoning: `maximum`
- Browser: native `agent-browser` skill/tool
- URL: `http://127.0.0.1:8766/#overview`
- Focused retry viewport: `1920x1080`
- Selected parent: `702082 · PCNO 20ml FT BOT NEW`
- Prior run note: the primary run created seven artifacts; `opencode-go` hit its usage limit; `commandcode-go` was unavailable. This focused primary retry completed the three remaining 1920x1080 cells.
- Scope: screenshot artifacts and this report only; no source or tests were edited.

## Completion gate

All 10 PNGs exist, are readable PNG files, and have the expected dimensions. The three missing 1920x1080 artifacts were recreated cleanly:

1. `overview-default-1920x1080.png`
2. `overview-parent-702082-PCNO-20ml-FT-BOT-NEW-1920x1080.png`
3. `overview-parent-702082-PCNO-20ml-FT-BOT-NEW-fullscreen-1920x1080.png`

## Full 5x2 viewport/state matrix

| State | 1280x720 artifact and visual state | 1920x1080 artifact and visual state |
|---|---|---|
| Default Overview | `overview-default-1280x720.png` — default Overview, `FILTERS · 0`, both charts rendered. | `overview-default-1920x1080.png` — default Overview, `FILTERS · 0`, both charts rendered, no visible overflow. |
| Parent 702082 Overview | `overview-parent-702082-PCNO-20ml-FT-BOT-NEW-1280x720.png` — parent selected, one-product sparse chart state. | `overview-parent-702082-PCNO-20ml-FT-BOT-NEW-1920x1080.png` — parent selected, closed filter control, dynamic 3–5 KL axis visible. |
| Parent 702082 volume fullscreen | `overview-parent-702082-PCNO-20ml-FT-BOT-NEW-fullscreen-1280x720.png` — chart-analysis dialog, parent filter retained. | `overview-parent-702082-PCNO-20ml-FT-BOT-NEW-fullscreen-1920x1080.png` — chart-analysis dialog, `Forecast compared with actual demand`, `FILTERS · 1`, `CLOSE`. |
| SKU class C Overview | `overview-class-c-1280x720.png` — class-C Overview; existing artifact has the SKU-class dropdown open over part of the KPI/chart area. | `overview-class-c-1920x1080.png` — class-C Overview with dropdown closed and rendered charts. |
| SKU class C volume fullscreen | `overview-class-c-fullscreen-1280x720.png` — rendered chart-analysis dialog. | `overview-class-c-fullscreen-1920x1080.png` — rendered chart-analysis dialog with no visible clipping. |

All ten images were inspected as a matrix, not only the three newly captured files.

## Live assertions for the focused 1920x1080 states

### Default Overview

- `svg.chart--overview-volume`: visible.
- Attributes finite:
  - data: `2045.62231944 .. 3275.0159520000807`
  - domain: `1898.0950835327903 .. 3422.5431879072903`
- Domain contains data: pass.
- `domain-max > domain-min`: pass.
- Padding: `147.52723590720962` on both sides over data extent `1229.3936325600807`; ratio `0.12` on both sides (exact within floating-point precision).
- Plotted series: 3 visible paths; every path stayed within the measured vertical plot bounds (`y=377.31 .. 935.93` in the browser viewport).
- Axis labels visible: `KL`, `3,423`, `3,041`, `2,660`, `2,279`, `1,898`, and Sep 2025–Aug 2026 labels.
- Page overflow: `scrollWidth=clientWidth=1920`, `scrollHeight=clientHeight=1080`; pass.
- State/title: Overview selected, `PARENT · All products`, `FILTERS · 0`, `Forecast versus actual volume`; pass.
- Console/page/network diagnostics after clearing: no console messages, no page errors, and no captured actionable network errors.

### Parent 702082 Overview

- `svg.chart--overview-volume`: visible.
- Attributes finite:
  - data: `3.245373353 .. 4.467810999999903`
  - domain: `3.0986808353600117 .. 4.614503517639892`
- Domain contains data: pass.
- `domain-max > domain-min`: pass.
- Padding: `0.14669251763998847` on both sides over data extent `1.2224376469999032`; ratio `0.12` on both sides (exact within floating-point precision).
- Parent minimum below the old `1600` floor: `3.245373353 < 1600`; pass. The visible axis is the dynamic low-volume scale (`KL` ticks around `3–5`), so the low minimum is not clipped by the old floor.
- Plotted-series bounds: no out-of-bounds geometry. This filtered population has one observation and the SVG exposes no visible series path/point to measure; this is recorded as a coverage caveat below rather than inventing a line-bound result.
- Axis labels visible: `KL`, `5`, `4`, `4`, `3`, `3`, and `Aug 2026`.
- Page overflow: `scrollWidth=clientWidth=1920`, `scrollHeight=clientHeight=1080`; pass.
- State/title: Overview selected, parent control closed after selection, `PARENT · 1 selected`, `FILTERS · 1`, `Forecast versus actual volume`; pass. The selected option text was verified as `702082 · PCNO 20ml FT BOT NEW` before closing the control.
- Console/page/network diagnostics after clearing: no console messages, no page errors, and no captured actionable network errors.

### Parent 702082 volume fullscreen

- `.chart-dialog` visible at the full `1920x1080` viewport.
- `.chart-dialog svg.chart--overview-volume`: visible; fullscreen copy uses `viewBox=0 0 1000 512`.
- Measured data/domain values match the parent Overview state above; domain containment, `max>min`, and exact 12% padding pass.
- Axis labels and legend visible: `KL`, dynamic `3–5` labels, `Aug 2026`, OLDEST/LATEST/FIXED/ACTUAL.
- Title/state: `CHART ANALYSIS`, `Forecast compared with actual demand`, `FILTERS · 1`, `CLOSE`; pass. Parent filter state was retained.
- No viewport clipping or overflow observed in the 1920x1080 capture.
- Console/page/network diagnostics after clearing: no console messages, no page errors, and no captured actionable network errors.

## Artifact dimensions

| Artifact | Dimensions |
|---|---:|
| `overview-class-c-1280x720.png` | 1280x720 |
| `overview-class-c-1920x1080.png` | 1920x1080 |
| `overview-class-c-fullscreen-1280x720.png` | 1280x720 |
| `overview-class-c-fullscreen-1920x1080.png` | 1920x1080 |
| `overview-default-1280x720.png` | 1280x720 |
| `overview-default-1920x1080.png` | 1920x1080 |
| `overview-parent-702082-PCNO-20ml-FT-BOT-NEW-1280x720.png` | 1280x720 |
| `overview-parent-702082-PCNO-20ml-FT-BOT-NEW-1920x1080.png` | 1920x1080 |
| `overview-parent-702082-PCNO-20ml-FT-BOT-NEW-fullscreen-1280x720.png` | 1280x720 |
| `overview-parent-702082-PCNO-20ml-FT-BOT-NEW-fullscreen-1920x1080.png` | 1920x1080 |

## Visual classification

### Improved

- The focused 1920x1080 parent Overview and fullscreen captures use the dynamic low-volume domain; the parent minimum is visible below the former 1600 floor.
- The focused parent Overview capture has the filter dropdown closed, and the fullscreen capture has the correct chart-analysis title and close control.
- The three missing 1920x1080 cells now complete the 5x2 matrix.

### Regressed

- None newly observed in the focused retry relative to the requested dynamic-axis behavior. The parent chart is visually sparse because the selected parent has one observation; no new clipping or overflow was introduced by these captures.

### Out of place

- Existing `overview-class-c-1280x720.png` contains an open SKU-class dropdown overlaying part of the KPI/chart area; its paired 1920x1080 artifact is closed and clean.
- Existing parent 1280x720 artifacts show a `FILTERS · 2` badge while the focused 1920x1080 parent artifacts show `FILTERS · 1`. The state visuals otherwise match the selected-parent matrix row; the count discrepancy is retained as an observed cross-artifact inconsistency, not changed during this screenshot-only task.

## Coverage gaps

- The selected parent has one observation, so the SVG has no visible line/point geometry in the parent normal/fullscreen copies. The bound assertion is therefore vacuous for plotted geometry; axis/data-attribute/domain/padding visibility were verified instead.
- The class-C artifacts were visually inspected but not re-driven live in this focused retry; the existing files were not overwritten.
- Network diagnostics reported no captured requests after clearing. This verifies no observed actionable network error, but is not a full traffic trace of every prior request.
- No source or test validation was run by design.
