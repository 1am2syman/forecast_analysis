# Dashboard instantaneous interaction implementation plan

## Shared contract

- Preserve all existing uncommitted dashboard work; edit on top of it and never reset/revert unrelated changes.
- Preserve analytical semantics: active population, weighted numerator/denominator metrics, missing/zero actual handling, hierarchy quality, revision tolerance, TM/ML exact-horizon comparison, exports, and product detail.
- Keep public behavior compatible unless a phase explicitly introduces an additive API.
- Use Polars grouped/vectorized operations for analytical aggregation; avoid Python loops that repeatedly filter DataFrames.
- Tests remain at public seams: analytical functions/dashboard view, `DashboardDataService`/HTTP responses, and real browser interaction. Add only focused regression tests.
- Runtime data is immutable for the process; caches must be bounded or version-scoped and concurrency-safe.
- Every phase uses Pi harness model `cliproxyapi/gpt-5.6-sol`, high effort, and is independently revalidated before the next phase starts.

## Depth tree

### leaf-1 — Phase 1 analytical hot path

State: READY

OWNS: `forecast_analysis/metrics.py`, `forecast_analysis/dashboard.py`, `forecast_analysis/comparison.py`, `tests/test_forecast_analysis_dashboard.py`, `scripts/benchmark_dashboard_performance.py`

Deliverable: vectorized brand/month metrics, consolidated monthly/horizon calculations, removal of duplicate pair computation, correctness regression coverage, and a reproducible benchmark.

Needs: none

### leaf-2 — Phase 2 service/API/caching

State: WAITING

OWNS: `dashboard/adapter.py`, `dashboard/server.py`, `tests/test_static_dashboard_adapter.py`, `tests/test_static_dashboard_server.py`, `scripts/benchmark_dashboard_performance.py`

Deliverable: additive modular dashboard payload API, version/request/module caching and request coalescing where useful, compact/prewarmed startup path, while preserving exports and old API compatibility needed during migration.

Needs: leaf-1 VERIFIED

### leaf-3 — Phase 3 browser interaction

State: WAITING

OWNS: `dashboard/app.js`, `dashboard/index.html`, `dashboard/styles.css`, `tests/test_forecast_analysis_dashboard_ui.py`, `scripts/validate_dashboard_functionality.mjs`, `scripts/validate_real_dashboard_ui.mjs`

Deliverable: immediate discrete filters, debounced numeric inputs, abort/coalesce stale requests, active-module/lazy rendering, retained-content updating state, and browser validation.

Needs: leaf-2 VERIFIED

### node-1 — Integration

State: OPEN

Children: leaf-1, leaf-2, leaf-3

Deliverable: focused Python regression suite, JS syntax and browser functionality validation, cold/cache performance measurement, and final diagnostics.
