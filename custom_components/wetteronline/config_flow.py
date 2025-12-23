"""Config flow for Wetteronline."""

from __future__ import annotations

from typing import Any

import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_ELEVATION,
    CONF_LANGUAGE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WetteronlineApiError, WetteronlineClient
from .const import (
    CONF_COUNTRY_CODE,
    CONF_ENABLE_RADAR,
    CONF_LOCATION_ID,
    CONF_SCAN_INTERVAL,
    CONF_TIME_ZONE,
    CONF_UNIT_SYSTEM,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_LANGUAGE,
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
    SUPPORTED_LANGUAGES,
    default_unit_system,
)

LOGGER = logging.getLogger(__name__)


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class NoStation(Exception):
    """Error to indicate no station found."""


async def _async_validate_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    client = WetteronlineClient(async_get_clientsession(hass))
    latitude = float(data[CONF_LATITUDE])
    longitude = float(data[CONF_LONGITUDE])
    altitude = float(data[CONF_ELEVATION])
    language = data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
    location_id = data.get(CONF_LOCATION_ID)

    try:
        station_name = None
        if not location_id:
            stations = await client.get_nearby_stations(latitude, longitude, language)
            if not stations:
                raise NoStation
            location_id = stations[0].get("location_id")
            station_name = stations[0].get("name")

        if not location_id:
            raise NoStation

        unit_system = default_unit_system(hass)
        system_of_measurement = unit_system
        windunit = "mph" if unit_system == "imperial" else "kmh"
        await client.get_nowcast(
            latitude=latitude,
            longitude=longitude,
            altitude=altitude,
            location_id=location_id,
            language=language,
            timezone=hass.config.time_zone,
            system_of_measurement=system_of_measurement,
            windunit=windunit,
            timeformat="H:mm",
        )
    except NoStation as err:
        raise err
    except WetteronlineApiError as err:
        raise CannotConnect from err
    except Exception as err:  # pylint: disable=broad-except
        LOGGER.exception("Unexpected error validating Wetteronline config")
        raise err

    title = (
        data.get(CONF_NAME)
        or station_name
        or f"Wetteronline {latitude:.4f},{longitude:.4f}"
    )
    return {"title": title, "location_id": location_id}


class WetteronlineConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Wetteronline."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _async_validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except NoStation:
                errors["base"] = "no_station"
            except Exception:
                errors["base"] = "unknown"
            else:
                data = {
                    CONF_LATITUDE: user_input[CONF_LATITUDE],
                    CONF_LONGITUDE: user_input[CONF_LONGITUDE],
                    CONF_ELEVATION: user_input[CONF_ELEVATION],
                    CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                    CONF_LOCATION_ID: user_input.get(CONF_LOCATION_ID)
                    or info["location_id"],
                }
                return self.async_create_entry(title=info["title"], data=data)

        defaults = {
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
            CONF_ELEVATION: self.hass.config.elevation,
            CONF_LANGUAGE: DEFAULT_LANGUAGE,
        }

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME): str,
                vol.Required(
                    CONF_LATITUDE, default=defaults[CONF_LATITUDE]
                ): vol.Coerce(float),
                vol.Required(
                    CONF_LONGITUDE, default=defaults[CONF_LONGITUDE]
                ): vol.Coerce(float),
                vol.Required(
                    CONF_ELEVATION, default=defaults[CONF_ELEVATION]
                ): vol.Coerce(float),
                vol.Required(CONF_LANGUAGE, default=defaults[CONF_LANGUAGE]): vol.In(
                    SUPPORTED_LANGUAGES
                ),
                vol.Optional(CONF_LOCATION_ID): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        return await self.async_step_user(user_input)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return WetteronlineOptionsFlowHandler(config_entry)


class WetteronlineOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Wetteronline options."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    def _get_value(self, key: str, default: Any) -> Any:
        if key in self.entry.options:
            return self.entry.options[key]
        if key in self.entry.data:
            return self.entry.data[key]
        return default

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LATITUDE,
                    default=self._get_value(CONF_LATITUDE, self.hass.config.latitude),
                ): vol.Coerce(float),
                vol.Required(
                    CONF_LONGITUDE,
                    default=self._get_value(CONF_LONGITUDE, self.hass.config.longitude),
                ): vol.Coerce(float),
                vol.Required(
                    CONF_ELEVATION,
                    default=self._get_value(CONF_ELEVATION, self.hass.config.elevation),
                ): vol.Coerce(float),
                vol.Required(
                    CONF_LANGUAGE,
                    default=self._get_value(CONF_LANGUAGE, DEFAULT_LANGUAGE),
                ): vol.In(SUPPORTED_LANGUAGES),
                vol.Optional(
                    CONF_LOCATION_ID,
                    default=self._get_value(CONF_LOCATION_ID, ""),
                ): str,
                vol.Required(
                    CONF_COUNTRY_CODE,
                    default=self._get_value(
                        CONF_COUNTRY_CODE,
                        self.hass.config.country or DEFAULT_COUNTRY_CODE,
                    ),
                ): str,
                vol.Required(
                    CONF_TIME_ZONE,
                    default=self._get_value(CONF_TIME_ZONE, self.hass.config.time_zone),
                ): str,
                vol.Required(
                    CONF_UNIT_SYSTEM,
                    default=self._get_value(
                        CONF_UNIT_SYSTEM, default_unit_system(self.hass)
                    ),
                ): vol.In(["metric", "imperial"]),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self._get_value(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MIN
                    ),
                ): vol.All(int, vol.Range(min=1, max=120)),
                vol.Optional(
                    CONF_ENABLE_RADAR,
                    default=self._get_value(CONF_ENABLE_RADAR, True),
                ): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
