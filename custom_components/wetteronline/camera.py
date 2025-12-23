"""Camera platform for Wetteronline."""

from __future__ import annotations

from typing import Any

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENABLE_RADAR, DOMAIN
from .coordinator import WetteronlineDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wetteronline camera entity."""
    # Check if radar is enabled in options (default True)
    if not entry.options.get(CONF_ENABLE_RADAR, True):
        return

    coordinator: WetteronlineDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WetteronlineCamera(coordinator, entry)])


class WetteronlineCamera(CoordinatorEntity[WetteronlineDataUpdateCoordinator], Camera):
    """Camera entity for Wetteronline radar."""

    _attr_has_entity_name = True
    _attr_name = "Radar"
    _attr_translation_key = "radar"

    def __init__(
        self, coordinator: WetteronlineDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the camera."""
        super().__init__(coordinator)
        Camera.__init__(self)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_radar"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Wetteronline",
            "model": "App API",
        }
        self._session = async_get_clientsession(coordinator.hass)
        self.content_type = "image/webp"

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return bytes of camera image."""
        url = self._get_image_url()
        if not url:
            return None

        # The radar API requires specific User-Agent, which is handled by the client
        # but here we are making a direct request.
        # We should use the same headers as the client.
        headers = {
            "User-Agent": "WetterApp/436435 CFNetwork/3860.200.71 Darwin/25.1.0",
            "Accept-Encoding": "gzip",
        }

        try:
            async with self._session.get(url, headers=headers) as response:
                response.raise_for_status()
                return await response.read()

        except Exception:  # pylint: disable=broad-except
            return None

    def _get_image_url(self) -> str | None:
        """Get the URL of the radar image."""
        radar_data = self.coordinator.data.get("radar")
        if not radar_data:
            return None

        # Find the best tile
        try:
            requested_center = radar_data.get("requestedCenter", {})
            center_x = requested_center.get("x")
            center_y = requested_center.get("y")

            tiles_meta = radar_data.get("tiles", [])
            time_steps = radar_data.get("timeSteps", [])

            if not time_steps or not tiles_meta:
                return None

            # Use the first time step (current/latest)
            current_step = time_steps[0]
            tiles_urls = current_step.get("tiles", [])

            if len(tiles_urls) != len(tiles_meta):
                # Fallback to first tile if mismatch
                return tiles_urls[0].get("url")

            best_index = 0
            if center_x is not None and center_y is not None:
                for i, tile_meta in enumerate(tiles_meta):
                    x = tile_meta.get("x")
                    y = tile_meta.get("y")
                    size = tile_meta.get("size")
                    if x is not None and y is not None and size is not None:
                        if x <= center_x < x + size and y <= center_y < y + size:
                            best_index = i
                            break

            return tiles_urls[best_index].get("url")

        except (IndexError, KeyError, TypeError):
            return None
