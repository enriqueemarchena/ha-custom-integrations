"""Constants for the Wetteronline integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.util.unit_system import METRIC_SYSTEM

DOMAIN = "wetteronline"
NAME = "Wetteronline"

API_BASE = "https://api-app.wo-cloud.com"
API_FORECAST_BASE = "https://api-app.wetteronline.de"
TILES_BASE = "https://tiles.wo-cloud.com"
AUTH_HEADER = "Basic d29hcHA6enZnR2V1MjliTHhOamhRVw=="
AUTH_HEADER_FORECAST = "Basic d2V0dGVyb25saW5lOkVWa3lraXRZOGJkazNKYk4="
USER_AGENT = "WetterApp/436435"

DEFAULT_TIMEOUT = 10
DEFAULT_SCAN_INTERVAL_MIN = 10
DEFAULT_LANGUAGE = "es-ES"
DEFAULT_COUNTRY_CODE = "ES"
DEFAULT_TIME_FORMAT = "H:mm"

CONF_LOCATION_ID = "location_id"
CONF_COUNTRY_CODE = "country_code"
CONF_UNIT_SYSTEM = "unit_system"
CONF_TIME_ZONE = "time_zone"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ENABLE_RADAR = "enable_radar"

SUPPORTED_LANGUAGES = {
    "es-ES": "Español",
    "en-US": "English",
}

PLATFORMS = ["weather", "sensor", "camera"]


def default_unit_system(hass: HomeAssistant) -> str:
    """Return Home Assistant unit system name."""
    return "metric" if hass.config.units is METRIC_SYSTEM else "imperial"
