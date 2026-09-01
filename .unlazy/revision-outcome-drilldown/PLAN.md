# Plan: revision outcome drill-down (tree 2)

## Shared contract

- Feature scope: Comparison tab → Revision subpanel outcome strip (`improved`, `worsened`, `neutral`, `unchanged`).
- Selection grain: `parent_code` (one row corresponds to one existing scatter bubble).
- Ranking: top 20 parent codes per category by error impact descending.
  - improved/worsened: absolute summed `error_improvement_kl`.
  - neutral/unchanged: summed Vintage-B absolute error (`absolute_error_b_kl`), because error-improvement is within tolerance.
- Drill-down rows expose parent code, description, brand, observations, target months, actual KL, absolute error KL, net error improvement KL, revision KL, and ranking impact KL.
- The base exceptions module adds `revision_drilldown` and includes `metrics` so a selected module response can redraw all three KPIs.
- Multi-selection request field: `drilldown_parent_codes: number[]`. It is local to this Revision subpanel and is not shown as a global scope control. Existing scalar `parent_code` takes precedence when present.
- Browser selection behavior:
  - ordinary click replaces selection with one parent;
  - Shift/Ctrl/Meta click toggles additive selection;
  - selection triggers a dedicated `exceptions` module request with `drilldown_parent_codes`;
  - base top-20 lists remain stable while selected KPIs, outcome counts, revision-history chart, scatter chart, and action queue render from the selected response;
  - clear selection restores the already-loaded base payload without a global dashboard refresh.
- Popover behavior: one accessible anchored popover at a time, Escape/outside click closes it, selected rows remain highlighted, and a visible selection summary offers Clear.
- Compatibility: no change to comparison-mode source panel; no change to global `parent_code`; no deep merge of module payloads.

## Depth tree

- root `1` — integrated drill-down feature and regression proof
  - leaf `1.1` — backend request contract, ranking payload, canonical multi-parent recomputation, Python tests
  - leaf `1.2` — outcome-card popovers, selection state/request flow, synchronized rendering, CSS, browser oracle

## State

- leaf 1.1: VERIFIED; Needs: none; OWNS: `dashboard/adapter.py`, `tests/test_static_dashboard_adapter.py`
- leaf 1.2: VERIFIED; Needs: none; OWNS: `dashboard/app.js`, `dashboard/styles.css`, `scripts/validate_revision_drilldown.mjs`, `scripts/validate_dashboard_functionality.mjs`
- root 1: VERIFIED; Needs: none

## Toolchain

- Working directory: `/root/GitHub/forecast_analysis`
- Shell: `/bin/sh`
- Python: `uv run python`
- Browser oracle: Node + Chromium against `dashboard.server`

## Status log

- Plan fixed before implementation; existing unrelated working-tree changes must be preserved.
- leaf 1.1 verified: ranked four-category payload and canonical `drilldown_parent_codes` module recomputation pass 19 adapter tests.
- leaf 1.2 verified: real Chromium proves the four popovers, native keyboard surfaces/Escape, single and Shift multi-selection, synchronized KPI/chart filtering, and clear restore.
- root 1 verified: both leaves reverified, 19 adapter tests and the focused Chromium integration oracle passed together, and touched-file diff checks are clean.
