# ML Forecast History Integration Plan

## Objective

Extend the existing forecast-history ETL so that the consolidated waterfall contains both forecast sources:

- Existing S&OP grid history: `source = "tm"`
- ML history from `artifacts/ml_history/forecast_history_ml.xlsx`: `source = "ml"`

The ETL will continue to write:

`artifacts/forecast_history/consolidated/forecast_history_waterfall.csv`

The target output contract is:

| Column | Type / format | Meaning |
| --- | --- | --- |
| `calculation_month` | `YYYY-MM` | Month in which the forecast vintage was produced |
| `snop_month` | `YYYY-MM` | Month being forecast |
| `parent_code` | integer | Parent product identifier |
| `parent_description` | string | Parent product description |
| `qty` | float | Forecast volume |
| `source` | `tm` or `ml` | Forecast-producing process |

## Workbook study

### File structure

- File: `artifacts/ml_history/forecast_history_ml.xlsx`
- Sheet: `data`
- Rows: 7,520 data rows
- Columns: 17
- Products: 101 parent codes
- Forecast horizons: `M+1` through `M+5`
- Inferred calculation vintages: April 2025 through July 2026, 16 continuous months
- Target months: May 2025 through December 2026
- Nulls in required mapping fields: none
- Duplicate `(KEY, MONTH_DATE, PREDICTING_MONTH)` records: none

### Relevant ML fields

| ML workbook field | Target field / use |
| --- | --- |
| `KEY` | `parent_code` |
| `DESCRIPTION` | `parent_description` |
| `MONTH_DATE` | `snop_month` |
| `TRAIN_TILL` | Base month used to derive `calculation_month` by adding one month |
| `PREDICTING_MONTH` | Validation of the interval between `calculation_month` and `snop_month` |
| `PRED_VOLUME` | `qty` |
| `Cal_forecast` | Optional validation/reference only; not written |
| `Oth_Ch_Contr._%` | Validation input for a supplied `Cal_forecast`; not written |

### Confirmed quantity choice

Use `PRED_VOLUME` as the ML `qty` value.

`PRED_VOLUME` is the authoritative model forecast. When `Cal_forecast` is supplied, retain it only as optional reference data and validate the workbook formula:

```text
Cal_forecast = PRED_VOLUME / (1 - Oth_Ch_Contr._%)
```

The current workbook contains `Cal_forecast` for all 7,520 rows, and the formula matches with zero numerical difference. The optional reference total is approximately 213,264.72, while the authoritative `PRED_VOLUME` total written as ML `qty` is approximately 192,541.91.

### Month derivation

Use the workbook's explicit date fields as the authoritative source:

```text
snop_month = MONTH_DATE
calculation_month = TRAIN_TILL + 1 month
```

Examples:

```text
MONTH_DATE=2025-05-01, TRAIN_TILL=2025-03-01 -> snop_month=2025-05, calculation_month=2025-04
MONTH_DATE=2025-09-01, TRAIN_TILL=2025-03-01 -> snop_month=2025-09, calculation_month=2025-04
```

`PREDICTING_MONTH` is not the source of either date. It is a validation field. After deriving the dates above, the ETL should confirm that the month interval from `calculation_month` to `snop_month` matches `M+1` through `M+5`.

All 7,520 current rows satisfy both the authoritative date rule and the horizon cross-check.

### Compatibility with TM history

- Current TM output: 8,515 rows and 141 parent codes.
- ML input: 7,520 rows and 101 parent codes.
- Parent-code overlap: 99.
- ML-only parent codes: 2 (`726858`, `726865`).
- TM-only parent codes: 42.
- Descriptions match exactly for all 99 overlapping parent codes.
- There are 5,113 overlapping `(parent_code, calculation_month, snop_month)` combinations. These are expected and must remain as separate rows because their `source` values differ.
- Expected combined output size with the current inputs: 16,035 rows.

## Implementation design

### 1. Add explicit ML input configuration

In `forecast_history_etl.py`, add a constant for:

```text
artifacts/ml_history/forecast_history_ml.xlsx
```

Keep the current TM source directory and consolidated output path unchanged.

### 2. Add a focused ML normalization helper

Add a helper such as `parse_ml_history(path)` that:

1. Requires the workbook to exist.
2. Reads only the `data` sheet with the Calamine engine.
3. Verifies that the required source columns exist.
4. Sets `snop_month` directly from `MONTH_DATE`.
5. Derives `calculation_month` by adding one month to `TRAIN_TILL`.
6. Parses `PREDICTING_MONTH` strictly as `M+1` through `M+5` and validates that it matches the interval between the derived dates.
7. Uses `PRED_VOLUME` as the authoritative `qty` value and requires it to be finite and non-negative.
8. When `Cal_forecast` is present and non-blank, validates it against its Excel formula within a small floating-point tolerance; the column itself is optional.
9. Renames and selects the target fields.
10. Adds `source = "ml"`.
11. Returns a DataFrame matching the final output contract exactly.

The helper should fail with a precise error instead of silently dropping malformed rows.

### 3. Label the existing TM result

After the current material-to-parent aggregation and description-selection logic completes, add:

```text
source = "tm"
```

Do not otherwise alter TM quantities, descriptions, month keys, aggregation rules, or Grand Total validation.

### 4. Normalize month representation

Before concatenation, make both sources use the same internal month type, preferably Polars `Date` values representing the first day of each month.

At the final CSV boundary, format both month columns consistently as `YYYY-MM` to preserve the existing waterfall convention.

### 5. Combine without cross-source aggregation

Concatenate the normalized TM and ML frames vertically.

Do **not** group or sum across sources. A TM row and an ML row with the same product, calculation month, and S&OP month are two alternative forecasts and must both remain present.

Use this as the final row identity:

```text
(parent_code, calculation_month, snop_month, source)
```

Sort deterministically by:

```text
parent_code, snop_month, calculation_month, source
```

Write the six-column combined frame to the existing output path.

### 6. Update the Marimo ETL report

Update the notebook display to show:

- TM row count
- ML row count
- Combined row count
- Parent count by source
- Calculation-month coverage by source
- Validation status for both source pipelines
- A small source summary table

The download button should export the combined six-column CSV.

## Validation and failure gates

The output must not be written unless all applicable checks pass.

### TM checks to preserve

- Exactly 16 S&OP grid files.
- Continuous TM calculation-month sequence.
- Header and month-range detection succeeds.
- Every file has one valid Grand Total row.
- Melted monthly sums match source Grand Totals within `1e-6`.

### New ML checks

- Workbook and `data` sheet exist.
- Required columns exist.
- Required mapping fields contain no nulls.
- `KEY` casts cleanly to integer.
- `MONTH_DATE` and `TRAIN_TILL` are valid month dates.
- `snop_month` equals `MONTH_DATE` without reinterpretation.
- `calculation_month` equals `TRAIN_TILL + 1 month`.
- Horizons are restricted to `M+1` through `M+5`.
- `PREDICTING_MONTH` matches the interval between `calculation_month` and `snop_month`.
- `PRED_VOLUME` is present, finite, and non-negative.
- `Cal_forecast` may be absent or blank because it is not the forecast-output source.
- When `Cal_forecast` is supplied, it is finite and non-negative.
- `Oth_Ch_Contr._%` is in `[0, 1)` so any supplied reference can be validated.
- A supplied `Cal_forecast` matches `PRED_VOLUME / (1 - Oth_Ch_Contr._%)` within tolerance.
- No duplicate ML final keys exist.

### Combined-output checks

- Columns are exactly:
  `calculation_month`, `snop_month`, `parent_code`, `parent_description`, `qty`, `source`.
- `source` contains only `tm` and `ml`.
- All existing TM records are retained and labeled `tm`.
- All normalized ML records are retained and labeled `ml`.
- No duplicate `(parent_code, calculation_month, snop_month, source)` keys exist.
- Row count equals `TM rows + ML rows`.
- With the currently studied files, the expected counts are:
  - TM: 8,515
  - ML: 7,520
  - Combined: 16,035
- Existing TM quantities remain unchanged after integration.

## Test plan

Create focused automated tests around pure transformation helpers rather than Marimo UI cells.

1. **Month derivation**
   - Confirm `snop_month` is copied directly from `MONTH_DATE`.
   - Confirm `calculation_month` is one month after `TRAIN_TILL`.
   - Cover ordinary months and year boundaries.

2. **Horizon validation**
   - Accept `M+1` through `M+5` when they match the interval between the derived dates.
   - Reject missing, malformed, zero, unsupported, or date-inconsistent horizons.

3. **ML schema and quantity validation**
   - Missing required column fails clearly.
   - Missing, negative, or non-finite `PRED_VOLUME` fails clearly.
   - Missing or blank `Cal_forecast` passes because it is optional reference data.
   - Invalid contribution percentage fails clearly.

4. **Optional formula validation**
   - A correct supplied `Cal_forecast` passes.
   - A changed supplied value fails within the selected tolerance.
   - Output `qty` always equals `PRED_VOLUME`, never `Cal_forecast`.

5. **Source labeling and concatenation**
   - TM rows receive `tm`.
   - ML rows receive `ml`.
   - Matching business keys across sources are retained as two rows.

6. **Regression test**
   - Run against the current files and assert the studied row counts, source counts, key uniqueness, and date coverage.

## Delivery sequence

1. Add ML input constants and pure normalization/validation helpers.
2. Add unit tests for authoritative month derivation, horizon validation, and ML normalization.
3. Label the TM frame with `source = "tm"`.
4. Normalize the ML frame with `source = "ml"`.
5. Concatenate and validate the combined frame.
6. Update the Marimo reporting cells and download output.
7. Regenerate `forecast_history_waterfall.csv`.
8. Verify diagnostics, tests, row counts, source counts, uniqueness, and unchanged TM values.

## Acceptance criteria

The work is complete when:

- Running the ETL reads both source families and produces one combined CSV.
- Existing records are labeled `tm`; ML records are labeled `ml`.
- ML `qty` comes from the authoritative `PRED_VOLUME` field.
- `Cal_forecast` is optional validation/reference data and is never written as forecast output.
- Both sources share the same six-column schema and month format.
- Same-key TM and ML forecasts coexist rather than being merged.
- The ETL refuses to write output when either source fails its validation gates.
- The current inputs produce 16,035 rows: 8,515 `tm` and 7,520 `ml`.
- Automated tests cover the new mapping and critical invariants.
