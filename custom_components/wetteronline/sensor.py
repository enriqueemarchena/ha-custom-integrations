"""Sensor platform for Wetteronline."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN


def _parse_date(value: str | None):
    if not value:
        return None
    return dt_util.parse_datetime(value)


def _select_day(days: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not days:
        return None
    today = dt_util.now().date()
    for day in days:
        date = _parse_date(day.get("date"))
        if date and dt_util.as_local(date).date() == today:
            return day
    return days[0]


def _get_warnings_levels(warnings: dict[str, Any] | None) -> dict[str, Any]:
    if not warnings:
        return {}
    levels = {}
    for key, value in warnings.items():
        if isinstance(value, dict) and "level_value" in value:
            levels[key] = value.get("level_value")
    return levels


class WetteronlineBaseSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, key: str, name: str, icon: str | None = None):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Wetteronline",
            model="App API",
        )
        if icon:
            self._attr_icon = icon


class WetteronlineAQISensor(WetteronlineBaseSensor):
    _attr_native_unit_of_measurement = "AQI"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "aqi", "AQI")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("aqi", {}).get("current", {}).get("index")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        current = self.coordinator.data.get("aqi", {}).get("current", {})
        return {
            "text": current.get("text"),
            "color": current.get("color"),
            "text_color": current.get("text_color"),
            "days": self.coordinator.data.get("aqi", {}).get("days"),
        }


class WetteronlineUVSensor(WetteronlineBaseSensor):
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "uv_max", "UV Max", "mdi:sun-wireless")

    @property
    def native_value(self) -> float | None:
        day = _select_day(self.coordinator.data.get("uv", {}).get("days"))
        if not day:
            return None
        values = [
            hour.get("uv_index", {}).get("value")
            for hour in day.get("hours", [])
            if hour.get("uv_index")
        ]
        return max(values) if values else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        day = _select_day(self.coordinator.data.get("uv", {}).get("days"))
        return {"day": day}


class WetteronlinePollenSensor(WetteronlineBaseSensor):
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "pollen_max", "Pollen Max", "mdi:flower")

    @property
    def native_value(self) -> int | None:
        day = _select_day(self.coordinator.data.get("pollen", {}).get("days"))
        if not day:
            return None
        return day.get("max_burden", {}).get("value")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        day = _select_day(self.coordinator.data.get("pollen", {}).get("days"))
        return {
            "max_burden": day.get("max_burden") if day else None,
            "pollen": day.get("pollen") if day else None,
        }


class WetteronlineWarningsSensor(WetteronlineBaseSensor):
    _attr_state_class = None

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "warnings_level", "Warnings Level", "mdi:alert")

    @property
    def native_value(self) -> int | None:
        levels = _get_warnings_levels(self.coordinator.data.get("warnings"))
        return max(levels.values()) if levels else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        warnings = self.coordinator.data.get("warnings") or {}
        return {
            "focus_type": warnings.get("focus_type"),
            "levels": _get_warnings_levels(warnings),
            "level_legend": warnings.get("level_legend"),
        }


class WetteronlineStationSensor(WetteronlineBaseSensor):
    """Sensor for station data."""

    def __init__(
        self,
        coordinator,
        entry,
        key: str,
        name: str,
        device_class: SensorDeviceClass | None,
        unit_of_measurement: str | None,
        value_fn,
    ):
        super().__init__(coordinator, entry, key, name)
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._value_fn = value_fn

    @property
    def native_value(self) -> float | int | None:
        station_report = self.coordinator.data.get("station_report")
        if not station_report:
            return None
        return self._value_fn(station_report)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    unit_system = coordinator.data["meta"]["unit_system"]
    is_imperial = unit_system == "imperial"

    station_sensors = [
        WetteronlineStationSensor(
            coordinator,
            entry,
            "station_temperature",
            "Station Temperature",
            SensorDeviceClass.TEMPERATURE,
            UnitOfTemperature.FAHRENHEIT if is_imperial else UnitOfTemperature.CELSIUS,
            lambda data: data.get("temperature", {}).get("fahrenheit" if is_imperial else "celsius"),
        ),
        WetteronlineStationSensor(
            coordinator,
            entry,
            "station_wind_speed",
            "Station Wind Speed",
            SensorDeviceClass.WIND_SPEED,
            UnitOfSpeed.MILES_PER_HOUR if is_imperial else UnitOfSpeed.KILOMETERS_PER_HOUR,
            lambda data: data.get("wind", {}).get("speed", {}).get("mph" if is_imperial else "kph"),
        ),
        WetteronlineStationSensor(
            coordinator,
            entry,
            "station_wind_gust",
            "Station Wind Gust",
            SensorDeviceClass.WIND_SPEED,
            UnitOfSpeed.MILES_PER_HOUR if is_imperial else UnitOfSpeed.KILOMETERS_PER_HOUR,
            lambda data: data.get("wind", {}).get("gust", {}).get("mph" if is_imperial else "kph"),
        ),
        WetteronlineStationSensor(
            coordinator,
            entry,
            "station_wind_direction",
            "Station Wind Direction",
            SensorDeviceClass.WIND_DIRECTION,
            DEGREE,
            lambda data: data.get("wind", {}).get("direction"),
        ),
        WetteronlineStationSensor(
            coordinator,
            entry,
            "station_height",
            "Station Height",
            SensorDeviceClass.DISTANCE,
            UnitOfLength.FEET if is_imperial else UnitOfLength.METERS,
            lambda data: data.get("height", {}).get("feet" if is_imperial else "meter"),
        ),
    ]

    async_add_entities(
        [
            WetteronlineAQISensor(coordinator, entry),
            WetteronlineUVSensor(coordinator, entry),
            WetteronlinePollenSensor(coordinator, entry),
            WetteronlineWarningsSensor(coordinator, entry),
            *station_sensors,
        ]
    )
