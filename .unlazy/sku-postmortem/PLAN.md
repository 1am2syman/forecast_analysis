# SKU post-mortem build plan

## Depth tree

- [x] Data module: deepen product detail into one auditable post-mortem projection.
  - [x] Add target-month metrics, revision outcome points, peer benchmark, and deterministic commentary.
  - [x] Add focused unit/adapter tests.
- [x] UI module: replace Product History presentation with dashboard-native post-mortem sections.
  - [x] Add semantic markup for decision summary, metrics, commentary, peer benchmark, and treatment.
  - [x] Add renderers for current data and existing comparison sparkline semantics.
  - [x] Add dashboard-native styling and compact responsive layout.
- [x] Verification module: browser assertions and screenshot review.
  - [x] Validate product state, selected SKU, chart/ledger/commentary presence, and no overflow.
  - [x] Inspect 1440x900, 1680x1050, and 800x700 screenshots.

## Integration order

1. Add pure post-mortem derivation and tests.
2. Extend adapter payload.
3. Replace Product History markup and renderer.
4. Add styles.
5. Run targeted tests, browser checks, and screenshot inspection.
6. Commit only in this worktree; do not merge into the parent checkout.
