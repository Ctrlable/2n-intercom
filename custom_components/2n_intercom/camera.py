"""
Camera platform for 2N Intercom.

Provides a standard HA camera entity that serves JPEG snapshots from the
2N device via /api/camera/snapshot.  The entity_picture URL is also exposed
so Lovelace picture-glance and the custom card can use it directly.

Supports:
  - Internal camera  (source=internal)
  - External camera  (source=external, if device has one)
  - Configurable resolution (from /api/camera/caps)
  - Snapshot refresh on demand via camera.snapshot service
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import TwoNApi, TwoNConnectionError, TwoNError, TwoNUnsupportedError
from .const import (
    CONF_DEVICE_NAME,
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    CONF_PORT,
    DATA_API,
    DATA_COORDINATOR,
    DOMAIN,
)
from .coordinator import TwoNCoordinator

_LOGGER = logging.getLogger(__name__)

# How long a cached snapshot stays valid before we re-fetch
SNAPSHOT_CACHE_TTL = timedelta(seconds=2)

# Default snapshot resolution — will be overridden by caps if available
DEFAULT_WIDTH  = 640
DEFAULT_HEIGHT = 480

CAMERA_SOURCES = ["internal", "external"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 2N camera entities from config entry."""
    api: TwoNApi               = hass.data[DOMAIN][entry.entry_id][DATA_API]
    coordinator: TwoNCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    device_name = entry.data.get(CONF_DEVICE_NAME, entry.title)

    # Fetch camera caps to discover available sources and resolutions
    try:
        caps = await api.get_camera_caps()
    except (TwoNUnsupportedError, TwoNError):
        _LOGGER.debug("[%s] Camera not supported on this device", entry.entry_id)
        return

    sources   = caps.get("sources", ["internal"])
    jpeg_res  = caps.get("jpegResolution", [{"width": DEFAULT_WIDTH, "height": DEFAULT_HEIGHT}])

    # Pick best default resolution (highest available up to 640x480)
    best = _pick_resolution(jpeg_res)

    entities = [
        TwoNCameraEntity(
            hass, entry, api, coordinator, device_name, source, best, jpeg_res
        )
        for source in sources
    ]

    if not entities:
        # Fallback: create internal camera entity even if caps call failed
        entities = [
            TwoNCameraEntity(
                hass, entry, api, coordinator, device_name, "internal",
                {"width": DEFAULT_WIDTH, "height": DEFAULT_HEIGHT},
                [{"width": DEFAULT_WIDTH, "height": DEFAULT_HEIGHT}],
            )
        ]

    async_add_entities(entities)
    _LOGGER.info(
        "[%s] Added %d camera entity(ies): %s",
        entry.entry_id, len(entities), [s for s in sources]
    )


def _pick_resolution(jpeg_res: list[dict]) -> dict:
    """Pick the best resolution ≤ 640×480, or the smallest available."""
    preferred = sorted(
        [r for r in jpeg_res if r["width"] <= 640],
        key=lambda r: r["width"] * r["height"],
        reverse=True,
    )
    if preferred:
        return preferred[0]
    # All resolutions are above 640 — pick smallest
    return sorted(jpeg_res, key=lambda r: r["width"] * r["height"])[0]


class TwoNCameraEntity(Camera):
    """
    2N IP Intercom camera entity.

    Fetches JPEG snapshots on demand from /api/camera/snapshot.
    The snapshot URL is also directly accessible for use in the
    Lovelace custom card and picture-glance cards.
    """

    _attr_has_entity_name = False
    _attr_supported_features = CameraEntityFeature(0)

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: TwoNApi,
        coordinator: TwoNCoordinator,
        device_name: str,
        source: str,
        resolution: dict,
        all_resolutions: list[dict],
    ) -> None:
        super().__init__()
        self._entry          = entry
        self._api            = api
        self._coordinator    = coordinator
        self._device_name    = device_name
        self._source         = source
        self._width          = resolution["width"]
        self._height         = resolution["height"]
        self._all_resolutions = all_resolutions

        label = "Camera" if source == "internal" else f"Camera ({source})"
        self._attr_name      = f"{device_name} {label}"
        self._attr_unique_id = f"{entry.entry_id}_camera_{source}"
        self._attr_icon      = "mdi:cctv"

        # Snapshot cache
        self._last_image:      bytes | None = None
        self._last_image_time: Any          = None
        self._lock = asyncio.Lock()

    # ── HA Camera interface ───────────────────────────────────────────────

    async def async_camera_image(
        self,
        width: int | None = None,
        height: int | None = None,
    ) -> bytes | None:
        """Return a JPEG snapshot, using a short-lived cache."""
        now = dt_util.utcnow()

        async with self._lock:
            if (
                self._last_image is not None
                and self._last_image_time is not None
                and (now - self._last_image_time) < SNAPSHOT_CACHE_TTL
            ):
                return self._last_image

            # Request at desired resolution, clamped to supported options
            req_w = width  or self._width
            req_h = height or self._height
            snap_w, snap_h = self._clamp_resolution(req_w, req_h)

            try:
                image = await self._api.get_camera_snapshot(
                    width=snap_w, height=snap_h, source=self._source
                )
                self._last_image      = image
                self._last_image_time = now
                return image
            except TwoNError as exc:
                _LOGGER.warning(
                    "[%s] Camera snapshot failed (%s): %s",
                    self._entry.entry_id, self._source, exc,
                )
                return self._last_image  # return stale image rather than None

    def _clamp_resolution(self, w: int, h: int) -> tuple[int, int]:
        """Return the closest supported resolution."""
        if not self._all_resolutions:
            return self._width, self._height
        # Find closest by total pixel count
        best = min(
            self._all_resolutions,
            key=lambda r: abs(r["width"] * r["height"] - w * h),
        )
        return best["width"], best["height"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "source":           self._source,
            "resolution":       f"{self._width}x{self._height}",
            "supported_resolutions": [
                f"{r['width']}x{r['height']}" for r in self._all_resolutions
            ],
            "snapshot_url":     self._snapshot_url(),
            "entry_id":         self._entry.entry_id,
        }

    def _snapshot_url(self) -> str:
        """Direct snapshot URL (useful for the Lovelace card)."""
        entry   = self._entry
        host    = entry.data.get(CONF_HOST, "")
        use_ssl = entry.data.get(CONF_USE_SSL, False)
        port    = entry.data.get(CONF_PORT)
        scheme  = "https" if use_ssl else "http"
        base    = f"{scheme}://{host}:{port}" if port else f"{scheme}://{host}"
        return (
            f"{base}/api/camera/snapshot"
            f"?width={self._width}&height={self._height}&source={self._source}"
        )

    @property
    def device_info(self) -> dict[str, Any]:
        d = self._coordinator.data
        return {
            "identifiers":  {(DOMAIN, self._entry.entry_id)},
            "name":         self._device_name,
            "manufacturer": "2N Telekomunikace",
            "model":        d.model if d else "IP Intercom",
            "sw_version":   d.firmware if d else None,
        }
