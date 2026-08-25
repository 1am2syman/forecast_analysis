"""Generate the forecast-history CSV through the validated atomic path."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import forecast_history_pipeline as pipeline  # pyright: ignore[reportMissingImports]


def main() -> int:
    """Build both sources and atomically publish the validated output."""
    build = pipeline.generate_forecast_history()
    print(
        "FORECAST HISTORY GENERATED "
        f"tm={build.tm.height} ml={build.ml.height} "
        f"combined={build.consolidated.height}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
