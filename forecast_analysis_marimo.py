import marimo

__generated_with = "0.23.14"
app = marimo.App(width="medium")

with app.setup:
    # Imports + paths available to every cell and to the top-level
    # `matched_frame` function (importable as a package from other notebooks).
    import glob
    from pathlib import Path

    import polars as pl
    from polars import selectors as cs

    ARTIFACTS_DIR = Path(__file__).parent / "artifacts"


@app.function
def matched_frame() -> pl.DataFrame:
    """Read the three artifacts and return one row per (parent_code, snop_month)
    that already has actuals, carrying actual_kl, oldest_fc, latest_fc and brand.

    oldest_fc / latest_fc are the first / last forecast made (by calculation_month)
    for that product+month — the earliest promise vs the most recent revision.
    """
    fc_files = glob.glob(str(ARTIFACTS_DIR / "common/*"))
    actual_files = glob.glob(str(ARTIFACTS_DIR / "secondary_sales/*"))
    ph_files = glob.glob(str(ARTIFACTS_DIR / "ph/*"))

    fc = pl.read_csv(fc_files[0]).with_columns(
        pl.col(["calculation_month", "snop_month"]).str.to_date("%Y-%m-%d")
    )

    # Actuals sheet has 5 title rows above the real header; bill-wise rows are
    # summed up to one actual volume per (product, month).
    actual = (
        pl.read_excel(actual_files[0], read_options={"header_row": 5})
        .select(
            cs.all()
            .name.to_lowercase()
            .name.replace(" ", "_")
            .name.replace("-", "_")
            .name.map(str.strip)
        )
        .rename(
            {
                "parent_material_code": "parent_code",
                "month_year": "snop_month",
                "sec_vol_kl_mth_(billwise)": "actual_kl",
            }
        )
        .with_columns(snop_month=("01-" + pl.col("snop_month")).str.to_date("%d-%b-%Y"))
        .with_columns(parent_code=pl.col("parent_code").cast(pl.Int64))
        .group_by(["parent_code", "snop_month"])
        .agg(actual_kl=pl.col("actual_kl").sum())
    )

    ph = (
        pl.read_excel(ph_files[0])
        .select(["material_code", "material_desc", "material_group_code"])
        .unique("material_code")
        .rename(
            {
                "material_code": "parent_code",
                "material_desc": "parent_description",
                "material_group_code": "brand",
            }
        )
        .select(["parent_code", "brand"])
    )

    return (
        fc.join(actual, on=["parent_code", "snop_month"], how="left")
        .filter(~pl.col("actual_kl").is_null())
        .sort(["parent_code", "snop_month", "calculation_month"])
        .group_by(["parent_code", "snop_month"])
        .agg(
            actual_kl=pl.col("actual_kl").first(),
            oldest_fc=pl.col("fc_kl").first(),
            latest_fc=pl.col("fc_kl").last(),
        )
        .join(ph, on="parent_code", how="left")
    )


@app.cell
def _():
    matched_frame()
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
