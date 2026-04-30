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
    import fastexcel
    from data_manipulation_utilities import clean_columns

    return Path, glob, pl


app._unparsable_cell(
    r"""
    !pip install git+https://github.com/1am2syman/data-manipulation-utilities.git
    """,
    name="_"
)


@app.cell
def _(Path, glob):
    fc_files = glob.glob(str(Path(__file__).parents[1])+r'\artifacts\common\forec*')
    actual_files = glob.glob(str(Path(__file__).parents[1])+r'\artifacts\secondary_sales\*')
    return actual_files, fc_files


@app.cell
def _(actual_files, fc_files, pl):
    fc = pl.scan_csv(fc_files)
    actual = pl.read_excel(actual_files, read_options={'header_row':5})
    return actual, fc


@app.cell
def _(fc):
    (fc
     
    .collect())
    return


@app.cell
def _(actual):
    actual
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
