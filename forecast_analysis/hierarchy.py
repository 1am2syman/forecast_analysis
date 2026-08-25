"""Clean product-hierarchy mappings and retain their quality evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import polars as pl

from ._utils import normalize_integer_values, normalize_text_values, require_columns
from .contracts import HIERARCHY_COLUMNS, HIERARCHY_DIAGNOSTIC_COLUMNS, HierarchyResult

HIERARCHY_SOURCE_COLUMNS = ["material_code", "material_desc", "material_group_code"]


def _select_description(values: list[str | None]) -> str | None:
    counts = Counter(value for value in values if value is not None)
    if not counts:
        return None
    return min(counts, key=lambda value: (-counts[value], value))


def normalize_hierarchy(raw: pl.DataFrame) -> HierarchyResult:
    """Collapse hierarchy rows to one deterministic mapping per parent code."""
    require_columns(raw, HIERARCHY_SOURCE_COLUMNS, "product hierarchy")
    work = pl.DataFrame(
        {
            "parent_code": normalize_integer_values(
                raw.get_column("material_code").to_list(),
                "material_code",
                "product hierarchy",
            ),
            "hierarchy_description": normalize_text_values(
                raw.get_column("material_desc").to_list(),
                "material_desc",
                "product hierarchy",
            ),
            "brand": normalize_text_values(
                raw.get_column("material_group_code").to_list(),
                "material_group_code",
                "product hierarchy",
            ),
        }
    ).unique()

    grouped: defaultdict[int, dict[str, list[str | None]]] = defaultdict(
        lambda: {"brand": [], "description": []}
    )
    for row in work.to_dicts():
        grouped[row["parent_code"]]["brand"].append(row["brand"])
        grouped[row["parent_code"]]["description"].append(
            row["hierarchy_description"]
        )

    hierarchy_rows: list[dict[str, object]] = []
    diagnostic_rows: list[dict[str, object]] = []
    for parent_code in sorted(grouped):
        values = grouped[parent_code]
        brands = sorted({brand for brand in values["brand"] if brand is not None})
        descriptions = [
            description
            for description in values["description"]
            if description is not None
        ]
        if len(brands) > 1:
            mapping_status = "conflict"
            brand = None
            diagnostic = "conflicting brand mappings: " + " | ".join(brands)
        elif not brands:
            mapping_status = "unmapped"
            brand = None
            diagnostic = "no usable brand mapping"
        else:
            mapping_status = "mapped"
            brand = brands[0]
            diagnostic = None

        hierarchy_rows.append(
            {
                "parent_code": parent_code,
                "hierarchy_description": _select_description(
                    values["description"]
                ),
                "brand": brand,
                "mapping_status": mapping_status,
            }
        )
        diagnostic_rows.append(
            {
                "parent_code": parent_code,
                "mapping_status": mapping_status,
                "candidate_brands": " | ".join(brands) or None,
                "candidate_descriptions": " | ".join(sorted(set(descriptions)))
                or None,
                "diagnostic": diagnostic,
            }
        )

    frame = pl.DataFrame(hierarchy_rows, schema={
        "parent_code": pl.Int64,
        "hierarchy_description": pl.String,
        "brand": pl.String,
        "mapping_status": pl.String,
    }).select(HIERARCHY_COLUMNS)
    diagnostics = pl.DataFrame(diagnostic_rows, schema={
        "parent_code": pl.Int64,
        "mapping_status": pl.String,
        "candidate_brands": pl.String,
        "candidate_descriptions": pl.String,
        "diagnostic": pl.String,
    }).select(HIERARCHY_DIAGNOSTIC_COLUMNS)
    return HierarchyResult(frame=frame, diagnostics=diagnostics)


# Domain name used by the dashboard specification; normalization is the implementation detail.
clean_hierarchy = normalize_hierarchy


def load_hierarchy(path: Path) -> HierarchyResult:
    """Read and clean the approved product-hierarchy workbook."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"product hierarchy workbook not found: {path}")
    try:
        raw = pl.read_excel(path, engine="calamine")
    except Exception as exc:
        raise ValueError(f"unable to read product hierarchy workbook {path}: {exc}") from exc
    return normalize_hierarchy(raw)
