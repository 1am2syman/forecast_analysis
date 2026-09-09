# Overview KPI cohort validation

## Screenshot matrix

| Viewport | Default (oldest) | Multiple incl. oldest | Multiple, promoted oldest | Single specific | Latest only |
| --- | --- | --- | --- | --- | --- |
| 1280×720 | `1280x720-default.png` | `1280x720-multiple-with-oldest.png` | `1280x720-multiple-promoted-oldest.png` | `1280x720-single-specific.png` | `1280x720-latest-only.png` |
| 1920×1080 | `1920x1080-default.png` | `1920x1080-multiple-with-oldest.png` | `1920x1080-multiple-promoted-oldest.png` | `1920x1080-single-specific.png` | `1920x1080-latest-only.png` |

## Assertions run

- Fixed latest series remains present exactly once.
- Default and multiple-with-oldest states use `oldest_available` (`M−5`) as the KPI primary.
- Removing the oldest selection promotes `specific_horizon:4` (`M−4`).
- A single selected historical vintage uses `specific_horizon:3` (`M−3`).
- No historical selection uses `latest_available` (`M−1`).
- Forecast accuracy, bias, WAPE, revision effectiveness, and accumulated error card values match the backend common-cohort projection.
- KPI captions identify the primary vintage.
- Chart paths, toolbar, and actions remain inside their containers; page horizontal overflow is zero.

Machine-readable results: `validation-report.json`.

## Categorical judgment

### Improved

- Every Overview KPI now changes with the same primary vintage and common parent-month cohort as the accuracy chart.
- KPI captions clearly show `M−5`, `M−4`, `M−3`, or `M−1`, making the selection rule visible.
- Latest-only revision effectiveness is explicitly unavailable rather than implying a historical-to-latest comparison.
- Both desktop sizes keep all seven KPI cards and both charts visible with coherent alignment and hierarchy.

### Regressed

None observed.

### Out of place

None observed. The transient “Shared population updated” toast does not obscure controls or chart data.

## Known unverified states

None. All required viewport/state cells were captured and inspected.
