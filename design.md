# Forecast Dashboard Design Language

**Status:** Living implementation guide  
**Applies to:** `dashboard/index.html`, `dashboard/styles.css`, and chart renderers in `dashboard/app.js`  
**Purpose:** Preserve the dashboard’s established visual, interaction, and information-design language when adding or changing features.

## 1. Design intent

The dashboard is a compact, source-aware operational instrument for forecast review. It should feel precise, auditable, and calm—not like a marketing site or a generic analytics template.

The interface prioritizes:

1. evidence and provenance before decoration;
2. dense but legible desktop information;
3. consistent source and outcome semantics;
4. visible quality and scope boundaries;
5. keyboard-accessible interactions;
6. the same analytical state in inline and fullscreen chart views.

New UI should reuse existing components and tokens before introducing a new visual treatment.

## 2. Typography

The application uses local font files so its visual hierarchy remains stable without external font loading.

| Role | Font | Weights | Typical use |
| --- | --- | --- | --- |
| Display | Chakra Petch | 600 | product title, major KPI values, strong analytical headings |
| Body | IBM Plex Sans | 400, 500, 600 | prose, labels, controls, table content |
| Data/utility | IBM Plex Mono | 400, 500, 600 | dates, units, status chips, provenance, chart labels, compact controls |

CSS families:

```css
--display: "Chakra Petch", system-ui, sans-serif;
--body: "IBM Plex Sans", system-ui, sans-serif;
--mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", monospace;
```

### Typography rules

- Use the body face for readable explanatory copy.
- Use the mono face for data-bearing labels, dates, units, small controls, and provenance.
- Use the display face sparingly for values or headings that need immediate scanning priority.
- Small labels are usually 8–10px and must remain high enough contrast to be readable.
- Avoid decorative type changes inside one component. Hierarchy should come from weight, scale, spacing, and tone.

## 3. Color system

### 3.1 Foundation tokens

| Token | Value | Meaning |
| --- | --- | --- |
| `--bg` | `#edf3f1` | application background |
| `--bg-2` | `#f4f7f6` | secondary shell background |
| `--panel` | `#ffffff` | primary surface |
| `--panel-2` | `#eef3f1` | quiet inset/control surface |
| `--panel-3` | `#e8f3f0` | active teal-tinted surface |
| `--hairline` | `#c8d5d1` | primary border |
| `--hairline-soft` | `#dbe4e1` | grid and secondary border |
| `--text` | `#172421` | primary text |
| `--muted` | `#536762` | secondary text |
| `--faint` | `#586b66` | tertiary labels |
| `--faint-2` | `#5d6f6a` | axis and quiet metadata |
| `--panel-shadow` | `0 1px 2px rgba(23, 36, 33, 0.055)` | restrained surface lift |

The shell background uses very subtle teal/amber radial light and a 34px technical grid. This texture is ambient only; content panels remain flat and readable.

### 3.2 Semantic colors

| Token | Value | Use |
| --- | --- | --- |
| `--teal` | `#087f75` | primary action, ML, positive active state |
| `--teal-dim` | `#69aaa3` | secondary teal series/evidence |
| `--teal-glow` | `rgba(8, 127, 117, 0.2)` | focus/selection emphasis |
| `--amber` | `#9a5e00` | TM, warning, over-forecast emphasis |
| `--amber-dim` | `#d9b677` | secondary amber series/evidence |
| `--red` | `#b63b35` | negative/error state |
| `--red-dim` | `#dda7a3` | secondary negative evidence |
| `--blue` | `#2e79a5` | under-forecast or alternate informational series |
| `--series-actual` | `#1e3a8a` | actual-volume series in source-oriented charts |
| `--series-vintage-a` | `#d6b98c` | older/reference vintage |
| `--series-vintage-b` | `#15803d` | newer/comparison vintage |

Do not assign semantic colors arbitrarily. TM remains amber; ML remains teal; actual remains navy where it is not colored by an FY series. Positive and negative state colors must retain their established meaning.

## 4. Shell and layout

The desktop shell is a fixed-height grid:

```css
--topbar-h: 56px;
--statusbar-h: 30px;
--scopebar-h: 48px;
--rail-w: 232px;
--rail-collapsed-w: 72px;
```

- The top bar carries identity, freshness, live-state, filters, and reset.
- The left rail is the primary section navigator and supports a compact state.
- The status bar communicates application state without becoming a notification banner.
- The main content region owns scrolling; the document body remains fixed to the viewport.
- Panels use `minmax(0, 1fr)` and `min-width: 0` to prevent chart/table overflow.

Desktop validation targets are 1280×720 and 1920×1080. Narrower layouts are not an implicit design target unless explicitly requested.

## 5. Spacing and density

The dashboard uses a practical 4px-derived rhythm rather than a large consumer-product spacing scale.

- **Micro spacing:** 2–5px for icon-label gaps, compact metadata, table internals.
- **Control spacing:** 6–9px internal padding and 4–8px gaps.
- **Panel headers:** commonly 7px 11px, with compact variants near 5px vertically.
- **Cards and analytical blocks:** commonly 8–14px internal padding.
- **Dialogs and explanatory overlays:** commonly 18–34px, depending on visual density.
- **Major shell gutters:** commonly 16–24px.

Prefer compact alignment over whitespace for its own sake. Increase spacing only when it clarifies hierarchy or separates analytical phases.

## 6. Shape, borders, and elevation

- Most controls use a 4–6px radius.
- Frames, tooltips, and cards generally use a 6–8px radius.
- Larger overlays may use 9–10px.
- Circular shapes are reserved for lamps, point markers, and status dots.
- Pills are reserved for true status or categorical chips, not ordinary buttons.
- Borders are usually 1px hairlines.
- Shadows are subtle. Borders, surface tones, and alignment establish structure before elevation.

Avoid exaggerated rounding, floating glass panels, strong drop shadows, and gradient-filled cards.

## 7. Component grammar

### 7.1 Frame

A `.frame` is the standard analytical container:

- `.frame__head` aligns the title block and actions;
- `.frame__title` names the analytical view;
- `.frame__sub` states scope, cohort, source, or provenance;
- `.frame__metric` holds a compact headline measure;
- `.frame__body` owns the chart, table, or visualization.

Headers may wrap when controls are dense. Actions should remain visually subordinate to the analytical title.

### 7.2 Buttons and segmented controls

- Default buttons are quiet, bordered, and compact.
- Accent actions use teal rather than a new color.
- A segmented control uses connected borders, a quiet active fill, and a teal inset underline.
- Active state must be conveyed by `aria-pressed` as well as styling.
- Labels should be direct: “FY overlay”, “Long horizon”, “Reset”.

### 7.3 Chips, badges, and severity

Chips communicate source, status, or compact scope. Severity components use stable good/warn/bad semantics. Never use a status color only as decoration.

### 7.4 Tables

Tables are dense, aligned, and audit-oriented:

- headers are compact and often mono;
- numeric columns should remain stable in width and alignment;
- states and exceptions remain visible rather than being silently omitted;
- summary/footer copy explains scope or export completeness.

### 7.5 Empty and blocked states

Empty states are explicit and local to the affected frame. They explain what is missing and, where possible, what control restores data. Blocked comparisons retain the panel and state reason instead of collapsing the layout.

### 7.6 Fullscreen charts

Fullscreen is another presentation of the same renderer and state, not a separate chart implementation. Legend selection, mode, source, tooltip behavior, and data must stay synchronized with the inline view.

## 8. Chart language

### 8.1 General chart rules

- Use SVG with a stable `viewBox` and responsive CSS sizing.
- Grid lines use `--hairline-soft` and must remain quiet.
- Axis labels use IBM Plex Mono, usually 9–10px.
- Units appear once near the plot boundary rather than repeated in every tick.
- Real gaps remain gaps. Do not synthesize observations to make lines continuous.
- Line and point colors must follow the chart’s semantic legend.
- Dashed lines communicate forecast/projection or another explicitly labeled non-actual state.
- Boundary markers are fine dashed rules with short, direct labels.
- Visual point circles are presentation. A separate interaction layer should own tooltips when the chart needs month-wide inspection.

### 8.2 Persistent month-wide tooltip pattern

The Overview forecast-accuracy chart defines the standard interaction.

#### Target geometry

For every populated month, render a transparent SVG rectangle spanning the full plot height and the month’s horizontal band:

```html
<rect
  class="chart__month-hit chart__point"
  tabindex="0"
  role="img"
  aria-label="…"
/>
```

The hit band—not a tiny visual point—is the tooltip target. This makes values discoverable across the entire month column and gives keyboard users one stable focus stop per month.

Interaction targets should be emitted after visual series so they remain on top. Visual points should use `pointer-events: none` when they could intercept the month band.

#### Shared tooltip

All chart targets use the single fixed `.chart-tooltip` element:

- fixed positioning, z-index 60;
- width `min(250px, calc(100vw - 20px))`;
- 11px × 12px padding;
- 7px radius;
- white panel, hairline border, restrained shadow;
- `pointer-events: none`.

The content structure is:

```html
<div class="chart-tooltip__head">
  <strong>Month or point identity</strong>
  <span>Source</span>
</div>
<dl>
  <div><dt>Measure</dt><dd>Value</dd></div>
</dl>
```

- Header identity is body text; source/provenance is compact mono.
- Definition-list labels are muted; values are right-aligned, mono, and semibold.
- Tooltip rows show only real evidence.
- The tooltip is positioned beside the pointer or focused target, then flipped/clamped to remain inside the viewport.

#### Lifecycle and accessibility

- Delegated `pointerover` and `focusin` show the tooltip.
- `pointermove` repositions it while active.
- `pointerout` and `focusout` hide it.
- While visible, the target receives `aria-describedby` pointing to the active tooltip.
- Keyboard focus must reveal the same information as pointer hover.
- A tooltip target must not inherit unrelated click behavior from another chart. Click selectors must be scoped to their owning chart.

## 9. History actual + forward chart contract

### 9.1 FY definition

The product calls the operating period **FY (financial year)**.

- FY begins in April and ends in March.
- The label uses the calendar year in which the FY starts.
- April 2027 through March 2028 is **FY27**.
- April 2028 through March 2029 is **FY28**.
- UI labels should say “FY”, not “calendar year” or a competing year convention.

The data contract may expose `fiscal_year` and `fiscal_month`, but user-facing copy is FY.

### 9.2 FY overlay mode

- Default mode.
- X-axis is fixed to Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec, Jan, Feb, Mar.
- Each FY is a separate color and a manipulable legend item.
- Click toggles an FY; double-click isolates it; Reset restores all available FYs.
- Actual is solid and forecast is dashed in the same FY color.
- Missing months split paths.
- Actual-through boundary remains visibly distinct and labeled.
- Tooltip targets are one full-height band per month and aggregate the visible FY values for that month.

### 9.3 Long horizon mode

- Plots the entire available history chronologically.
- Uses solid navy actual and a dashed source-colored forecast: amber for TM, teal for ML.
- Inserts empty axis slots for absent calendar months so time remains truthful, but keeps values null so gaps stay visible.
- Draws an FY separator at every visible April boundary and labels it `FYxx`.
- Draws the actual-through boundary separately from FY separators.
- Uses the same persistent month-wide tooltip pattern.
- Tooltip evidence includes FY, actual or forecast, and forecast-run month when applicable.

### 9.4 Data and provenance

The chart is product-level and independent of the selected post-mortem target month. It uses:

1. all normalized actual history available for the selected SKU;
2. the latest coherent forecast run for the selected global source and SKU;
3. only forecast targets strictly after the latest actual month.

Do not fall back to an older run merely because the latest run has no targets after the actual cutoff. Do not add a synthetic actual value as a forecast anchor.

## 10. Interaction and accessibility

- Every interactive element needs a visible focus state.
- Tabs, toggles, chart targets, and dialogs must expose correct roles and state attributes.
- Keyboard users must be able to obtain chart tooltip evidence.
- Hover-only controls are insufficient.
- Use `aria-label` when visible text is absent or abbreviated.
- State changes should preserve focus where practical.
- Dialog close must restore focus to its trigger.
- Color must be reinforced with labels, line styles, icons, or text.

## 11. Copy and information tone

Copy is concise, operational, and evidence-bound.

Preferred patterns:

- state the scope: “common cohort”, “selected source”, “actual through Sep 2026”;
- name provenance: “forecast run Jul 2026”;
- name units explicitly: KL, %, pp;
- distinguish evidence from recommendation;
- say when data is unavailable or excluded.

Avoid promotional language, unexplained abbreviations, ambiguous “latest” labels, and causal claims unsupported by the data.

## 12. Responsive and validation expectations

Every visible UI change must be validated at:

- 1280×720;
- 1920×1080.

Capture every impacted state, including normal context, opened controls, each selection result, tooltip visibility, and inline/fullscreen variants. Validation must inspect:

- alignment and hierarchy;
- wrapping and truncation;
- chart and table clipping;
- control visibility and focus;
- tooltip placement;
- synchronized state between inline and fullscreen;
- neighboring content;
- horizontal and vertical overflow.

Record findings as **Improved**, **Regressed**, and **Out of place**. Any regression or out-of-place result requires correction and recapture.

## 13. Anti-patterns

Do not:

- introduce a new visual system for one feature;
- use calendar-year labels for an FY comparison;
- label April 2027–March 2028 as FY28;
- average percentages where aggregate numerators are required;
- merge TM and ML semantics;
- fill missing chart observations;
- use tiny point-only hover targets for monthly charts;
- duplicate tooltip components per chart;
- create a fullscreen renderer with independent state;
- add unscoped chart click handlers;
- use strong shadows, excessive rounding, decorative gradients, or large whitespace that weakens the operational density.

## 14. Primary implementation references

- Tokens and component styles: `dashboard/styles.css`
- Shell and semantic markup: `dashboard/index.html`
- Chart rendering and delegated tooltip behavior: `dashboard/app.js`
- Product/data behavior: `docs/forecast-analysis-dashboard-spec.md`
- Browser validation procedure: `.pi/workflows/validate-dashboard-screenshot/SKILL.md`
