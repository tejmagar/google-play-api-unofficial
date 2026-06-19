"""google-play-api — Play Store research CLI (suggestions, search, per-app details, publisher)."""

from .suggest import fetch_suggestions, Filter
from .search import fetch_apps
from .details import fetch_app_details, AppNotFoundError
from .publisher import fetch_publisher_apps

__all__ = [
    "fetch_suggestions",
    "fetch_apps",
    "fetch_app_details",
    "fetch_publisher_apps",
    "Filter",
    "AppNotFoundError",
]
__version__ = "0.1.0"
