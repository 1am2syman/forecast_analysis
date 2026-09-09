# Product filter multi-select screenshot validation

## Result

PASS for the Product filter UI scope.

## Viewport/state matrix

| State | 1280×720 | 1920×1080 |
| --- | --- | --- |
| Drawer closed in Overview context | `screenshots/01-drawer-closed-1280x720.png` | `screenshots/01-drawer-closed-1920x1080.png` |
| Drawer open, default scope | `screenshots/02-drawer-open-default-1280x720.png` | `screenshots/02-drawer-open-default-1920x1080.png` |
| Brand fuzzy query (`bbl`) with two selections | `screenshots/03-brand-fuzzy-two-selected-1280x720.png` | `screenshots/03-brand-fuzzy-two-selected-1920x1080.png` |
| SKU Class partial query (`unclass`) with selection | `screenshots/04-sku-search-selected-1280x720.png` | `screenshots/04-sku-search-selected-1920x1080.png` |
| Parent product code query (`3584`) with selection | `screenshots/05-parent-code-search-selected-1280x720.png` | `screenshots/05-parent-code-search-selected-1920x1080.png` |
| Compatible combined selection (`BPAR-ADV`, `Unclassified`, `703584`) | `screenshots/06-combined-product-selection-1280x720.png` | `screenshots/06-combined-product-selection-1920x1080.png` |
| Comparison mode: Product enabled, Performance disabled | `screenshots/07-comparison-product-enabled-1280x720.png` | `screenshots/07-comparison-product-enabled-1920x1080.png` |

All files have the exact dimensions encoded in their names.

## Assertions exercised

- Product group contains Brand, SKU Class, and Parent product controls.
- Global Horizon, Minimum actual, and Vintage A/B controls are absent.
- Brand fuzzy input tolerates the missing character in `bbl` and supports two checked selections.
- SKU Class partial input and Parent product partial-code input return selectable matches.
- Selected values stay pinned, summaries show the selection count, Clear all submits an empty array, and Escape closes only the popover and returns focus to its trigger.
- Canonical requests submit `brands`, `sku_classes`, and `parent_codes` arrays.
- Product triggers remain enabled in comparison mode while the Performance fieldset is disabled.
- Popovers remain inside the viewport, are not clipped by the drawer, and preserve the surrounding layout at both desktop targets.
- No console, page, network, or HTTP failures occurred during the Product filter checks.

## Visual review

### Improved

- Product filtering is now grouped under a clearly labeled Product column instead of global vintage-comparison controls.
- Searchable checked lists make multi-selection visible and reversible without expanding the permanent drawer height.
- The compact count summaries preserve the existing dense dashboard hierarchy.
- Removing Horizon and Minimum actual reduces the Primary column and makes the core product scope easier to scan.

### Regressed

None observed.

### Out of place

None observed. The popover overlays neighboring drawer columns at 1280×720 as expected for a transient menu, but remains fully visible and does not displace or clip controls. Compact trigger-label truncation is cosmetic; field labels and selected counts remain understandable.

## Known unrelated validation failures

The repository-wide exhaustive dashboard script still reports pre-existing/non-Product failures in product-history drill-down, revision rendering, CSV export discovery, and classification of existing timeline/vintage buttons. The Product filter checks and global console/network checks in that same run pass; see `exhaustive/validation-report.json`.
