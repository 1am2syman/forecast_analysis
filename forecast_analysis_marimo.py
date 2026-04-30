import marimo

__generated_with = "0.19.9"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import polars as pl
    import glob as glob
    import altair as alt
    from pathlib import Path
    from polars import selectors as cs
    # from data_manipulation_utilities import clean_columns
    return Path, cs, glob, pl


@app.cell
def _(Path, glob):
    fc_files= glob.glob(str(Path(__file__).parents[0])+'/artifacts/common/*')
    actual_files = glob.glob(str(Path(__file__).parents[0])+'/artifacts/secondary_sales/*')
    ph_files = glob.glob(str(Path(__file__).parents[0])+'/artifacts/ph/*')
    return actual_files, fc_files, ph_files


@app.cell
def _(actual_files, fc_files, ph_files, pl):
    fc = pl.read_csv(fc_files[0])
    fc = fc.with_columns(pl.col(['calculation_month', 'snop_month']).str.to_date('%Y-%m-%d'))
    actual = pl.read_excel(actual_files[0], read_options={'header_row':5})
    ph = pl.read_excel(ph_files[0])
    ph = ph.select(['material_code', 'material_desc', 'material_group_code']).unique('material_code').rename({'material_code':'parent_code', 'material_desc':'parent_description','material_group_code':'brand'})
    return actual, fc, ph


@app.cell
def _(fc):
    fc
    return


@app.cell
def _(actual, cs, pl):
    def clean_actual():
        return\
        (actual
         .select(cs.all().name.to_lowercase().name.replace('-','_').name.replace(' ','_').name.map(str.strip))
         .rename({
             'parent_material_code':'parent_code',
             'month_year': 'snop_month', 
             'sec_vol_kl_mth_(billwise)':'actual_kl'})
         .with_columns(snop_month = ('01-'+pl.col('snop_month')).str.to_date('%d-%b-%Y'))   .with_columns(pl.col('parent_code').cast(pl.Int64))
        )

    return (clean_actual,)


@app.cell
def _(clean_actual, fc, ph, pl):
    (fc
     .join(clean_actual(), on=['parent_code', 'snop_month'], how='left')
     .filter(~pl.col('actual_kl').is_null())
     .sort(['parent_code','snop_month', 'calculation_month'], descending=[False, True, False])
     .with_columns(oldest_fc = pl.col('fc_kl').first().over(['parent_code', 'snop_month']))
     .with_columns(deficit = pl.col('oldest_fc')- pl.col('actual_kl'))
     .with_columns(under_ach_pct = pl.col('deficit')/pl.col('oldest_fc')*100)
     .join(ph, on='parent_code', how='left')
     # .group_by([ 'snop_month'], maintain_order=True)
     # .agg(pl.col(['deficit', 'oldest_fc']).sum())
     # .with_columns(under_ach_pct = pl.col('deficit')/pl.col('oldest_fc')*100)
     # .sort(['brand', 'snop_month'], descending=[False, True])
    )
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
