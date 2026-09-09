# Interconnected Product filter screenshot validation

## Result

PASS for the interconnected Product-filter scope.

## Viewport/state matrix

| State | 1280×720 | 1920×1080 |
| --- | --- | --- |
| Default Product facets | `screenshots/01-default-product-facets-1280x720.png` | `screenshots/01-default-product-facets-1920x1080.png` |
| SKU Class A selected; Parent product list reduced to compatible products | `screenshots/02-class-a-parent-options-1280x720.png` | `screenshots/02-class-a-parent-options-1920x1080.png` |
| Parent 706059 selected; incompatible Brand values visible and disabled | `screenshots/03-parent-brand-disabled-1280x720.png` | `screenshots/03-parent-brand-disabled-1920x1080.png` |
| Parent 706059 selected; incompatible SKU Class values visible and disabled | `screenshots/04-parent-class-disabled-1280x720.png` | `screenshots/04-parent-class-disabled-1920x1080.png` |
| Source changed ML→TM; unavailable Brand removed with count feedback | `screenshots/05-source-removal-feedback-1280x720.png` | `screenshots/05-source-removal-feedback-1920x1080.png` |
| Comparison mode retains active Product faceting | `screenshots/06-comparison-product-facets-1280x720.png` | `screenshots/06-comparison-product-facets-1920x1080.png` |

All 12 screenshots have the exact dimensions encoded in their filenames.

## Assertions exercised

- Selecting SKU Class A reduces Parent product options to six compatible products, including 706059 and excluding 703584.
- Class A marks the ML-only Class C Brand `BBEL_LUP` unavailable.
- Selecting Parent product 706059 leaves `BPCNO-SP` enabled while disabling incompatible Brand values and SKU Classes B, C, and Unclassified.
- Clicking a disabled option does not alter the Product request or summary.
- Parent products are omitted rather than displayed as a long disabled list.
- Source ML→TM removes `BBEL_LUP`, restores the Brand summary to `All brands`, and displays `1 removed Brand selection`.
- Comparison mode keeps Product controls enabled while Performance controls remain disabled.
- Product-scope browser checks completed without console, page, network, or HTTP failures.

## Visual review

### Improved

- The Parent product list now reflects the selected SKU Class rather than presenting the full catalog.
- Disabled Brand and SKU Class values communicate reverse constraints without forcing users to infer why a combination is unavailable.
- Disabled values remain readable but visually subordinate to selectable values.
- Source-driven removal feedback is concise and identifies the affected field and count.

### Regressed

None observed.

### Out of place

None observed. Transient Product popovers overlap neighboring filter columns at 1280×720 as designed, but remain fully visible, aligned, and unclipped. The disabled treatment is consistent with the dashboard palette and remains distinguishable from selected values.

## Known unrelated validation failures

The repository-wide exhaustive dashboard script continues to report existing failures in product-history drill-down, revision rendering, CSV export discovery, and classification of pre-existing timeline/vintage buttons. The interconnected Product checks and global console/network checks pass in `exhaustive/validation-report.json`.
