"""Source-aware forecast performance dashboard built on the canonical population."""

import marimo

__generated_with = "0.23.14"
app = marimo.App(width="full")


with app.setup:
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import polars as pl

    from forecast_analysis import build_analysis_dataset, load_analysis_inputs
    from forecast_analysis.dashboard import build_dashboard_view  # pyright: ignore[reportMissingImports]
    from forecast_analysis.filters import (  # pyright: ignore[reportMissingImports]
        DashboardFilters,
        available_filter_values,
        with_display_brand,
    )
    from forecast_analysis.metrics import format_metric  # pyright: ignore[reportMissingImports]

    ROOT = Path(__file__).parent
    FORECAST_HISTORY_PATH = (
        ROOT / "artifacts/forecast_history/consolidated/forecast_history_waterfall.csv"
    )
    HIERARCHY_PATH = ROOT / "artifacts/ph/PH_FG.xlsx"
    ACTUALS_PATH = ROOT / "artifacts/secondary_sales"


@app.cell
def _(mo):
    try:
        _inputs = load_analysis_inputs(
            FORECAST_HISTORY_PATH,
            HIERARCHY_PATH,
            ACTUALS_PATH,
        )
        validated_dataset = build_analysis_dataset(_inputs)
    except (FileNotFoundError, ValueError) as exc:
        mo.stop(
            True,
            mo.md(
                "## Dashboard input error\n\n"
                f"The canonical population could not be loaded: `{exc}`"
            ),
        )
        raise RuntimeError("dashboard data loading stopped after displaying the error")
    return validated_dataset,


@app.cell
def _(mo):
    source_filter = mo.ui.dropdown(
        options={"TM": "tm", "ML": "ml"},
        value="tm",
        label="Forecast source",
    )
    mo.hstack([source_filter], justify="start")
    return source_filter,


@app.cell
def _(validated_dataset, mo, source_filter, available_filter_values):
    _options = available_filter_values(validated_dataset.frame, source_filter.value)
    _target_months = _options["target_months"]
    _brands = _options["brands"]
    _products = _options["parent_products"]

    target_month_filter = mo.ui.multiselect(
        options=_target_months,
        value=_target_months,
        label="Target month",
    )
    brand_filter = mo.ui.multiselect(
        options=_brands,
        value=_brands,
        label="Brand",
    )
    product_filter = mo.ui.multiselect(
        options={
            f"{row['parent_code']} — {row['parent_description']}": row["parent_code"]
            for row in _products
        },
        value=[row["parent_code"] for row in _products],
        label="Parent product",
    )
    minimum_actual_filter = mo.ui.number(
        value=0,
        start=0,
        step=1,
        label="Minimum actual volume (KL)",
    )
    mo.hstack(
        [target_month_filter, brand_filter, product_filter, minimum_actual_filter],
        widths="equal",
    )
    return brand_filter, minimum_actual_filter, product_filter, target_month_filter


@app.cell
def _(
    DashboardFilters,
    build_dashboard_view,
    validated_dataset,
    brand_filter,
    minimum_actual_filter,
    product_filter,
    source_filter,
    target_month_filter,
):
    filters = DashboardFilters(
        source=source_filter.value,
        target_months=tuple(target_month_filter.value),
        brands=tuple(brand_filter.value),
        parent_codes=tuple(product_filter.value),
        minimum_actual_volume=minimum_actual_filter.value or 0,
    )
    view = build_dashboard_view(
        validated_dataset.frame,
        validated_dataset.actual_population,
        filters,
    )
    return filters, view


@app.cell
def _(filters, format_metric, mo, view):
    _months = view.filtered_population["snop_month"].unique().sort().to_list()
    _month_label = (
        f"{_months[0]} → {_months[-1]}" if _months else "no target months"
    )
    _m = view.metrics
    mo.md(
        f"""# Forecast performance — {filters.source.upper()}

**Population:** `{view.filtered_population.height:,}` forecast rows · `{view.vintage_pairs.height:,}` product-target groups · `{_month_label}` · `{format_metric(_m.actual_kl, 'KL')}` actual volume

**Comparison:** Vintage A = oldest available · Vintage B = latest available · `{_m.complete_pairs:,}` complete vintage pairs · `{_m.missing_vintage_pairs:,}` missing vintage pairs · `{_m.missing_actual_observations:,}` missing actuals · `{_m.zero_actual_observations:,}` zero actuals"""
    )
    return


@app.cell
def _(format_metric, mo, view):
    _m = view.metrics
    _empty_reason = (
        "No rows in the current selection"
        if view.filtered_population.height == 0
        else "No complete vintage pairs in the current selection"
        if _m.complete_pairs == 0 and _m.missing_vintage_pairs > 0
        else "No positive actuals in the current selection"
        if _m.eligible_observations == 0
        else f"{_m.eligible_observations:,} eligible observations"
    )
    _cards = [
        mo.md(
            f"**Forecast accuracy**\n\n## {format_metric(_m.forecast_accuracy_pct, '%')}\n\n{_empty_reason}"
        ),
        mo.md(
            f"**Bias**\n\n## {format_metric(_m.bias_pct, '%')}\n\n{_empty_reason}"
        ),
        mo.md(
            f"**Absolute error**\n\n## {format_metric(_m.absolute_error_kl, 'KL')}\n\n{_empty_reason}"
        ),
        mo.md(
            f"**Actual volume**\n\n## {format_metric(_m.actual_kl, 'KL')}\n\n{_empty_reason}"
        ),
        mo.md(
            f"**Forecast volume**\n\n## {format_metric(_m.forecast_kl, 'KL')}\n\n{_empty_reason}"
        ),
        mo.md(
            f"**Coverage**\n\n## {format_metric(_m.coverage_pct, '%')}\n\n{_empty_reason}"
        ),
        mo.md(
            f"**Eligible observations**\n\n## {format_metric(_m.eligible_observations, 'count')}\n\nPositive-actual rows"
        ),
    ]
    mo.hstack(_cards, widths="equal")
    return


@app.cell
def _(mo):
    monthly_metric = mo.ui.dropdown(
        options={
            "Forecast accuracy": "accuracy",
            "Bias": "bias",
            "Absolute error": "absolute_error",
            "Forecast versus actual volume": "forecast_vs_actual",
        },
        value="accuracy",
        label="Monthly performance metric",
    )
    mo.hstack([monthly_metric], justify="start")
    return monthly_metric,


@app.cell
def _(alt, monthly_metric, mo, pl, view):
    _monthly = view.monthly_performance
    if _monthly.height == 0:
        _output = mo.md("### Monthly performance\n\nNo target months remain in this selection.")
    elif monthly_metric.value == "forecast_vs_actual":
        _chart_data = _monthly.unpivot(
            on=["actual_kl", "forecast_kl"],
            index=["source", "snop_month", "eligible_observations"],
            variable_name="series",
            value_name="value",
        ).with_columns(
            pl.col("series")
            .str.replace("_kl", "")
            .str.replace("actual", "Actual")
            .str.replace("forecast", "Forecast")
        )
        if _chart_data.filter(pl.col("value").is_not_null()).height == 0:
            _output = mo.md(
                "### Monthly performance\n\nNo actual or forecast volume is available."
            )
        else:
            _chart = (
                alt.Chart(_chart_data.to_pandas())
                .mark_line(point=True, strokeWidth=2.5)
                .encode(
                    x=alt.X("snop_month:T", title="Target month"),
                    y=alt.Y("value:Q", title="Volume (KL)"),
                    color=alt.Color("series:N", title="Series"),
                    tooltip=[
                        "source:N",
                        alt.Tooltip("snop_month:T", title="Target month"),
                        "series:N",
                        alt.Tooltip("value:Q", format=",.1f"),
                        "eligible_observations:Q",
                    ],
                )
                .properties(height=360)
            )
            _output = mo.ui.altair_chart(
                _chart, chart_selection=False, legend_selection=False
            )
    else:
        _column = {
            "accuracy": "forecast_accuracy_pct",
            "bias": "bias_pct",
            "absolute_error": "absolute_error_kl",
        }[monthly_metric.value]
        _title = {
            "accuracy": "Forecast accuracy (%)",
            "bias": "Bias (%)",
            "absolute_error": "Absolute error (KL)",
        }[monthly_metric.value]
        _chart_data = _monthly.filter(pl.col(_column).is_not_null())
        if _chart_data.height == 0:
            _output = mo.md(
                f"### Monthly performance\n\nNo eligible {_title.lower()} is available for this selection."
            )
        else:
            _chart = (
                alt.Chart(_chart_data.to_pandas())
                .mark_line(point=True, strokeWidth=2.5)
                .encode(
                    x=alt.X("snop_month:T", title="Target month"),
                    y=alt.Y(_column + ":Q", title=_title, scale=alt.Scale(zero=False)),
                    color=alt.Color("source:N", title="Source"),
                    tooltip=[
                        alt.Tooltip("source:N", title="Source"),
                        alt.Tooltip("snop_month:T", title="Target month"),
                        alt.Tooltip(_column + ":Q", title=_title, format=",.1f"),
                        alt.Tooltip("actual_kl:Q", title="Actual KL", format=",.1f"),
                        alt.Tooltip("forecast_kl:Q", title="Forecast KL", format=",.1f"),
                        alt.Tooltip(
                            "eligible_observations:Q",
                            title="Observations",
                            format=",.0f",
                        ),
                    ],
                )
                .properties(height=360)
            )
            _plot = _chart
            if monthly_metric.value == "bias":
                _zero_rule = (
                    alt.Chart(pl.DataFrame({"baseline": [0.0]}).to_pandas())
                    .mark_rule(color="#5B6870", strokeDash=[5, 4])
                    .encode(y=alt.Y("baseline:Q", title=_title))
                )
                _plot = _chart + _zero_rule
            _output = mo.ui.altair_chart(
                _plot, chart_selection=False, legend_selection=False
            )
    mo.vstack([_output])


@app.cell
def _(mo, view, with_display_brand):
    _pairs = view.vintage_pairs
    if _pairs.height == 0:
        _output = mo.md(
            "## Filtered vintage table\n\nNo product-target pairs remain in this selection."
        )
    else:
        _table = (
            with_display_brand(_pairs)
            .select(
                [
                    "source",
                    "parent_code",
                    "parent_description",
                    "brand_display",
                    "snop_month",
                    "actual_kl",
                    "vintage_a_calculation_month",
                    "vintage_a_forecast_kl",
                    "vintage_b_calculation_month",
                    "vintage_b_forecast_kl",
                    "pair_status",
                ]
            )
            .sort(["snop_month", "parent_code"])
        )
        _output = mo.vstack(
            [mo.md("## Filtered vintage table"), mo.ui.table(_table, page_size=20)]
        )
    mo.vstack([_output])


@app.cell
def _(mo, pl, view):
    _population = view.filtered_population
    _pairs = view.vintage_pairs
    _quality = []
    for _column in ("mapping_status", "actual_status"):
        if _population.height:
            _quality.append(
                _population.group_by(_column).len().rename({_column: "status", "len": "rows"})
            )
    if _pairs.height:
        _quality.append(
            _pairs.group_by("pair_status").len().rename({"pair_status": "status", "len": "rows"})
        )
    if not _quality:
        _output = mo.md("## Data quality\n\nNo quality rows remain in this selection.")
    else:
        _quality_table = pl.concat(
            [table.with_columns(group=pl.lit(index)) for index, table in enumerate(_quality)],
            how="diagonal",
        ).select(["group", "status", "rows"])
        _output = mo.vstack(
            [
                mo.md(
                    "## Data quality\n\n"
                    "Missing actuals, zero actuals, and incomplete vintage pairs remain visible "
                    "instead of being folded into the ratio denominators."
                ),
                mo.ui.table(_quality_table, page_size=12),
            ]
        )
    mo.vstack([_output])


if __name__ == "__main__":
    app.run()
