import marimo

__generated_with = "0.23.14"
app = marimo.App(width="medium")


with app.setup:
    # The pipeline module owns source parsing, validation, transformations, and
    # atomic output writes. This module is deliberately only report orchestration.
    from datetime import UTC, datetime

    import marimo as mo
    import polars as pl

    from forecast_history_pipeline import (  # pyright: ignore[reportMissingImports]
        FORECAST_HISTORY_DIR,
        GRAND_TOTAL_TOLERANCE,
        ML_HISTORY_PATH,
        OUTPUT_CSV,
        build_forecast_history,
        parse_all,
        write_forecast_history_atomically,
    )


@app.cell
def _():
    files = sorted(FORECAST_HISTORY_DIR.glob("*.xlsx"))
    inventory = pl.DataFrame(
        {
            "file": [path.name for path in files],
            "size_kb": [round(path.stat().st_size / 1024, 1) for path in files],
            "modified": [
                datetime.fromtimestamp(path.stat().st_mtime, tz=UTC) for path in files
            ],
        }
    )
    mo.md(
        f"# Forecast history ETL\n\n**{len(files)} TM S&OP grid files** in "
        f"`{FORECAST_HISTORY_DIR}` plus ML history from `{ML_HISTORY_PATH}`."
    )
    mo.ui.table(inventory, page_size=10)
    return files, inventory


@app.cell
def _(files):
    metas, longs = parse_all(FORECAST_HISTORY_DIR)
    profile = pl.DataFrame(
        {
            "file": [meta["file"] for meta in metas],
            "calc_month": [meta["calc_month"] for meta in metas],
            "snop_months": [" → ".join(meta["sheet_months"]) for meta in metas],
            "layout": [meta["layout"] for meta in metas],
            "leaf_rows": [meta["leaf_rows"] for meta in metas],
            "total_rows_dropped": [meta["total_rows_dropped"] for meta in metas],
            "issues": ["; ".join(meta["issues"]) or "none" for meta in metas],
        }
    )
    n_leaf = sum(meta["leaf_rows"] for meta in metas)
    n_issues = sum(1 for meta in metas if meta["issues"])
    mo.md(
        f"## 1 · Profile\n\nAll **{len(metas)}** files parsed. **{n_leaf}** leaf "
        f"(material) rows across files, **{sum(meta['total_rows_dropped'] for meta in metas)}** "
        f"pivot total rows dropped, **{n_issues}** file(s) with flagged issues."
    )
    mo.ui.table(profile, page_size=10)
    return metas, longs, profile


@app.cell
def _():
    mo.md("""
    ## 2 · Challenges found in the source files

    1. **Two header layouts (vintage drift).** The 2025 files have a four-row
       header block while the 2026 files merge names and month names in one row.
       The pipeline locates the month-anchor and `parent_code` rows instead of
       hard-coding either layout.
    2. **Pivot artifacts and totals.** Cosmetic pivot labels are ignored, total
       rows are dropped, and every file's `Grand Total` is reconciled after melt.
    3. **Month provenance.** TM years come from anchored file names. ML uses
       `MONTH_DATE` as `snop_month` and `TRAIN_TILL + 1 month` as
       `calculation_month`; `PREDICTING_MONTH` is an independent cross-check.
    4. **Legitimate splits and drift.** Type-split material rows remain additive,
       while parent descriptions use the existing deterministic vote and tie-break.
    5. **Fail-fast output.** Both source pipelines, the six-column contract, key
       uniqueness, deterministic ordering, and the CSV round-trip are validated
       before the prior output can be atomically replaced.
    """)


@app.cell
def _(metas, longs):
    build = build_forecast_history(metas, longs, ML_HISTORY_PATH)
    write_forecast_history_atomically(build.consolidated, OUTPUT_CSV)

    consolidated = build.consolidated
    tm_validation = build.tm_validation
    ml_validation = build.ml_validation
    validation_status = build.validation_status
    source_summary = build.source_summary
    n_parents = consolidated.select(pl.col("parent_code").n_unique()).item()
    max_tm_diff = tm_validation["max_abs_diff_vs_grand_total"].max()
    mo.md(
        f"## 3 · Consolidated vertical waterfall\n\n"
        f"**{consolidated.height:,}** combined rows · **{n_parents}** parents\n\n"
        f"TM: **{build.tm.height:,}** rows · ML: **{build.ml.height:,}** rows · "
        f"combined: **{consolidated.height:,}** rows\n\n"
        f"TM Grand Total max |diff|: **{max_tm_diff:.2e}** "
        f"(tolerance {GRAND_TOTAL_TOLERANCE:.0e})\n\n"
        "The validated six-column CSV was atomically written to "
        f"`{OUTPUT_CSV}`."
    )
    mo.md("### Source summary")
    mo.ui.table(source_summary, page_size=10)
    mo.md("### Validation status")
    mo.ui.table(validation_status, page_size=10)
    mo.md("### ML validation evidence")
    mo.ui.table(ml_validation.to_frame(), page_size=10)
    mo.ui.table(consolidated.head(500), page_size=10)
    return (
        consolidated,
        tm_validation,
        ml_validation,
        validation_status,
        source_summary,
    )


@app.cell
def _(tm_validation, ml_validation, validation_status, source_summary):
    mo.md(
        "## 4 · Validation evidence\n\n"
        "The explicit status table is derived from successful TM and ML "
        "validation evidence. The detailed tables remain available below: "
        "TM Grand Total differences per file, plus ML checked rows, formula "
        "error, exact horizon and date coverage, and duplicate-key count."
    )
    mo.ui.table(validation_status, page_size=10)
    mo.ui.table(tm_validation, page_size=10)
    mo.ui.table(ml_validation.to_frame(), page_size=10)
    mo.ui.table(source_summary, page_size=10)


@app.cell
def _(consolidated):
    mo.download(
        consolidated.write_csv().encode(),
        filename="forecast_history_waterfall.csv",
        label="⬇ Download consolidated waterfall CSV",
    )


if __name__ == "__main__":
    app.run()
