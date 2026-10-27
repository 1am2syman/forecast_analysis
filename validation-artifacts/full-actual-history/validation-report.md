# Full actual history dashboard validation

**Status:** COMPLETE — all eight required screenshot cells are present, valid, and visually inspected. No visual regression or out-of-place content was observed. Runtime-state caveats are listed below.

## Scope

- Repository: `/root/GitHub/forecast_analysis`
- Branch / HEAD: `feat/static-html-dashboard` / `46be28b8a4ad209d3fd3be8ea222fa4567236352`
- Dashboard state: Product history (`#history`), parent code `706059`, `PCNO 100ml FT BOT NEW PB`
- Reviewed scope: `validation-artifacts/full-actual-history/**` only. No application, source, or test files were edited.
- The worktree already contained 25 modified tracked files, 87 untracked files, and no staged files; those pre-existing changes were not used as screenshot evidence.

## Viewport/state matrix

All eight image files are non-empty RGB PNGs. The normal screenshots show Product history selected; fullscreen screenshots show the corresponding chart-analysis overlay for parent `706059`.

| Viewport | State | Screenshot | Dimensions / bytes | State evidence | Result |
|---|---|---|---:|---|---|
| 1280×720 | FY comparison · normal | `validation-artifacts/full-actual-history/1280_fy_comparison_normal.png` | 1280×720 / 187,311 | Visual confirmation; `browser-assertions-manual.json` confirms `#history`, FY layout, parent 706059, no horizontal overflow | Pass |
| 1280×720 | FY comparison · fullscreen | `validation-artifacts/full-actual-history/1280_fy_comparison_fullscreen.png` | 1280×720 / 160,880 | Visual confirmation; no dedicated 1280 state JSON | Pass, runtime caveat |
| 1280×720 | Long horizon · normal | `validation-artifacts/full-actual-history/1280_long_horizon_normal.png` | 1280×720 / 187,063 | Visual confirmation; no dedicated state JSON | Pass, runtime caveat |
| 1280×720 | Long horizon · fullscreen | `validation-artifacts/full-actual-history/1280_long_horizon_fullscreen.png` | 1280×720 / 166,068 | Visual confirmation; no dedicated 1280 state JSON | Pass, runtime caveat |
| 1920×1080 | FY comparison · normal | `validation-artifacts/full-actual-history/1920_fy_comparison_normal.png` | 1920×1080 / 263,555 | `state-1920-fy-normal.json`: parent 706059, FY overlay true, fullscreen false, no overflow | Pass |
| 1920×1080 | FY comparison · fullscreen | `validation-artifacts/full-actual-history/1920_fy_comparison_fullscreen.png` | 1920×1080 / 266,888 | `state-1920-fy-fullscreen.json`: parent 706059, FY overlay true, fullscreen true, no overflow/outside elements | Pass |
| 1920×1080 | Long horizon · normal | `validation-artifacts/full-actual-history/1920_long_horizon_normal.png` | 1920×1080 / 268,842 | `state-1920-long-normal.json`: parent 706059, Long horizon true, fullscreen false, no overflow | Pass |
| 1920×1080 | Long horizon · fullscreen | `validation-artifacts/full-actual-history/1920_long_horizon_fullscreen.png` | 1920×1080 / 279,590 | `state-1920-long-fullscreen.json`: parent 706059, Long horizon true, fullscreen true, no overflow/outside elements | Pass |

Contact sheet reviewed: `validation-artifacts/full-actual-history/matrix-contact-sheet.png`.

## Assertions and data evidence

`api-assertions.json` reports `all_passed: true`; its checks all passed:

- Selected parent: expected and actual `706059`.
- Actual history begins `2021-04-01`.
- No negative `actual_kl` values; negative row list is empty.
- Completed-month cutoff: actuals end `2026-08-01`; the `2026-09-01` row has `actual_kl: null`, `actual_status: missing`, and forecast data only.
- Multiple fiscal years render: FY2022–FY2027 (six years).
- Full chronology is contiguous for 69 monthly rows from `2021-04-01` through `2026-12-01`.

An independent read of `product-706059.json` confirmed the same parent, 65 actual rows, no negative actuals, contiguous chronology, and September 2026 excluded from actuals.

`browser-assertions-manual.json` passed and recorded:

- `#history`, selected detail parent `706059`, summary `706059 · PCNO 100ml FT BOT NEW PB`.
- Actual begin/through, chronology, fiscal-year list, September cutoff, and empty negative-actual list.
- No body/document horizontal overflow.

Network verification:

- `network-requests.json`: 30 recorded requests, all HTTP 200.
- `product-module.har`: 15 entries, all HTTP 200; the selected product request uses `product_parent_code: 706059`.
- Hash/size references for `bootstrap.json` and `product-706059.json` in `api-assertions.json` match the files on disk.

## Visual classifications

- **Improved:** None observed as a before/after delta; no before screenshots were supplied. The requested complete history and forecast-tail behavior is visibly present in every chart state.
- **Regressed:** None observed. Headers, Product history navigation, product identity, chart controls, chart/table content, footer, and fullscreen boundaries remain coherent across the matrix.
- **Out of place:** None observed. Any visible chart tooltip in the 1280 fullscreen captures is contained within the chart and corresponds to the active chart state; no foreign overlay, clipping, or stray viewport content was observed.

## Known unverified states

- No dedicated state JSON was captured for the three remaining 1280 cells (FY fullscreen, Long normal, Long fullscreen). Their dimensions and visual states are verified, but their exact runtime parent/mode/fullscreen/overflow state is not independently asserted in JSON.
- The manual 1280 assertion records a browser viewport of 1280×577, while the supplied screenshot is 1280×720; exact 720px runtime geometry is therefore unverified even though the PNG dimensions are correct.
- No before-image baseline, browser-console log, or non-empty `subagent.log` was supplied, so relative improvement and console-silence claims remain unverified.
