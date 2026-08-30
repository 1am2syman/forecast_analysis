# Forecast Analysis Dashboard UI Fix-up Plan

**Status:** Proposed implementation plan  
**Primary UI:** `forecast_accuracy_app.py`  
**Analysis/view-model seam:** `forecast_analysis/dashboard.py`  
**Baseline preview:** <https://sazzadvps.taildd3bd9.ts.net/forecast-analysis-dashboard/>  
**Baseline captured:** 2026-08-26  
**Baseline full-page dimensions:** `6650 × 11082 px`

## 1. Purpose

This plan turns the current forecast-analysis Marimo notebook into a usable analytical dashboard without changing its forecast calculations, filtering semantics, quality diagnostics, or download contracts.

The redesign must fix the observed layout, readability, positioning, density, and overflow problems while retaining the dashboard's existing analytical depth and auditability.

The implementation is complete only when:

1. the application no longer creates document-level horizontal overflow at supported viewport sizes;
2. filters, KPIs, charts, tables, and quality diagnostics have a clear visual and information hierarchy;
3. the existing functional and download behavior still passes its automated contracts;
4. a new baseline-equivalent long screenshot is generated with the same Marimo full-page capture method;
5. the before-and-after screenshots and objective browser measurements are compared;
6. the final validation report explicitly decides whether each issue in this plan is fixed, partially fixed, or still open.

---

## 2. Baseline visual evidence

The following image is the current expanded full-page baseline. It was captured from the live preview using agent-browser-native after normalizing Marimo's internal `#App` scroll container.

[Open the original 6650 × 11082 screenshot](../validation-artifacts/forecast-analysis-dashboard-long-full.png)

![Current full-page forecast-analysis dashboard baseline](../validation-artifacts/forecast-analysis-dashboard-long-full.png)

### 2.1 Baseline observations

| Area | Current condition | Consequence |
| --- | --- | --- |
| Page width | The normalized document is `6650 px` wide | Most content is outside a normal desktop viewport and requires page-level horizontal movement |
| Filter placement | Related controls are distributed across the full 6650 px canvas | Labels and their conceptual peers feel disconnected; users cannot scan the filter state as one form |
| Initial viewport | Controls begin immediately, without a clear product title or page-level explanation | The page lacks an obvious starting point and analytical purpose |
| KPI layout | Eight to eleven KPI blocks are placed in a single `mo.hstack` | KPI values become small, widely separated, and difficult to compare |
| Chart sizing | Charts remain narrow and left-aligned while the page contains large empty regions | Data is technically present but visually underweighted and difficult to inspect |
| Main flow | Product vintage history appears before the primary performance overview | Specialist drill-down interrupts the main analytical narrative |
| Tables | Wide technical tables participate in the page's intrinsic width | Tables dominate the layout and force global horizontal overflow |
| Data quality | Every diagnostic table and exception table appears in the main vertical flow | The page becomes extremely long and the primary business analysis is buried |
| Typography | Native controls, Markdown headings, chart labels, and table text have inconsistent visual scale | The page reads as a notebook output rather than a designed dashboard |
| Navigation | There is no sticky section navigation or compact overview of the page structure | Users must scroll through more than 11,000 px and remember where sections are located |

### 2.2 Important capture note

A normal `screenshot --full` initially produced only a `1280 × 577 px` viewport because Marimo scrolls inside `#App`. The long baseline was produced by temporarily setting `#App` and its ancestors to `height: auto`, `max-height: none`, and `overflow: visible` before capture.

Post-implementation validation must use the same normalization process. Otherwise a short viewport screenshot could incorrectly appear to prove that the page is fixed.

---

## 3. Current implementation findings

The layout defects are primarily presentation-layer defects. The analysis model already has strong separation and should remain stable.

### 3.1 Filter layout

In `forecast_accuracy_app.py:399-735`:

- five primary filters are rendered in one equal-width `mo.hstack`;
- four data-quality multiselects are rendered in another equal-width `mo.hstack`;
- Vintage A/B rule and conditional controls are rendered in wide horizontal rows;
- six performance controls are rendered in one equal-width row;
- all exact-month and exact-horizon controls are visible regardless of the selected Vintage rule.

This composition assumes unlimited horizontal space and gives every control equal width even though their content and importance differ significantly.

### 3.2 KPI layout

In `forecast_accuracy_app.py:1340-1446`, `_cards` can contain:

- Forecast accuracy;
- Bias;
- Absolute error;
- MAE;
- Actual volume;
- Forecast volume;
- Coverage;
- Eligible observations;
- Accuracy delta;
- Revision effectiveness;
- Total error improvement.

All cards are currently passed into a single `mo.hstack(_cards, widths="equal")`. This is the direct cause of the tiny, widely separated KPI presentation.

### 3.3 Chart layout

In `forecast_accuracy_app.py:1549-2173`:

- charts set height but generally do not declare a responsive container width;
- charts are stacked one after another rather than composed into an overview grid;
- legends can occupy a large share of a small plot;
- metric selectors are separate from the chart container they control;
- the heatmap and revision scatter do not receive stronger visual priority than surrounding explanatory text.

### 3.4 Table layout

In `forecast_accuracy_app.py:2177-2392`:

- the filtered vintage table exposes many columns at once;
- data-quality sections render summary and raw exception tables inline;
- table width is not isolated from page width;
- healthy summary information and technical row-level diagnostics receive similar prominence;
- all four quality categories and baseline exclusions remain in the normal page flow.

### 3.5 Existing behavior that must not regress

The redesign must preserve:

- `DashboardFilters` and shared population semantics;
- source isolation between TM and ML;
- Vintage A/B selection rules;
- filter-to-KPI/chart/table/download consistency;
- quality counts and exception downloads;
- comparison-mode alignment behavior;
- product-history filtering;
- exact filtered-vintage CSV schema and values;
- safe empty states;
- existing unit, release-validator, and browser test contracts.

---

## 4. Target dashboard structure

The dashboard should follow the order in which a business user asks questions.

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Forecast performance dashboard                         Refreshed …  │
│ Understand forecast accuracy, bias, revisions, and data coverage.   │
├─────────────────────────────────────────────────────────────────────┤
│ Sticky section navigation                                      Reset│
│ Overview · Trends · Revisions · Product history · Data quality      │
├─────────────────────────────────────────────────────────────────────┤
│ Primary filters: mode/source · period · brand · product · horizon   │
│ Advanced filters: vintage rules · performance · quality             │
├─────────────────────────────────────────────────────────────────────┤
│ Active population summary / warnings                               │
├─────────────────────────────────────────────────────────────────────┤
│ Headline KPI cards: Accuracy · Bias · Abs error · Coverage           │
│ Secondary KPI cards: Actual · Forecast · MAE · Eligible observations│
├───────────────────────────────┬─────────────────────────────────────┤
│ Monthly performance           │ Performance by horizon              │
├───────────────────────────────┴─────────────────────────────────────┤
│ Brand × target-month heatmap                                      │
├───────────────────────────────┬─────────────────────────────────────┤
│ Revision effectiveness        │ Revision scatter / comparison       │
├─────────────────────────────────────────────────────────────────────┤
│ Product vintage history drill-down                                 │
├─────────────────────────────────────────────────────────────────────┤
│ Filtered exceptions table and downloads                            │
├─────────────────────────────────────────────────────────────────────┤
│ Data-quality summary cards                                         │
│ Expandable category tables and baseline exclusions                 │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.1 Information order

The final page order should be:

1. header and refresh/status information;
2. section navigation;
3. primary and advanced filters;
4. active population summary and warnings;
5. core KPI overview;
6. monthly and horizon performance;
7. brand/target-month analysis;
8. revision or source-comparison analysis;
9. product-history drill-down;
10. filtered exception table and downloads;
11. data-quality summaries and expandable diagnostics.

Product vintage history must no longer interrupt the path from filters to the main performance results.

---

## 5. Visual system

The dashboard should remain sober and analytical. It does not need decorative visual effects; it needs disciplined typography, spacing, grouping, and scale.

### 5.1 Layout tokens

| Token | Target |
| --- | --- |
| Application maximum width | `1440–1560 px` |
| Desktop page padding | `24–32 px` |
| Tablet page padding | `20–24 px` |
| Mobile page padding | `12–16 px` |
| Section gap | `32–48 px` |
| Card gap | `12–16 px` |
| Card padding | `16–20 px` |
| Card radius | `8–10 px` |
| Minimum interactive control height | `36 px`; target `40 px` where Marimo permits |
| Main body size | at least `14 px` |
| Supporting/audit text | at least `12 px`, with sufficient contrast |
| KPI value size | approximately `24–32 px` depending on viewport |

### 5.2 Color roles

Keep the established source colors and reserve other colors for meaning.

| Role | Use |
| --- | --- |
| TM color | Consistent TM series and source marker |
| ML color | Consistent ML series and source marker |
| Vintage A/B colors | Only for vintage comparison evidence |
| Positive/improved | Positive outcome, not general decoration |
| Negative/worsened | Negative outcome and alert conditions |
| Warning | Coverage mismatch, incomplete pair, or insufficient history |
| Neutral surface | Card and grouped-section background |
| Border/divider | Quiet structural grouping |

Do not use color alone to communicate improved/worsened, source, or quality status. Preserve labels, icons, or text.

### 5.3 Typography hierarchy

Use one consistent UI family inherited from Marimo or explicitly defined in the dashboard stylesheet.

- Page title: strongest type treatment.
- Section titles: consistent size and weight.
- Card labels: compact and semibold.
- KPI values: large tabular numerals.
- Audit formulas: smaller monospace or utility text.
- Table headers: compact semibold text with visible separation from values.

Long audit explanations should be placed behind “Metric details” or similar expandable content rather than competing with the KPI values.

---

## 6. Detailed implementation phases

## Phase 0 — Preserve the baseline and define the visual validation harness

### Work

1. Retain the current screenshot at:
   - `validation-artifacts/forecast-analysis-dashboard-long-full.png`
2. Add a deterministic browser validation procedure that records:
   - URL;
   - viewport dimensions;
   - `document.documentElement.clientWidth`;
   - `document.documentElement.scrollWidth`;
   - `#App.clientWidth`;
   - `#App.scrollWidth`;
   - document and `#App` heights;
   - screenshot path and dimensions.
3. Capture the current default control values so the post-implementation screenshot uses the same data population and state.
4. Define two screenshot states:
   - **Default UX state:** advanced and data-quality detail sections collapsed;
   - **Expanded audit state:** all diagnostic accordions expanded for baseline-equivalent inspection.

### Acceptance

- Baseline screenshot remains available and embedded in this document.
- The capture procedure proves whether the image is a viewport-only screenshot or a true normalized Marimo full-page screenshot.
- Browser measurements are saved with the validation artifacts.

---

## Phase 1 — Add the dashboard shell and responsive width containment

### Primary file

- `forecast_accuracy_app.py`

### Work

1. Add one dashboard-scoped stylesheet near the top of the Marimo presentation file.
2. Add a root dashboard wrapper with:
   - a constrained maximum width;
   - automatic horizontal centering;
   - responsive horizontal padding;
   - `min-width: 0` on grid/flex descendants;
   - page-level overflow protection.
3. Add reusable presentation wrappers/classes for:
   - page header;
   - section container;
   - card surface;
   - KPI grid;
   - chart grid;
   - filter grid;
   - table viewport;
   - status/warning banner;
   - supporting audit details.
4. Ensure `mo.ui.table` and chart wrappers cannot set the width of the entire `#App` document.
5. Add CSS breakpoints for:
   - wide desktop: `>= 1280 px`;
   - desktop/tablet: `768–1279 px`;
   - mobile/narrow: `< 768 px`.

### Hard acceptance

At `1280 × 800`, `1440 × 900`, and `1920 × 1080`:

```text
document.scrollWidth <= document.clientWidth + 2
#App.scrollWidth <= #App.clientWidth + 2
```

At `390 × 844`:

- no label or control is clipped;
- filters stack vertically;
- cards use one column;
- tables may scroll inside their own containers, but the page itself does not scroll horizontally.

### Regression boundary

No analysis logic, filter semantics, metric formulas, or download schemas should change in this phase.

---

## Phase 2 — Build a real header and section navigation

### Work

1. Add a visible title such as **Forecast performance dashboard**.
2. Add one concise supporting sentence explaining the page's purpose.
3. Display refresh timestamp as secondary metadata rather than as the first item in a long Markdown paragraph.
4. Display the active mode and source as a compact status badge or text group.
5. Add sticky in-page navigation for:
   - Overview;
   - Trends;
   - Revisions/Comparison;
   - Product history;
   - Exceptions;
   - Data quality.
6. Keep Reset all filters visible near the filter area or navigation, not detached in a separate row.
7. Use section anchors so keyboard and mouse users can jump through the long page.

### Acceptance

- The first viewport clearly communicates what the dashboard is and what population is being viewed.
- Reset filters is discoverable without appearing as an isolated button.
- Users can reach every major analytical section without manually scanning the full page.

---

## Phase 3 — Recompose the filter workbench

### Current seam

- `forecast_accuracy_app.py:399-735`
- `build_view_controls()`
- `build_mapped_filter_controls()`

### Work

#### 3.1 Primary filter group

Render the following as the always-visible filter workbench:

1. View mode;
2. Forecast source when in single-source mode;
3. Target month range;
4. Brand;
5. Parent product;
6. Forecast/comparison horizon.

Use a responsive grid, not a single equal-width horizontal stack.

Recommended desktop sizing:

```text
Mode/source: 2 columns
Target range: 2 columns
Brand: 3 columns
Parent product: 3 columns
Horizon: 2 columns
```

#### 3.2 Advanced vintage group

Move Vintage A/B controls into an expandable **Vintage comparison** group.

- Pair Vintage A and Vintage B visually.
- Only show or enable the exact month input when its rule is `specific_calculation_month`.
- Only show or enable the exact horizon input when its rule is `specific_horizon`.
- Keep revision tolerance beside the controls it affects.
- In comparison mode, replace the unavailable controls with one concise aligned-horizon explanation.

#### 3.3 Performance group

Place performance filters in an expandable **Performance filters** group.

- Group direction, accuracy/bias band, and minimum error together.
- Group Top N and ranking metric together.
- Explain disabled controls once at group level rather than through scattered no-op copy.

#### 3.4 Data-quality group

Keep quality filters collapsed by default.

- Arrange status filters in a responsive two-column grid.
- Keep checkboxes together.
- Replace the current long explanation with a short summary and a “How these filters affect counts” disclosure.

#### 3.5 Active filter summary

Below the workbench, show a compact summary of:

- selected source/mode;
- date range;
- selected products/brands/horizons;
- Vintage A/B rules;
- active advanced-filter count.

### Acceptance

- Every control is within the root content width.
- No primary label is separated from its input by more than its normal form-group spacing.
- Related Vintage A/B controls read as pairs.
- Conditional controls do not create meaningless empty space.
- The default state is understandable without opening advanced filters.
- Existing labels required by browser tests remain accessible, even if visible wording is shortened.

---

## Phase 4 — Replace the population wall of text with a compact status panel

### Current seams

- `population_summary_markdown()`
- `forecast_accuracy_app.py:1239-1336`

### Work

1. Render a compact **Active population** panel with:
   - products;
   - forecast rows;
   - eligible observations;
   - comparable pairs;
   - actual volume;
   - coverage.
2. Keep source/mode/date/horizon state visible above or inside the panel.
3. Move detailed vintage rules, formula policy, and denominator explanation into expandable audit details.
4. Render comparison warnings and population mismatches as visible banners.
5. Keep exact existing values in the DOM so current text-based tests and auditing remain possible.

### Acceptance

- A user can understand the current analytical population in under one screen scan.
- Formula details remain available but do not visually compete with the headline results.
- Coverage warnings are more prominent than routine metadata.

---

## Phase 5 — Rebuild KPI presentation

### Current seam

- `forecast_accuracy_app.py:1340-1446`

### Work

1. Replace the single `mo.hstack` with a responsive KPI grid.
2. Put the four most important metrics first:
   - Forecast accuracy;
   - Bias;
   - Absolute error;
   - Coverage.
3. Put supporting metrics in a second row:
   - Actual volume;
   - Forecast volume;
   - MAE;
   - Eligible observations.
4. Show revision-only metrics in a separate comparison/revision strip:
   - Accuracy delta;
   - Revision effectiveness;
   - Total error improvement.
5. Each KPI card should have:
   - compact label;
   - large value and explicit unit;
   - short denominator/count subtitle;
   - optional audit detail;
   - consistent height and alignment.
6. Use semantic status styling sparingly:
   - negative accuracy remains visible, not clipped or converted to zero;
   - large positive or negative bias is distinguishable;
   - undefined values show `—` with an explanatory subtitle.
7. In TM-vs-ML mode:
   - show TM and ML cards in two clear source panels;
   - show ML-minus-TM deltas in a separate row;
   - do not mix common-population metrics with source-coverage metrics without labels.

### Acceptance

- No more than four KPI cards appear per row on desktop.
- KPI values are readable at a glance at 1280 px width.
- Undefined and empty states remain explicit.
- Existing metric values and audit formulas remain unchanged.

---

## Phase 6 — Resize and regroup charts

### Current seams

- Monthly performance: `forecast_accuracy_app.py:1549-1697`
- Horizon performance: `forecast_accuracy_app.py:1715-1843`
- Brand heatmap: `forecast_accuracy_app.py:1872-2069`
- Revision scatter: `forecast_accuracy_app.py:2073-2173`

### Work

#### 6.1 Shared chart behavior

1. Set Altair charts to responsive container width where supported.
2. Place charts inside `min-width: 0; width: 100%` wrappers.
3. Standardize heights:
   - overview line charts: `320–400 px`;
   - heatmap: content-dependent but bounded sensibly;
   - scatter: `380–460 px`.
4. Keep metric selector, title, explanatory sentence, and chart inside one visual section.
5. Reduce explanatory copy to one concise sentence; move formulas to expandable details.
6. Keep visible zero references for signed metrics.
7. Keep consistent TM/ML and Vintage A/B colors.

#### 6.2 Overview chart grid

Place Monthly performance and Performance by forecast horizon side by side on wide desktops and stack them below approximately 1000 px.

Each overview chart should be at least approximately `480 px` wide in a two-column layout.

#### 6.3 Horizon chart

- Prefer concise labels such as `4 mo`, `3 mo`, `2 mo`, `1 mo`, `Current`.
- Avoid vertical or overlapping axis text.
- Preserve full labels in tooltips.

#### 6.4 Heatmap

- Give the heatmap full content width.
- Keep target months ordered chronologically.
- Preserve worst-first brand ordering.
- Ensure the legend is legible and close to the visualization.
- Keep quality groups visible but distinguish them from mapped brands.

#### 6.5 Revision scatter

- Increase the plot area.
- Move long brand legends outside the plot or replace them with a more usable interaction when the legend becomes too large.
- Preserve zero lines and point-size encoding.
- Keep the four revision outcome counts in compact summary cards above the chart.

### Acceptance

- Charts use the available content width rather than occupying a narrow left column.
- Labels and legends do not overlap at 1280 px.
- Charts remain readable at 768 px by stacking.
- Tooltips retain numerator, denominator, volume, source, and observation evidence.
- Empty chart states use the same section container and do not collapse the layout unpredictably.

---

## Phase 7 — Reposition and simplify product-history drill-down

### Current seams

- Product controls: `forecast_accuracy_app.py:739-777`
- Product-history rendering: `forecast_accuracy_app.py:1047-1235`

### Work

1. Move Product vintage history after the primary performance and revision views.
2. Present it as a clearly named drill-down section.
3. Keep product and target-month controls together inside the section header.
4. Place product identity, brand, mapping status, and actual value in a compact summary row.
5. Give the history chart enough width to show chronological development.
6. Place Point audit, consecutive revisions, and stability tables in expandable subsections.
7. Show insufficient-history warnings as a compact status banner rather than a long interruption above a mostly empty chart.

### Acceptance

- The main performance story is visible before specialist product history.
- Product controls do not consume the global filter area.
- A one-vintage product still communicates why stability is unavailable without making the page appear broken.

---

## Phase 8 — Contain and prioritize tables

### Current seams

- Comparison tables: `forecast_accuracy_app.py:1450-1529`
- Filtered vintage table: `forecast_accuracy_app.py:2177-2280`
- Quality tables: `forecast_accuracy_app.py:2284-2392`

### Work

#### 8.1 Table containment

Every wide table must be inside a bounded wrapper with:

```text
width: 100%
max-width: 100%
min-width: 0
overflow-x: auto
```

Document-level horizontal scrolling is never an acceptable substitute for a table viewport.

#### 8.2 Filtered exceptions table

1. Rename the visible section to emphasize its purpose, for example **Largest forecast exceptions**.
2. Show a business-focused default column set:
   - source;
   - product;
   - brand;
   - target month;
   - actual;
   - Vintage B forecast;
   - absolute error;
   - bias;
   - revision outcome;
   - pair/mapping status.
3. Keep the complete audit schema in the CSV download.
4. Provide an expandable **Show audit columns** table when row-level vintage details are needed.
5. Keep search, sort, pagination, and download controls discoverable.

#### 8.3 Comparison tables

- Show the source-population summary and winner counts as compact cards or small tables.
- Keep the row-level paired comparison table collapsed by default.

#### 8.4 Table usability

Where Marimo's table implementation permits:

- use sticky headers;
- keep product/source identifiers visible during horizontal movement;
- use tabular numerals;
- align numeric columns right;
- render nulls quietly as `—` rather than visually loud `None` values.

### Acceptance

- A table may scroll horizontally within its own viewport.
- Opening a table does not change `document.scrollWidth` or `#App.scrollWidth` beyond the 2 px tolerance.
- Default tables emphasize business decisions rather than every audit field.
- Downloads remain complete and exactly filter-aligned.

---

## Phase 9 — Redesign data-quality presentation with progressive disclosure

### Current seam

- `forecast_accuracy_app.py:2284-2392`

### Work

1. Keep one Data quality section near the end of the page.
2. Show four summary cards first:
   - Hierarchy mapping;
   - Actual availability;
   - Vintage pairs;
   - Source availability.
3. Each summary card should display:
   - healthy count;
   - warning/error count;
   - severity;
   - affected products or observations.
4. Put each category's explanation, count table, exception table, and download inside an accordion.
5. Keep accordions collapsed by default.
6. Put Baseline scope exclusions in a separate final accordion with a clear explanation of why healthy rows can appear there.
7. Do not render every raw exception table during the initial visual scan unless Marimo performance requires precomputation; hide the visual output even if the data already exists.
8. Keep blocking input errors visible at the top of the section.

### Acceptance

- The default page does not show all quality exception rows.
- Users can understand whether quality issues exist before opening raw tables.
- All existing quality downloads remain available.
- Expanded audit mode can still expose every quality table for long-screenshot and contract validation.

---

## Phase 10 — Accessibility and interaction polish

### Work

1. Preserve accessible labels currently used by the e2e suite.
2. Add visible keyboard focus styles to links, buttons, dropdowns, and disclosures.
3. Ensure heading levels follow the page hierarchy.
4. Use descriptive section-anchor names.
5. Do not rely on color alone for source, outcome, or quality state.
6. Keep text contrast at least WCAG AA for normal body text where dashboard CSS controls it.
7. Ensure warning and empty-state text gives a next action or reason.
8. Verify that collapsed advanced controls remain keyboard reachable when expanded.
9. Respect reduced-motion settings; avoid unnecessary animation.
10. Keep control vocabulary consistent:
    - Reset all filters;
    - Download filtered vintage CSV;
    - Download brand × target-month CSV;
    - Show metric details;
    - Show audit columns.

### Acceptance

- Keyboard traversal follows the visual order.
- Focus is visible.
- Heading and landmark order is logical.
- Existing browser queries by label continue to work.

---

## 7. Proposed code-change map

| File | Expected change |
| --- | --- |
| `forecast_accuracy_app.py` | Main layout composition, dashboard stylesheet, header/navigation, filter grid, KPI grid, chart grid, table wrappers, accordions, section ordering |
| `forecast_analysis/dashboard.py` | Prefer no behavioral change; only add presentation-ready summary data if the UI cannot derive it without duplicating business logic |
| `tests/test_forecast_analysis_dashboard.py` | Add or adjust pure presentation-helper tests only when helpers are extracted; retain metric/population tests unchanged |
| `tests/e2e/test_forecast_analysis_dashboard.py` | Add layout, disclosure, overflow, navigation, responsive, and post-redesign interaction tests while preserving existing data/download tests |
| `scripts/validate_forecast_analysis_dashboard.py` | Keep as the analytical release oracle; do not weaken it for visual work |
| `scripts/validate_forecast_analysis_dashboard_ui.py` | Proposed new optional browser/DOM validation entry point if the native-browser measurements need a repeatable repo command |
| `validation-artifacts/forecast-analysis-dashboard-long-full.png` | Existing baseline; do not overwrite |
| `validation-artifacts/forecast-analysis-dashboard-long-fixed.png` | New baseline-equivalent expanded full-page capture |
| `validation-artifacts/forecast-analysis-dashboard-default-fixed.png` | New default collapsed-state full-page capture |
| `validation-artifacts/forecast-analysis-dashboard-before-after.png` | Side-by-side review artifact |
| `validation-artifacts/forecast-analysis-dashboard-visual-diff.png` | Pixel/structural diff where tool support and image dimensions permit |
| `validation-artifacts/forecast-analysis-dashboard-ui-validation.md` | Final issue-by-issue validation verdict and browser measurements |

### Architectural boundary

Keep Marimo and Altair presentation concerns at the application edge. Do not move CSS, HTML wrappers, or Marimo controls into the analysis modules. Do not modify metric logic merely to make presentation easier.

If reusable UI helpers are extracted, place them in a presentation-specific module that does not become an analysis dependency.

---

## 8. Automated test plan

## 8.1 Existing required checks

Run before and after the UI changes:

```bash
uv run marimo check forecast_accuracy_app.py
uv run python -m unittest tests.test_forecast_analysis_dashboard
uv run python scripts/validate_forecast_analysis_dashboard.py
```

Run the deferred browser suite against the live app:

```bash
FORECAST_DASHBOARD_URL=https://sazzadvps.taildd3bd9.ts.net/forecast-analysis-dashboard/ \
  uv run python -m unittest discover -s tests/e2e -p 'test_*.py'
```

Use the `preview` helper if the app is restarted on a new localhost port. Do not create a separate Tailscale Funnel.

## 8.2 New browser layout tests

Add tests for the following conditions.

### Desktop overflow

At viewport widths `1280`, `1440`, and `1920`:

```javascript
expect(document.documentElement.scrollWidth)
  .toBeLessThanOrEqual(document.documentElement.clientWidth + 2)
expect(app.scrollWidth).toBeLessThanOrEqual(app.clientWidth + 2)
```

Run these assertions in:

- default collapsed state;
- Vintage comparison expanded;
- Performance filters expanded;
- Data quality expanded;
- filtered exception table visible;
- comparison mode;
- product-history section visible.

### Responsive layout

At `390 × 844` and `768 × 1024`:

- page-level horizontal overflow remains absent;
- visible filter controls are inside the viewport;
- KPI cards stack correctly;
- charts remain visible;
- tables retain an internal horizontal scroll viewport;
- sticky navigation does not cover focused content.

### Information architecture

Verify that the DOM order is:

1. title/header;
2. filters;
3. population summary;
4. KPI overview;
5. performance charts;
6. revision/comparison;
7. product history;
8. exceptions;
9. data quality.

### Progressive disclosure

Verify on first load:

- advanced filter groups are collapsed or compact;
- raw data-quality exception tables are not visible;
- baseline exclusions are not visible;
- summary counts and download access remain discoverable.

Verify after expansion:

- all relevant controls/tables become visible;
- no page overflow is introduced;
- existing filtering and download behavior still works.

### Existing behavior

Retain all existing e2e assertions for:

- default TM values;
- ML mode values;
- comparison values;
- quality filters;
- deterministic filtered scope;
- download schema and visible-row fidelity;
- safe empty state.

---

## 9. Post-implementation screenshot and comparison protocol

This protocol is mandatory. Passing unit tests alone does not prove the UI is fixed.

## 9.1 Open the same live route

Use agent-browser-native to open:

```text
https://sazzadvps.taildd3bd9.ts.net/forecast-analysis-dashboard/
```

Confirm the URL and wait for **Population summary** or its redesigned equivalent.

## 9.2 Use the same default analytical state

Before capture, verify:

- View mode: Single source;
- Source: TM;
- Target month range: full default range;
- Brands: all;
- Parent products: all;
- Horizons: all available;
- Vintage A: oldest available;
- Vintage B: latest available;
- Minimum actual volume: 0;
- Performance and quality filters: default values.

The comparison is invalid if the baseline and final screenshots represent different analytical populations.

## 9.3 Record pre-normalization browser measurements

Through agent-browser-native, evaluate and save:

```javascript
({
  viewport: { width: innerWidth, height: innerHeight },
  document: {
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    scrollHeight: document.documentElement.scrollHeight
  },
  app: (() => {
    const app = document.querySelector('#App');
    return app ? {
      clientWidth: app.clientWidth,
      scrollWidth: app.scrollWidth,
      clientHeight: app.clientHeight,
      scrollHeight: app.scrollHeight
    } : null;
  })()
})
```

This measurement is the primary overflow oracle. Screenshot appearance alone is insufficient.

## 9.4 Capture the default-state screenshot

Normalize `#App` and its ancestors exactly as in the baseline capture, then save:

```text
validation-artifacts/forecast-analysis-dashboard-default-fixed.png
```

The screenshot should show the intended default progressive-disclosure state.

## 9.5 Capture the baseline-equivalent expanded screenshot

Expand all dashboard audit accordions/disclosures, normalize `#App`, and save:

```text
validation-artifacts/forecast-analysis-dashboard-long-fixed.png
```

This is the direct successor to:

```text
validation-artifacts/forecast-analysis-dashboard-long-full.png
```

Both captures must use agent-browser-native `screenshot --full` after Marimo full-page normalization.

## 9.6 Compare before and after

Perform three forms of comparison.

### A. Objective measurement comparison

| Measurement | Baseline | Required final |
| --- | ---: | ---: |
| Full screenshot width | `6650 px` | approximately the selected viewport width; never thousands of pixels wider |
| Document horizontal overflow | Present | Absent within `2 px` tolerance |
| `#App` horizontal overflow | Present | Absent within `2 px` tolerance |
| Primary filters visible in first viewport | Partial/clipped | Yes |
| Core KPI readability | Poor | Four or fewer cards per row with readable values |
| Raw quality tables visible by default | Yes | No |
| Product history before overview | Yes | No |
| Table scrolling | Global/page-level | Local table viewport only |

### B. Visual side-by-side comparison

Create:

```text
validation-artifacts/forecast-analysis-dashboard-before-after.png
```

The artifact should place the current baseline and final expanded screenshot side by side with labels and recorded dimensions.

### C. Screenshot diff

Use agent-browser-native's screenshot-diff support when it can compare the files safely:

```text
diff screenshot --baseline validation-artifacts/forecast-analysis-dashboard-long-full.png \
  --output validation-artifacts/forecast-analysis-dashboard-visual-diff.png \
  --full
```

Because the redesign intentionally changes dimensions and composition, pixel similarity is **not** the pass criterion. The diff is evidence of where the design changed. The pass decision comes from the objective gates and manual issue checklist below.

If the diff tool cannot compare images with different dimensions, retain the side-by-side artifact and record that limitation in the validation report.

## 9.7 Read the final screenshots directly

Use the direct image `read` tool on:

- the full final screenshot;
- focused crops of the header/filter area;
- KPI and chart area;
- exception table;
- expanded data-quality area;
- a mobile screenshot.

Do not declare the UI fixed from DOM metrics alone. Inspect the rendered evidence for spacing, hierarchy, clipping, label overlap, chart readability, and table containment.

## 9.8 Write the final validation verdict

Create:

```text
validation-artifacts/forecast-analysis-dashboard-ui-validation.md
```

Use this table:

| Issue | Baseline evidence | Final evidence | Verdict |
| --- | --- | --- | --- |
| Document horizontal overflow | 6650 px full-page width | Browser width metrics and final screenshot | Fixed / Partial / Open |
| Fragmented filters | Baseline top crops | Final top crop | Fixed / Partial / Open |
| Missing page identity | Baseline initial viewport | Final header | Fixed / Partial / Open |
| Tiny KPI row | Baseline performance crop | Final KPI crop | Fixed / Partial / Open |
| Undersized charts | Baseline chart crops | Final chart crops | Fixed / Partial / Open |
| Product-history placement | Baseline section order | Final section order | Fixed / Partial / Open |
| Global table overflow | Baseline table crops | Final DOM metrics and table crop | Fixed / Partial / Open |
| Data-quality overload | Baseline lower screenshot | Final default and expanded states | Fixed / Partial / Open |
| Responsive behavior | Not established | Mobile/tablet captures | Fixed / Partial / Open |
| Accessibility/navigation | Weak/absent | Keyboard, heading, and focus checks | Fixed / Partial / Open |

The implementation must not be called complete while any high-priority issue is **Open**. A **Partial** verdict requires a specific follow-up task and explanation.

---

## 10. Definition of done

The UI fix-up is done only when all of the following are true.

### Functional

- [ ] Existing analytical unit tests pass.
- [ ] `scripts/validate_forecast_analysis_dashboard.py` passes.
- [ ] `marimo check forecast_accuracy_app.py` passes.
- [ ] Existing e2e population, filtering, empty-state, and download tests pass.
- [ ] No metric, filter, source-isolation, quality, or download contract changed unintentionally.

### Layout

- [ ] No document-level or `#App` horizontal overflow at 390, 768, 1280, 1440, and 1920 px widths.
- [ ] Tables scroll only inside bounded table viewports.
- [ ] Primary filters fit within the root dashboard container.
- [ ] Related labels and controls remain visually grouped.
- [ ] No more than four KPI cards appear per row on desktop.
- [ ] Overview charts use a meaningful share of the available width.
- [ ] Product history follows the primary analysis.
- [ ] Raw quality tables are collapsed by default.

### Readability and hierarchy

- [ ] The first viewport contains a title, purpose, active scope, and primary controls.
- [ ] KPI values are readable without zooming.
- [ ] Chart labels and legends do not overlap.
- [ ] Audit formulas remain available through progressive disclosure.
- [ ] Empty and warning states are visible and actionable.
- [ ] Section navigation works through keyboard and pointer input.

### Visual evidence

- [ ] `forecast-analysis-dashboard-default-fixed.png` exists and is verified.
- [ ] `forecast-analysis-dashboard-long-fixed.png` exists and is verified.
- [ ] `forecast-analysis-dashboard-before-after.png` exists.
- [ ] A visual diff exists, or its dimension limitation is documented.
- [ ] Final screenshots were read directly, including focused crops.
- [ ] Browser dimension/overflow measurements were saved.
- [ ] `forecast-analysis-dashboard-ui-validation.md` gives an issue-by-issue verdict.
- [ ] Every high-priority issue is marked Fixed.

---

## 11. Recommended delivery sequence

1. Preserve baseline and add overflow measurements.
2. Add root width containment and table wrappers.
3. Add header, navigation, and responsive filter grid.
4. Rebuild population and KPI presentation.
5. Regroup and resize charts.
6. Move and simplify product history.
7. Add progressive disclosure to tables and quality diagnostics.
8. Add responsive and overflow e2e tests.
9. Run analytical and browser regression suites.
10. Generate default and expanded final screenshots.
11. Produce before/after and visual-diff artifacts.
12. Read the final screenshots directly.
13. Write the validation verdict and fix every remaining Open item.

The work should be delivered in reviewable phases. Width containment and overflow tests should land first because every later visual decision depends on a trustworthy page geometry.
