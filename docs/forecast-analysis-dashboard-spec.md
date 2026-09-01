# Forecast Analysis Dashboard Specification

**Status:** Approved for implementation  
**Primary artifact:** `artifacts/forecast_history/consolidated/forecast_history_waterfall.csv`  
**Dashboard runtime:** Marimo  
**Document purpose:** Product and technical specification for replacing the current oldest-versus-latest analysis with a source-aware forecast-performance dashboard.

## 1. Objective

Build an interactive dashboard that measures forecast accuracy, bias, revision effectiveness, and stability using the consolidated forecast-history artifact, cleaned product hierarchy, and monthly secondary-sales actuals.

The dashboard must:

1. consume the consolidated history directly rather than parse the original S&OP workbooks;
2. clean and validate the product hierarchy before analysis;
3. preserve TM and ML as separate forecast sources;
4. select forecast vintages independently within each source;
5. calculate volume-weighted metrics at the filtered population level;
6. support drill-down from the total business to brand, parent product, target month, horizon, source, and individual vintage;
7. expose coverage and data-quality problems instead of silently dropping them.

## 2. Scope

### 2.1 In scope

- Consolidated forecast-history ingestion.
- Product-hierarchy cleaning and diagnostics.
- Secondary-sales normalization.
- TM and ML source filtering and comparison.
- Vintage and forecast-horizon selection.
- Forecast-accuracy, bias, error, revision, stability, and coverage metrics.
- Interactive filters, KPI cards, charts, heatmaps, and exception tables.
- Download of the filtered analysis data.
- Automated tests for transformations and metric formulas.

### 2.2 Out of scope

- Rebuilding the upstream forecast-history ETL.
- Editing forecasts from the dashboard.
- Writing results back to source systems.
- Forecast generation or model training.
- User authentication and row-level permissions.
- Statistical causal claims about why a forecast changed.
- Treating TM and ML rows as interchangeable vintages.

## 3. Domain terminology

| Term | Definition |
| --- | --- |
| Target month | The month being forecast; represented by `snop_month`. |
| Calculation month | The month in which a forecast was produced. |
| Vintage | A forecast identified by source, parent product, target month, and calculation month. |
| Forecast source | The forecast family. The initial values are `tm` and `ml`. |
| Forecast horizon | Whole-month distance from calculation month to target month. |
| Oldest vintage | Earliest available calculation month within one source and product-target-month population. |
| Latest vintage | Latest available calculation month within one source and product-target-month population. |
| Parent product | Analysis entity identified by `parent_code`. |
| Brand | Cleaned `material_group_code` mapped from the product hierarchy. |
| Revision | Change between two selected vintages from the same source. |
| Comparable pair | Two selected vintages for the same source, parent product, and target month. |
| Forecast accuracy | Volume-weighted accuracy derived from absolute error and actual volume. |
| Bias | Signed forecast error relative to actual volume. |

## 4. Architectural decisions

### 4.1 Consolidated history is the analysis seam

The analysis must consume:

```text
artifacts/forecast_history/consolidated/forecast_history_waterfall.csv
```

It must not know how the upstream TM or ML files were parsed. Upstream ETL owns source extraction and consolidated-output validation. The dashboard owns downstream normalization, matching, metric calculation, filtering, and presentation.

### 4.2 Sources remain separate

TM and ML may have the same `parent_code`, `calculation_month`, and `snop_month`, but they represent different forecast families.

The dashboard must therefore:

- include `source` in every forecast key;
- select oldest/latest vintages independently per source;
- calculate source metrics independently;
- allow TM-versus-ML comparison only after aligning both sources to the same parent products, target months, and comparison horizon or vintage rule;
- never combine TM and ML quantities into one forecast total;
- never choose an oldest vintage from one source and a latest vintage from another.

### 4.3 Metrics use recomputed aggregate numerators

The dashboard must calculate metrics from the filtered detail rows. It must not average precomputed product, brand, or month percentages.

### 4.4 Data-quality states remain visible

Unmapped products, conflicting hierarchy records, missing actuals, zero actuals, and incomplete vintage pairs must be retained in quality diagnostics. Metric populations may exclude them according to the rules in this specification, but the dashboard must report the exclusions.

## 5. Desired data flow

```text
Consolidated forecast history ──► normalize history ──────┐
                                                         │
Product hierarchy ─────────────► clean hierarchy ────────┼──► analysis frame
                                                         │
Secondary-sales actuals ───────► aggregate actuals ──────┘
                                                                  │
                                                                  ▼
                                                        apply population filters
                                                                  │
                                                                  ▼
                                                    select source-specific vintages
                                                                  │
                                                                  ▼
                                                  calculate metrics and diagnostics
                                                                  │
                                                                  ▼
                                                         render dashboard views
```

## 6. Input contracts

### 6.1 Forecast-history input

Required columns:

| Column | Required type after normalization | Meaning |
| --- | ---: | --- |
| `calculation_month` | `Date` | First day of the calculation month. |
| `snop_month` | `Date` | First day of the target month. |
| `parent_code` | `Int64` | Parent-product identifier. |
| `parent_description` | `String` | Forecast-history product description. |
| `qty` | `Float64` | Forecast quantity in KL. |
| `source` | `String` | Forecast source, initially `tm` or `ml`. |

Canonical forecast grain:

```text
source × parent_code × calculation_month × snop_month
```

Required validation:

- all six columns exist;
- month values parse from `YYYY-MM` and normalize to first-of-month dates;
- `parent_code` is non-null `Int64`;
- `qty` is finite and non-negative;
- `source` is non-null and belongs to the configured source set;
- canonical forecast keys are unique;
- forecast horizon is non-negative;
- source is never discarded during grouping or joining.

Canonical output name:

```text
qty → forecast_kl
```

Derived field:

```text
forecast_horizon_months =
    12 × (snop_year − calculation_year)
    + (snop_month_number − calculation_month_number)
```

The current artifact supports different horizon ranges by source. Controls must be populated from available data rather than hard-coded.

### 6.2 Product-hierarchy input

Input path:

```text
artifacts/ph/PH_FG.xlsx
```

Required source columns:

| Source column | Canonical column |
| --- | --- |
| `material_code` | `parent_code` |
| `material_desc` | `hierarchy_description` |
| `material_group_code` | `brand` |

The source contains repeated material codes across plant or organizational records. Duplicate rows are expected; conflicting mappings are not.

Cleaning rules:

1. Select only required source columns before further processing.
2. Cast `material_code` to `Int64` without lossy conversion.
3. Trim leading and trailing whitespace from descriptions and brands.
4. Convert blank strings to null.
5. Normalize exact duplicate rows.
6. Group by `parent_code`.
7. If all non-null normalized brands agree, emit one hierarchy row.
8. If more than one normalized brand exists for a parent code, set `mapping_status = "conflict"`, leave canonical `brand` null, and emit a diagnostic containing the competing values.
9. If no usable brand exists, set `mapping_status = "unmapped"`.
10. Otherwise set `mapping_status = "mapped"`.
11. Use a deterministic description: prefer the single normalized value; when several descriptions exist, select the most frequent and break ties alphabetically.

Canonical hierarchy grain:

```text
one row per parent_code
```

Canonical hierarchy columns:

```text
parent_code
hierarchy_description
brand
mapping_status
```

Analysis display groups:

- mapped rows use their cleaned brand;
- missing mappings display as `Unmapped`;
- conflicting mappings display as `Hierarchy conflict`;
- quality panels retain the underlying status and diagnostic values.

### 6.3 Actual-sales input

Input directory:

```text
artifacts/secondary_sales/
```

The initial adapter supports the current workbook shape with the real header on row 6.

Required normalized source fields:

| Source field | Canonical field |
| --- | --- |
| `parent_material_code` | `parent_code` |
| `Month-Year` | `snop_month` |
| `sec_vol_kl_mth (billwise)` | `actual_kl` |

Cleaning rules:

1. Normalize column names before matching them.
2. Parse `Month-Year` to a first-of-month `Date`.
3. Cast `parent_code` to `Int64`.
4. Cast actual volume to finite `Float64`.
5. Aggregate bill-wise rows by `parent_code × snop_month`.
6. Preserve zero actuals as valid observations with special metric handling.
7. Reject negative actual volume unless an explicit business rule is added later.

Canonical actual grain:

```text
parent_code × snop_month
```

## 7. Canonical analysis frames

### 7.1 Long analysis frame

Join forecast history to actuals and hierarchy while preserving every forecast row.

Required columns:

```text
source
parent_code
parent_description
hierarchy_description
brand
mapping_status
calculation_month
snop_month
forecast_horizon_months
forecast_kl
actual_kl
actual_status
```

`actual_status` values:

- `matched_positive`: actual exists and is greater than zero;
- `matched_zero`: actual exists and equals zero;
- `missing`: no actual row exists.

### 7.2 Comparable-pair frame

When the user compares Vintage A and Vintage B, produce one row per:

```text
source × parent_code × snop_month
```

Required columns:

```text
source
parent_code
parent_description
brand
mapping_status
snop_month
actual_kl
vintage_a_rule
vintage_a_calculation_month
vintage_a_horizon_months
vintage_a_forecast_kl
vintage_b_rule
vintage_b_calculation_month
vintage_b_horizon_months
vintage_b_forecast_kl
pair_status
```

`pair_status` values:

- `complete`: both selected vintages exist;
- `missing_a`;
- `missing_b`;
- `missing_both`;
- `missing_actual`;
- `zero_actual`.

Revision metrics must use only `complete` pairs. Coverage views must include every pair status.

## 8. Vintage-selection rules

Each selected source has independent Vintage A and Vintage B controls.

Supported rules:

- `oldest_available`;
- `latest_available`;
- `specific_calculation_month`;
- `specific_horizon`.

Selection behavior:

### 8.1 Oldest available

Choose the minimum calculation month for each source, parent product, and target month after population filters but before metric aggregation.

### 8.2 Latest available

Choose the maximum calculation month for each source, parent product, and target month after population filters but before metric aggregation.

### 8.3 Specific calculation month

Choose the exact calculation month. Missing product-target combinations remain visible as incomplete coverage.

### 8.4 Specific horizon

Choose the exact `forecast_horizon_months`. Missing product-target combinations remain visible as incomplete coverage.

### 8.5 Default comparison

For a single selected source:

```text
Vintage A = oldest available
Vintage B = latest available
```

For TM-versus-ML source comparison, default to a common forecast horizon available in both selected populations. The initial preferred common horizon is one month ahead when available. The dashboard must not compare different horizons without displaying that mismatch prominently.

## 9. Metric definitions

All ratio metrics use the currently filtered, eligible detail rows.

Define:

```text
error_i = forecast_i − actual_i
absolute_error_i = |error_i|
```

### 9.1 Actual volume

```text
Actual KL = Σ actual_i
```

### 9.2 Forecast volume

```text
Forecast KL = Σ forecast_i
```

### 9.3 Absolute error

```text
Absolute Error KL = Σ |forecast_i − actual_i|
```

### 9.4 Net error

```text
Net Error KL = Σ(forecast_i − actual_i)
```

### 9.5 Forecast accuracy

```text
Forecast Accuracy % =
    [1 − Σ|forecast_i − actual_i| / Σactual_i] × 100
```

Rules:

- include only rows with positive actuals;
- return null when the eligible actual denominator is zero;
- do not cap negative values;
- do not average row-level or subgroup accuracy percentages.

### 9.6 Bias

```text
Bias % = Σ(forecast_i − actual_i) / Σactual_i × 100
```

Rules match forecast accuracy denominator handling.

### 9.7 Mean absolute error

```text
MAE KL = mean(|forecast_i − actual_i|)
```

Display observation count beside MAE.

### 9.8 Accuracy delta

For comparable Vintage A and Vintage B populations:

```text
Accuracy Delta pp = Forecast Accuracy B − Forecast Accuracy A
```

The unit is percentage points.

### 9.9 Error improvement

Per comparable row:

```text
Error Improvement KL =
    |Vintage A Forecast − Actual|
    − |Vintage B Forecast − Actual|
```

- positive means Vintage B improved the forecast;
- negative means Vintage B worsened it.

Aggregate error improvement:

```text
Σ Error Improvement KL
```

### 9.10 Revision amount

```text
Revision KL = Vintage B Forecast − Vintage A Forecast
```

```text
Revision % = Revision KL / Vintage A Forecast × 100
```

Revision percentage is null when Vintage A forecast equals zero.

### 9.11 Revision direction

Using a configurable absolute tolerance, default `0.01 KL`:

- `up` when revision is greater than tolerance;
- `down` when revision is less than negative tolerance;
- `unchanged` otherwise.

### 9.12 Revision outcome

Using the same tolerance on error improvement:

- `improved` when error improvement is greater than tolerance;
- `worsened` when error improvement is less than negative tolerance;
- `neutral` otherwise.

### 9.13 Revision effectiveness

```text
Revision Effectiveness % =
    improved revised rows / all materially revised rows × 100
```

Unchanged rows are excluded from the denominator.

### 9.14 Forecast stability

For each source, parent product, and target month across available vintages:

```text
Forecast Range KL = max(forecast_kl) − min(forecast_kl)
Forecast Volatility KL = population standard deviation(forecast_kl)
Revision Count = count of consecutive changes beyond tolerance
Maximum Revision KL = max absolute consecutive-vintage change
```

Stability metrics require at least two vintages. Otherwise they are null and the observation is marked insufficient history.

### 9.15 Parent vintage improvement score

The revision scatter contains one bubble per parent. Its evidence window is the
selected target-end month plus the preceding five target months, regardless of
the target-start control. A parent is eligible only when all six target months
have positive actuals and at least five forecast vintages; the five latest
vintages are used for each target month.

For each parent-target month, fit ordinary least-squares trends across vintage
indices `0..4`:

```text
Monthly Forecast Trend = slope(Forecast / Actual × 100)
Monthly Vintage Improvement = slope((1 − |Forecast − Actual| / Actual) × 100)
```

The forecast trend is percentage of actual per vintage. The vintage improvement
score is forecast-accuracy percentage points per vintage; positive improves and
negative degrades.

Retain each monthly trend as calculated, including seasonal extremes. The
parent bubble coordinates are the medians of the six monthly trends, preventing
one volatile month from dominating without capping seasonal products. The
six-month window, five vintages per month, 24 consecutive vintage changes, and
improving/degrading month counts remain available as evidence.

### 9.16 Coverage metrics

Required coverage indicators:

- forecast rows loaded;
- distinct source-parent-target combinations;
- distinct parent products;
- products mapped to a brand;
- products with hierarchy conflicts;
- products missing hierarchy mappings;
- product-target combinations matched to actuals;
- positive-actual combinations;
- zero-actual combinations;
- missing-actual combinations;
- complete Vintage A/B pairs;
- incomplete Vintage A/B pairs;
- actual-volume coverage percentage.

```text
Actual-volume coverage % =
    actual volume represented by eligible forecasts
    / total actual volume in the selected actual population
    × 100
```

## 10. Filters

Filters must update KPI cards, charts, tables, coverage counts, and downloads from one shared filtered population.

### 10.1 Primary filters

| Filter | Control | Default |
| --- | --- | --- |
| Forecast source | Multi-select: TM, ML | TM |
| Target month | Date range | Full matched range |
| Brand | Multi-select | All mapped brands plus quality groups |
| Parent product | Searchable multi-select by code and description | All |
| Forecast horizon | Multi-select populated from selected sources | All available |
| Vintage A | Rule selector with conditional value control | Oldest available |
| Vintage B | Rule selector with conditional value control | Latest available |
| Minimum actual volume | Numeric input | `0 KL` |

### 10.2 Performance filters

- over-forecast;
- under-forecast;
- within tolerance;
- revision direction: up, down, unchanged;
- revision outcome: improved, worsened, neutral;
- forecast-accuracy band;
- bias band;
- minimum absolute error;
- top N by actual volume, absolute error, or deterioration.

Performance filters that depend on Vintage A/B are disabled until a comparable pair exists.

### 10.3 Data-quality filters

Place in an expandable section:

- actual status;
- hierarchy mapping status;
- complete or incomplete vintage pair;
- zero actuals;
- zero forecasts;
- complete vintage history only;
- source availability: TM only, ML only, both sources.

### 10.4 Source-comparison rules

When more than one source is selected:

- the dashboard shows each source separately by default;
- charts use source as color, facet, or explicit series;
- KPI cards either display one card per source or a clearly labeled delta;
- source comparison requires an aligned horizon or aligned calculation-month rule;
- a warning appears when source populations differ;
- the dashboard displays the common matched population and source-specific coverage.

## 11. Dashboard views

### 11.1 Header and filter bar

Show:

- dashboard title;
- data refresh timestamp derived from input modification times;
- active forecast sources;
- compact primary filters;
- reset-filters action;
- expandable advanced and data-quality filters.

The primary filters include a monthly `SKU Class` selection. Classification is
calculated at national parent-product level from the six completed actual months
immediately preceding each target month. Parents are ranked by rolling actual KL
with `parent_code` as the deterministic tie-breaker. The parent crossing 70%
remains Class A, the parent crossing 90% remains Class B, and remaining positive
volume is Class C. Parents without positive rolling actuals are `Unclassified`.
When a target month is later than the latest actual month, the latest complete
classification snapshot is carried forward and its as-of month remains explicit.

### 11.2 KPI row

For each selected source or comparison mode, show:

1. Forecast Accuracy %;
2. Bias %;
3. Absolute Error KL;
4. Actual KL;
5. Forecast KL;
6. Coverage %;
7. Accuracy Delta pp when comparing vintages;
8. Revision Effectiveness % when comparing vintages.

Every KPI must include eligible observation count in its tooltip or subtitle.

### 11.3 Accuracy and bias over target month

Line chart:

- x: `snop_month`;
- y: selected metric;
- series: source and/or Vintage A/B;
- tooltip: source, target month, metric, actual KL, forecast KL, and count.

Metric toggle:

- forecast accuracy;
- bias;
- absolute error;
- forecast versus actual volume.

### 11.4 Accuracy by forecast horizon

Line or dot chart:

- x: `forecast_horizon_months`, sorted descending or labeled clearly from long-range to near-term;
- y: forecast accuracy or bias;
- series: source;
- include actual volume and observation count in tooltips.

This view must allow only like-for-like source comparison at the same horizon.

### 11.5 Brand × target-month heatmap

Rows: brand.  
Columns: target month.  
Metric toggle:

- Vintage B forecast accuracy;
- Vintage A forecast accuracy;
- accuracy delta;
- bias;
- absolute error;
- revision effectiveness.

Defaults:

- sort brands by worst selected performance metric;
- include `All brands`, `Unmapped`, and `Hierarchy conflict` rows where applicable;
- use diverging scales for signed metrics and sequential scales for magnitude metrics.

### 11.6 Revision-effectiveness view

Show:

- improved, worsened, neutral, and unchanged counts;
- revised-up and revised-down percentages;
- total error improvement KL;
- latest six target months ending at the maximum selected actual month as independent bands, excluding forecast-only future months, each containing an angular forecast-revision path;
- shared delta-percent y-axis indexed to each target month's oldest forecast;
- one endpoint rectangle for the latest vintage and no start marker;
- color each within-month segment green, red, or gray based on whether that revision improved, worsened, or did not materially change forecast accuracy;
- keep the net forecast-accuracy result in the endpoint tooltip rather than adding labels under the month bands;
- provide a full-screen revision-path view with the same segment and endpoint tooltips;
- fixed product cohort per target month so changing coverage does not create false oscillation;
- parent-deduplicated scatter anchored to the selected target-end month;
- six target months and five vintages per target month for every eligible parent;
- x-axis: median normalized forecast trend across vintages;
- y-axis: robust vintage improvement score in forecast-accuracy pp per vintage;
- six-month median aggregation with seasonal extremes retained;
- point size by six-month actual volume;
- color by improvement, degradation, or neutral outcome;
- a chart-local SKU Class filter whose available values are limited by the active global filter;
- exclude all SKUs in the super-seasonal PA Bodylot (`PA-BDYLOT`), JFB Powder (`JFB_POWDR`), RK Cooling (`RK_CLO_R` and `RK_CLO_S`), Saff Honey (`SAF_HONEY`), and SP Petroleum Jelly (`BPA_PET_J`) brands;
- exclude PCNO EJ SKUs whose parent description contains both `PCNO` and `EJ`, with all exclusions displayed in the chart header.

### 11.7 Source comparison

When TM and ML are selected at an aligned horizon, show:

- TM accuracy, ML accuracy, and delta;
- TM bias, ML bias, and delta;
- common-population count;
- TM-only and ML-only coverage counts;
- paired scatter of TM error versus ML error;
- winner classification per product-target month: TM better, ML better, tie.

Source winner is determined by lower absolute error on the common population, using the revision tolerance for ties.

### 11.8 Product detail

Selecting a parent product opens or updates a detail section containing:

- product code and descriptions;
- cleaned brand and mapping status;
- target-month selector;
- chronological vintage lines for TM and ML;
- actual-volume reference line;
- forecast horizon labels;
- consecutive revision table;
- source-specific error and bias.

### 11.9 Exceptions table

Required columns:

```text
source
parent_code
parent_description
brand
snop_month
actual_kl
vintage_a_calculation_month
vintage_a_forecast_kl
vintage_b_calculation_month
vintage_b_forecast_kl
absolute_error_b_kl
bias_b_kl
revision_kl
error_improvement_kl
revision_direction
revision_outcome
pair_status
mapping_status
```

Features:

- sortable columns;
- text search;
- configurable top N;
- default sort by largest Vintage B absolute error;
- download exactly the currently filtered rows.

### 11.10 Data-quality panel

Show counts and downloadable exception tables for:

- hierarchy conflicts;
- unmapped products;
- missing actuals;
- zero actuals;
- incomplete vintage pairs;
- invalid or rejected input rows;
- source population mismatches.

## 12. Visual and interaction requirements

- Use consistent source colors across every view.
- Use consistent Vintage A and Vintage B colors within a source.
- Display units explicitly: `%`, `pp`, `KL`, count, or months.
- Signed metrics must include a visible zero reference.
- Negative forecast accuracy must remain visible.
- Tooltips must expose numerator, denominator, and count where practical.
- Empty selections show a clear empty state, not an exception trace.
- Expensive transformations should be centralized and reused by reactive cells.
- Filtering one view must not silently use a different population in another view.
- A visible population summary must state selected sources, date range, products, actual volume, and comparable-pair count.

## 13. Error and empty-state behavior

### 13.1 Blocking input errors

Stop dashboard construction and display a clear error when:

- a required input file is missing;
- a required column is missing;
- forecast canonical keys are duplicated;
- dates cannot be normalized;
- forecast or actual values violate numeric invariants;
- an unknown source appears without configuration.

### 13.2 Non-blocking quality issues

Continue with diagnostics when:

- hierarchy mapping is missing;
- hierarchy values conflict;
- actuals are missing;
- selected vintage pairs are incomplete;
- a source lacks a requested horizon;
- a metric denominator is zero.

### 13.3 Metric empty state

When no eligible rows remain:

- KPI value displays `—`;
- subtitle explains why, such as `No positive actuals in selection`;
- charts display a matching empty-state message;
- coverage counts remain available.

## 14. Proposed module structure

```text
forecast_analysis/
├── __init__.py
├── contracts.py             # canonical columns, enums, result dataclasses
├── forecast_history.py      # load and normalize consolidated history
├── hierarchy.py             # PH cleaning and diagnostics
├── actuals.py               # actual-sales adapter and aggregation
├── analysis_frame.py        # joins, horizons, statuses, population construction
├── vintages.py              # source-aware vintage selection and pair construction
├── metrics.py               # pure aggregate and row-level metrics
├── filters.py               # filter-state application
└── diagnostics.py           # coverage and quality summaries

forecast_accuracy_app.py     # Marimo presentation and interactions
tests/
├── test_forecast_history_analysis.py
├── test_hierarchy_cleaning.py
├── test_actuals_normalization.py
├── test_vintage_selection.py
├── test_forecast_metrics.py
└── test_dashboard_population.py
```

The analysis modules must not import Marimo or Altair. The dashboard imports the analysis modules and owns presentation only.

## 15. Core module interfaces

Names may change during implementation, but the interface shape must remain small.

```python
@dataclass(frozen=True)
class AnalysisInputs:
    forecast_history: pl.DataFrame
    hierarchy: pl.DataFrame
    actuals: pl.DataFrame


@dataclass(frozen=True)
class AnalysisDataset:
    frame: pl.DataFrame
    diagnostics: pl.DataFrame


def load_analysis_inputs(
    forecast_history_path: Path,
    hierarchy_path: Path,
    actuals_path: Path,
) -> AnalysisInputs: ...


def build_analysis_dataset(inputs: AnalysisInputs) -> AnalysisDataset: ...


def select_vintage_pair(
    frame: pl.DataFrame,
    source: str,
    vintage_a: VintageRule,
    vintage_b: VintageRule,
) -> pl.DataFrame: ...


def calculate_metrics(frame: pl.DataFrame) -> MetricSummary: ...
```

Pure transformation functions must accept frames and return frames or typed result objects. File access remains in input adapters.

## 16. Testing requirements

### 16.1 Forecast-history tests

- six-column input normalizes to canonical types;
- source remains in the uniqueness key;
- duplicate keys within a source fail;
- identical keys across TM and ML remain valid separate rows;
- horizon calculation handles year boundaries;
- unknown sources fail clearly.

### 16.2 Hierarchy tests

- exact duplicates collapse;
- plant-level duplicates with the same brand collapse;
- whitespace and blanks normalize;
- conflicting brands produce conflict diagnostics;
- missing brands produce unmapped status;
- description choice is deterministic.

### 16.3 Actuals tests

- bill-wise rows aggregate correctly;
- dates normalize correctly;
- zero actuals remain present;
- missing and negative values follow the specified behavior.

### 16.4 Vintage tests

- oldest/latest selection is independent per source;
- specific month and horizon selection preserve missing coverage;
- TM and ML are never mixed in one pair;
- incomplete pairs receive the correct status;
- filters do not incorrectly redefine vintage order.

### 16.5 Metric tests

- forecast accuracy uses aggregate absolute error;
- subgroup percentages are not averaged;
- bias preserves sign;
- negative accuracy remains negative;
- zero denominators return null;
- accuracy delta uses percentage points;
- revision direction and outcome respect tolerance;
- stability metrics use chronological consecutive vintages.

### 16.6 Population tests

- every dashboard view receives the same filtered population;
- source comparisons use the common population;
- source-only coverage remains visible;
- quality filters affect downloads consistently.

## 17. Acceptance criteria

### AC1 — Consolidated-history adoption

The dashboard reads `forecast_history_waterfall.csv`, requires the six-column contract, renames `qty` to `forecast_kl`, derives forecast horizon, and does not read the 16 raw S&OP grids.

### AC2 — Source isolation

TM and ML are selectable and comparable, but vintage selection and metric calculation remain source-specific. No metric sums TM and ML forecast quantities together.

### AC3 — Clean hierarchy

The PH adapter emits one row per parent code, collapses agreeing duplicates, identifies missing mappings, and visibly reports conflicting brand mappings.

### AC4 — Canonical actuals

Secondary-sales rows are normalized and aggregated to one row per parent product and target month.

### AC5 — Correct vintage selection

Oldest, latest, specific calculation month, and specific horizon produce deterministic source-aware selections with explicit incomplete-pair statuses.

### AC6 — Correct metrics

Forecast accuracy, bias, absolute error, revision amount, error improvement, revision effectiveness, stability, and coverage match hand-calculated fixtures.

### AC7 — Required filters

The dashboard provides source, target month, brand, parent product, horizon, Vintage A, Vintage B, minimum actual volume, revision direction, revision outcome, and data-quality filters.

### AC8 — Required views

The dashboard provides KPI cards, monthly performance, horizon performance, brand-month heatmap, revision effectiveness, source comparison, product detail, exceptions table, and data-quality panel.

### AC9 — Population transparency

Every view updates from the same selected population, and the dashboard displays eligible row count, comparable-pair count, actual volume, and coverage.

### AC10 — Safe empty states

Selections with no eligible metric rows render explanatory empty states while retaining coverage and quality diagnostics.

### AC11 — Download fidelity

The dashboard download contains exactly the rows represented by the active filters and selected vintage rules.

### AC12 — Verification

All analysis tests, Python diagnostics, and `marimo check forecast_accuracy_app.py` pass before the implementation is considered complete.

## 18. Delivery sequence

### Phase 1 — Data foundation

- Implement canonical contracts and adapters.
- Clean PH and actuals.
- Build the long analysis frame and diagnostics.
- Add unit tests.

Completion criterion: validated canonical analysis frame exists for both TM and ML with visible coverage counts.

### Phase 2 — Vintage and metric engine

- Implement source-aware vintage rules.
- Build comparable-pair frames.
- Implement core, revision, stability, and coverage metrics.
- Add hand-calculated metric fixtures.

Completion criterion: all metric and vintage tests pass without Marimo involvement.

### Phase 3 — Dashboard MVP

- Add primary filters and KPI cards.
- Add monthly trend, horizon chart, brand heatmap, revision view, and exceptions table.
- Add filtered download and empty states.

Completion criterion: AC1 through AC7 and AC9 through AC12 pass.

### Phase 4 — Comparison and drill-down

- Add aligned TM-versus-ML comparison.
- Add product-detail history.
- Add full data-quality panel and advanced filters.

Completion criterion: all acceptance criteria pass.

## 19. Default dashboard state

On first load:

```text
Source: TM
Target months: full matched range
Brands: all
Products: all
Forecast horizons: all available
Vintage A: oldest available
Vintage B: latest available
Minimum actual volume: 0 KL
Revision filters: all
Data-quality population: metric-eligible rows, with exclusions summarized
```

Users can then switch to ML or select TM and ML for an aligned source comparison.

## 20. Definition of done

The feature is complete when:

- all acceptance criteria pass;
- analysis logic is isolated from Marimo presentation;
- formulas are tested against small hand-calculated datasets;
- TM and ML remain source-safe throughout the pipeline;
- hierarchy and coverage problems are visible;
- the dashboard can reproduce oldest-versus-latest analysis and additionally analyze fixed horizons and TM-versus-ML performance;
- no tracked generated artifact changes unexpectedly during dashboard execution;
- the specification and implemented behavior agree.
