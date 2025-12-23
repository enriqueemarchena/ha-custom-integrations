"""API client for Wetteronline."""

from __future__ import annotations

from typing import Any

import async_timeout
from aiohttp import ClientError, ClientSession

from .const import (
    API_BASE,
    API_FORECAST_BASE,
    AUTH_HEADER,
    AUTH_HEADER_FORECAST,
    DEFAULT_TIMEOUT,
    TILES_BASE,
    USER_AGENT,
)


class WetteronlineApiError(Exception):
    """API error for Wetteronline."""


class WetteronlineClient:
    def __init__(self, session: ClientSession, timeout: int | None = None) -> None:
        self._session = session
        self._timeout = timeout or DEFAULT_TIMEOUT

    async def _request(
        self,
        path: str,
        params: dict[str, Any],
        base_url: str = API_BASE,
        auth: bool = True,
        auth_header: str | None = None,
    ) -> Any:
        headers = {
            "User-Agent": USER_AGENT,
            # Avoid brotli to keep dependencies minimal; gzip is supported.
            "Accept-Encoding": "gzip",
        }
        if auth:
            headers["Authorization"] = auth_header or AUTH_HEADER

        url = f"{base_url}{path}"
        try:
            async with async_timeout.timeout(self._timeout):
                resp = await self._session.get(url, params=params, headers=headers)
                resp.raise_for_status()
                return await resp.json()
        except (ClientError, ValueError) as err:
            raise WetteronlineApiError(str(err)) from err

    async def get_radar_metadata(
        self, latitude: float, longitude: float, language: str
    ) -> dict[str, Any]:
        return await self._request(
            "/snippet-tiles",
            {
                "adjustviewport": "true",
                "alltimesteps": "false",
                "format": "webp",
                "geoonly": "false",
                "height": "366",
                "highres": "true",
                "latitude": latitude,
                "layergroup": "RegenRadar",
                "locale": language,
                "longitude": longitude,
                "width": "418",
            },
            base_url=TILES_BASE,
            auth=False,
        )

    async def get_nearby_stations(
        self, latitude: float, longitude: float, language: str
    ) -> list[dict[str, Any]]:
        return await self._request(
            "/weatherstationreport/nearby/v2",
            {
                "language": language,
                "latitude": latitude,
                "longitude": longitude,
            },
        )

    async def get_station_report(
        self, location_id: str, language: str, system_of_measurement: str, windunit: str
    ) -> dict[str, Any]:
        return await self._request(
            "/weatherstationreport/v2",
            {
                "id": location_id,
                "language": language,
                "systemOfMeasurement": system_of_measurement,
                "windunit": windunit,
            },
        )

    async def get_nowcast(
        self,
        *,
        latitude: float,
        longitude: float,
        altitude: float,
        location_id: str,
        language: str,
        timezone: str,
        system_of_measurement: str,
        windunit: str,
        timeformat: str,
    ) -> dict[str, Any]:
        return await self._request(
            "/weather/nowcast/v10",
            {
                "altitude": altitude,
                "grid_latitude": latitude,
                "grid_longitude": longitude,
                "language": language,
                "latitude": latitude,
                "location_id": location_id,
                "longitude": longitude,
                "system_of_measurement": system_of_measurement,
                "timeformat": timeformat,
                "timezone": timezone,
                "windunit": windunit,
            },
        )

    async def get_uv_index(self, *, location_id: str, timezone: str) -> dict[str, Any]:
        return await self._request(
            "/uv-index/v1/", {"location_id": location_id, "timezone": timezone}
        )

    async def get_aqi(
        self, *, location_id: str, language: str, timezone: str
    ) -> dict[str, Any]:
        return await self._request(
            "/aqi/v1/",
            {
                "language": language,
                "location_id": location_id,
                "timezone": timezone,
            },
        )

    async def get_pollen(
        self, *, location_id: str, language: str, timezone: str
    ) -> dict[str, Any]:
        return await self._request(
            "/pollen/v3",
            {
                "language": language,
                "location_id": location_id,
                "timezone": timezone,
            },
        )

    async def get_warnings(
        self, *, iso_country_code: str, timezone: str
    ) -> dict[str, Any]:
        return await self._request(
            "/warnings/maps/v3",
            {"isoCountryCode": iso_country_code, "timezone": timezone},
        )

    async def get_forecast(
        self, *, location_id: str, timezone: str
    ) -> list[dict[str, Any]]:
        return await self._request(
            "/app/weather/forecast",
            {
                "av": "1",
                "location_id": location_id,
                "mv": "16",
                "timezone": timezone,
            },
            base_url=API_FORECAST_BASE,
            auth_header=AUTH_HEADER_FORECAST,
        )
