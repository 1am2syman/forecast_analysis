# Static dashboard real-data integration plan

## Architectural seam

`forecast_analysis/` remains the analytical core. A new `dashboard.adapter` module exposes a small browser-facing interface:

1. load the canonical dataset once;
2. advertise valid filter options and defaults;
3. validate a browser request into `DashboardFilters` and `VintageRule` values;
4. call `build_dashboard_view()` and `build_product_detail()`;
5. normalize Polars/date/metric objects into bounded JSON payloads;
6. serialize the exact active exception and quality frames to CSV from the same validated request.

`dashboard.server` is a stdlib HTTP adapter around that module. It serves the existing dependency-light shell and endpoints for health/bootstrap, view recomputation, product detail, and request-bound CSV download. The browser never reimplements metric formulas.

## Implementation sequence

1. **Contract and fixtures**
   - Define request/default/filter-option and payload shapes.
   - Add adapter tests against canonical artifacts and focused invalid/empty requests.
2. **Data adapter**
   - Add robust JSON normalization, bounded table/chart projections, request validation, vintage-rule construction, and bounded view caching.
3. **HTTP adapter**
   - Load inputs once at process startup.
   - Serve static assets safely, JSON endpoints with structured errors, CSV with content disposition, and no-store data responses.
4. **Browser binding**
   - Replace synthetic-state controls with real options.
   - Recompute all tabs from one shared request.
   - Render KPIs, SVG trends/scatters/history, quality statuses/exceptions, and exact-scope tables.
   - Preserve tab keyboard behavior, fixed viewport, internal bounded content, loading/error/empty states, and hash routing.
5. **Verification**
   - Unit-test real canonical values and request semantics.
   - Exercise the HTTP process and CSV fidelity.
   - Run browser validation over desktop, short, and narrow viewports.
   - Run LSP/pi-lens diagnostics and publish using `preview`.

## Failure policy

- Missing/invalid source files block server startup with a clear fatal message.
- Invalid filter requests return HTTP 400 with field-specific JSON diagnostics.
- Valid empty populations return HTTP 200 with explicit empty-state payloads.
- Comparison alignment failures return a blocked comparison payload while preserving quality and coverage evidence.
- Downloads rebuild from the submitted validated filter request, so CSV scope cannot drift from the visible analytical contract.
