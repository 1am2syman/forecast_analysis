# Ticket 01 — Forecast dashboard visual baseline and overflow oracle

**Scope:** baseline and measurement harness only. `forecast_accuracy_app.py` and the analytical modules were not changed.

**Harness artifact:** `forecast-analysis-dashboard-ui-baseline.json`

## Immutable before-state

The expanded before-state remains preserved at:

- `validation-artifacts/forecast-analysis-dashboard-long-full.png`
- Capture date recorded in the artifact: **2026-08-26**
- Dimensions: **6650 × 11082 px**
- SHA256: `29cd5651eadfec811b1c0671786f4a807dc846e1c59f9b5bddfab17e7261dfdd`

The baseline verifier recomputes the PNG dimensions and SHA256; it does not trust copied metadata.

## Deterministic analytical state

The browser evidence records the default TM state:

- View mode: `Single source`
- Source: `TM`
- Target range: full available range, `2025-05-01` → `2026-12-01`
- Brand and parent product: all available TM values
- Horizons: all available TM horizons
- Vintage A: `Oldest available`
- Vintage B: `Latest available`
- Minimum actual volume: `0 KL`
- Performance and quality filters: all/default values
- Quality detail: collapsed in the default capture and open in the expanded capture

The browser route was `http://127.0.0.1:8765/`, at a `1280 × 800` viewport with device pixel ratio `1`.

Raw state and normalization evidence are checked in beside the summary artifact:

- `forecast-analysis-dashboard-ui-raw-default.json`
- `forecast-analysis-dashboard-ui-raw-expanded.json`
- `forecast-analysis-dashboard-ui-normalization-default.json`
- `forecast-analysis-dashboard-ui-normalization-expanded.json`

All four raw evidence files share one capture execution and browser session. The validator binds each normalization record to its source state and screenshot.

## Independent overflow measurements

The oracle uses an inclusive **2 px tolerance** and evaluates the document and Marimo application container independently.

| Capture phase | Container | Client width | Scroll width | Overflow | Result |
| --- | --- | ---: | ---: | ---: | --- |
| Pre-normalization | document | 1280 | 1280 | 0 px | pass |
| Pre-normalization | `#App` | 1280 | 2000 | 720 px | **overflow** |
| Normalized full-page | document | 1280 | 6650 | 5370 px | **overflow** |
| Normalized full-page | `#App` | 6650 | 6650 | 0 px | pass |

This records both baseline failure modes without collapsing them into one measurement: before normalization, the internal Marimo application overflows; after normalization, the document exposes the full 6650 px baseline width needed for the genuine full-content screenshot.

The normalized expanded measurement records a document height of `11186 px` and an application height of `11186 px`; the default normalized measurement is `11082 px`. The expanded height includes the open **Data-quality filters** disclosure. The full-page screenshots are checked against their recomputed PNG dimensions rather than being treated as viewport screenshots.

## Captured artifacts

| State | Artifact | Dimensions | SHA256 |
| --- | --- | ---: | --- |
| Default analytical state | `forecast-analysis-dashboard-default.png` | 6650 × 11082 | `50290e0b328da578717d60c4fea2e6e2abaf39a6fc203c19d76d984147f84fe1` |
| Expanded audit state | `forecast-analysis-dashboard-expanded.png` | 6650 × 11186 | `02131ea641894398e066800cccc0c43b2cf71e39b539bcd1e70f7d31f844e745` |
| Immutable before-state | `forecast-analysis-dashboard-long-full.png` | 6650 × 11082 | `29cd5651eadfec811b1c0671786f4a807dc846e1c59f9b5bddfab17e7261dfdd` |

Both new captures were produced with the native browser session after Marimo full-page normalization (`marimo-full-page-normalization-v1`). The expanded image contains the open quality-filter region and reaches the lower quality and exception sections, providing full-content evidence rather than only the initial viewport.

## Verification commands

```text
uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-baseline --root . --artifact validation-artifacts/forecast-analysis-dashboard-long-full.png --expected-width 6650 --expected-height 11082
# baseline verification passed

uv run python scripts/validate_forecast_analysis_dashboard_ui.py verify-capture --root . --artifact validation-artifacts/forecast-analysis-dashboard-ui-baseline.json --require-normalized
# capture verification passed

uv run python -m unittest tests.test_forecast_analysis_dashboard_ui
# Ran 7 tests ... OK
# UI validation logic tests passed
```

The focused tests include an overflowing positive control, inclusive tolerance behavior, reverse cases proving document/application results remain independent, live-control state checks, disclosure-state checks, raw-evidence binding, and screenshot identity/dimension checks.

## Ticket 01 decision

**Complete.** The immutable visual reference, deterministic default state, Marimo normalization contract, screenshot metadata, disclosure transition evidence, and independent overflow oracle are reproducible. The recorded overflow is intentionally the current before-state evidence; fixing the dashboard layout belongs to later UI-fixup tickets.
