"""Data coordinator for Wetteronline."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.const import (
    CONF_ELEVATION,
    CONF_LANGUAGE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WetteronlineApiError, WetteronlineClient
from .const import (
    CONF_COUNTRY_CODE,
    CONF_LOCATION_ID,
    CONF_SCAN_INTERVAL,
    CONF_TIME_ZONE,
    CONF_UNIT_SYSTEM,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_LANGUAGE,
    DEFAULT_SCAN_INTERVAL_MIN,
    DEFAULT_TIME_FORMAT,
    DOMAIN,
    default_unit_system,
)

LOGGER = logging.getLogger(__name__)


class WetteronlineDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch data from Wetteronline."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self.client = WetteronlineClient(async_get_clientsession(hass))
        update_interval = timedelta(
            minutes=self._get_entry_value(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MIN)
        )
        super().__init__(
            hass,
            logger=LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    def _get_entry_value(self, key: str, default: Any | None = None) -> Any:
        if key in self.entry.options:
            return self.entry.options[key]
        if key in self.entry.data:
            return self.entry.data[key]
        return default

    def _unit_system(self) -> str:
        return self._get_entry_value(CONF_UNIT_SYSTEM, default_unit_system(self.hass))

    def _timezone(self) -> str:
        return self._get_entry_value(CONF_TIME_ZONE, self.hass.config.time_zone)

    def _language(self) -> str:
        return self._get_entry_value(CONF_LANGUAGE, DEFAULT_LANGUAGE)

    def _country_code(self) -> str:
        return self._get_entry_value(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE)

    async def _async_update_data(self) -> dict[str, Any]:
        latitude = float(
            self._get_entry_value(CONF_LATITUDE, self.hass.config.latitude)
        )
        longitude = float(
            self._get_entry_value(CONF_LONGITUDE, self.hass.config.longitude)
        )
        altitude = float(
            self._get_entry_value(CONF_ELEVATION, self.hass.config.elevation)
        )
        language = self._language()
        timezone = self._timezone()
        unit_system = self._unit_system()
        system_of_measurement = "imperial" if unit_system == "imperial" else "metric"
        windunit = "mph" if unit_system == "imperial" else "kmh"
        location_id = self._get_entry_value(CONF_LOCATION_ID)

        try:
            station = None
            if not location_id:
                stations = await self.client.get_nearby_stations(
                    latitude, longitude, language
                )
                if not stations:
                    raise UpdateFailed("No station found for coordinates")
                station = stations[0]
                location_id = station.get("location_id")
            if not location_id:
                raise UpdateFailed("Missing location_id")

            nowcast_task = self.client.get_nowcast(
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                location_id=location_id,
                language=language,
                timezone=timezone,
                system_of_measurement=system_of_measurement,
                windunit=windunit,
                timeformat=DEFAULT_TIME_FORMAT,
            )
            aqi_task = self.client.get_aqi(
                location_id=location_id, language=language, timezone=timezone
            )
            uv_task = self.client.get_uv_index(
                location_id=location_id, timezone=timezone
            )
            pollen_task = self.client.get_pollen(
                location_id=location_id, language=language, timezone=timezone
            )
            warnings_task = self.client.get_warnings(
                iso_country_code=self._country_code(), timezone=timezone
            )
            radar_task = self.client.get_radar_metadata(
                latitude=latitude, longitude=longitude, language=language
            )
            # Use nearby stations to get the report, as direct ID lookup seems to fail
            station_report_task = self.client.get_nearby_stations(
                latitude=latitude, longitude=longitude, language=language
            )
            forecast_task = self.client.get_forecast(
                location_id=location_id, timezone=timezone
            )

            (
                nowcast,
                aqi,
                uv,
                pollen,
                warnings,
                radar,
                nearby_stations,
                forecast,
            ) = await asyncio.gather(
                nowcast_task,
                aqi_task,
                uv_task,
                pollen_task,
                warnings_task,
                radar_task,
                station_report_task,
                forecast_task,
                return_exceptions=True,
            )

            # Handle exceptions for individual tasks
            if isinstance(nowcast, Exception):
                raise nowcast

            # Optional tasks
            if isinstance(aqi, Exception):
                LOGGER.warning("Failed to fetch AQI: %s", aqi)
                aqi = {}
            if isinstance(uv, Exception):
                LOGGER.warning("Failed to fetch UV: %s", uv)
                uv = {}
            if isinstance(pollen, Exception):
                LOGGER.warning("Failed to fetch Pollen: %s", pollen)
                pollen = {}
            if isinstance(warnings, Exception):
                LOGGER.warning("Failed to fetch Warnings: %s", warnings)
                warnings = {}
            if isinstance(radar, Exception):
                LOGGER.warning("Failed to fetch Radar: %s", radar)
                radar = {}
            if isinstance(nearby_stations, Exception):
                LOGGER.warning("Failed to fetch Stations: %s", nearby_stations)
                nearby_stations = []
            if isinstance(forecast, Exception):
                LOGGER.warning("Failed to fetch Forecast: %s", forecast)
                forecast = []

            station_report = None
            if nearby_stations:
                # Try to find the station with the same ID
                for s in nearby_stations:
                    if s.get("location_id") == location_id:
                        station_report = s
                        break
                # If not found, use the first one (closest)
                if not station_report:
                    station_report = nearby_stations[0]

        except WetteronlineApiError as err:
            raise UpdateFailed(f"API error: {err}") from err
        except UpdateFailed:
            raise
        except Exception as err:  # pylint: disable=broad-except
            raise UpdateFailed(str(err)) from err

        return {
            "location_id": location_id,
            "station": station,
            "nowcast": nowcast,
            "aqi": aqi,
            "uv": uv,
            "pollen": pollen,
            "warnings": warnings,
            "radar": radar,
            "station_report": station_report,
            "forecast": forecast,
            "meta": {
                "latitude": latitude,
                "longitude": longitude,
                "altitude": altitude,
                "language": language,
                "timezone": timezone,
                "unit_system": unit_system,
            },
        }
