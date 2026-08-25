import marimo

__generated_with = "0.23.14"
app = marimo.App(width="medium")


with app.setup:
    # Imports + constants + helpers, available to every cell and importable
    # as a package from other notebooks.
    import re
    from datetime import datetime
    from pathlib import Path

    import marimo as mo
    import polars as pl

    FORECAST_HISTORY_DIR = Path(__file__).parent / "artifacts" / "forecast_history"
    OUTPUT_CSV = (
        FORECAST_HISTORY_DIR / "consolidated" / "forecast_history_waterfall.csv"
    )
    # The folder must always hold the full set of monthly grid files; a missing
    # file would silently truncate the history, so the count is enforced.
    EXPECTED_FILES = 16
    # Melted sums are checked against each sheet's own Grand Total row; the CSV
    # is only written when every file is within this tolerance (float noise is
    # ~5e-9, so 1e-6 is comfortably above it).
    GRAND_TOTAL_TOLERANCE = 1e-6

    MONTHS = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    MONTH_NO = {abbr: i + 1 for i, abbr in enumerate(MONTHS)}
    # Anchored: the whole file name must match, nothing may precede or follow
    # the S&OP pattern.
    FILENAME_RE = re.compile(
        r"^S&OP_grid file_(\w{3})-(\d{2}) to (\w{3})-(\d{2})_circulation\.xlsx$"
    )

    def _month_sequence(
        start_abbr: str, start_year: int, end_abbr: str, end_year: int
    ) -> list[tuple[str, int]]:
        """Walk the month/year pairs covered by a file, e.g. Nov-25 to Mar-26.

        Raises ValueError for unknown month abbreviations, windows longer than
        12 months (reversed or unaligned ranges would loop forever otherwise).
        """
        for abbr in (start_abbr, end_abbr):
            if abbr not in MONTHS:
                raise ValueError(f"unknown month abbreviation {abbr!r}")
        seq: list[tuple[str, int]] = []
        cur, cur_year = start_abbr, start_year
        while True:
            if len(seq) >= 12:
                raise ValueError(
                    f"month window {start_abbr}-{start_year} to "
                    f"{end_abbr}-{end_year} is longer than 12 months "
                    f"(reversed range or bad years?)"
                )
            seq.append((cur, cur_year))
            if cur == end_abbr and cur_year == end_year:
                return seq
            cur = MONTHS[(MONTHS.index(cur) + 1) % 12]
            if cur == "Jan":
                cur_year += 1

    def parse_grid(path: Path) -> tuple[dict, pl.DataFrame]:
        """Read one S&OP grid file (full_s&op sheet only).

        Returns (meta, long) where ``long`` is the material-level melt:
        calculation_month, snop_month, parent_code, parent_description,
        material_code, qty — one row per non-empty month cell.

        The sheet is a pivot-table dump whose header block differs between the
        2025 and 2026 vintages, so the layout is auto-detected instead of assumed:
          * month-anchor row: the header row holding >= 2 month abbreviations
          * column-name row:  the header row holding "parent_code"
        Data starts on the row after both.
        """
        meta: dict = {}
        issues: list[str] = []

        raw = pl.read_excel(
            path,
            sheet_name="full_s&op",
            engine="calamine",
            read_options={"header_row": None},
        )

        # ---- detect header layout ----------------------------------------------
        anchor_idx = names_idx = None
        for i in range(min(6, raw.height)):
            row = raw.row(i)
            if anchor_idx is None:
                n_months = sum(
                    1 for c in row if isinstance(c, str) and c.strip() in MONTHS
                )
                if n_months >= 2:
                    anchor_idx = i
            if names_idx is None and any(
                isinstance(c, str) and c.strip() == "parent_code" for c in row
            ):
                names_idx = i
        if anchor_idx is None or names_idx is None:
            raise ValueError(
                f"{path.name}: header block not found "
                f"(anchor row={anchor_idx}, names row={names_idx})"
            )
        data_start = max(anchor_idx, names_idx) + 1
        month_positions = [
            i
            for i, c in enumerate(raw.row(anchor_idx))
            if isinstance(c, str) and c.strip() in MONTHS
        ]

        # ---- calc month + snop months from the file name ------------------------
        m = FILENAME_RE.search(path.name)
        if m is None:
            raise ValueError(f"{path.name}: file name does not match the S&OP pattern")
        try:
            # two-digit year → full year: 25 → 2025, 26 → 2026
            s_abbr, s_yr, e_abbr, e_yr = (
                m.group(1), 2000 + int(m.group(2)), m.group(3), 2000 + int(m.group(4)),
            )
        except (IndexError, ValueError):
            raise ValueError(f"{path.name}: cannot parse months from file name") from None
        try:
            seq = _month_sequence(s_abbr, s_yr, e_abbr, e_yr)
        except ValueError as exc:
            raise ValueError(f"{path.name}: {exc}") from None
        sheet_months = [raw.row(anchor_idx)[i].strip() for i in month_positions]
        if sheet_months != [a for a, _ in seq]:
            raise ValueError(
                f"{path.name}: sheet month columns {sheet_months} do not match "
                f"the file-name range {[a for a, _ in seq]}"
            )
        calc_month = f"{s_yr}-{MONTH_NO[s_abbr]:02d}"
        abbr_to_month = {
            abbr: f"{y}-{MONTH_NO[abbr]:02d}" for abbr, (_, y) in zip(sheet_months, seq)
        }

        # ---- data rows: drop pivot totals, melt month cells ----------------------
        data = raw[data_start:]
        leaf = data.filter(pl.nth(1).cast(pl.String).is_not_null())
        meta["total_rows_dropped"] = data.height - leaf.height

        month_exprs = []
        non_numeric = 0
        for i, abbr in zip(month_positions, sheet_months):
            non_numeric += leaf.filter(
                pl.nth(i).is_not_null()
                & ~pl.nth(i).cast(pl.String).str.contains(r"^-?\d*\.?\d+$")
            ).height
            month_exprs.append(pl.nth(i).cast(pl.Float64, strict=False).alias(abbr))
        if non_numeric:
            issues.append(f"{non_numeric} non-numeric qty cell(s) set to null")

        long = (
            leaf.select(
                pl.nth(1).cast(pl.String).alias("parent_code"),
                pl.nth(2).cast(pl.String).alias("parent_description"),
                pl.nth(3).cast(pl.String).alias("material_code"),
                *month_exprs,
            )
            .unpivot(
                index=["parent_code", "parent_description", "material_code"],
                on=sheet_months,
                variable_name="month_abbr",
                value_name="qty",
            )
            .filter(pl.col("qty").is_not_null())  # empty month cell = no forecast
            .with_columns(
                calculation_month=pl.lit(calc_month),
                snop_month=pl.col("month_abbr").replace_strict(abbr_to_month),
            )
            .drop("month_abbr")
            .with_columns(parent_code=pl.col("parent_code").cast(pl.Int64))
            .select(
                [
                    "calculation_month",
                    "snop_month",
                    "parent_code",
                    "parent_description",
                    "material_code",
                    "qty",
                ]
            )
        )

        # ---- material appearing on >1 row (pivot 'type' split, e.g. co/non co) ---
        multi_type = (
            leaf.group_by(
                [
                    pl.nth(1).cast(pl.String).alias("parent_code"),
                    pl.nth(3).cast(pl.String).alias("material_code"),
                ]
            )
            .len()
            .filter(pl.col("len") > 1)
        )
        if multi_type.height:
            issues.append(
                f"{multi_type.height} material(s) split across multiple rows/types "
                f"(e.g. {multi_type.row(0)[0]}/{multi_type.row(0)[1]})"
            )

        # ---- grand total row (used later as an exact cross-check) -----------------
        gt = raw.filter(pl.nth(0).cast(pl.String) == "Grand Total")
        if gt.height != 1:
            raise ValueError(
                f"{path.name}: expected exactly 1 'Grand Total' row, found {gt.height}"
            )
        gt_row = gt.row(0)
        gt_values = {}
        for i, abbr in zip(month_positions, sheet_months):
            cell = gt_row[i]
            if cell is None:
                raise ValueError(
                    f"{path.name}: Grand Total row has a blank value for "
                    f"month {abbr} — validation would be meaningless"
                )
            try:
                gt_values[abbr_to_month[abbr]] = float(cell)
            except (TypeError, ValueError):
                raise ValueError(
                    f"{path.name}: Grand Total cell for month {abbr} is not "
                    f"numeric: {cell!r}"
                ) from None
        meta["grand_total"] = gt_values

        meta.update(
            {
                "file": path.name,
                "calc_month": calc_month,
                "snop_months": [f"{y}-{MONTH_NO[a]:02d}" for a, y in seq],
                "sheet_months": sheet_months,
                "layout": (
                    "merged names+months row"
                    if names_idx == anchor_idx
                    else "separate header rows"
                ),
                "leaf_rows": leaf.height,
                "issues": issues,
            }
        )
        return meta, long

    def _ym(yyyymm: str) -> tuple[int, int]:
        """Parse a 'YYYY-MM' key into (year, month), raising on malformed keys."""
        try:
            return int(yyyymm[:4]), int(yyyymm[5:7])
        except (IndexError, ValueError):
            raise ValueError(f"malformed month key: {yyyymm!r}") from None

    def parse_all(
        folder: Path = FORECAST_HISTORY_DIR,
        expected_files: int = EXPECTED_FILES,
    ) -> tuple[list[dict], list[pl.DataFrame]]:
        """Parse every S&OP grid xlsx in the folder -> (metas, longs).

        Fails fast on an incomplete file set (a missing file would silently
        truncate the forecast history): wrong file count or a gap in the
        calculation-month series raises.
        """
        files = sorted(folder.glob("*.xlsx"))
        if len(files) != expected_files:
            raise FileNotFoundError(
                f"expected {expected_files} S&OP grid files in {folder}, "
                f"found {len(files)}: {[f.name for f in files]}"
            )
        metas, longs = [], []
        for path in files:
            meta, long = parse_grid(path)
            metas.append(meta)
            longs.append(long)
        calc_months = sorted(meta["calc_month"] for meta in metas)
        for prev, nxt in zip(calc_months, calc_months[1:]):
            y1, m1 = _ym(prev)
            y2, m2 = _ym(nxt)
            if (y2, m2) != (y1 + (1 if m1 == 12 else 0), m1 % 12 + 1):
                raise ValueError(
                    f"gap in calculation-month series: {prev} → {nxt} "
                    f"(expected continuous monthly coverage)"
                )
        return metas, longs


@app.cell
def _():
    files = sorted(FORECAST_HISTORY_DIR.glob("*.xlsx"))
    inventory = pl.DataFrame(
        {
            "file": [f.name for f in files],
            "size_kb": [round(f.stat().st_size / 1024, 1) for f in files],
            "modified": [datetime.fromtimestamp(f.stat().st_mtime) for f in files],
        }
    )
    mo.md(f"# Forecast history ETL\n\n**{len(files)} S&OP grid files** in "
          f"`{FORECAST_HISTORY_DIR}` — each carries a 5-month forecast window.")
    mo.ui.table(inventory, page_size=10)
    return files, inventory


@app.cell
def _(files):
    metas, longs = parse_all(FORECAST_HISTORY_DIR)
    profile = pl.DataFrame(
        {
            "file": [m["file"] for m in metas],
            "calc_month": [m["calc_month"] for m in metas],
            "snop_months": [" → ".join(m["sheet_months"]) for m in metas],
            "layout": [m["layout"] for m in metas],
            "leaf_rows": [m["leaf_rows"] for m in metas],
            "total_rows_dropped": [m["total_rows_dropped"] for m in metas],
            "issues": ["; ".join(m["issues"]) or "none" for m in metas],
        }
    )
    n_leaf = sum(m["leaf_rows"] for m in metas)
    n_issues = sum(1 for m in metas if m["issues"])
    mo.md(f"## 1 · Profile\n\nAll **{len(metas)}** files parsed. "
          f"**{n_leaf}** leaf (material) rows across files, "
          f"**{sum(m['total_rows_dropped'] for m in metas)}** pivot total rows dropped, "
          f"**{n_issues}** file(s) with flagged issues.")
    mo.ui.table(profile, page_size=10)
    return metas, longs, profile


@app.cell
def _():
    mo.md(
        """
## 2 · Challenges found in the source files

1. **Two header layouts (vintage drift).** The 2025 files have a 4-row header
   block (pivot labels, FY month numbers, month names, then column names).
   The 2026 files dropped the column-name row — names and month names are
   merged in one row and data starts one row earlier. The ETL auto-detects
   the layout (month-anchor row + `parent_code` row) instead of hard-coding it.
2. **Pivot artifact labels.** Row 0 labels (`Sum of qty`, `fy_month_no`,
   `date (Month)`, `date`) do not line up with the data columns — 2025 files
   even have a stray `date` label sitting on top of a real month column.
   They are ignored; columns are located via the month-name row.
3. **No year in the sheet.** Month columns are bare abbreviations
   (`Aug`…`Dec`) — the year comes from the file name, where the two-digit
   number is the century year (`Nov-25` → year **2025**, `Mar-26` → 2026).
   The ETL expands `yy` → `2000 + yy` and walks the range with year wrap:
   `Nov-25 to Mar-26` → Nov/Dec 2025, Jan–Mar 2026.
   Verified: the sheet month sequence matches the file-name range in all 16 files.
4. **Pivot total rows.** Every per-batch `X Total` row plus the final
   `Grand Total` row (~50–60 per file) carry a null parent code — dropped.
5. **Material split across `type` rows.** In `Apr-26`, material `732995`
   appears twice — once as `non co` and once as `price off`, with *different*
   quantities in the same months. Both lines are legitimate forecast buckets;
   each non-empty month cell flows into the parent-level sum exactly once
   (the pivot's Grand Total row is still matched exactly).
6. **Empty month cells** are dropped from the long file — an empty cell is
   treated as "no forecast that month", not as 0.
7. **Fiscal-month label drift.** 2025 files label months `05`…`09` (FY month
   number), 2026 files use `2027_01`…`2027_05` (FY year_month). Cosmetic —
   not used by the ETL.
8. **Descriptions drift across files.** 4 parent codes (`702082`, `731495`,
   `715677`, `715678`) have different descriptions in different files; the
   consolidated file attaches the most common description per parent — one
   vote per file, deterministic tie-break (most votes, then alphabetically).
9. **Fractional quantities** (e.g. `239.9954`) are kept as floats, never rounded.
10. **Fail-fast guards.** The ETL refuses to run on bad input instead of
    producing a plausible-but-wrong CSV: a wrong file count or a gap in the
    calculation-month series raises; month windows longer than 12 months
    (reversed ranges) and unknown month abbreviations raise; a sheet whose
    month columns disagree with its file-name range raises; a missing
    `Grand Total` row — or one with a blank/non-numeric month value — raises;
    and the CSV is written only after every file's melted sums match its
    Grand Total row within 1e-6.
        """
    )


@app.cell
def _(metas, longs):
    # Validation first: melted per-month sums vs each sheet's own Grand Total
    # row. The CSV is only written when every file is within tolerance.
    validation_rows = []
    for meta, long in zip(metas, longs):
        per_month = long.group_by("snop_month").agg(s=pl.col("qty").sum())
        gt = pl.DataFrame(
            {
                "snop_month": list(meta["grand_total"]),
                "gt": list(meta["grand_total"].values()),
            }
        )
        joined = per_month.join(gt, on="snop_month", how="full").fill_null(0)
        diff = (joined["s"] - joined["gt"]).abs().max()
        max_diff = diff if diff is not None else 0.0
        validation_rows.append(
            {
                "file": meta["file"],
                "leaf_rows": meta["leaf_rows"],
                "total_rows_dropped": meta["total_rows_dropped"],
                "max_abs_diff_vs_grand_total": max_diff,
                "issues": "; ".join(meta["issues"]) or "none",
            }
        )
    validation = pl.DataFrame(validation_rows)
    offenders = validation.filter(
        pl.col("max_abs_diff_vs_grand_total") > GRAND_TOTAL_TOLERANCE
    )
    if offenders.height:
        raise RuntimeError(
            f"grand-total validation failed for {offenders.height} file(s) — "
            f"CSV not written:\n{offenders.select(['file', 'max_abs_diff_vs_grand_total'])}"
        )

    consolidated = (
        pl.concat(longs)
        .group_by(["parent_code", "calculation_month", "snop_month"])
        .agg(qty=pl.col("qty").sum())
        .join(
            (
                # most common description per parent, one literal vote per file:
                # within a file, a parent's description is the one covering the
                # most distinct materials (tie-break: lexicographically smallest),
                # then across files the description with the most votes wins
                # (tie-break: lexicographically smallest).
                per_file_desc := pl.concat(longs)
                .select(
                    [
                        "calculation_month",
                        "parent_code",
                        "parent_description",
                        "material_code",
                    ]
                )
                .unique()
                .group_by(
                    ["calculation_month", "parent_code", "parent_description"]
                )
                .len()
                .sort(
                    ["calculation_month", "parent_code", "len", "parent_description"],
                    descending=[False, False, True, False],
                )
                .group_by(["calculation_month", "parent_code"], maintain_order=True)
                .first()
                .group_by(["parent_code", "parent_description"])
                .len()
                .sort(
                    ["parent_code", "len", "parent_description"],
                    descending=[False, True, False],
                )
                .group_by("parent_code", maintain_order=True)
                .first()
                .select(["parent_code", "parent_description"])
            ),
            on="parent_code",
            how="left",
        )
        .select(
            [
                "calculation_month",
                "snop_month",
                "parent_code",
                "parent_description",
                "qty",
            ]
        )
        .sort(["parent_code", "snop_month", "calculation_month"])
    )
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    consolidated.write_csv(OUTPUT_CSV)
    n_parents = consolidated.select(pl.col("parent_code").n_unique()).item()
    n_rows = consolidated.height
    max_diff = validation["max_abs_diff_vs_grand_total"].max()
    mo.md(
        f"## 3 · Consolidated vertical waterfall\n\n"
        f"**{n_rows:,}** rows · **{n_parents}** parents · "
        f"calculation month = the file's month · snop month = the sheet column month\n\n"
        f"All {len(metas)} files passed the Grand Total cross-check "
        f"(max |diff| {max_diff:.2e} ≤ {GRAND_TOTAL_TOLERANCE:.0e}) and the CSV was "
        f"written to `{OUTPUT_CSV}`."
    )
    mo.ui.table(consolidated.head(500), page_size=10)
    return consolidated, validation


@app.cell
def _(validation):
    mo.md(
        "## 4 · Validation\n\n"
        "Per-file melted sums vs the sheet's own `Grand Total` row — "
        f"the CSV write is gated on every file being within "
        f"{GRAND_TOTAL_TOLERANCE:.0e} of its Grand Total."
    )
    mo.ui.table(validation, page_size=10)
    return


@app.cell
def _(consolidated):
    mo.download(
        consolidated.write_csv().encode(),
        filename="forecast_history_waterfall.csv",
        label="⬇ Download consolidated waterfall CSV",
    )
    return
