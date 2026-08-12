import marimo

__generated_with = "0.23.14"
app = marimo.App(width="full")


with app.setup:
    import altair as alt
    import marimo as mo
    import polars as pl

    from forecast_analysis_marimo import matched_frame


@app.cell
def _():
    mo.md(
        """
        # Forecast accuracy — oldest vs latest vintage

        **FA = (1 − Σ|fc − actual| / Σ actual) × 100**, summed at SKU level
        within each group then divided (WAPE). The **chart** shows overall
        accuracy by month for the earliest forecast (`oldest`) and the most
        recent revision (`latest`). The **heatmap** breaks the same comparison
        out by brand × month — toggle the vintage on the right.
        """
    )
    return


@app.cell
def _(matched_frame):
    matched = matched_frame()
    return (matched,)


@app.cell
def _(matched, mo):
    _brands = sorted(matched["brand"].drop_nulls().unique().to_list())
    brand_filter = mo.ui.multiselect(
        options=_brands,
        value=_brands,
        label="Brands included  (deselect to exclude — try PN_SHMP_S)",
        full_width=True,
    )
    mo.hstack([brand_filter])
    return (brand_filter,)


@app.cell
def _(brand_filter, matched, pl):
    # everything below derives from `m`, so deselecting a brand recomputes
    # the chart, heatmap and revision panel live.
    m = matched.filter(pl.col("brand").is_in(brand_filter.value))
    return (m,)


@app.cell
def _(pl):
    def fa(df, groups, vintage):
        # WAPE-based FA: sum |fc-actual| and actual at SKU level within the
        # group, then divide. Never averages per-SKU accuracies.
        return (
            df.group_by(groups)
            .agg(
                abs_err=(pl.col(f"{vintage}_fc") - pl.col("actual_kl")).abs().sum(),
                denom=pl.col("actual_kl").sum(),
            )
            .with_columns(fa=(1 - pl.col("abs_err") / pl.col("denom")) * 100)
        )

    return (fa,)


@app.cell
def _(fa, m):
    chart_df = (
        fa(m, ["snop_month"], "oldest")
        .rename({"fa": "fa_oldest"})
        .join(fa(m, ["snop_month"], "latest").rename({"fa": "fa_latest"}), on="snop_month")
        .sort("snop_month")
    )
    return (chart_df,)


@app.cell
def _(alt, chart_df, mo, pl):
    chart_long = chart_df.unpivot(
        on=["fa_oldest", "fa_latest"], index="snop_month", variable_name="vintage", value_name="fa"
    ).with_columns(vintage=pl.col("vintage").str.replace("fa_", ""))
    chart = (
        alt.Chart(chart_long.to_pandas())
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=alt.X("snop_month:T", title="SNOP month"),
            y=alt.Y("fa:Q", title="Forecast accuracy (%)"),
            color=alt.Color(
                "vintage:N",
                title="Vintage",
                scale=alt.Scale(domain=["oldest", "latest"], range=["#E8A33D", "#3FB8AF"]),
            ),
            tooltip=["snop_month:T", "vintage:N", alt.Tooltip("fa:Q", format=".1f")],
        )
        .properties(height=340)
    )
    mo.ui.altair_chart(chart, chart_selection=False, legend_selection=False)
    return


@app.cell
def _(chart_df, fa, m, mo, pl):
    _bm = (
        fa(m, ["brand", "snop_month"], "oldest")
        .rename({"fa": "fa_oldest"})
        .join(
            fa(m, ["brand", "snop_month"], "latest").rename({"fa": "fa_latest"}),
            on=["brand", "snop_month"],
        )
        .with_columns(delta=pl.col("fa_latest") - pl.col("fa_oldest"))
        .select(["brand", "snop_month", "fa_oldest", "fa_latest", "delta"])
    )
    _all = chart_df.with_columns(
        brand=pl.lit("All brands"), delta=pl.col("fa_latest") - pl.col("fa_oldest")
    ).select(["brand", "snop_month", "fa_oldest", "fa_latest", "delta"])
    bm = pl.concat([_all, _bm])

    _order = (
        fa(m, ["brand"], "latest").rename({"fa": "fa_latest"}).sort("fa_latest")["brand"].to_list()
    )
    brand_order = ["All brands"] + _order

    toggle = mo.ui.dropdown(
        options={"Latest": "fa_latest", "Oldest": "fa_oldest", "Δ (latest − oldest)": "delta"},
        value="Latest",
        label="Vintage",
    )
    mo.hstack([mo.md("### Accuracy by brand × month"), toggle], justify="space-between")
    return (bm, brand_order, toggle)


@app.cell
def _(alt, bm, brand_order, mo, toggle):
    col = toggle.value
    heat = bm.select("brand", "snop_month", col).rename({col: "metric"})

    if col == "delta":
        scale = alt.Scale(domain=[-30, 0, 30], range=["#D9544D", "#ffffff", "#3FB8AF"], clamp=True)
        title = "Δ FA (pp)"
    else:
        scale = alt.Scale(domain=[-50, 50, 100], range=["#D9544D", "#E8A33D", "#3FB8AF"], clamp=True)
        title = f"FA (%) — {col.replace('fa_', '')}"

    heat_chart = (
        alt.Chart(heat.to_pandas())
        .mark_rect(stroke="#0E1518", strokeWidth=1)
        .encode(
            x=alt.X("snop_month:T", title="SNOP month"),
            y=alt.Y("brand:N", sort=brand_order, title=None),
            color=alt.Color(
                "metric:Q",
                title=title,
                scale=scale,
                legend=alt.Legend(direction="horizontal", orient="bottom"),
            ),
            tooltip=[
                "brand:N",
                alt.Tooltip("snop_month:T", title="month"),
                alt.Tooltip("metric:Q", format=".1f"),
            ],
        )
        .properties(width=560, height={"step": 17})
    )
    mo.ui.altair_chart(heat_chart, chart_selection=False, legend_selection=False)
    return


@app.cell
def _(m, pl):
    # Per-brand revision diagnostics (only rows with a real actual, to keep ratios sane)
    brand_bias = (
        m.filter(pl.col("actual_kl") > 0)
        .group_by("brand")
        .agg(
            n=pl.len(),
            total_actual_kl=pl.col("actual_kl").sum().round(1),
            pct_revised_up=((pl.col("latest_fc") > pl.col("oldest_fc")).mean() * 100).round(1),
            pct_revised_down=((pl.col("latest_fc") < pl.col("oldest_fc")).mean() * 100).round(1),
            mean_revision_kl=(pl.col("latest_fc") - pl.col("oldest_fc")).mean().round(2),
            med_oldest_over=(pl.col("oldest_fc") / pl.col("actual_kl")).median().round(2),
            med_latest_over=(pl.col("latest_fc") / pl.col("actual_kl")).median().round(2),
        )
        .sort("med_latest_over", descending=True)
    )
    return (brand_bias,)


@app.cell
def _(mo):
    mo.md(
        """
        ## Revision bias by brand

        "Latest beats oldest" assumes revisions *correct* error. Here they *amplify* it: forecasts are revised **up** on average, on top of an already-too-high baseline. In the scatter, **top-right = revises up AND overshoots actual** — those brands are what's dragging `latest` accuracy below `oldest`. Circle size = actual volume. (Top 25 brands by volume shown; the table lists all.)
        """
    )
    return


@app.cell
def _(alt, brand_bias, mo, pl):
    _bb = brand_bias.sort("total_actual_kl", descending=True).head(25)
    scatter = (
        alt.Chart(_bb.to_pandas())
        .mark_circle(opacity=0.75)
        .encode(
            x=alt.X(
                "pct_revised_up:Q",
                title="% product-months revised UP",
                scale=alt.Scale(domain=[0, 100]),
            ),
            y=alt.Y(
                "med_latest_over:Q",
                title="median latest_fc / actual  (1.0 = perfect)",
                scale=alt.Scale(zero=False),
            ),
            size=alt.Size("total_actual_kl:Q", legend=None, scale=alt.Scale(range=[60, 900])),
            color=alt.Color(
                "mean_revision_kl:Q",
                title="mean revision (KL)",
                scale=alt.Scale(domainMid=0, range=["#3FB8AF", "#ffffff", "#D9544D"]),
            ),
            tooltip=[
                "brand",
                "n",
                "pct_revised_up",
                "pct_revised_down",
                "med_oldest_over",
                "med_latest_over",
                "mean_revision_kl",
            ],
        )
        .properties(height=440)
    )
    _rule = (
        alt.Chart(pl.DataFrame({"y": [1]}).to_pandas())
        .mark_rule(color="#8A9A9F", strokeDash=[5, 4])
        .encode(y="y:Q")
    )
    mo.ui.altair_chart(scatter + _rule, chart_selection=False, legend_selection=False)
    return


@app.cell
def _(brand_bias, mo):
    mo.ui.table(brand_bias, page_size=12)
    return


if __name__ == "__main__":
    app.run()
