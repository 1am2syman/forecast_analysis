import hashlib
import io
import json
import stat
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import polars as pl
from polars.testing import assert_frame_equal

import forecast_history_pipeline as etl  # pyright: ignore[reportMissingImports]
from scripts import verify_forecast_history_output as verifier

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures"
TM_ORACLE_MANIFEST = FIXTURE_DIR / "tm_forecast_history_baseline.json"
TM_ORACLE_CSV = FIXTURE_DIR / "tm_forecast_history_baseline.csv"
CURRENT_INPUT_MANIFEST = FIXTURE_DIR / "current_input_regression.json"
TM_SORT_COLUMNS = ["parent_code", "snop_month", "calculation_month"]


def month_keys(frame: pl.DataFrame, column: str) -> list[str]:
    """Return sorted YYYY-MM values from an internal Date column."""
    return [value.strftime("%Y-%m") for value in sorted(frame[column].unique())]


def load_tm_oracle() -> tuple[pl.DataFrame, dict]:
    """Load the fixture only after checking its manifest checksum."""
    manifest = json.loads(TM_ORACLE_MANIFEST.read_text(encoding="utf-8"))
    fixture_bytes = TM_ORACLE_CSV.read_bytes()
    self_hash = hashlib.sha256(fixture_bytes).hexdigest()
    if self_hash != manifest["fixture_sha256"]:
        raise AssertionError("TM oracle fixture checksum does not match manifest")
    return pl.read_csv(io.BytesIO(fixture_bytes)), manifest


def canonicalize_legacy_tm_oracle(frame: pl.DataFrame) -> pl.DataFrame:
    """Shift the immutable pre-fix oracle onto canonical calculation months."""
    return frame.with_columns(
        pl.col("calculation_month")
        .str.to_date("%Y-%m")
        .dt.offset_by("-1mo")
        .dt.strftime("%Y-%m")
    )


class TmGridProvenanceTests(unittest.TestCase):
    def test_april_through_august_file_is_march_calculation_vintage(self):
        path = (
            etl.FORECAST_HISTORY_DIR
            / "S&OP_grid file_Apr-26 to Aug-26_circulation.xlsx"
        )

        meta, rows = etl.parse_grid(path)

        self.assertEqual(meta["calc_month"], "2026-03")
        self.assertEqual(rows["calculation_month"].unique().to_list(), [date(2026, 3, 1)])
        horizons = (
            rows.select(
                (
                    pl.col("snop_month").dt.year() * 12
                    + pl.col("snop_month").dt.month()
                    - pl.col("calculation_month").dt.year() * 12
                    - pl.col("calculation_month").dt.month()
                ).alias("horizon")
            )["horizon"]
            .unique()
            .sort()
            .to_list()
        )
        self.assertEqual(horizons, [1, 2, 3, 4, 5])


class MlHistoryNormalizationTests(unittest.TestCase):
    def make_row(self, **overrides):
        row = {
            "KEY": 123,
            "DESCRIPTION": "Example product",
            "MONTH_DATE": date(2025, 5, 1),
            "TRAIN_TILL": date(2025, 3, 1),
            "PREDICTING_MONTH": "M+1",
            "PRED_VOLUME": 90.0,
            "Oth_Ch_Contr._%": 0.1,
            "Cal_forecast": 100.0,
        }
        row.update(overrides)
        return row

    def normalize(self, *rows):
        return etl.normalize_ml_history(pl.DataFrame(list(rows)))

    def test_month_derivation_uses_authoritative_dates_across_year_boundary(self):
        result = self.normalize(
            self.make_row(
                MONTH_DATE=date(2026, 2, 1),
                TRAIN_TILL=date(2025, 12, 1),
                PREDICTING_MONTH="M+1",
            )
        )

        self.assertEqual(
            result.select(["calculation_month", "snop_month"]).row(0),
            (date(2026, 1, 1), date(2026, 2, 1)),
        )

    def test_horizons_m_plus_one_through_five_are_accepted(self):
        rows = [
            self.make_row(
                KEY=index,
                MONTH_DATE=date(2025, 4 + horizon, 1),
                PREDICTING_MONTH=f"M+{horizon}",
            )
            for index, horizon in enumerate(range(1, 6), start=1)
        ]

        result = self.normalize(*rows)

        self.assertEqual(result.height, 5)

    def test_missing_malformed_zero_unsupported_and_inconsistent_horizons_are_rejected(
        self,
    ):
        for horizon in (None, "", "M+0", "M+6", "M+01", "not-a-horizon"):
            with (
                self.subTest(horizon=horizon),
                self.assertRaisesRegex(ValueError, "PREDICTING_MONTH|mapping"),
            ):
                self.normalize(self.make_row(PREDICTING_MONTH=horizon))

        with self.assertRaisesRegex(ValueError, "PREDICTING_MONTH"):
            self.normalize(
                self.make_row(MONTH_DATE=date(2025, 7, 1), PREDICTING_MONTH="M+1")
            )

    def test_pred_volume_is_the_authoritative_forecast_quantity(self):
        result = self.normalize(
            self.make_row(PRED_VOLUME=90.0, Cal_forecast=100.0)
        )

        self.assertEqual(result["qty"].item(), 90.0)

    def test_cal_forecast_column_and_blank_values_are_optional(self):
        without_column = self.make_row()
        del without_column["Cal_forecast"]
        without_reference = etl.validate_and_normalize_ml_history(
            pl.DataFrame([without_column])
        )
        blank_reference = etl.validate_and_normalize_ml_history(
            pl.DataFrame([self.make_row(Cal_forecast="")])
        )

        self.assertEqual(without_reference.frame["qty"].item(), 90.0)
        self.assertEqual(without_reference.validation.cal_forecast_checked_rows, 0)
        self.assertIsNone(without_reference.validation.max_formula_difference)
        self.assertEqual(blank_reference.frame["qty"].item(), 90.0)
        self.assertEqual(blank_reference.validation.cal_forecast_checked_rows, 0)
        self.assertIsNone(blank_reference.validation.max_formula_difference)

    def test_missing_required_column_is_rejected(self):
        row = self.make_row()
        del row["PRED_VOLUME"]

        with self.assertRaisesRegex(ValueError, "PRED_VOLUME"):
            self.normalize(row)

        row = self.make_row()
        del row["PREDICTING_MONTH"]
        with self.assertRaisesRegex(ValueError, "PREDICTING_MONTH"):
            self.normalize(row)

    def test_missing_workbook_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.xlsx"
            with self.assertRaisesRegex(FileNotFoundError, "workbook not found"):
                etl.parse_ml_history(missing)

    def test_missing_data_sheet_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            workbook = Path(directory) / "history.xlsx"
            workbook.touch()
            with (
                patch.object(
                    etl.pl,
                    "read_excel",
                    side_effect=RuntimeError("worksheet data is missing"),
                ),
                self.assertRaisesRegex(ValueError, "sheet 'data'"),
            ):
                etl.parse_ml_history(workbook)

    def test_null_mapping_value_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "required mapping fields"):
            self.normalize(self.make_row(DESCRIPTION=None))

    def test_invalid_and_non_first_of_month_dates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "required mapping fields"):
            self.normalize(self.make_row(MONTH_DATE="not-a-date"))

        with self.assertRaisesRegex(ValueError, "first-of-month"):
            self.normalize(self.make_row(MONTH_DATE=date(2025, 5, 2)))

        with self.assertRaisesRegex(ValueError, "first-of-month"):
            self.normalize(self.make_row(TRAIN_TILL=date(2025, 3, 15)))

    def test_integer_key_conversion_preserves_values_above_float_safe_range(self):
        large_integer = 9_007_199_254_740_993
        integer_result = self.normalize(self.make_row(KEY=large_integer))
        self.assertEqual(integer_result["parent_code"].item(), large_integer)

        string_result = self.normalize(self.make_row(KEY=str(large_integer)))
        self.assertEqual(string_result["parent_code"].item(), large_integer)

    def test_fractional_float_and_malformed_keys_are_rejected(self):
        for key in (123.5, "123.5", "1e3", True, 123.0, ""):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "KEY"):
                self.normalize(self.make_row(KEY=key))

    def test_nonfinite_and_negative_pred_volume_values_are_rejected(self):
        for value in (float("nan"), float("inf"), -1.0):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "PRED_VOLUME"),
            ):
                self.normalize(self.make_row(PRED_VOLUME=value))

    def test_supplied_invalid_cal_forecast_reference_values_are_rejected(self):
        for value in (float("nan"), float("inf"), -1.0, "not-a-number"):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "Cal_forecast"),
            ):
                self.normalize(self.make_row(Cal_forecast=value))

    def test_contribution_bounds_are_rejected(self):
        for contribution in (-0.01, 1.0, float("nan"), float("inf")):
            with (
                self.subTest(contribution=contribution),
                self.assertRaisesRegex(ValueError, "Oth_Ch_Contr"),
            ):
                self.normalize(self.make_row(**{"Oth_Ch_Contr._%": contribution}))

    def test_formula_tolerance_boundary_passes_and_mismatch_fails(self):
        boundary = self.normalize(
            self.make_row(Cal_forecast=100.0 + etl.ML_FORMULA_TOLERANCE)
        )
        self.assertEqual(boundary.height, 1)

        with self.assertRaisesRegex(ValueError, "Cal_forecast does not match"):
            self.normalize(self.make_row(Cal_forecast=101.0))

    def test_duplicate_ml_final_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate final keys"):
            self.normalize(self.make_row(), self.make_row())

    def test_ml_validation_returns_structured_measured_evidence(self):
        result = etl.validate_and_normalize_ml_history(pl.DataFrame([self.make_row()]))

        self.assertEqual(result.validation.checked_rows, 1)
        self.assertEqual(result.validation.cal_forecast_checked_rows, 1)
        self.assertEqual(result.validation.max_formula_difference, 0.0)
        self.assertEqual(result.validation.horizon_counts, (("M+1", 1),))
        self.assertEqual(result.validation.duplicate_final_key_count, 0)
        self.assertEqual(
            result.validation.to_frame().columns,
            [
                "checked_rows",
                "cal_forecast_checked_rows",
                "max_formula_difference",
                "formula_tolerance",
                "horizon_coverage",
                "calculation_month_coverage",
                "snop_month_coverage",
                "duplicate_final_key_count",
            ],
        )


class ForecastHistoryCombinationTests(unittest.TestCase):
    def history_row(self, source: str, code: int = 123):
        return pl.DataFrame(
            {
                "calculation_month": [date(2025, 5, 1)],
                "snop_month": [date(2025, 6, 1)],
                "parent_code": [code],
                "parent_description": [f"{source} description"],
                "qty": [10.0 if source == "tm" else 12.0],
                "source": [source],
            }
        )

    def test_matching_business_keys_remain_as_two_source_rows(self):
        tm = self.history_row("tm")
        ml = self.history_row("ml")

        result = etl.combine_forecast_history(tm, ml)

        self.assertEqual(result.height, 2)
        self.assertEqual(set(result["source"].to_list()), {"tm", "ml"})
        self.assertEqual(
            result.group_by(["parent_code", "calculation_month", "snop_month"])
            .len()
            .select("len")
            .item(),
            2,
        )

    def test_invalid_combined_source_is_rejected(self):
        invalid = self.history_row("tm").with_columns(pl.lit("other").alias("source"))

        with self.assertRaisesRegex(ValueError, "unsupported source"):
            etl.combine_forecast_history(invalid, self.history_row("ml"))

    def test_tm_argument_rejects_ml_labeled_rows(self):
        with self.assertRaisesRegex(ValueError, "expected only source 'tm'"):
            etl.combine_forecast_history(self.history_row("ml"), self.history_row("ml"))

    def test_ml_argument_rejects_tm_labeled_rows(self):
        with self.assertRaisesRegex(ValueError, "expected only source 'ml'"):
            etl.combine_forecast_history(self.history_row("tm"), self.history_row("tm"))

    def test_swapped_source_labels_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "TM source.*expected only source 'tm'"):
            etl.combine_forecast_history(self.history_row("ml"), self.history_row("tm"))

    def test_duplicate_combined_source_key_is_rejected(self):
        duplicate = pl.concat([self.history_row("tm"), self.history_row("tm")])
        duplicate = duplicate.sort(etl.HISTORY_SORT_COLUMNS)

        with self.assertRaisesRegex(ValueError, "duplicate final keys"):
            etl.combine_forecast_history(duplicate, self.history_row("ml"))

    def test_noncanonical_horizons_are_rejected_before_combining(self):
        for source, target_month in (("tm", date(2025, 5, 1)), ("ml", date(2025, 12, 1))):
            with self.subTest(source=source), self.assertRaisesRegex(
                ValueError, "canonical forecast horizon must be M1 through M5"
            ):
                etl.combine_forecast_history(
                    self.history_row(source).with_columns(
                        pl.lit(target_month).alias("snop_month")
                    ),
                    self.history_row("ml"),
                )

    def test_tm_aggregation_labels_rows_without_changing_business_keys(self):
        longs = [
            pl.DataFrame(
                {
                    "calculation_month": [date(2025, 5, 1), date(2025, 5, 1)],
                    "snop_month": [date(2025, 6, 1), date(2025, 6, 1)],
                    "parent_code": [123, 123],
                    "parent_description": ["Example product", "Example product"],
                    "material_code": ["a", "b"],
                    "qty": [2.5, 3.5],
                }
            )
        ]

        result = etl.build_tm_history(longs)

        self.assertEqual(result.height, 1)
        self.assertEqual(result["qty"].item(), 6.0)
        self.assertEqual(result["source"].item(), "tm")


class ValidationStatusTests(unittest.TestCase):
    def test_status_is_derived_from_completed_validation_evidence(self):
        tm_validation = pl.DataFrame(
            {"max_abs_diff_vs_grand_total": [0.0, etl.GRAND_TOTAL_TOLERANCE]}
        )
        ml_validation = etl.MlValidationEvidence(
            checked_rows=1,
            cal_forecast_checked_rows=1,
            max_formula_difference=0.0,
            formula_tolerance=etl.ML_FORMULA_TOLERANCE,
            horizon_counts=(("M+1", 1),),
            calculation_months=(date(2025, 5, 1),),
            snop_months=(date(2025, 6, 1),),
            duplicate_final_key_count=0,
        )

        status = etl.build_validation_status(tm_validation, ml_validation)

        self.assertEqual(
            status.to_dicts(),
            [{"source": "tm", "status": "passed"}, {"source": "ml", "status": "passed"}],
        )

    def test_status_accepts_an_optional_cal_forecast_reference_that_is_absent(self):
        tm_validation = pl.DataFrame({"max_abs_diff_vs_grand_total": [0.0]})
        ml_validation = etl.MlValidationEvidence(
            checked_rows=1,
            cal_forecast_checked_rows=0,
            max_formula_difference=None,
            formula_tolerance=etl.ML_FORMULA_TOLERANCE,
            horizon_counts=(("M+1", 1),),
            calculation_months=(date(2025, 5, 1),),
            snop_months=(date(2025, 6, 1),),
            duplicate_final_key_count=0,
        )

        status = etl.build_validation_status(tm_validation, ml_validation)

        self.assertEqual(status.get_column("status").to_list(), ["passed", "passed"])

    def test_status_rejects_invalid_formula_measurements(self):
        tm_validation = pl.DataFrame({"max_abs_diff_vs_grand_total": [0.0]})
        for difference in (float("nan"), float("inf"), float("-inf"), -1.0):
            with self.subTest(difference=difference), self.assertRaisesRegex(
                ValueError, "formula evidence"
            ):
                etl.build_validation_status(
                    tm_validation,
                    etl.MlValidationEvidence(
                        checked_rows=1,
                        cal_forecast_checked_rows=1,
                        max_formula_difference=difference,
                        formula_tolerance=etl.ML_FORMULA_TOLERANCE,
                        horizon_counts=(("M+1", 1),),
                        calculation_months=(date(2025, 5, 1),),
                        snop_months=(date(2025, 6, 1),),
                        duplicate_final_key_count=0,
                    ),
                )


class OracleProvenanceTests(unittest.TestCase):
    def load_with_manifest(
        self,
        fixture_bytes: bytes,
        *,
        source_blob: str | None = None,
        fixture_sha256: str | None = None,
    ):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            fixture_path = directory_path / "fixture.csv"
            fixture_path.write_bytes(fixture_bytes)
            manifest = json.loads(TM_ORACLE_MANIFEST.read_text(encoding="utf-8"))
            manifest["fixture_path"] = fixture_path.name
            manifest["fixture_sha256"] = fixture_sha256 or hashlib.sha256(
                fixture_bytes
            ).hexdigest()
            if source_blob is not None:
                manifest["source_git_blob_oid"] = source_blob
            manifest_path = directory_path / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with (
                patch.object(verifier, "TM_ORACLE_MANIFEST", manifest_path),
                patch.object(verifier, "_repo_path", return_value=fixture_path),
            ):
                return verifier.load_tm_regression_oracle()

    def test_current_fixture_matches_recorded_git_blob_identity(self):
        fixture_bytes = TM_ORACLE_CSV.read_bytes()
        manifest = json.loads(TM_ORACLE_MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual(
            verifier._git_blob_oid(fixture_bytes), manifest["source_git_blob_oid"]
        )
        frame, _ = verifier.load_tm_regression_oracle()
        self.assertEqual(frame.height, manifest["row_count"])

    def test_changed_fixture_with_refreshed_checksum_fails_blob_check(self):
        with self.assertRaisesRegex(AssertionError, "Git blob identity"):
            self.load_with_manifest(TM_ORACLE_CSV.read_bytes() + b"# changed\\n")

    def test_arbitrary_valid_looking_blob_identity_fails(self):
        with self.assertRaisesRegex(AssertionError, "Git blob identity"):
            self.load_with_manifest(
                TM_ORACLE_CSV.read_bytes(), source_blob="0" * 40
            )

    def test_incorrect_fixture_checksum_still_fails(self):
        with self.assertRaisesRegex(AssertionError, "checksum"):
            self.load_with_manifest(
                TM_ORACLE_CSV.read_bytes(), fixture_sha256="0" * 64
            )


class VerifierContractTests(unittest.TestCase):
    def test_command_line_verifier_rejects_tm_only_output(self):
        output_frame = pl.DataFrame(
            {
                "calculation_month": ["2025-05"],
                "snop_month": ["2025-06"],
                "parent_code": [123],
                "parent_description": ["Example"],
                "qty": [10.0],
                "source": ["tm"],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "tm-only.csv"
            output_frame.write_csv(output)

            with self.assertRaisesRegex(AssertionError, "expected source families"):
                verifier.verify_output_contract(output)


class CurrentWorkbookRegressionTests(unittest.TestCase):
    def test_current_workbooks_match_independent_oracle_and_exact_coverage(self):
        oracle, oracle_manifest = load_tm_oracle()
        current_manifest = json.loads(
            CURRENT_INPUT_MANIFEST.read_text(encoding="utf-8")
        )
        expected = current_manifest["expected"]
        metas, longs = etl.parse_all()
        build = etl.build_forecast_history(metas, longs)

        actual_tm = etl.format_forecast_history_output(
            build.tm, required_sources={"tm"}
        ).select(oracle.columns)
        canonical_oracle = canonicalize_legacy_tm_oracle(oracle)
        assert_frame_equal(
            actual_tm.sort(TM_SORT_COLUMNS),
            canonical_oracle.sort(TM_SORT_COLUMNS),
            check_dtypes=False,
        )
        self.assertEqual(oracle.height, oracle_manifest["row_count"])
        self.assertEqual(build.tm.height, expected["tm_rows"])
        self.assertEqual(build.ml.height, expected["ml_rows"])
        self.assertEqual(build.consolidated.height, expected["combined_rows"])
        self.assertEqual(build.tm["parent_code"].n_unique(), expected["tm_parents"])
        self.assertEqual(build.ml["parent_code"].n_unique(), expected["ml_parents"])
        self.assertEqual(
            month_keys(build.tm, "calculation_month"),
            expected["tm_calculation_months"],
        )
        self.assertEqual(
            month_keys(build.ml, "calculation_month"),
            expected["ml_calculation_months"],
        )
        self.assertEqual(month_keys(build.tm, "snop_month"), expected["snop_months"])
        self.assertEqual(month_keys(build.ml, "snop_month"), expected["snop_months"])
        self.assertEqual(
            list(build.ml_validation.horizon_counts),
            [tuple(item) for item in expected["ml_horizon_counts"]],
        )
        self.assertEqual(
            build.ml_validation.cal_forecast_checked_rows,
            expected["ml_rows"],
        )
        self.assertIsNotNone(build.ml_validation.max_formula_difference)
        assert build.ml_validation.max_formula_difference is not None
        self.assertLessEqual(
            build.ml_validation.max_formula_difference,
            build.ml_validation.formula_tolerance,
        )
        self.assertEqual(build.ml_validation.duplicate_final_key_count, 0)
        self.assertEqual(
            build.validation_status.to_dicts(),
            [{"source": "tm", "status": "passed"}, {"source": "ml", "status": "passed"}],
        )
        raw_ml = pl.read_excel(
            etl.ML_HISTORY_PATH,
            sheet_name="data",
            engine="calamine",
        )
        expected_ml_values = (
            raw_ml.select(
                pl.col("KEY").alias("parent_code"),
                pl.col("TRAIN_TILL")
                .dt.offset_by("1mo")
                .alias("calculation_month"),
                pl.col("MONTH_DATE").alias("snop_month"),
                pl.col("PRED_VOLUME").alias("qty"),
            )
            .sort(["parent_code", "snop_month", "calculation_month"])
        )
        actual_ml_values = build.ml.select(expected_ml_values.columns).sort(
            ["parent_code", "snop_month", "calculation_month"]
        )
        assert_frame_equal(actual_ml_values, expected_ml_values)
        self.assertEqual(build.consolidated.columns, etl.OUTPUT_COLUMNS)
        self.assertTrue(
            build.consolidated.equals(build.consolidated.sort(etl.HISTORY_SORT_COLUMNS))
        )

    def test_output_validation_requires_both_source_families(self):
        valid = pl.DataFrame(
            {
                "calculation_month": ["2025-05", "2025-05"],
                "snop_month": ["2025-06", "2025-06"],
                "parent_code": [123, 123],
                "parent_description": ["ML Example", "TM Example"],
                "qty": [12.0, 10.0],
                "source": ["ml", "tm"],
            }
        )
        etl.validate_formatted_history(valid)
        etl.validate_formatted_history(
            valid.filter(pl.col("source") == "tm"), required_sources={"tm"}
        )

        for source in ("tm", "ml"):
            with self.subTest(source=source), self.assertRaisesRegex(
                ValueError, "expected source families"
            ):
                etl.validate_formatted_history(
                    valid.filter(pl.col("source") == source)
                )

    def test_output_validation_requires_the_six_column_contract(self):
        valid = pl.DataFrame(
            {
                "calculation_month": ["2025-05", "2025-05"],
                "snop_month": ["2025-06", "2025-06"],
                "parent_code": [123, 123],
                "parent_description": ["ML Example", "TM Example"],
                "qty": [12.0, 10.0],
                "source": ["ml", "tm"],
            }
        )

        with self.assertRaisesRegex(ValueError, "expected columns"):
            etl.validate_formatted_history(valid.drop("source"))


class AtomicOutputTests(unittest.TestCase):
    @staticmethod
    def valid_history():
        return pl.DataFrame(
            {
                "calculation_month": ["2025-05", "2025-05"],
                "snop_month": ["2025-06", "2025-06"],
                "parent_code": [123, 123],
                "parent_description": ["ML Example", "TM Example"],
                "qty": [12.0, 10.0],
                "source": ["ml", "tm"],
            }
        )

    def test_generation_failure_leaves_existing_output_bytes_and_mode_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "forecast_history_waterfall.csv"
            previous_bytes = b"previous validated output\n"
            output.write_bytes(previous_bytes)
            output.chmod(0o640)
            previous_mode = stat.S_IMODE(output.stat().st_mode)

            with self.assertRaisesRegex(FileNotFoundError, "workbook not found"):
                etl.generate_forecast_history(
                    output_path=output,
                    ml_path=Path(directory) / "missing.xlsx",
                )

            self.assertEqual(output.read_bytes(), previous_bytes)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), previous_mode)

    def test_validation_failure_leaves_existing_output_byte_for_byte_unchanged(self):
        invalid = pl.DataFrame(
            {
                "calculation_month": ["2025-05"],
                "snop_month": ["2025-06"],
                "parent_code": [123],
                "parent_description": ["Example"],
                "qty": [10.0],
                "source": ["not-a-source"],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "forecast_history_waterfall.csv"
            previous_bytes = b"previous validated output\n"
            output.write_bytes(previous_bytes)
            output.chmod(0o640)
            previous_mode = stat.S_IMODE(output.stat().st_mode)

            with self.assertRaisesRegex(ValueError, "unsupported source"):
                etl.write_forecast_history_atomically(invalid, output)

            self.assertEqual(output.read_bytes(), previous_bytes)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), previous_mode)

    def test_existing_output_permissions_are_preserved(self):
        for mode in (0o644, 0o640):
            with self.subTest(mode=oct(mode)), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "forecast_history_waterfall.csv"
                output.write_bytes(b"old output\n")
                output.chmod(mode)

                etl.write_forecast_history_atomically(self.valid_history(), output)

                self.assertEqual(stat.S_IMODE(output.stat().st_mode), mode)

    def test_new_output_uses_documented_default_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "forecast_history_waterfall.csv"
            etl.write_forecast_history_atomically(self.valid_history(), output)

            self.assertEqual(
                stat.S_IMODE(output.stat().st_mode), etl.DEFAULT_OUTPUT_MODE
            )
    def test_valid_output_is_replaced_after_round_trip_validation(self):
        valid = self.valid_history()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "forecast_history_waterfall.csv"
            etl.write_forecast_history_atomically(valid, output)
            assert_frame_equal(pl.read_csv(output), valid)


if __name__ == "__main__":
    unittest.main()
