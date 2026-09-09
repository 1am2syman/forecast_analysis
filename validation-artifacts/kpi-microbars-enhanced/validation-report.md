# Enhanced KPI microbars validation

## Change scope

Bias, WAPE, Revision effectiveness, and Error accumulated cards on the Overview tab.

- Removed the bottom padding beneath each microchart.
- Increased microchart height from 27px to 32px.
- Increased bar color strength and opacity while retaining pastel tones.
- Increased KPI figures to 20px at full desktop width and 18px at 1280px.
- Card dimensions and the existing header/help arrangement remain unchanged.

## Screenshot matrix

| State | 1280×720 | 1920×1080 |
| --- | --- | --- |
| Default (oldest vintage selected) | `default-1280x720.png` | `default-1920x1080.png` |
| Latest only (no comparison vintage) | `latest-only-1280x720.png` | `latest-only-1920x1080.png` |
| Single specific vintage (M−3) | `single-specific-1280x720.png` | `single-specific-1920x1080.png` |
| Multiple vintages (oldest + M−3) | `multiple-vintages-1280x720.png` | `multiple-vintages-1920x1080.png` |

Previous screenshots for visual comparison remain in `validation-artifacts/kpi-microbars/`.

## Browser assertions

Assertion artifacts:

- `assertions-1280x720.json`
- `assertions-1920x1080.json`

Passed at both supported desktop targets:

- Four KPI microchart cards are present and have equal heights.
- Microcharts are 32px tall and finish 1px from the card edge (the card border only).
- KPI values are at least 18px at 1280×720 and 20px at 1920×1080.
- Standard bars use at least 0.62 opacity; latest bars use 0.96 opacity.
- Header labels do not overlap KPI figures.
- Help controls remain beneath header labels.
- Microcharts remain within card bounds and contain no month-axis text.
- Bias retains its zero reference line.
- The multiple-vintage state renders 12 bars in each of the four cards.

## Visual review

### Improved

- The empty strip under the microbars is gone; only the 1px card border remains.
- Taller bars use the reclaimed vertical space and are easier to compare.
- Stronger teal, blue, amber, and signed-bias shades are more noticeable without becoming visually heavy.
- Larger KPI figures improve hierarchy while remaining aligned at the upper-right.
- The treatment is consistent across all four microbar cards.

### Regressed

None observed.

### Out of place

None observed.

## Known unverified states

None.
