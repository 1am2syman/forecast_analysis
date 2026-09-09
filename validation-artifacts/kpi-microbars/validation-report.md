# KPI microbars validation

## Screenshot matrix

| State | 1280×720 | 1920×1080 |
| --- | --- | --- |
| Default (oldest vintage selected) | `default-1280x720.png` | `default-1920x1080.png` |
| Latest only (no comparison vintage) | `latest-only-1280x720.png` | `latest-only-1920x1080.png` |
| Single specific vintage (M−3) | `single-specific-1280x720.png` | `single-specific-1920x1080.png` |
| Multiple vintages (oldest + M−3) | `multiple-vintages-1280x720.png` | `multiple-vintages-1920x1080.png` |

## Browser assertions

Validated at 1280×720 and 1920×1080:

- Four KPI microchart cards are present.
- All four cards have equal heights at each viewport.
- Header labels do not overlap the KPI figures.
- Help controls sit beneath the header labels.
- Microcharts remain inside card bounds.
- Microcharts contain no month-axis text.
- Bias includes a zero reference line.
- In the multiple-vintage state, all four charts show the same 12 eligible monthly observations.

## Visual review

### Improved

- Bias, WAPE, Revision effectiveness, and Error accumulated now expose individual monthly data points without increasing card height.
- KPI figures remain large and aligned at the upper-right.
- Help controls appear under the header rather than competing with the figure.
- Pastel bars are borderless, visually quiet, and anchored at the bottom of each card.
- Bias communicates positive and negative values around a subtle zero line.
- Responsive compact labels preserve the KPI row at 1280×720 without collisions.

### Regressed

None observed.

### Out of place

None observed.

## Known unverified states

None.
