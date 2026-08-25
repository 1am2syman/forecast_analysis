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
    from forecast_analysis.vintages import VintageRule  # pyright: ignore[reportMissingImports]
    from forecast_analysis.metrics import (  # pyright: ignore[reportMissingImports]
        brand_target_metric_definition,
        brand_target_month_order,
        format_horizon_label,
        format_metric,
        format_revision_tolerance,
    )

    ROOT = Path(__file__).parent
    FORECAST_HISTORY_PATH = (
        ROOT / "artifacts/forecast_history/consolidated/forecast_history_waterfall.csv"
    )
    HIERARCHY_PATH = ROOT / "artifacts/ph/PH_FG.xlsx"
    ACTUALS_PATH = ROOT / "artifacts/secondary_sales"
    SOURCE_COLORS = {"tm": "#0F5B78", "ml": "#D97757"}


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
    comparison_mode_filter = mo.ui.dropdown(
        options={
            "Single source": "single",
            "Compare TM vs ML": "comparison",
        },
        value="single",
        label="View mode",
    )
    source_filter = mo.ui.dropdown(
        options={"TM": "tm", "ML": "ml"},
        value="tm",
        label="Forecast source (single-source mode)",
    )
    mo.hstack([comparison_mode_filter, source_filter], justify="start")
    return comparison_mode_filter, source_filter


@app.cell
def _(
    validated_dataset,
    mo,
    source_filter,
    comparison_mode_filter,
    available_filter_values,
):
    _comparison_mode = comparison_mode_filter.value == "comparison"
    _options = available_filter_values(
        validated_dataset.frame,
        source_filter.value,
        comparison_mode=_comparison_mode,
    )
    _target_months = _options["target_months"]
    _brands = _options["brands"]
    _products = _options["parent_products"]
    _horizons = _options["horizons"]
    _calculation_months = _options["calculation_months"]

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
    _default_horizons = (
        [_options["default_comparison_horizon"]]
        if _comparison_mode and _options["default_comparison_horizon"] is not None
        else _horizons
    )
    horizon_filter = mo.ui.multiselect(
        options={format_horizon_label(horizon): horizon for horizon in _horizons},
        value=_default_horizons,
        label=("Comparison horizon (exact)" if _comparison_mode else "Forecast horizon"),
    )
    minimum_actual_filter = mo.ui.number(
        value=0,
        start=0,
        step=1,
        label="Minimum actual volume (KL)",
    )

    _rule_options = {
        "Oldest available": "oldest_available",
        "Latest available": "latest_available",
        "Exact calculation month": "specific_calculation_month",
        "Exact horizon": "specific_horizon",
    }
    _month_options = {
        str(month): month for month in _calculation_months
    } or {"No calculation months available": None}
    _horizon_options = {
        format_horizon_label(horizon): horizon for horizon in _horizons
    } or {"No horizons available": None}
    vintage_a_rule_filter = mo.ui.dropdown(
        options=_rule_options,
        value="oldest_available",
        label="Vintage A rule",
    )
    vintage_b_rule_filter = mo.ui.dropdown(
        options=_rule_options,
        value="latest_available",
        label="Vintage B rule",
    )
    vintage_a_month_filter = mo.ui.dropdown(
        options=_month_options,
        value=next(iter(_month_options.values())),
        label="Vintage A exact calculation month",
    )
    vintage_b_month_filter = mo.ui.dropdown(
        options=_month_options,
        value=next(iter(_month_options.values())),
        label="Vintage B exact calculation month",
    )
    vintage_a_horizon_filter = mo.ui.dropdown(
        options=_horizon_options,
        value=next(iter(_horizon_options.values())),
        label="Vintage A exact horizon",
    )
    vintage_b_horizon_filter = mo.ui.dropdown(
        options=_horizon_options,
        value=next(iter(_horizon_options.values())),
        label="Vintage B exact horizon",
    )
    revision_direction_filter = mo.ui.multiselect(
        options={"Up": "up", "Down": "down", "Unchanged": "unchanged"},
        value=["up", "down", "unchanged"],
        label="Revision direction (active with comparable pairs)",
    )
    revision_outcome_filter = mo.ui.multiselect(
        options={"Improved": "improved", "Worsened": "worsened", "Neutral": "neutral"},
        value=["improved", "worsened", "neutral"],
        label="Revision outcome (active with comparable pairs)",
    )
    revision_tolerance_filter = mo.ui.number(
        value=0.01,
        start=0,
        step=0.01,
        label=(
            "Comparison tie tolerance (KL)"
            if _comparison_mode
            else "Revision tolerance (KL)"
        ),
    )
    _controls = [
        mo.hstack(
            [
                target_month_filter,
                brand_filter,
                product_filter,
                horizon_filter,
                minimum_actual_filter,
            ],
            widths="equal",
        )
    ]
    if _comparison_mode:
        _controls.extend(
            [
                mo.md(
                    "**Comparison mode:** TM and ML use one selected shared exact "
                    "horizon. Vintage A/B and revision direction/outcome controls "
                    "are unavailable because comparison is not a revision self-pair."
                ),
                revision_tolerance_filter,
            ]
        )
    else:
        _controls.extend(
            [
                mo.md("### Vintage comparison and revision filters"),
                mo.hstack(
                    [vintage_a_rule_filter, vintage_b_rule_filter],
                    widths="equal",
                ),
                mo.hstack(
                    [
                        vintage_a_month_filter,
                        vintage_b_month_filter,
                        vintage_a_horizon_filter,
                        vintage_b_horizon_filter,
                    ],
                    widths="equal",
                ),
                mo.hstack(
                    [
                        revision_direction_filter,
                        revision_outcome_filter,
                        revision_tolerance_filter,
                    ],
                    widths="equal",
                ),
            ]
        )
    mo.vstack(_controls)
    return (
        brand_filter,
        horizon_filter,
        minimum_actual_filter,
        product_filter,
        target_month_filter,
        vintage_a_rule_filter,
        vintage_b_rule_filter,
        vintage_a_month_filter,
        vintage_b_month_filter,
        vintage_a_horizon_filter,
        vintage_b_horizon_filter,
        revision_direction_filter,
        revision_outcome_filter,
        revision_tolerance_filter,
    )


@app.cell
def _(
    DashboardFilters,
    VintageRule,
    build_dashboard_view,
    validated_dataset,
    brand_filter,
    horizon_filter,
    minimum_actual_filter,
    product_filter,
    source_filter,
    target_month_filter,
    vintage_a_rule_filter,
    vintage_b_rule_filter,
    vintage_a_month_filter,
    vintage_b_month_filter,
    vintage_a_horizon_filter,
    vintage_b_horizon_filter,
    revision_direction_filter,
    revision_outcome_filter,
    revision_tolerance_filter,
    comparison_mode_filter,
):
    _comparison_mode = comparison_mode_filter.value == "comparison"

    def _make_vintage_rule(kind, calculation_month, horizon):
        try:
            if (
                kind == "specific_calculation_month"
                and calculation_month is not None
            ):
                return VintageRule.specific_calculation_month(calculation_month)
            if kind == "specific_horizon" and horizon is not None:
                return VintageRule.specific_horizon(int(horizon))
            if kind == "latest_available":
                return VintageRule.latest_available()
        except (TypeError, ValueError):
            return VintageRule.oldest_available()
        return VintageRule.oldest_available()

    def _all_or_selected(values, all_values):
        selected = tuple(values)
        return None if set(selected) == set(all_values) else selected

    _revision_tolerance = (
        0.01
        if revision_tolerance_filter.value is None
        else revision_tolerance_filter.value
    )
    _selected_revision_directions = (
        None
        if _comparison_mode
        else _all_or_selected(
            revision_direction_filter.value,
            ("up", "down", "unchanged"),
        )
    )
    _selected_revision_outcomes = (
        None
        if _comparison_mode
        else _all_or_selected(
            revision_outcome_filter.value,
            ("improved", "worsened", "neutral"),
        )
    )
    vintage_a = (
        None
        if _comparison_mode
        else _make_vintage_rule(
            vintage_a_rule_filter.value,
            vintage_a_month_filter.value,
            vintage_a_horizon_filter.value,
        )
    )
    vintage_b = (
        None
        if _comparison_mode
        else _make_vintage_rule(
            vintage_b_rule_filter.value,
            vintage_b_month_filter.value,
            vintage_b_horizon_filter.value,
        )
    )
    _selected_horizons = tuple(horizon_filter.value)
    _comparison_horizon = (
        _selected_horizons[0]
        if _comparison_mode and len(_selected_horizons) == 1
        else None
    )
    base_filters = DashboardFilters(
        source=source_filter.value,
        comparison_mode=_comparison_mode,
        comparison_horizon=_comparison_horizon,
        target_months=tuple(target_month_filter.value),
        brands=tuple(brand_filter.value),
        parent_codes=tuple(product_filter.value),
        horizons=tuple(horizon_filter.value),
        minimum_actual_volume=minimum_actual_filter.value or 0,
        revision_tolerance_kl=_revision_tolerance,
    )
    base_view = build_dashboard_view(
        validated_dataset.frame,
        validated_dataset.actual_population,
        base_filters,
        vintage_a=vintage_a,
        vintage_b=vintage_b,
    )
    comparison_ready = (
        base_view.comparison.ready
        if _comparison_mode and base_view.comparison is not None
        else base_view.metrics.complete_pairs > 0
    )
    filters = DashboardFilters(
        source=source_filter.value,
        comparison_mode=_comparison_mode,
        comparison_horizon=_comparison_horizon,
        target_months=tuple(target_month_filter.value),
        brands=tuple(brand_filter.value),
        parent_codes=tuple(product_filter.value),
        horizons=tuple(horizon_filter.value),
        minimum_actual_volume=minimum_actual_filter.value or 0,
        revision_directions=(
            _selected_revision_directions
            if comparison_ready and not _comparison_mode
            else None
        ),
        revision_outcomes=(
            _selected_revision_outcomes
            if comparison_ready and not _comparison_mode
            else None
        ),
        revision_tolerance_kl=_revision_tolerance,
    )
    view = build_dashboard_view(
        validated_dataset.frame,
        validated_dataset.actual_population,
        filters,
        vintage_a=vintage_a,
        vintage_b=vintage_b,
    )
    return comparison_ready, filters, view


@app.cell
def _(
    comparison_ready,
    filters,
    format_horizon_label,
    format_metric,
    format_revision_tolerance,
    mo,
    pl,
    view,
):
    _comparison_output = None
    if filters.comparison_mode and view.comparison is not None:
        _comparison = view.comparison
        _month_frame = (
            _comparison.common_population
            if _comparison.common_population.height
            else _comparison.filtered_population
        )
        _months = _month_frame["snop_month"].unique().sort().to_list()
        _month_label = (
            f"{_months[0]} → {_months[-1]}" if _months else "no target months"
        )
        _horizon_label = (
            format_horizon_label(_comparison.selected_horizon)
            if _comparison.selected_horizon is not None
            else "not aligned"
        )
        _alignment = _comparison.alignment_rule or "not selected"
        _warning = _comparison.warning or _comparison.coverage_warning
        _warning_text = (
            f"\n\n> ⚠️ **Comparison note:** {_warning}" if _warning else ""
        )
        _comparison_output = mo.md(
            f"""# Forecast performance — TM vs ML comparison

**Common population:** `{_comparison.comparable_pairs:,}` paired product-target observations · `{_month_label}` · **aligned horizon:** `{_horizon_label}` · **rule:** `{_alignment}`

**Coverage:** `{_comparison.population_summary.filter(pl.col('population') == 'common')['actual_kl'].item() if _comparison.population_summary.filter(pl.col('population') == 'common').height else 0.0:,.1f} KL` common actual volume · `{_comparison.population_summary.filter(pl.col('population') == 'tm_only')['observations'].item() if _comparison.population_summary.filter(pl.col('population') == 'tm_only').height else 0:,}` TM-only · `{_comparison.population_summary.filter(pl.col('population') == 'ml_only')['observations'].item() if _comparison.population_summary.filter(pl.col('population') == 'ml_only').height else 0:,}` ML-only

Accuracy, bias, and absolute error use the common aligned population; each source's coverage uses its full aligned-horizon population (common plus source-only). {_warning_text}"""
        )

    _month_frame = (
        view.coverage_pairs
        if view.coverage_pairs.height
        else view.filtered_population
    )
    _months = _month_frame["snop_month"].unique().sort().to_list()
    _month_label = (
        f"{_months[0]} → {_months[-1]}" if _months else "no target months"
    )
    if filters.horizons is None:
        _horizon_label = "all available"
    elif not filters.horizons:
        _horizon_label = "none selected"
    else:
        _horizon_label = ", ".join(
            format_horizon_label(horizon) for horizon in filters.horizons
        )
    _rules = (
        view.coverage_pairs.select(
            ["vintage_a_rule", "vintage_b_rule"]
        ).unique().row(0, named=True)
        if view.coverage_pairs.height
        else {"vintage_a_rule": "not selected", "vintage_b_rule": "not selected"}
    )
    _m = view.metrics
    _revision_filter_message = (
        "Revision direction/outcome filters are active."
        if comparison_ready
        else "Revision direction/outcome filters are a no-op: no complete positive-actual Vintage A/B pairs are available in this selection."
    )
    _standard_output = mo.md(
        f"""# Forecast performance — {filters.source.upper()}

**Population:** `{view.filtered_population.height:,}` forecast rows · `{view.coverage_pairs.height:,}` coverage product-target groups · `{view.vintage_pairs.height:,}` selected pair rows · `{_month_label}` · `{format_metric(_m.actual_kl, 'KL')}` actual volume

**Horizon:** `{_horizon_label}` · **Comparison:** Vintage A = `{_rules['vintage_a_rule']}` · Vintage B = `{_rules['vintage_b_rule']}` · `{_m.complete_pairs:,}` complete selected pairs · `{_m.missing_vintage_pairs:,}` missing vintage pairs · `{_m.missing_actual_observations:,}` missing actuals · `{_m.zero_actual_observations:,}` zero actuals

**Revision policy:** tolerance `{format_revision_tolerance(filters.revision_tolerance_kl)}`; revisions above tolerance are **up**, below negative tolerance are **down**, and the remainder are **unchanged**. Error improvement above, below, or within the same tolerance is **improved**, **worsened**, or **neutral**. {_revision_filter_message}"""
    )
    _comparison_output if filters.comparison_mode else _standard_output


@app.cell
def _(format_metric, mo, view):
    _comparison_output = None
    if view.filters.comparison_mode and view.comparison is not None:
        _comparison = view.comparison

        def _source_card(label, summary):
            return mo.md(
                f"**{label}**\n\n"
                f"Accuracy: **{format_metric(summary.forecast_accuracy_pct, '%')}**  \n"
                f"Bias: **{format_metric(summary.bias_pct, '%')}**  \n"
                f"Absolute error: **{format_metric(summary.absolute_error_kl, 'KL')}**  \n"
                f"Aligned-horizon coverage: **{format_metric(summary.coverage_pct, '%')}**  \n"
                f"Common actual: `{format_metric(summary.actual_kl, 'KL')}` · "
                f"Common forecast: `{format_metric(summary.forecast_kl, 'KL')}`  \n"
                f"Eligible observations: `{summary.eligible_observations:,}`"
            )

        _delta_cards = []
        for _row in _comparison.deltas.iter_rows(named=True):
            _unit = "KL" if _row["metric"] == "Absolute error" else "pp"
            _delta_cards.append(
                mo.md(
                    f"**ML − TM {_row['metric']}**\n\n"
                    f"## {format_metric(_row['delta_ml_minus_tm'], _unit)}\n\n"
                    "Positive means ML is higher; lower absolute error is better."
                )
            )
        _comparison_output = mo.vstack(
            [
                mo.hstack(
                    [
                        _source_card("TM", _comparison.tm_metrics),
                        _source_card("ML", _comparison.ml_metrics),
                    ],
                    widths="equal",
                ),
                mo.md("### Comparison deltas · ML minus TM"),
                mo.hstack(_delta_cards, widths="equal"),
            ]
        )

    _m = view.metrics
    _empty_reason = (
        "No rows in the current selection"
        if view.filtered_population.height == 0 and view.vintage_pairs.height == 0
        else "No exact-horizon observations in the current selection"
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
    if _m.complete_pairs:
        _cards.extend(
            [
                mo.md(
                    f"**Accuracy delta**\n\n## {format_metric(_m.accuracy_delta_pp, 'pp')}\n\n{_m.complete_pairs:,} complete positive-actual comparisons · Vintage B − Vintage A"
                ),
                mo.md(
                    f"**Revision effectiveness**\n\n## {format_metric(_m.revision_effectiveness_pct, '%')}\n\n{_m.improved_revisions:,} improved / {_m.materially_revised_observations:,} materially revised"
                ),
                mo.md(
                    f"**Total error improvement**\n\n## {format_metric(_m.total_error_improvement_kl, 'KL')}\n\n{_m.complete_pairs:,} complete positive-actual comparisons · Positive values improve error"
                ),
            ]
        )
    _standard_output = mo.hstack(_cards, widths="equal")
    _comparison_output if view.filters.comparison_mode else _standard_output


@app.cell
def _(mo, view):
    _output = None
    if view.filters.comparison_mode and view.comparison is not None:
        _comparison = view.comparison
        _paired = _comparison.paired_comparison
        _paired_columns = [
            "parent_code",
            "snop_month",
            "actual_kl",
            "tm_forecast_kl",
            "ml_forecast_kl",
            "tm_absolute_error_kl",
            "ml_absolute_error_kl",
            "winner_label",
            "pair_status",
        ]
        _output = mo.vstack(
            [
                mo.md(
                    "## TM ↔ ML aligned population\n\n"
                    "Common, TM-only, and ML-only counts use the one selected shared exact horizon. "
                    "Source-only observations contribute to source coverage; winner labels compare "
                    "absolute error only on common product-target observations."
                ),
                mo.ui.table(_comparison.population_summary, page_size=4),
                mo.ui.table(
                    _comparison.winner_counts,
                    page_size=3,
                ),
                mo.ui.table(
                    _paired.select(_paired_columns)
                    if _paired.height
                    else _paired,
                    page_size=20,
                ),
            ]
        )
    mo.vstack([_output] if _output is not None else [])


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
def _(SOURCE_COLORS, alt, monthly_metric, mo, pl, view):
    _monthly = view.monthly_performance
    _source_scale = alt.Scale(
        domain=["tm", "ml"],
        range=[SOURCE_COLORS["tm"], SOURCE_COLORS["ml"]],
    )
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
            _color = (
                alt.Color("source:N", title="Source", scale=_source_scale)
                if view.filters.comparison_mode
                else alt.Color("series:N", title="Series")
            )
            _chart = (
                alt.Chart(_chart_data.to_pandas())
                .mark_line(point=True, strokeWidth=2.5)
                .encode(
                    x=alt.X("snop_month:T", title="Target month"),
                    y=alt.Y("value:Q", title="Volume (KL)"),
                    color=_color,
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
            if view.filters.comparison_mode:
                _chart = _chart.encode(
                    strokeDash=alt.StrokeDash("series:N", title="Measure")
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
                    color=alt.Color(
                        "source:N",
                        title="Source",
                        scale=_source_scale,
                    ),
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
def _(mo):
    horizon_metric = mo.ui.dropdown(
        options={
            "Forecast accuracy": "accuracy",
            "Bias": "bias",
        },
        value="accuracy",
        label="Horizon performance metric",
    )
    mo.hstack([horizon_metric], justify="start")
    return horizon_metric,


@app.cell
def _(SOURCE_COLORS, alt, horizon_metric, mo, pl, view):
    _horizon = view.horizon_performance
    _source_scale = alt.Scale(
        domain=["tm", "ml"],
        range=[SOURCE_COLORS["tm"], SOURCE_COLORS["ml"]],
    )
    _column = {
        "accuracy": "forecast_accuracy_pct",
        "bias": "bias_pct",
    }[horizon_metric.value]
    _title = {
        "accuracy": "Forecast accuracy (%)",
        "bias": "Bias (%)",
    }[horizon_metric.value]
    _chart_data = _horizon.filter(pl.col(_column).is_not_null())
    if _chart_data.height == 0:
        _output = mo.md(
            "No eligible forecast accuracy or bias is available at the selected "
            "horizons. Coverage and missing observations remain visible below."
        )
    else:
        _chart = (
            alt.Chart(_chart_data.to_pandas())
            .mark_line(point=True, strokeWidth=2.5)
            .encode(
                x=alt.X(
                    "horizon_label:N",
                    sort=alt.SortField(
                        field="forecast_horizon_months", order="descending"
                    ),
                    title="Forecast horizon",
                ),
                y=alt.Y(_column + ":Q", title=_title, scale=alt.Scale(zero=False)),
                color=alt.Color(
                    "source:N",
                    title="Source",
                    scale=_source_scale,
                ),
                tooltip=[
                    alt.Tooltip("source:N", title="Source"),
                    alt.Tooltip("horizon_label:N", title="Horizon"),
                    alt.Tooltip(
                        "forecast_horizon_months:Q",
                        title="Months ahead",
                        format=",.0f",
                    ),
                    alt.Tooltip(_column + ":Q", title=_title, format=",.1f"),
                    alt.Tooltip("actual_kl:Q", title="Actual KL", format=",.1f"),
                    alt.Tooltip(
                        "forecast_kl:Q", title="Forecast KL", format=",.1f"
                    ),
                    alt.Tooltip(
                        "coverage_pct:Q", title="Coverage (%)", format=",.1f"
                    ),
                    alt.Tooltip(
                        "eligible_observations:Q",
                        title="Positive-actual observations",
                        format=",.0f",
                    ),
                    alt.Tooltip(
                        "population_observations:Q",
                        title="Forecast observations",
                        format=",.0f",
                    ),
                    alt.Tooltip(
                        "missing_actual_observations:Q",
                        title="Missing actuals",
                        format=",.0f",
                    ),
                ],
            )
            .properties(height=360)
        )
        _plot = _chart
        if horizon_metric.value == "bias":
            _zero_rule = (
                alt.Chart(pl.DataFrame({"baseline": [0.0]}).to_pandas())
                .mark_rule(color="#5B6870", strokeDash=[5, 4])
                .encode(y=alt.Y("baseline:Q", title=_title))
            )
            _plot = _chart + _zero_rule
        _output = mo.ui.altair_chart(
            _plot, chart_selection=False, legend_selection=False
        )
    mo.vstack(
        [
            mo.md(
                "## Performance by forecast horizon\n\n"
                "Long-range forecasts appear first; near-term forecasts appear last. "
                "Tooltips retain actual volume, forecast volume, coverage, and counts."
            ),
            _output,
        ]
    )


@app.cell
def _(mo, view):
    _brand_metric_options = {
        "Forecast accuracy": "forecast_accuracy",
        "Bias": "bias",
        "Absolute error": "absolute_error",
    }
    if not view.filters.comparison_mode:
        _brand_metric_options.update(
            {
                "Vintage A accuracy": "vintage_a_accuracy",
                "Vintage B accuracy": "vintage_b_accuracy",
                "Accuracy delta": "accuracy_delta",
                "Revision effectiveness": "revision_effectiveness",
            }
        )
    brand_month_metric = mo.ui.dropdown(
        options=_brand_metric_options,
        value="forecast_accuracy",
        label="Brand × target-month metric",
    )
    mo.hstack([brand_month_metric], justify="start")
    return brand_month_metric,


@app.cell
def _(
    alt,
    brand_month_metric,
    brand_target_metric_definition,
    brand_target_month_order,
    mo,
    pl,
    view,
):
    _heatmap = view.brand_target_month_performance
    _metric_column, _metric_title, _unit, _scale_kind, _ = (
        brand_target_metric_definition(brand_month_metric.value)
    )
    _metric_rows = _heatmap.filter(pl.col(_metric_column).is_not_null())
    _scale_note = ""
    if _heatmap.height == 0:
        _output = mo.md(
            "## Brand × target-month performance\n\n"
            "No brand or target-month rows remain in this selection."
        )
    elif _metric_rows.height == 0:
        _output = mo.md(
            f"## Brand × target-month performance\n\n"
            f"No {_metric_title.lower()} is applicable in this selection. "
            "Coverage rows remain available in the filtered vintage download."
        )
    else:
        _order = brand_target_month_order(_heatmap, brand_month_metric.value)
        _chart_data = _heatmap.with_columns(
            pl.col(_metric_column).alias("metric_value")
        )
        _legend_title = f"{_metric_title} ({_unit})"
        if _scale_kind == "diverging":
            _color_scale = alt.Scale(scheme="redblue", domainMid=0)
            _legend_title += " · zero = 0"
            _scale_note = "Diverging scale centered on the visible zero point (0 = neutral)."
        elif _metric_column == "absolute_error_kl":
            _color_scale = alt.Scale(scheme="oranges")
            _scale_note = "Sequential scale shows increasing absolute-error magnitude."
        else:
            _color_scale = alt.Scale(scheme="greens")
            _scale_note = "Sequential scale shows increasing effectiveness."
        if brand_month_metric.value == "absolute_error":
            _count_tooltips = [
                alt.Tooltip(
                    "absolute_error_observations:Q",
                    title="Absolute-error observations (including zero actuals)",
                    format=",.0f",
                )
            ]
        elif brand_month_metric.value == "revision_effectiveness":
            _count_tooltips = [
                alt.Tooltip(
                    "improved_revisions:Q",
                    title="Improved revisions (numerator)",
                    format=",.0f",
                ),
                alt.Tooltip(
                    "materially_revised_observations:Q",
                    title="Materially revised (denominator)",
                    format=",.0f",
                ),
            ]
        elif brand_month_metric.value == "vintage_a_accuracy":
            _count_tooltips = [
                alt.Tooltip(
                    "vintage_a_eligible_observations:Q",
                    title="Vintage A eligible observations",
                    format=",.0f",
                )
            ]
        elif brand_month_metric.value == "accuracy_delta":
            _count_tooltips = [
                alt.Tooltip(
                    "complete_pairs:Q",
                    title="Eligible complete Vintage A/B pairs",
                    format=",.0f",
                )
            ]
        else:
            _count_tooltips = [
                alt.Tooltip(
                    "vintage_b_eligible_observations:Q",
                    title="Vintage B eligible observations",
                    format=",.0f",
                )
            ]
        _chart = (
            alt.Chart(_chart_data.to_pandas())
            .mark_rect(stroke="white", strokeWidth=1)
            .encode(
                x=alt.X(
                    "snop_month:T",
                    title="Target month",
                    sort=alt.SortField(field="snop_month", order="ascending"),
                ),
                y=alt.Y(
                    "brand_display:N",
                    title="Brand",
                    sort=_order,
                ),
                color=alt.Color(
                    "metric_value:Q",
                    title=_legend_title,
                    scale=_color_scale,
                ),
                tooltip=[
                    alt.Tooltip("source:N", title="Source"),
                    alt.Tooltip("brand_display:N", title="Brand"),
                    alt.Tooltip("snop_month:T", title="Target month"),
                    alt.Tooltip(
                        "metric_value:Q",
                        title=f"{_metric_title} ({_unit})",
                        format=",.1f",
                    ),
                    alt.Tooltip("actual_kl:Q", title="Actual volume (KL)", format=",.1f"),
                    *_count_tooltips,
                    alt.Tooltip(
                        "population_observations:Q",
                        title="Population observations",
                        format=",.0f",
                    ),
                ],
            )
            .properties(height=max(240, len(_order) * 26))
        )
        if view.filters.comparison_mode:
            _chart = _chart.facet(
                row=alt.Row(
                    "source:N",
                    title="Source",
                    sort=["tm", "ml"],
                )
            )
        _output = mo.ui.altair_chart(
            _chart,
            chart_selection=False,
            legend_selection=False,
        )
    mo.vstack(
        [
            mo.md(
                "## Brand × target-month performance\n\n"
                "Rows are sorted worst-first by the selected metric. "
                "All brands summarizes the currently filtered brand population. "
                f"{_scale_note if _heatmap.height and _metric_rows.height else ''}"
            ),
            _output,
        ]
    )


@app.cell
def _(SOURCE_COLORS, alt, format_metric, mo, pl, view):
    _diagnostics = view.revision_diagnostics
    _m = view.metrics
    _summary_table = mo.ui.table(_diagnostics, page_size=4)
    if view.revision_scatter.height == 0:
        _chart_output = mo.md(
            "No complete positive-actual vintage pairs remain for the revision scatter plot."
        )
    else:
        _color = (
            alt.Color(
                "source:N",
                title="Source",
                scale=alt.Scale(
                    domain=["tm", "ml"],
                    range=[SOURCE_COLORS["tm"], SOURCE_COLORS["ml"]],
                ),
            )
            if view.filters.comparison_mode
            else alt.Color("brand:N", title="Brand")
        )
        _chart = (
            alt.Chart(view.revision_scatter.to_pandas())
            .mark_circle(opacity=0.8)
            .encode(
                x=alt.X("revision_kl:Q", title="Revision amount (KL)"),
                y=alt.Y(
                    "error_improvement_kl:Q",
                    title="Error improvement (KL)",
                ),
                color=_color,
                size=alt.Size("actual_kl:Q", title="Actual volume (KL)"),
                tooltip=[
                    alt.Tooltip("source:N", title="Source"),
                    alt.Tooltip("parent_code:Q", title="Parent product"),
                    alt.Tooltip("snop_month:T", title="Target month"),
                    alt.Tooltip("actual_kl:Q", title="Actual KL", format=",.1f"),
                    alt.Tooltip("revision_kl:Q", title="Revision KL", format=",.3f"),
                    alt.Tooltip(
                        "error_improvement_kl:Q",
                        title="Error improvement KL",
                        format=",.3f",
                    ),
                    alt.Tooltip("revision_direction:N", title="Direction"),
                    alt.Tooltip("revision_outcome:N", title="Outcome"),
                ],
            )
            .properties(height=360)
        )
        _zero_data = pl.DataFrame({"baseline": [0.0]}).to_pandas()
        _vertical_zero = (
            alt.Chart(_zero_data)
            .mark_rule(color="#5B6870", strokeDash=[5, 4])
            .encode(x=alt.X("baseline:Q", title="Revision amount (KL)"))
        )
        _horizontal_zero = (
            alt.Chart(_zero_data)
            .mark_rule(color="#5B6870", strokeDash=[5, 4])
            .encode(y=alt.Y("baseline:Q", title="Error improvement (KL)"))
        )
        _chart_output = mo.ui.altair_chart(
            _chart + _vertical_zero + _horizontal_zero,
            chart_selection=False,
            legend_selection=False,
        )
    if view.filters.comparison_mode:
        _revision_output = mo.md(
            "## Revision effectiveness\n\n"
            "Not applicable in exact-horizon comparison mode. TM and ML are "
            "compared at one shared horizon; Vintage A/B and revision direction "
            "and outcome controls are disabled to prevent artificial self-pairs."
        )
    else:
        _revision_output = mo.vstack(
            [
                mo.md(
                    f"## Revision effectiveness\n\n"
                    f"Improved: **{_m.improved_revisions:,}** · "
                    f"Worsened: **{_m.worsened_revisions:,}** · "
                    f"Neutral: **{_m.neutral_revisions:,}** · "
                    f"Unchanged: **{_m.unchanged_revisions:,}**\n\n"
                    f"Revised up: `{format_metric(_m.revised_up_pct, '%')}` · "
                    f"Revised down: `{format_metric(_m.revised_down_pct, '%')}` · "
                    f"Total error improvement: `{format_metric(_m.total_error_improvement_kl, 'KL')}`"
                ),
                _summary_table,
                _chart_output,
            ]
        )
    mo.vstack([_revision_output])


@app.cell
def _(mo, view, with_display_brand):
    _pairs = view.vintage_pairs
    _scope_label = "tm_vs_ml" if view.filters.comparison_mode else view.filters.source
    _download = mo.download(
        _pairs.write_csv().encode(),
        filename=f"forecast_{_scope_label}_filtered_vintages.csv",
        label="Download filtered vintage CSV",
    )
    _brand_month_download = mo.download(
        view.brand_target_month_performance.write_csv().encode(),
        filename=f"forecast_{_scope_label}_brand_target_month_performance.csv",
        label="Download brand × target-month CSV",
    )
    if _pairs.height == 0:
        _output = mo.md(
            "## Filtered vintage table\n\nNo product-target pairs remain in this selection."
        )
    else:
        _table_source = with_display_brand(_pairs)
        if view.filters.comparison_mode:
            _table = (
                _table_source.select(
                    [
                        "source",
                        "parent_code",
                        "parent_description",
                        "brand_display",
                        "mapping_status",
                        "snop_month",
                        "actual_kl",
                        "actual_status",
                        "vintage_b_horizon_months",
                        "vintage_b_forecast_kl",
                        "vintage_b_absolute_error_kl",
                        "pair_status",
                    ]
                )
                .sort(
                    ["vintage_b_absolute_error_kl", "snop_month", "parent_code"],
                    descending=[True, False, False],
                    nulls_last=True,
                )
            )
        else:
            _table = (
                _table_source.select(
                    [
                        "source",
                        "parent_code",
                        "parent_description",
                        "brand_display",
                        "mapping_status",
                        "snop_month",
                        "actual_kl",
                        "actual_status",
                        "vintage_a_rule",
                        "vintage_a_calculation_month",
                        "vintage_a_horizon_months",
                        "vintage_a_forecast_kl",
                        "vintage_a_absolute_error_kl",
                        "vintage_a_bias_kl",
                        "vintage_b_rule",
                        "vintage_b_calculation_month",
                        "vintage_b_horizon_months",
                        "vintage_b_forecast_kl",
                        "vintage_b_absolute_error_kl",
                        "vintage_b_bias_kl",
                        "revision_kl",
                        "revision_pct",
                        "error_improvement_kl",
                        "revision_direction",
                        "revision_outcome",
                        "pair_status",
                    ]
                )
                .sort(
                    ["vintage_b_absolute_error_kl", "snop_month", "parent_code"],
                    descending=[True, False, False],
                    nulls_last=True,
                )
            )
        _table_note = (
            "Rows use the selected target months, products, brands, and one shared "
            "exact comparison horizon. Vintage A/B and revision filters are not "
            "applied in comparison mode."
            if view.filters.comparison_mode
            else "Rows use the selected source, target months, products, brands, "
            "horizons, vintage rules, revision filters, and tolerance."
        )
        _output = mo.vstack(
            [
                mo.md(
                    "## Filtered vintage table\n\n"
                    f"{_table_note} The table is sorted by largest Vintage B absolute error."
                ),
                mo.ui.table(_table, page_size=20),
            ]
        )
    mo.vstack([_output, _download, _brand_month_download])


@app.cell
def _(mo, pl, view):
    _population = view.filtered_population
    _pairs = view.coverage_pairs
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
