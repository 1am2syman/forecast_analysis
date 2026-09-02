# Plan: forecast accuracy vintage selector

## Depth tree (requested depth 2)

- Root `node-1`: integrate a fixed latest forecast accuracy series with selectable historical comparison series.
  - Leaf `leaf-1.1`: browser data contract and adapter tests.
  - Leaf `leaf-1.2`: overview UI selector, chart rendering, interaction tests, and screenshot validation. Needs `leaf-1.1`.

## Shared contract

- `accuracy_vintages.latest` is the fixed latest-available series and never appears as a selectable checkbox.
- `accuracy_vintages.options` contains historical comparison series. `oldest_available` is first and selected by default; intermediate exact-horizon series follow in oldest-to-newest order.
- Selector changes are chart-local presentation state. They do not alter the shared dashboard population or KPI request.
- Empty optional selection is allowed; the fixed latest series remains visible.
- The selector sits immediately before the accuracy chart full-screen button and remains usable when that chart is full screen.
- Existing user modifications in touched files must be preserved.

## Ownership and dependencies

| ID | State | Needs | OWNS |
| --- | --- | --- | --- |
| leaf-1.1 | READY | — | `dashboard/adapter.py`, `tests/test_static_dashboard_adapter.py` |
| leaf-1.2 | WAITING | leaf-1.1 | `dashboard/app.js`, `dashboard/index.html`, `dashboard/styles.css`, `tests/test_forecast_analysis_dashboard_ui.py`, `scripts/validate_vintage_selector.mjs`, `validation-artifacts/vintage-selector/**` |
| node-1 | OPEN | leaf-1.1, leaf-1.2 | integration only |

## Toolchain

- Working directory: repository root.
- Shell: `/bin/sh`.
- Python checks: `uv run python -m unittest ...`.
- Browser checks: Node.js + Chromium against `dashboard.server`.
