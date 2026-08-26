"""Source-aware forecast performance dashboard built on the canonical population."""

import marimo

__generated_with = "0.23.14"
app = marimo.App(width="full")


with app.setup:
    from datetime import datetime
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import polars as pl

    from forecast_analysis import (
        build_analysis_dataset,
        build_product_detail,
        load_analysis_inputs,
    )
    from forecast_analysis.contracts import (  # pyright: ignore[reportMissingImports]
        ACTUAL_REFERENCE_COLOR,
        SOURCE_COLORS,
        SOURCE_LABELS,
        VINTAGE_COLORS,
        VINTAGE_LABELS,
        ZERO_REFERENCE_COLOR,
    )
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

    def _latest_input_timestamp(paths):
        """Return the latest input file modification time for the header audit."""
        files = []
        for path in paths:
            if path.is_file():
                files.append(path)
            elif path.is_dir():
                files.extend(candidate for candidate in path.rglob("*") if candidate.is_file())
        if not files:
            return "unknown"
        latest = max(path.stat().st_mtime for path in files)
        return datetime.fromtimestamp(latest).astimezone().isoformat(timespec="seconds")

    DATA_REFRESH_TIMESTAMP = _latest_input_timestamp(
        [FORECAST_HISTORY_PATH, HIERARCHY_PATH, ACTUALS_PATH]
    )

    def with_source_labels(frame):
        """Add display labels without changing the canonical source column."""
        if "source" not in frame.columns:
            return frame
        return frame.with_columns(
            pl.when(pl.col("source") == "tm")
            .then(pl.lit(SOURCE_LABELS["tm"]))
            .when(pl.col("source") == "ml")
            .then(pl.lit(SOURCE_LABELS["ml"]))
            .otherwise(pl.col("source"))
            .alias("source_label")
        )

    def metric_audit_text(summary):
        """Explain ratio numerators, denominators, and observation policies."""
        ratio_denominator = format_metric(
            summary.accuracy_denominator_actual_kl,
            "KL",
        )
        accuracy_numerator = format_metric(summary.accuracy_numerator_kl, "KL")
        bias_numerator = format_metric(summary.bias_numerator_kl, "KL")
        coverage_numerator = format_metric(summary.coverage_numerator_actual_kl, "KL")
        coverage_denominator = format_metric(
            summary.coverage_denominator_actual_kl,
            "KL",
        )
        if summary.coverage_denominator_actual_kl is None:
            coverage_status = "Coverage is undefined because no selected actual-volume denominator exists"
        elif summary.coverage_denominator_actual_kl == 0:
            coverage_status = "Coverage is undefined because the selected actual-volume denominator is zero"
        elif summary.coverage_numerator_actual_kl == 0:
            coverage_status = (
                f"Coverage = {coverage_numerator} / {coverage_denominator}; "
                "no selected forecast represents a positive actual"
            )
        else:
            coverage_status = f"Coverage = {coverage_numerator} / {coverage_denominator}"
        ratio_status = (
            f"Accuracy = 1 − {accuracy_numerator} / {ratio_denominator}; "
            f"Bias = {bias_numerator} / {ratio_denominator}"
            if summary.accuracy_denominator_actual_kl not in (None, 0)
            else "Accuracy and bias are undefined because the positive-actual denominator is zero"
        )
        return (
            f"Eligible positive-actual observations: {summary.eligible_observations:,} · "
            f"absolute-error observations: {summary.absolute_error_observations:,} · "
            f"{ratio_status} · "
            f"MAE = {format_metric(summary.mae_kl, 'KL')} "
            f"({format_metric(summary.absolute_error_kl, 'KL')} / "
            f"{summary.mae_observations:,} observations) · "
            f"{coverage_status}"
        )

    def metric_card_context(summary, metric):
        """Return the shortest formula context appropriate for one KPI card."""
        if metric == "accuracy":
            return (
                f"{summary.eligible_observations:,} eligible · "
                f"1 − {format_metric(summary.accuracy_numerator_kl, 'KL')} / "
                f"{format_metric(summary.accuracy_denominator_actual_kl, 'KL')}"
            )
        if metric == "bias":
            return (
                f"{summary.eligible_observations:,} eligible · "
                f"{format_metric(summary.bias_numerator_kl, 'KL')} / "
                f"{format_metric(summary.bias_denominator_actual_kl, 'KL')}"
            )
        if metric == "absolute_error":
            return (
                f"{summary.absolute_error_observations:,} observations · "
                f"MAE {format_metric(summary.mae_kl, 'KL')}"
            )
        if metric == "coverage":
            return (
                f"{format_metric(summary.coverage_numerator_actual_kl, 'KL')} / "
                f"{format_metric(summary.coverage_denominator_actual_kl, 'KL')} actual KL"
            )
        return f"{summary.absolute_error_observations:,} measured observations"

    def population_summary_markdown(view):
        """Render the auditable population contract shared by every view."""
        if view.population_summary.height:
            summary = view.population_summary.row(0, named=True)
        else:
            summary = {
                "mode": "comparison" if view.filters.comparison_mode else "single_source",
                "sources": " + ".join(
                    SOURCE_LABELS.get(source) or source
                    for source in view.filters.selected_sources
                ),
                "target_range": "none selected",
                "horizons": "none selected",
                "products": 0,
                "forecast_rows": 0,
                "eligible_observations": 0,
                "comparable_pairs": 0,
                "actual_volume_kl": None,
                "coverage_pct": None,
                "coverage_numerator_actual_kl": None,
                "coverage_denominator_actual_kl": None,
                "coverage_scope": "selected_source_population",
            }
        mode = "TM vs ML comparison" if summary["mode"] == "comparison" else "Single source"
        source_coverage = ""
        if view.filters.comparison_mode:
            source_coverage = (
                f" · TM eligible: {summary.get('tm_eligible_observations') or 0:,} · "
                f"ML eligible: {summary.get('ml_eligible_observations') or 0:,} · "
                f"TM coverage: {format_metric(summary.get('tm_coverage_pct'), '%')} "
                f"({format_metric(summary.get('tm_coverage_numerator_actual_kl'), 'KL')} / "
                f"{format_metric(summary.get('tm_coverage_denominator_actual_kl'), 'KL')}) · "
                f"ML coverage: {format_metric(summary.get('ml_coverage_pct'), '%')} "
                f"({format_metric(summary.get('ml_coverage_numerator_actual_kl'), 'KL')} / "
                f"{format_metric(summary.get('ml_coverage_denominator_actual_kl'), 'KL')})"
            )
        coverage_scope = summary.get("coverage_scope") or "selected_source_population"
        coverage_label = (
            "Coverage (common aligned population)"
            if coverage_scope == "common_aligned_population"
            else "Coverage (selected source population)"
        )
        coverage_denominator = summary.get("coverage_denominator_actual_kl")
        if coverage_denominator is None:
            coverage = "undefined (no selected actual-volume denominator)"
        elif coverage_denominator == 0:
            coverage = "undefined (zero selected actual-volume denominator)"
        else:
            coverage = (
                f"{format_metric(summary.get('coverage_pct'), '%')} "
                f"({format_metric(summary.get('coverage_numerator_actual_kl'), 'KL')} / "
                f"{format_metric(coverage_denominator, 'KL')} actual KL)"
            )
        return (
            "## Population summary\n\n"
            f"**Data refresh (latest input modification):** `{DATA_REFRESH_TIMESTAMP}`\n\n"
            f"**Mode:** {mode} · **Source(s):** {summary['sources']} · "
            f"**Target range:** {summary['target_range']} · "
            f"**Horizons:** {summary['horizons']}\n\n"
            f"**Products:** {summary['products']:,} · **Forecast rows:** {summary['forecast_rows']:,} · "
            f"**Actual volume:** {format_metric(summary.get('actual_volume_kl'), 'KL')} · "
            f"**Eligible observations:** {summary['eligible_observations']:,} · "
            f"**Comparable pairs:** {summary['comparable_pairs']:,} · "
            f"**{coverage_label}:** {coverage}{source_coverage}"
        )

    def build_product_detail_controls(mo_module, products, target_months):
        """Construct detail dropdowns with Marimo option keys and domain values."""
        product_options = {
            f"{row['parent_code']} — {row['parent_description']}": row["parent_code"]
            for row in products
        }
        product_placeholder = "No products available"
        product_dropdown = mo_module.ui.dropdown(
            options=product_options or {product_placeholder: None},
            value=next(iter(product_options), product_placeholder),
            allow_select_none=True,
            searchable=True,
            label="Vintage history product (search code or description)",
        )

        target_month_options = {str(month): month for month in target_months}
        target_month_placeholder = "No target months available"
        target_month_dropdown = mo_module.ui.dropdown(
            options=target_month_options or {target_month_placeholder: None},
            value=next(iter(target_month_options), target_month_placeholder),
            allow_select_none=True,
            label="Vintage history target month",
        )
        return product_dropdown, target_month_dropdown

    def build_view_controls(mo_module):
        """Construct mapped view/source controls with display-key defaults."""
        comparison_mode_filter = mo_module.ui.dropdown(
            options={
                "Single source": "single",
                "Compare TM vs ML": "comparison",
            },
            value="Single source",
            label="View mode",
        )
        source_filter = mo_module.ui.dropdown(
            options={"TM": "tm", "ML": "ml"},
            value="TM",
            label="Forecast source (single-source mode)",
        )
        return comparison_mode_filter, source_filter

    def build_mapped_filter_controls(
        mo_module,
        horizons,
        default_horizons,
        calculation_months,
        horizon_label="Forecast horizon",
    ):
        """Construct mapped dashboard controls with key-based defaults."""
        horizon_options = {
            format_horizon_label(horizon): horizon for horizon in horizons
        }
        selected_horizon_keys = [
            key for key, value in horizon_options.items() if value in default_horizons
        ]
        horizon_filter = mo_module.ui.multiselect(
            options=horizon_options,
            value=selected_horizon_keys,
            label=horizon_label,
        )

        rule_options = {
            "Oldest available": "oldest_available",
            "Latest available": "latest_available",
            "Exact calculation month": "specific_calculation_month",
            "Exact horizon": "specific_horizon",
        }
        month_options = {
            str(month): month for month in calculation_months
        } or {"No calculation months available": None}
        exact_horizon_options = {
            format_horizon_label(horizon): horizon for horizon in horizons
        } or {"No horizons available": None}
        vintage_a_rule_filter = mo_module.ui.dropdown(
            options=rule_options,
            value="Oldest available",
            label="Vintage A rule",
        )
        vintage_b_rule_filter = mo_module.ui.dropdown(
            options=rule_options,
            value="Latest available",
            label="Vintage B rule",
        )
        vintage_a_month_filter = mo_module.ui.dropdown(
            options=month_options,
            value=next(iter(month_options)),
            label="Vintage A exact calculation month",
        )
        vintage_b_month_filter = mo_module.ui.dropdown(
            options=month_options,
            value=next(iter(month_options)),
            label="Vintage B exact calculation month",
        )
        vintage_a_horizon_filter = mo_module.ui.dropdown(
            options=exact_horizon_options,
            value=next(iter(exact_horizon_options)),
            label="Vintage A exact horizon",
        )
        vintage_b_horizon_filter = mo_module.ui.dropdown(
            options=exact_horizon_options,
            value=next(iter(exact_horizon_options)),
            label="Vintage B exact horizon",
        )
        direction_options = {
            "Up": "up",
            "Down": "down",
            "Unchanged": "unchanged",
        }
        revision_direction_filter = mo_module.ui.multiselect(
            options=direction_options,
            value=list(direction_options),
            label="Revision direction (active with comparable pairs)",
        )
        outcome_options = {
            "Improved": "improved",
            "Worsened": "worsened",
            "Neutral": "neutral",
        }
        revision_outcome_filter = mo_module.ui.multiselect(
            options=outcome_options,
            value=list(outcome_options),
            label="Revision outcome (active with comparable pairs)",
        )
        return (
            horizon_filter,
            vintage_a_rule_filter,
            vintage_b_rule_filter,
            vintage_a_month_filter,
            vintage_b_month_filter,
            vintage_a_horizon_filter,
            vintage_b_horizon_filter,
            revision_direction_filter,
            revision_outcome_filter,
        )

    # Backward-compatible module aliases for existing non-Marimo unit tests.
    _build_product_detail_controls = build_product_detail_controls
    _build_view_controls = build_view_controls
    _build_mapped_filter_controls = build_mapped_filter_controls


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
                "## Dashboard blocking input error\n\n"
                f"The canonical population could not be loaded: `{exc}`\n\n"
                "This input error blocks dashboard construction; hierarchy, actual, "
                "vintage-pair, and source-availability quality diagnostics are "
                "non-blocking issues shown only after valid inputs load."
            ),
        )
        raise RuntimeError("dashboard data loading stopped after displaying the error")
    return validated_dataset,


@app.cell
def _(mo, build_view_controls, reset_filters):
    _ = reset_filters.value
    comparison_mode_filter, source_filter = build_view_controls(mo)
    mo.hstack([comparison_mode_filter, source_filter], justify="start")
    return comparison_mode_filter, source_filter


@app.cell
def _(mo):
    reset_filters = mo.ui.button(
        label="Reset all filters",
        tooltip="Recreate every filter with its approved default value.",
    )
    mo.hstack([reset_filters], justify="start")
    return reset_filters,


@app.cell
def _(
    validated_dataset,
    mo,
    pl,
    build_mapped_filter_controls,
    source_filter,
    comparison_mode_filter,
    available_filter_values,
    reset_filters,
):
    _ = reset_filters.value
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
    _performance_enabled = _comparison_mode or (
        validated_dataset.frame
        .filter(
            (pl.col("source") == source_filter.value)
            & (pl.col("actual_status") == "matched_positive")
        )
        .group_by(["parent_code", "snop_month"])
        .len()
        .filter(pl.col("len") >= 2)
        .height
        > 0
    )

    target_month_filter = mo.ui.date_range(
        start=_target_months[0] if _target_months else None,
        stop=_target_months[-1] if _target_months else None,
        value=(
            (_target_months[0], _target_months[-1])
            if _target_months
            else None
        ),
        label="Target month range",
    )
    brand_filter = mo.ui.multiselect(
        options=_brands,
        value=_brands,
        label="Brand",
    )
    _product_options = {
        f"{row['parent_code']} — {row['parent_description']}": row["parent_code"]
        for row in _products
    }
    product_filter = mo.ui.multiselect(
        options=_product_options,
        value=list(_product_options),
        label="Parent product",
    )
    _default_horizons = (
        [_options["default_comparison_horizon"]]
        if _comparison_mode and _options["default_comparison_horizon"] is not None
        else _horizons
    )
    (
        horizon_filter,
        vintage_a_rule_filter,
        vintage_b_rule_filter,
        vintage_a_month_filter,
        vintage_b_month_filter,
        vintage_a_horizon_filter,
        vintage_b_horizon_filter,
        revision_direction_filter,
        revision_outcome_filter,
    ) = build_mapped_filter_controls(
        mo,
        _horizons,
        _default_horizons,
        _calculation_months,
        horizon_label=(
            "Comparison horizon (exact)" if _comparison_mode else "Forecast horizon"
        ),
    )
    minimum_actual_filter = mo.ui.number(
        value=0,
        start=0,
        step=1,
        label="Minimum actual volume (KL)",
    )
    forecast_direction_filter = mo.ui.multiselect(
        options={
            "Over forecast": "over",
            "Under forecast": "under",
            "Within tolerance": "within_tolerance",
        },
        value=["Over forecast", "Under forecast", "Within tolerance"],
        label="Forecast direction",
        disabled=_comparison_mode or not _performance_enabled,
    )
    accuracy_band_filter = mo.ui.dropdown(
        options=["All", "Below 0%", "0–50%", "50–100%", "Above 100%"],
        value="All",
        label="Vintage B accuracy band",
        disabled=_comparison_mode or not _performance_enabled,
    )
    bias_band_filter = mo.ui.dropdown(
        options=["All", "Below 0%", "0–50%", "Above 50%"],
        value="All",
        label="Vintage B bias band",
        disabled=_comparison_mode or not _performance_enabled,
    )
    minimum_absolute_error_filter = mo.ui.number(
        value=0,
        start=0,
        step=0.1,
        label="Minimum Vintage B absolute error (KL)",
        disabled=_comparison_mode or not _performance_enabled,
    )
    top_n_filter = mo.ui.number(
        value=0,
        start=0,
        step=1,
        label="Top N product-target exceptions",
        disabled=_comparison_mode or not _performance_enabled,
    )
    top_n_metric_filter = mo.ui.dropdown(
        options=[
            "Actual volume",
            "Absolute error",
            "Deterioration (worst error improvement)",
        ],
        value="Actual volume",
        label="Top N ranking",
        disabled=_comparison_mode or not _performance_enabled,
    )

    _hierarchy_status_options = {
        "Mapped": "mapped",
        "Unmapped": "unmapped",
        "Hierarchy conflict": "conflict",
    }
    _actual_status_options = {
        "Positive actual": "matched_positive",
        "Zero actual": "matched_zero",
        "Missing actual": "missing",
    }
    _pair_status_options = {
        "Complete pair": "complete",
        "Missing Vintage A": "missing_a",
        "Missing Vintage B": "missing_b",
        "Missing both vintages": "missing_both",
        "Missing actual": "missing_actual",
        "Zero actual": "zero_actual",
    }
    _source_availability_options = (
        {
            "TM only": "tm_only",
            "ML only": "ml_only",
            "Both sources": "both_sources",
        }
        if _comparison_mode
        else (
            {"TM only": "tm_only", "Both sources": "both_sources"}
            if source_filter.value == "tm"
            else {"ML only": "ml_only", "Both sources": "both_sources"}
        )
    )
    hierarchy_status_filter = mo.ui.multiselect(
        options=_hierarchy_status_options,
        value=list(_hierarchy_status_options),
        label="Hierarchy quality status",
    )
    actual_status_filter = mo.ui.multiselect(
        options=_actual_status_options,
        value=list(_actual_status_options),
        label="Actual quality status",
    )
    pair_status_filter = mo.ui.multiselect(
        options=_pair_status_options,
        value=list(_pair_status_options),
        label="Vintage-pair quality status",
    )
    source_availability_filter = mo.ui.multiselect(
        options=_source_availability_options,
        value=list(_source_availability_options),
        label="Source availability",
    )
    zero_forecast_filter = mo.ui.checkbox(
        value=False,
        label="Zero forecasts only",
    )
    complete_history_filter = mo.ui.checkbox(
        value=False,
        label="Complete vintage history only",
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
        ),
    ]
    _controls.extend(
        [
            mo.accordion(
                {
                    "Data-quality filters": mo.vstack(
                        [
                            mo.md(
                                "Quality filters narrow the active quality counts and "
                                "exception downloads. The baseline scope below retains "
                                "the shared selection before quality, revision, "
                                "performance, and volume exclusions, so its scope "
                                "exclusions explain removed rows without changing the "
                                "active counts. Zero-forecast and complete-history "
                                "filters restrict the actual denominator to surviving "
                                "product-target keys. Complete history means a forecast "
                                "exists at every horizon currently selected."
                            ),
                            mo.hstack(
                                [
                                    hierarchy_status_filter,
                                    actual_status_filter,
                                    pair_status_filter,
                                    source_availability_filter,
                                ],
                                widths="equal",
                            ),
                            mo.hstack(
                                [zero_forecast_filter, complete_history_filter],
                                widths="equal",
                            ),
                        ]
                    )
                }
            )
        ]
    )
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
    _controls.extend(
        [
            mo.md("### Performance filters"),
            mo.hstack(
                [
                    forecast_direction_filter,
                    accuracy_band_filter,
                    bias_band_filter,
                    minimum_absolute_error_filter,
                    top_n_filter,
                    top_n_metric_filter,
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
        forecast_direction_filter,
        accuracy_band_filter,
        bias_band_filter,
        minimum_absolute_error_filter,
        top_n_filter,
        top_n_metric_filter,
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
        hierarchy_status_filter,
        actual_status_filter,
        pair_status_filter,
        source_availability_filter,
        zero_forecast_filter,
        complete_history_filter,
    )


@app.cell
def _(
    build_product_detail_controls,
    mo,
    reset_filters,
    view,
):
    _ = reset_filters.value
    _detail_scope = view.vintage_pairs
    if _detail_scope.height:
        _detail_products = (
            _detail_scope.select(["parent_code", "parent_description"])
            .unique()
            .sort(["parent_code", "parent_description"])
            .to_dicts()
        )
        _detail_target_months = _detail_scope["snop_month"].unique().sort().to_list()
    else:
        _detail_products = []
        _detail_target_months = []
    product_detail_filter, product_detail_target_month_filter = (
        build_product_detail_controls(
            mo,
            _detail_products,
            _detail_target_months,
        )
    )
    mo.vstack(
        [
            mo.md(
                "### Product vintage history\n\n"
                "Options are limited to the current shared population; selecting a product or month can only narrow it."
            ),
            mo.hstack(
                [product_detail_filter, product_detail_target_month_filter],
                widths="equal",
            ),
        ]
    )
    return product_detail_filter, product_detail_target_month_filter


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
    forecast_direction_filter,
    accuracy_band_filter,
    bias_band_filter,
    minimum_absolute_error_filter,
    top_n_filter,
    top_n_metric_filter,
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
    hierarchy_status_filter,
    actual_status_filter,
    pair_status_filter,
    source_availability_filter,
    zero_forecast_filter,
    complete_history_filter,
    comparison_mode_filter,
    available_filter_values,
):
    _comparison_mode = comparison_mode_filter.value == "comparison"
    _available_target_months = available_filter_values(
        validated_dataset.frame,
        source_filter.value,
        comparison_mode=_comparison_mode,
    )["target_months"]
    _target_range = target_month_filter.value
    _target_months = (
        tuple(
            month
            for month in _available_target_months
            if _target_range[0] <= month <= _target_range[1]
        )
        if _target_range is not None
        else tuple()
    )

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
    _selected_hierarchy_statuses = _all_or_selected(
        hierarchy_status_filter.value,
        ("mapped", "unmapped", "conflict"),
    )
    _selected_actual_statuses = _all_or_selected(
        actual_status_filter.value,
        ("matched_positive", "matched_zero", "missing"),
    )
    _selected_pair_statuses = _all_or_selected(
        pair_status_filter.value,
        ("complete", "missing_a", "missing_b", "missing_both", "missing_actual", "zero_actual"),
    )
    _source_availability_values = (
        ("tm_only", "ml_only", "both_sources")
        if _comparison_mode
        else (
            ("tm_only", "both_sources")
            if source_filter.value == "tm"
            else ("ml_only", "both_sources")
        )
    )
    _selected_source_availability = _all_or_selected(
        source_availability_filter.value,
        _source_availability_values,
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
    _selected_forecast_directions = (
        None
        if _comparison_mode
        or set(forecast_direction_filter.value) == {
            "over",
            "under",
            "within_tolerance",
        }
        else tuple(forecast_direction_filter.value)
    )
    _accuracy_band_values = {
        "Below 0%": (-1_000_000.0, 0.0),
        "0–50%": (0.0, 50.0),
        "50–100%": (50.0, 100.0),
        "Above 100%": (100.0, 1_000_000.0),
    }
    _bias_band_values = {
        "Below 0%": (-1_000_000.0, 0.0),
        "0–50%": (0.0, 50.0),
        "Above 50%": (50.0, 1_000_000.0),
    }
    _selected_accuracy_band = (
        None
        if _comparison_mode or accuracy_band_filter.value == "All"
        else _accuracy_band_values[accuracy_band_filter.value]
    )
    _selected_bias_band = (
        None
        if _comparison_mode or bias_band_filter.value == "All"
        else _bias_band_values[bias_band_filter.value]
    )
    try:
        _top_n = (
            None
            if _comparison_mode or not top_n_filter.value or top_n_filter.value < 1
            else int(top_n_filter.value)
        )
    except (TypeError, ValueError, OverflowError):
        _top_n = None
    _top_n_metric = {
        "Actual volume": "actual_volume",
        "Absolute error": "absolute_error",
        "Deterioration (worst error improvement)": "deterioration",
    }[top_n_metric_filter.value]
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
        target_months=_target_months,
        brands=tuple(brand_filter.value),
        parent_codes=tuple(product_filter.value),
        horizons=tuple(horizon_filter.value),
        minimum_actual_volume=minimum_actual_filter.value or 0,
        hierarchy_statuses=_selected_hierarchy_statuses,
        actual_statuses=_selected_actual_statuses,
        pair_statuses=_selected_pair_statuses,
        source_availability=_selected_source_availability,
        zero_forecast_only=zero_forecast_filter.value,
        complete_vintage_history_only=complete_history_filter.value,
        revision_tolerance_kl=_revision_tolerance,
        forecast_directions=_selected_forecast_directions,
        forecast_accuracy_band=_selected_accuracy_band,
        bias_band=_selected_bias_band,
        minimum_absolute_error_kl=minimum_absolute_error_filter.value or 0,
        top_n=_top_n,
        top_n_metric=_top_n_metric,
    )
    base_view = build_dashboard_view(
        validated_dataset.frame,
        validated_dataset.actual_population,
        base_filters,
        vintage_a=vintage_a,
        vintage_b=vintage_b,
        hierarchy_diagnostics=validated_dataset.hierarchy_diagnostics,
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
        target_months=_target_months,
        brands=tuple(brand_filter.value),
        parent_codes=tuple(product_filter.value),
        horizons=tuple(horizon_filter.value),
        minimum_actual_volume=minimum_actual_filter.value or 0,
        hierarchy_statuses=_selected_hierarchy_statuses,
        actual_statuses=_selected_actual_statuses,
        pair_statuses=_selected_pair_statuses,
        source_availability=_selected_source_availability,
        zero_forecast_only=zero_forecast_filter.value,
        complete_vintage_history_only=complete_history_filter.value,
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
        forecast_directions=_selected_forecast_directions,
        forecast_accuracy_band=_selected_accuracy_band,
        bias_band=_selected_bias_band,
        minimum_absolute_error_kl=minimum_absolute_error_filter.value or 0,
        top_n=_top_n,
        top_n_metric=_top_n_metric,
    )
    view = build_dashboard_view(
        validated_dataset.frame,
        validated_dataset.actual_population,
        filters,
        vintage_a=vintage_a,
        vintage_b=vintage_b,
        hierarchy_diagnostics=validated_dataset.hierarchy_diagnostics,
    )
    return comparison_ready, filters, view


@app.cell
def _(
    build_product_detail,
    filters,
    product_detail_filter,
    product_detail_target_month_filter,
    validated_dataset,
    view,
):
    _parent_code = product_detail_filter.value
    _target_month = product_detail_target_month_filter.value
    product_history_error = None
    if (
        _parent_code is None
        or _target_month is None
        or not isinstance(_parent_code, int)
        or isinstance(_parent_code, bool)
    ):
        product_history = None
    else:
        try:
            product_history = build_product_detail(
                validated_dataset.frame,
                filters,
                _parent_code,
                _target_month,
                active_key_frame=view.vintage_pairs,
            )
        except ValueError as exc:
            product_history = None
            product_history_error = str(exc)
    return product_history, product_history_error


@app.cell
def _(
    ACTUAL_REFERENCE_COLOR,
    SOURCE_COLORS,
    SOURCE_LABELS,
    VINTAGE_COLORS,
    VINTAGE_LABELS,
    with_source_labels,
    alt,
    filters,
    mo,
    pl,
    product_history,
    product_history_error,
):
    if product_history_error is not None:
        _output = mo.md(
            "## Product vintage history\n\n"
            f"⚠️ {product_history_error}."
        )
    elif product_history is None:
        _output = mo.md(
            "## Product vintage history\n\n"
            "Select a product and target month to inspect forecast development."
        )
    elif product_history.points.height == 0:
        _output = mo.vstack(
            [
                mo.md(
                    f"## Product vintage history\n\n"
                    f"No {', '.join(source.upper() for source in product_history.sources)} "
                    f"vintage is available for parent product `{product_history.parent_code}` "
                    f"and target month `{product_history.target_month}` under the active filters."
                ),
                mo.ui.table(product_history.stability, page_size=10),
            ]
        )
    else:
        _title = (
            f"## Product vintage history — {product_history.parent_code} · "
            f"{product_history.target_month}"
        )
        _metadata = (
            f"**Description:** {product_history.parent_description or '—'} · "
            f"**Brand:** {product_history.brand or 'Unmapped'} · "
            f"**Mapping:** {product_history.mapping_status or '—'} · "
            f"**Actual:** {product_history.actual_kl if product_history.actual_kl is not None else '—'} KL"
        )
        _scope_note = (
            "Comparison mode uses the shared exact horizon; TM and ML remain separate "
            "legend series."
            if filters.comparison_mode
            else "History respects the selected source and forecast-horizon filters."
        )
        _status_notes = [
            mo.md(
                f"{_title}\n\n{_metadata}\n\n{product_history.status_message}\n\n{_scope_note}"
            )
        ]
        _insufficient = product_history.stability.filter(
            pl.col("history_status") != "ready"
        )
        if _insufficient.height:
            _status_notes.append(
                mo.md(
                    "\n".join(
                        f"> ⚠️ **{row['source'].upper()}:** {row['history_message']}"
                        for row in _insufficient.iter_rows(named=True)
                    )
                )
            )

        _points = with_source_labels(product_history.points)
        _source_scale = alt.Scale(
            domain=[SOURCE_LABELS["tm"], SOURCE_LABELS["ml"]],
            range=[SOURCE_COLORS["tm"], SOURCE_COLORS["ml"]],
        )
        _forecast_chart = (
            alt.Chart(_points.to_pandas())
            .mark_line(point=True, strokeWidth=2.5)
            .encode(
                x=alt.X("calculation_month:T", title="Calculation month"),
                y=alt.Y("forecast_kl:Q", title="Forecast (KL)"),
                color=alt.Color(
                    "source_label:N",
                    title="Forecast source",
                    scale=_source_scale,
                ),
                tooltip=[
                    alt.Tooltip("source_label:N", title="Source"),
                    alt.Tooltip("calculation_month:T", title="Calculation month"),
                    alt.Tooltip(
                        "forecast_horizon_months:Q",
                        title="Forecast horizon (months)",
                        format=",.0f",
                    ),
                    alt.Tooltip("forecast_kl:Q", title="Forecast quantity (KL)", format=",.3f"),
                    alt.Tooltip("actual_kl:Q", title="Actual quantity (KL)", format=",.3f"),
                    alt.Tooltip("error_kl:Q", title="Error (KL)", format=",.3f"),
                    alt.Tooltip("bias_pct:Q", title="Bias (%)", format=",.2f"),
                ],
            )
            .properties(height=360)
        )
        _actual_reference = product_history.actual_reference.filter(
            pl.col("actual_kl").is_not_null()
        )
        _chart = _forecast_chart
        if _actual_reference.height:
            _actual_chart = (
                alt.Chart(_actual_reference.to_pandas())
                .mark_rule(color=ACTUAL_REFERENCE_COLOR, strokeDash=[6, 4])
                .encode(
                    y=alt.Y("actual_kl:Q", title="Forecast / actual (KL)"),
                    tooltip=[
                        alt.Tooltip("actual_kl:Q", title="Actual quantity (KL)", format=",.3f"),
                        alt.Tooltip("actual_status:N", title="Actual status"),
                    ],
                )
            )
            _chart = _forecast_chart + _actual_chart

        _audit_columns = [
            "source_label",
            "calculation_month",
            "forecast_horizon_months",
            "forecast_kl",
            "actual_kl",
            "error_kl",
            "bias_pct",
            "actual_status",
        ]
        _revision_table = (
            mo.ui.table(with_source_labels(product_history.revisions), page_size=20)
            if product_history.revisions.height
            else mo.md("No consecutive revisions are available in the selected history.")
        )
        _output = mo.vstack(
            [
                *_status_notes,
                mo.ui.altair_chart(_chart, chart_selection=False, legend_selection=False),
                mo.md(
                    "### Point audit\n\n"
                    "Every plotted point retains its calculation month, horizon, forecast, actual, error, and bias. "
                    f"Actual reference = `{ACTUAL_REFERENCE_COLOR}`; source colors are stable across views. "
                    f"{VINTAGE_LABELS['a']} / {VINTAGE_LABELS['b']} are reserved for paired vintage evidence "
                    f"({VINTAGE_COLORS['a']} / {VINTAGE_COLORS['b']})."
                ),
                mo.ui.table(_points.select(_audit_columns), page_size=20),
                mo.md("### Consecutive source-specific revisions"),
                _revision_table,
                mo.md("### Source-specific stability"),
                mo.ui.table(product_history.stability, page_size=10),
            ]
        )
    mo.vstack([_output])


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
    metric_audit_text,
    population_summary_markdown,
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
    _standard_output = mo.vstack(
        [
            mo.md(
                f"""# Forecast performance — {filters.source.upper()}

**Selected month range:** `{_month_label}` · **Selected horizons:** `{_horizon_label}` · **Selected pair rows:** `{view.vintage_pairs.height:,}`

**Vintage rules:** Vintage A = `{_rules['vintage_a_rule']}` · Vintage B = `{_rules['vintage_b_rule']}` · **Complete pairs:** `{_m.complete_pairs:,}` · **Missing vintages:** `{_m.missing_vintage_pairs:,}` · **Missing actuals:** `{_m.missing_actual_observations:,}` · **Zero actuals:** `{_m.zero_actual_observations:,}`

**Revision policy:** tolerance `{format_revision_tolerance(filters.revision_tolerance_kl)}`; revisions above tolerance are **up**, below negative tolerance are **down**, and the remainder are **unchanged**. Error improvement above, below, or within the same tolerance is **improved**, **worsened**, or **neutral**. {_revision_filter_message}"""
            ),
            mo.md(
                "### Metric audit context\n\n"
                + metric_audit_text(_m)
                + "\n\nAll ratio metrics use aggregate numerators and positive-actual denominators; zero and missing actuals remain visible but do not create ratio denominators."
            ),
        ]
    )
    mo.vstack(
        [
            mo.md(population_summary_markdown(view)),
            _comparison_output if filters.comparison_mode else _standard_output,
        ]
    )


@app.cell
def _(format_metric, mo, view, metric_card_context, metric_audit_text):
    _comparison_output = None
    if view.filters.comparison_mode and view.comparison is not None:
        _comparison = view.comparison

        def _source_card(label, summary):
            return mo.md(
                f"**{label}**\n\n"
                f"Accuracy (%): **{format_metric(summary.forecast_accuracy_pct, '%')}**  \n"
                f"Bias (%): **{format_metric(summary.bias_pct, '%')}**  \n"
                f"Absolute error (KL): **{format_metric(summary.absolute_error_kl, 'KL')}**  \n"
                f"MAE (KL): **{format_metric(summary.mae_kl, 'KL')}**  \n"
                f"Aligned-horizon coverage (%): **{format_metric(summary.coverage_pct, '%')}**  \n"
                f"Common actual (KL): `{format_metric(summary.actual_kl, 'KL')}` · "
                f"Common forecast (KL): `{format_metric(summary.forecast_kl, 'KL')}`  \n"
                f"{metric_audit_text(summary)}"
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
        if _comparison.blocked:
            _comparison_output = mo.md(
                "## Comparison unavailable\n\n"
                f"⚠️ {_comparison.warning or 'TM and ML cannot be aligned in the current selection.'}\n\n"
                "No source KPI delta is shown until both sources share one exact horizon. "
                "The population and quality panels below remain available for diagnosis."
            )
        else:
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
        "No forecast rows match the active filters"
        if view.filtered_population.height == 0
        else "No selected vintage pairs remain after the active pair/performance filters"
        if view.vintage_pairs.height == 0
        else "No selected exact vintage pair is complete"
        if _m.complete_pairs == 0 and _m.missing_vintage_pairs > 0
        else "No positive actuals; accuracy and bias are undefined"
        if _m.eligible_observations == 0 and _m.absolute_error_observations == 0
        else f"{_m.eligible_observations:,} eligible observations"
    )
    _cards = [
        mo.md(
            f"**Forecast accuracy (%)**\n\n## {format_metric(_m.forecast_accuracy_pct, '%')}\n\n{metric_card_context(_m, 'accuracy')}\n\n{_empty_reason}"
        ),
        mo.md(
            f"**Bias (%)**\n\n## {format_metric(_m.bias_pct, '%')}\n\n{metric_card_context(_m, 'bias')}\n\n{_empty_reason}"
        ),
        mo.md(
            f"**Absolute error (KL)**\n\n## {format_metric(_m.absolute_error_kl, 'KL')}\n\n{metric_card_context(_m, 'absolute_error')}\n\n{_empty_reason}"
        ),
        mo.md(
            f"**MAE (KL)**\n\n## {format_metric(_m.mae_kl, 'KL')}\n\n{_m.mae_observations:,} observations\n\n{_empty_reason}"
        ),
        mo.md(
            f"**Actual volume (KL)**\n\n## {format_metric(_m.actual_kl, 'KL')}\n\n{_m.absolute_error_observations:,} measured observations\n\n{_empty_reason}"
        ),
        mo.md(
            f"**Forecast volume (KL)**\n\n## {format_metric(_m.forecast_kl, 'KL')}\n\n{_m.absolute_error_observations:,} measured observations\n\n{_empty_reason}"
        ),
        mo.md(
            f"**Coverage (%)**\n\n## {format_metric(_m.coverage_pct, '%')}\n\n{metric_card_context(_m, 'coverage')}\n\n{_empty_reason}"
        ),
        mo.md(
            f"**Eligible observations (count)**\n\n## {format_metric(_m.eligible_observations, 'count')}\n\nPositive-actual rows\n\n{_empty_reason}"
        ),
    ]
    if _m.complete_pairs:
        _cards.extend(
            [
                mo.md(
                    f"**Accuracy delta (pp)**\n\n## {format_metric(_m.accuracy_delta_pp, 'pp')}\n\n{_m.complete_pairs:,} complete positive-actual comparisons · "
                    f"{format_metric(_m.accuracy_delta_numerator_kl, 'KL')} error improvement / "
                    f"{format_metric(_m.accuracy_delta_denominator_actual_kl, 'KL')} actual denominator"
                ),
                mo.md(
                    f"**Revision effectiveness (%)**\n\n## {format_metric(_m.revision_effectiveness_pct, '%')}\n\n"
                    f"{_m.effectiveness_numerator:,} improved / {_m.effectiveness_denominator:,} materially revised"
                ),
                mo.md(
                    f"**Total error improvement (KL)**\n\n## {format_metric(_m.total_error_improvement_kl, 'KL')}\n\n{_m.complete_pairs:,} complete positive-actual comparisons · Positive values improve error"
                ),
            ]
        )
    _standard_output = mo.hstack(_cards, widths="equal")
    _comparison_output if view.filters.comparison_mode else _standard_output


@app.cell
def _(alt, mo, pl, view):
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
        _paired_scatter_data = _paired.filter(
            pl.col("tm_absolute_error_kl").is_not_null()
            & pl.col("ml_absolute_error_kl").is_not_null()
        )
        if _paired_scatter_data.height:
            _scatter = (
                alt.Chart(_paired_scatter_data.to_pandas())
                .mark_circle(opacity=0.75)
                .encode(
                    x=alt.X(
                        "tm_absolute_error_kl:Q",
                        title="TM absolute error (KL)",
                    ),
                    y=alt.Y(
                        "ml_absolute_error_kl:Q",
                        title="ML absolute error (KL)",
                    ),
                    color=alt.Color("winner_label:N", title="Winner"),
                    tooltip=[
                        alt.Tooltip("parent_code:Q", title="Parent product"),
                        alt.Tooltip("snop_month:T", title="Target month"),
                        alt.Tooltip("actual_kl:Q", title="Actual KL", format=",.1f"),
                        alt.Tooltip("tm_forecast_kl:Q", title="TM forecast KL", format=",.1f"),
                        alt.Tooltip("ml_forecast_kl:Q", title="ML forecast KL", format=",.1f"),
                        alt.Tooltip("tm_absolute_error_kl:Q", title="TM absolute error KL", format=",.1f"),
                        alt.Tooltip("ml_absolute_error_kl:Q", title="ML absolute error KL", format=",.1f"),
                        alt.Tooltip("winner_label:N", title="Winner"),
                    ],
                )
                .properties(height=360)
            )
            _scatter_output = mo.ui.altair_chart(
                _scatter,
                chart_selection=False,
                legend_selection=False,
            )
        else:
            _scatter_output = mo.md(
                "No complete common-source error observations are available for the paired scatter plot."
            )
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
                mo.md("### Paired absolute-error scatter\n\nPoints above the diagonal favor TM; points below favor ML."),
                _scatter_output,
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
        value="Forecast accuracy",
        label="Monthly performance metric",
    )
    mo.hstack([monthly_metric], justify="start")
    return monthly_metric,


@app.cell
def _(
    SOURCE_COLORS,
    SOURCE_LABELS,
    with_source_labels,
    ZERO_REFERENCE_COLOR,
    alt,
    monthly_metric,
    mo,
    pl,
    view,
):
    _monthly = with_source_labels(view.monthly_audit)
    _source_scale = alt.Scale(
        domain=[SOURCE_LABELS["tm"], SOURCE_LABELS["ml"]],
        range=[SOURCE_COLORS["tm"], SOURCE_COLORS["ml"]],
    )
    if _monthly.height == 0:
        _output = mo.md("### Monthly performance\n\nNo target months remain in this selection.")
    elif monthly_metric.value == "forecast_vs_actual":
        _chart_data = _monthly.unpivot(
            on=["actual_kl", "forecast_kl"],
            index=["source", "source_label", "snop_month", "eligible_observations"],
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
                alt.Color("source_label:N", title="Source", scale=_source_scale)
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
                        "source_label:N",
                        alt.Tooltip("snop_month:T", title="Target month"),
                        "series:N",
                        alt.Tooltip("value:Q", title="Volume (KL)", format=",.1f"),
                        alt.Tooltip("eligible_observations:Q", title="Eligible observations"),
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
                        "source_label:N",
                        title="Source",
                        scale=_source_scale,
                    ),
                    tooltip=[
                        alt.Tooltip("source_label:N", title="Source"),
                        alt.Tooltip("snop_month:T", title="Target month"),
                        alt.Tooltip(_column + ":Q", title=_title, format=",.1f"),
                        alt.Tooltip("actual_kl:Q", title="Actual KL", format=",.1f"),
                        alt.Tooltip("forecast_kl:Q", title="Forecast KL", format=",.1f"),
                        alt.Tooltip(
                            "accuracy_numerator_kl:Q",
                            title="Accuracy numerator · absolute error KL",
                            format=",.1f",
                        ),
                        alt.Tooltip(
                            "accuracy_denominator_actual_kl:Q",
                            title="Accuracy denominator · positive actual KL",
                            format=",.1f",
                        ),
                        alt.Tooltip(
                            "bias_numerator_kl:Q",
                            title="Bias numerator · net error KL",
                            format=",.1f",
                        ),
                        alt.Tooltip(
                            "bias_denominator_actual_kl:Q",
                            title="Bias denominator · positive actual KL",
                            format=",.1f",
                        ),
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
            if monthly_metric.value in {"accuracy", "bias"}:
                _zero_rule = (
                    alt.Chart(pl.DataFrame({"baseline": [0.0]}).to_pandas())
                    .mark_rule(color=ZERO_REFERENCE_COLOR, strokeDash=[5, 4])
                    .encode(y=alt.Y("baseline:Q", title=_title))
                )
                _plot = _chart + _zero_rule
            _output = mo.ui.altair_chart(
                _plot, chart_selection=False, legend_selection=False
            )
    mo.vstack(
        [
            mo.md(
                "## Monthly performance\n\n"
                "Values are aggregate, volume-weighted metrics for the selected population. "
                "Accuracy = 1 − absolute error KL / positive-actual KL; bias = net error KL / positive-actual KL. "
                "Signed metrics include a visible zero reference."
            ),
            _output,
        ]
    )


@app.cell
def _(mo):
    horizon_metric = mo.ui.dropdown(
        options={
            "Forecast accuracy": "accuracy",
            "Bias": "bias",
        },
        value="Forecast accuracy",
        label="Horizon performance metric",
    )
    mo.hstack([horizon_metric], justify="start")
    return horizon_metric,


@app.cell
def _(
    SOURCE_COLORS,
    SOURCE_LABELS,
    ZERO_REFERENCE_COLOR,
    with_source_labels,
    alt,
    horizon_metric,
    mo,
    pl,
    view,
):
    _horizon = with_source_labels(view.horizon_audit)
    _source_scale = alt.Scale(
        domain=[SOURCE_LABELS["tm"], SOURCE_LABELS["ml"]],
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
                    "source_label:N",
                    title="Source",
                    scale=_source_scale,
                ),
                tooltip=[
                    alt.Tooltip("source_label:N", title="Source"),
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
                        "absolute_error_kl:Q",
                        title="Absolute error KL",
                        format=",.1f",
                    ),
                    alt.Tooltip(
                        "coverage_pct:Q", title="Coverage (%)", format=",.1f"
                    ),
                    alt.Tooltip(
                        "accuracy_numerator_kl:Q",
                        title="Accuracy numerator · absolute error KL",
                        format=",.1f",
                    ),
                    alt.Tooltip(
                        "accuracy_denominator_actual_kl:Q",
                        title="Accuracy denominator · positive actual KL",
                        format=",.1f",
                    ),
                    alt.Tooltip(
                        "bias_numerator_kl:Q",
                        title="Bias numerator · net error KL",
                        format=",.1f",
                    ),
                    alt.Tooltip(
                        "bias_denominator_actual_kl:Q",
                        title="Bias denominator · positive actual KL",
                        format=",.1f",
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
        if horizon_metric.value in {"accuracy", "bias"}:
            _zero_rule = (
                alt.Chart(pl.DataFrame({"baseline": [0.0]}).to_pandas())
                .mark_rule(color=ZERO_REFERENCE_COLOR, strokeDash=[5, 4])
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
        value="Forecast accuracy",
        label="Brand × target-month metric",
    )
    mo.hstack([brand_month_metric], justify="start")
    return brand_month_metric,


@app.cell
def _(
    SOURCE_LABELS,
    with_source_labels,
    alt,
    brand_month_metric,
    brand_target_metric_definition,
    brand_target_month_order,
    mo,
    pl,
    view,
):
    _heatmap = with_source_labels(view.brand_target_month_performance)
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
                    "vintage_a_absolute_error_kl:Q",
                    title="Vintage A accuracy numerator · absolute error KL",
                    format=",.1f",
                ),
                alt.Tooltip(
                    "vintage_a_actual_kl:Q",
                    title="Vintage A accuracy denominator · positive actual KL",
                    format=",.1f",
                ),
                alt.Tooltip(
                    "vintage_a_eligible_observations:Q",
                    title="Vintage A eligible observations",
                    format=",.0f",
                ),
            ]
        elif brand_month_metric.value == "forecast_accuracy":
            _count_tooltips = [
                alt.Tooltip(
                    "vintage_b_absolute_error_kl:Q",
                    title="Accuracy numerator · absolute error KL",
                    format=",.1f",
                ),
                alt.Tooltip(
                    "vintage_b_actual_kl:Q",
                    title="Accuracy denominator · positive actual KL",
                    format=",.1f",
                ),
                alt.Tooltip(
                    "vintage_b_eligible_observations:Q",
                    title="Vintage B eligible observations",
                    format=",.0f",
                ),
            ]
        elif brand_month_metric.value == "bias":
            _count_tooltips = [
                alt.Tooltip(
                    "vintage_b_net_error_kl:Q",
                    title="Bias numerator · net error KL",
                    format=",.1f",
                ),
                alt.Tooltip(
                    "vintage_b_actual_kl:Q",
                    title="Bias denominator · positive actual KL",
                    format=",.1f",
                ),
                alt.Tooltip(
                    "vintage_b_eligible_observations:Q",
                    title="Vintage B eligible observations",
                    format=",.0f",
                ),
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
                    alt.Tooltip("source_label:N", title="Source"),
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
                    "source_label:N",
                    title="Source",
                    sort=[SOURCE_LABELS["tm"], SOURCE_LABELS["ml"]],
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
def _(
    SOURCE_COLORS,
    SOURCE_LABELS,
    ZERO_REFERENCE_COLOR,
    with_source_labels,
    alt,
    format_metric,
    mo,
    pl,
    view,
):
    _diagnostics = view.revision_diagnostics
    _m = view.metrics
    _summary_table = mo.ui.table(_diagnostics, page_size=4)
    if view.revision_scatter.height == 0:
        _chart_output = mo.md(
            "No complete positive-actual vintage pairs remain for the revision scatter plot."
        )
    else:
        _scatter = with_source_labels(view.revision_scatter)
        _color = (
            alt.Color(
                "source_label:N",
                title="Source",
                scale=alt.Scale(
                    domain=[SOURCE_LABELS["tm"], SOURCE_LABELS["ml"]],
                    range=[SOURCE_COLORS["tm"], SOURCE_COLORS["ml"]],
                ),
            )
            if view.filters.comparison_mode
            else alt.Color("brand:N", title="Brand")
        )
        _chart = (
            alt.Chart(_scatter.to_pandas())
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
                    alt.Tooltip("source_label:N", title="Source"),
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
            .mark_rule(color=ZERO_REFERENCE_COLOR, strokeDash=[5, 4])
            .encode(x=alt.X("baseline:Q", title="Revision amount (KL)"))
        )
        _horizontal_zero = (
            alt.Chart(_zero_data)
            .mark_rule(color=ZERO_REFERENCE_COLOR, strokeDash=[5, 4])
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
def _(mo, view, with_display_brand, with_source_labels):
    _pairs = view.vintage_pairs
    _download_frame = view.download_frame
    _scope_label = "tm_vs_ml" if view.filters.comparison_mode else view.filters.source
    _download = mo.download(
        _download_frame.write_csv().encode(),
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
        _table_source = with_source_labels(with_display_brand(_pairs))
        if view.filters.comparison_mode:
            _table = (
                _table_source.select(
                    [
                        "source_label",
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
                        "source_label",
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
            "horizons, vintage rules, revision filters, performance filters, and tolerance. "
            "The download contains exactly the displayed selected-pair rows with the auditable export contract."
        )
        _filtered_vintage_table = mo.Html(
            f'<div data-testid="filtered-vintage-table">{mo.ui.table(_table, page_size=20)}</div>'
        )
        _output = mo.vstack(
            [
                mo.md(
                    "## Filtered vintage table\n\n"
                    f"{_table_note} The table is sorted by largest Vintage B absolute error."
                ),
                _filtered_vintage_table,
            ]
        )
    mo.vstack([_output, _download, _brand_month_download])


@app.cell
def _(mo, view):
    _quality = view.quality
    _blocking = (
        "**Blocking input errors:** "
        + " · ".join(f"`{error}`" for error in _quality.blocking_errors)
        if _quality.blocking_errors
        else "**Blocking input errors:** none"
    )
    _category_labels = {
        "hierarchy": "Hierarchy mapping",
        "actual": "Actual availability",
        "pairs": "Vintage pairs",
        "source_availability": "Source availability",
    }
    _sections = [
        mo.md(
            "## Data quality\n\n"
            "Active counts and exception downloads use the same shared target, brand, "
            "product, source, horizon, quality, revision, performance, and volume "
            "selection as the KPI and chart populations. Metric actual-volume "
            "denominators use the selected actual key population; zero-forecast and "
            "complete-history filters narrow that denominator to surviving forecast keys.\n\n"
            + _blocking
        )
    ]
    for _category, _label in _category_labels.items():
        _counts = getattr(_quality, _category)
        _exceptions = _quality.exceptions[_category]
        _download = mo.download(
            _exceptions.write_csv().encode(),
            filename=f"forecast_quality_{_category}_exceptions.csv",
            label=f"Download {_label.lower()} exceptions",
        )
        _sections.extend(
            [
                mo.md(f"### {_label}\n\n{_quality.explanation_text(_category)}"),
                mo.ui.table(
                    _counts.select(
                        [
                            "status",
                            "status_group",
                            "observations",
                            "products",
                            "sources",
                            "target_months",
                            "actual_kl",
                            "forecast_kl",
                            "severity",
                        ]
                    ),
                    page_size=10,
                ),
                mo.md(
                    "**Active exception rows** — healthy statuses are omitted; "
                    "these are the exact rows in the active-filter download."
                ),
                mo.ui.table(_exceptions, page_size=12),
                _download,
            ]
        )

    _scope_counts = _quality.scope_exclusion_counts
    _sections.append(
        mo.md(
            "### Baseline scope exclusions\n\n"
            "These rows belong to the quality baseline before quality, revision, "
            "performance, and volume exclusions but were removed from the active "
            "quality scope by a shared filter. They are separate "
            "from active counts and exception downloads; healthy rows may appear "
            "here because the exclusion reason is scope, not data quality."
        )
    )
    if _scope_counts.height:
        _sections.append(
            mo.ui.table(
                _scope_counts.select(
                    [
                        "category",
                        "status",
                        "status_group",
                        "observations",
                        "products",
                        "sources",
                        "target_months",
                        "actual_kl",
                        "forecast_kl",
                    ]
                ),
                page_size=20,
            )
        )
        for _category, _label in _category_labels.items():
            _scope_frame = _quality.scope_exclusions.get(_category)
            if _scope_frame is None or _scope_frame.height == 0:
                continue
            _sections.extend(
                [
                    mo.md(f"**{_label} baseline rows outside active scope**"),
                    mo.ui.table(_scope_frame, page_size=12),
                    mo.download(
                        _scope_frame.write_csv().encode(),
                        filename=f"forecast_quality_{_category}_scope_exclusions.csv",
                        label=f"Download {_label.lower()} scope exclusions",
                    ),
                ]
            )
    else:
        _sections.append(mo.md("No baseline quality rows are outside the active scope."))
    mo.vstack(_sections)


if __name__ == "__main__":
    app.run()
