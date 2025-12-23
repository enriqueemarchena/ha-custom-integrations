"""Weather platform for Wetteronline."""

from __future__ import annotations

from collections import Counter
from typing import Any

from homeassistant.components.weather import WeatherEntity, WeatherEntityFeature
from homeassistant.const import UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, default_unit_system


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _probability_to_pct(value: Any) -> int | None:
    prob = _to_float(value)
    if prob is None:
        return None
    if prob <= 1:
        prob = prob * 100
    return int(round(prob))


def _map_condition(value: str | None) -> str | None:
    if not value:
        return None
    text = value.lower()

    # Check if it looks like a Wetteronline code (e.g. bdr1__, so____)
    # Codes are typically 6 chars long with underscores
    if "_" in text and len(text) == 6:
        prefix = text[:2]
        suffix = text[2:]

        # Precip logic in suffix
        if "g" in suffix:
            return "lightning-rainy"
        if "sr" in suffix:
            return "snowy-rainy"
        if "sn" in suffix:
            return "snowy"
        if "h" in suffix:
            return "hail"
        if "r" in suffix:
            return "rainy"
        if "s" in suffix:  # Shower
            return "rainy"

        # Base conditions
        if prefix == "so":
            return "sunny"
        if prefix == "mo":
            return "clear-night"
        if prefix == "wb":
            return "partlycloudy"
        if prefix in ("bd", "bw", "md", "mb", "mw"):
            return "cloudy"
        if prefix == "nb":
            return "fog"

    # Fallback to text matching for descriptions
    # Thunderstorm
    if any(
        x in text
        for x in ("thunder", "lightning", "tormenta", "rayos", "gewitter", "blitz")
    ):
        return "lightning-rainy"

    # Snow/Sleet
    if any(
        x in text for x in ("sleet", "freezing", "aguanieve", "helada", "schneeregen")
    ):
        return "snowy-rainy"
    if any(x in text for x in ("snow", "nieve", "schnee")):
        return "snowy"
    if any(x in text for x in ("hail", "granizo", "hagel")):
        return "hail"

    # Rain
    if any(
        x in text for x in ("rain", "shower", "lluvia", "chubasco", "regen", "schauer")
    ):
        return "rainy"

    # Fog
    if any(x in text for x in ("fog", "mist", "niebla", "neblina", "nebel", "dunst")):
        return "fog"

    # Cloudy
    if any(x in text for x in ("partly", "parcial", "intervalos", "wolkig", "heiter")):
        return "partlycloudy"
    if any(
        x in text
        for x in ("cloud", "overcast", "nublado", "cubierto", "bedeckt", "wolken")
    ):
        return "cloudy"

    # Clear
    if any(
        x in text
        for x in ("clear", "sun", "despejado", "soleado", "sol", "sonne", "klar")
    ):
        if "night" in text or "noche" in text or "nacht" in text:
            return "clear-night"
        return "sunny"

    return None


def _wind_speed(data: dict[str, Any], unit_system: str) -> float | None:
    speed = data.get("wind", {}).get("speed", {})
    if unit_system == "imperial":
        return _to_float(speed.get("miles_per_hour", {}).get("value"))
    return _to_float(speed.get("kilometer_per_hour", {}).get("value"))


def _visibility(value: Any, unit_system: str) -> float | None:
    visibility = _to_float(value)
    if visibility is None:
        return None
    if unit_system == "imperial":
        return visibility / 1609.344
    return visibility / 1000


def _humidity(value: Any) -> int | None:
    humidity = _to_float(value)
    if humidity is None:
        return None
    return int(round(humidity * 100)) if humidity <= 1 else int(round(humidity))


def _condition_from_entry(entry: dict[str, Any]) -> str | None:
    return _map_condition(entry.get("symbol") or entry.get("weather_condition_image"))


class WetteronlineWeatherEntity(CoordinatorEntity, WeatherEntity):
    """Weather entity for Wetteronline."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_weather"
        self._attr_name = entry.title
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Wetteronline",
            model="App API",
        )

    @property
    def supported_features(self) -> WeatherEntityFeature:
        return (
            WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY
        )

    @property
    def native_temperature_unit(self) -> str:
        return (
            UnitOfTemperature.FAHRENHEIT
            if self._unit_system == "imperial"
            else UnitOfTemperature.CELSIUS
        )

    @property
    def native_pressure_unit(self) -> str:
        return (
            UnitOfPressure.INHG
            if self._unit_system == "imperial"
            else UnitOfPressure.HPA
        )

    @property
    def native_wind_speed_unit(self) -> str:
        return (
            UnitOfSpeed.MILES_PER_HOUR
            if self._unit_system == "imperial"
            else UnitOfSpeed.KILOMETERS_PER_HOUR
        )

    @property
    def _unit_system(self) -> str:
        return self.coordinator.data.get("meta", {}).get(
            "unit_system",
            default_unit_system(self.hass),
        )

    @property
    def _current(self) -> dict[str, Any]:
        return self.coordinator.data.get("nowcast", {}).get("current", {})

    @property
    def temperature(self) -> float | None:
        return _to_float(self._current.get("temperature", {}).get("air"))

    @property
    def native_temperature(self) -> float | None:
        return self.temperature

    @property
    def apparent_temperature(self) -> float | None:
        return _to_float(self._current.get("temperature", {}).get("apparent"))

    @property
    def native_apparent_temperature(self) -> float | None:
        return self.apparent_temperature

    @property
    def humidity(self) -> int | None:
        humidity = _to_float(self._current.get("humidity"))
        if humidity is None:
            return None
        return int(round(humidity * 100)) if humidity <= 1 else int(round(humidity))

    @property
    def pressure(self) -> float | None:
        pressure = self._current.get("air_pressure", {})
        return _to_float(
            pressure.get("inhg" if self._unit_system == "imperial" else "hpa")
        )

    @property
    def native_pressure(self) -> float | None:
        return self.pressure

    @property
    def wind_speed(self) -> float | None:
        return _wind_speed(self._current, self._unit_system)

    @property
    def native_visibility(self) -> float | None:
        return _visibility(self._current.get("visibility"), self._unit_system)

    @property
    def native_wind_speed(self) -> float | None:
        return self.wind_speed

    @property
    def wind_bearing(self) -> float | None:
        return _to_float(self._current.get("wind", {}).get("direction"))

    @property
    def precipitation_probability(self) -> int | None:
        return _probability_to_pct(
            self._current.get("precipitation", {}).get("probability")
        )

    @property
    def condition(self) -> str | None:
        return _condition_from_entry(self._current)

    @property
    def sunrise(self):
        sun = self._current.get("sun", {})
        value = sun.get("rise")
        if not value:
            return None
        return dt_util.as_local(dt_util.parse_datetime(value))

    @property
    def sunset(self):
        sun = self._current.get("sun", {})
        value = sun.get("set")
        if not value:
            return None
        return dt_util.as_local(dt_util.parse_datetime(value))

    @property
    def forecast(self) -> list[dict[str, Any]] | None:
        return self._hourly_forecast()

    async def async_forecast_hourly(self) -> list[dict[str, Any]] | None:
        return self._hourly_forecast()

    async def async_forecast_daily(self) -> list[dict[str, Any]] | None:
        return self._daily_forecast()

    def _hourly_forecast(self) -> list[dict[str, Any]] | None:
        nowcast = self.coordinator.data.get("nowcast", {})
        forecast_entries: list[dict[str, Any]] = []
        seen: set[Any] = set()

        # Combine nowcast hours and trend items
        sources = []
        if hours := nowcast.get("hours"):
            sources.append(hours)
        if trend := nowcast.get("trend", {}).get("items"):
            sources.append(trend)

        for source in sources:
            for hour in source or []:
                when = dt_util.parse_datetime(hour.get("date"))
                if when is None:
                    continue
                when_local = dt_util.as_local(when)
                if when_local in seen:
                    continue
                seen.add(when_local)
                precipitation = hour.get("precipitation", {})
                dew_point = hour.get("dew_point", {})
                pressure = hour.get("air_pressure", {})
                entry: dict[str, Any] = {
                    "datetime": when_local,
                    "condition": _condition_from_entry(hour),
                    "temperature": _to_float(hour.get("temperature", {}).get("air")),
                    "precipitation_probability": _probability_to_pct(
                        precipitation.get("probability")
                    ),
                    "wind_speed": _wind_speed(hour, self._unit_system),
                    "wind_bearing": _to_float(hour.get("wind", {}).get("direction")),
                    "pressure": _to_float(
                        pressure.get(
                            "inhg" if self._unit_system == "imperial" else "hpa"
                        )
                    ),
                    "dew_point": _to_float(
                        dew_point.get(
                            "fahrenheit"
                            if self._unit_system == "imperial"
                            else "celsius"
                        )
                    ),
                    "humidity": _humidity(hour.get("humidity")),
                    "visibility": _visibility(
                        hour.get("visibility"), self._unit_system
                    ),
                }
                forecast_entries.append(
                    {key: value for key, value in entry.items() if value is not None}
                )

        # Also try to add hourly data from the long-term forecast if available
        # The long-term forecast has daily items, but maybe we can extract more?
        # Actually, the 'forecast' endpoint returns daily summaries, not hourly.
        # But let's check if we can get more hours from the 'trend' part of nowcast.
        # The 'trend' usually goes further than 'hours'.

        forecast_entries.sort(key=lambda entry: entry["datetime"])
        return forecast_entries or None

    def _parse_daily_forecast(self, data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        forecast_entries = []
        for day in data:
            date_str = day.get("date")
            if not date_str:
                continue

            dt = dt_util.parse_datetime(date_str)
            if not dt:
                continue

            # Map condition using symbol_description or symbol
            # The API returns symbols like 'w_symbol_1' or descriptions like 'sunny'
            condition = _map_condition(day.get("symbol_description"))
            if not condition:
                condition = _map_condition(day.get("symbol"))

            entry = {
                "datetime": dt,
                "temperature": _to_float(
                    day.get("temperature", {}).get("max", {}).get("air")
                ),
                "templow": _to_float(
                    day.get("temperature", {}).get("min", {}).get("air")
                ),
                "precipitation_probability": _probability_to_pct(
                    day.get("precipitation", {}).get("probability")
                ),
                "condition": condition,
                "wind_speed": _wind_speed(day, self._unit_system),
                "wind_bearing": _to_float(day.get("wind", {}).get("direction")),
                "humidity": _humidity(day.get("humidity")),
                "pressure": _to_float(
                    day.get("air_pressure", {}).get(
                        "inhg" if self._unit_system == "imperial" else "hpa"
                    )
                ),
                "uv_index": _to_float(day.get("uv_index", {}).get("value")),
            }
            forecast_entries.append(
                {key: value for key, value in entry.items() if value is not None}
            )

        forecast_entries.sort(key=lambda entry: entry["datetime"])
        return forecast_entries

    def _daily_forecast(self) -> list[dict[str, Any]] | None:
        # Try to use the dedicated forecast data first
        forecast_data = self.coordinator.data.get("forecast")
        if forecast_data:
            return self._parse_daily_forecast(forecast_data)

        # Fallback to aggregating hourly forecast (nowcast)
        hourly = self._hourly_forecast()
        if not hourly:
            return None

        grouped: dict[Any, dict[str, Any]] = {}
        for entry in hourly:
            when = entry["datetime"]
            day = when.date()
            bucket = grouped.setdefault(
                day,
                {
                    "datetime": when.replace(hour=0, minute=0, second=0, microsecond=0),
                    "temperatures": [],
                    "precip": [],
                    "conditions": [],
                },
            )
            if (temp := entry.get("temperature")) is not None:
                bucket["temperatures"].append(temp)
            if (prob := entry.get("precipitation_probability")) is not None:
                bucket["precip"].append(prob)
            if (condition := entry.get("condition")) is not None:
                bucket["conditions"].append(condition)

        daily_forecast: list[dict[str, Any]] = []
        for _, bucket in sorted(grouped.items()):
            if not bucket["temperatures"]:
                continue
            day_entry: dict[str, Any] = {
                "datetime": bucket["datetime"],
                "temperature": max(bucket["temperatures"]),
                "templow": min(bucket["temperatures"]),
            }
            if bucket["precip"]:
                day_entry["precipitation_probability"] = max(bucket["precip"])
            if bucket["conditions"]:
                day_entry["condition"] = Counter(bucket["conditions"]).most_common(1)[
                    0
                ][0]
            daily_forecast.append(day_entry)

        return daily_forecast or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "location_id": self.coordinator.data.get("location_id"),
            "symbol": self._current.get("symbol"),
            "smog_level": self._current.get("smog_level"),
            "dew_point": self._current.get("dew_point", {}).get(
                "fahrenheit" if self._unit_system == "imperial" else "celsius"
            ),
            "water_temperature": self._current.get("temperature", {}).get("water"),
            "precipitation_type": self._current.get("precipitation", {}).get("type"),
            "precipitation_probability": _probability_to_pct(
                self._current.get("precipitation", {}).get("probability")
            ),
            "visibility": _visibility(
                self._current.get("visibility"), self._unit_system
            ),
            "moon": self.coordinator.data.get("nowcast", {}).get("moon"),
        }
        station = self.coordinator.data.get("station") or {}
        if station:
            attrs["station_name"] = station.get("name")
            attrs["station_id"] = station.get("location_id")
        return attrs


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Wetteronline weather entity."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WetteronlineWeatherEntity(coordinator, entry)])
