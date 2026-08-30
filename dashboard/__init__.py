"""Static forecast-dashboard HTTP and browser adapters."""

from .adapter import (  # pyright: ignore[reportMissingImports]
    DashboardDataService,
    DashboardRequestError,
)

__all__ = ["DashboardDataService", "DashboardRequestError"]
