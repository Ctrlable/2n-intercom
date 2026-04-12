"""
Camera platform for 2N Intercom.

Provides a HA camera entity serving JPEG snapshots via /api/camera/snapshot.

Key fix vs v1: Only creates camera entities for sources that are actually
enabled on the device. External camera sources that are disabled (common
when no external camera is connected) are skipped entirely.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import TwoNApi, TwoNError, TwoNUnsupportedError
from .const import (
    CONF_DEVICE_NAME,
    CONF_HOST,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    CONF_PORT,
    DATA_API,
    DATA_COORDINATOR,
    DOMAIN,
)
from .coordinator import TwoNCoordinator

_LOGGER = logging.getLogger(__name__)

SNAPSHOT_CACHE_TTL = timedelta(seconds=2)
DEFAULT_WIDTH  = 640
DEFAULT_HEIGHT = 480


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 2N camera entities — only for sources that are actually enabled."""
    api: TwoNApi                = hass.data[DOMAIN][entry.entry_id][DATA_API]
    coordinator: TwoNCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    device_name = entry.data.get(CONF_DEVICE_NAME, entry.title)

    try:
        caps = await api.get_camera_caps()
    except TwoNUnsupportedError:
        _LOGGER.debug("[%s] Camera API not supported on this device", entry.entry_id)
        return
    except TwoNError as exc:
        _LOGGER.warning("[%s] Could not fetch camera caps: %s", entry.entry_id, exc)
        # Still try to create an internal camera entity as fallback
        caps = {}

    jpeg_res = caps.get("jpegResolution", [{"width": DEFAULT_WIDTH, "height": DEFAULT_HEIGHT}])
    best     = _pick_resolution(jpeg_res)

    # ── Determine which sources to create entities for ────────────────────
    #
    # The caps response looks like:
    #   {
    #     "sources": ["internal", "external"],
    #     "jpegResolution": [...],
    #     "external": [{"id": 1, "enabled": false, "active": false}]  ← v2.x
    #   }
    #
    # OR older firmware just returns:
    #   {"sources": ["internal"], "jpegResolution": [...]}
    #
    # We only create an entity for a source if:
    #   - source == "internal"  (always present if listed)
    #   - source == "external"  AND at least one external entry is enabled=true

    raw_sources: list[str] = caps.get("sources", ["internal"])
    enabled_sources: list[str] = []

    for src in raw_sources:
        if src == "internal":
            enabled_sources.append(src)
        elif src == "external":
            ext_list = caps.get("external", [])
            if not ext_list:
                # Older firmware — no status info, assume enabled
                enabled_sources.append(src)
            elif any(e.get("enabled", False) for e in ext_list):
                enabled_sources.append(src)
            else:
                _LOGGER.debug(
                    "[%s] Skipping external camera — no enabled external sources found. "
                    "Connect an external camera or enable it in the device web UI.",
                    entry.entry_id,
                )

    if not enabled_sources:
        _LOGGER.warning(
            "[%s] No enabled camera sources found. "
            "Check Camera service is enabled in the 2N device web UI "
            "under Services → HTTP API → Camera.",
            entry.entry_id,
        )
        return

    entities = [
        TwoNCameraEntity(
            entry, api, coordinator, device_name, source, best, jpeg_res
        )
        for source in enabled_sources
    ]

    async_add_entities(entities)
    _LOGGER.info(
        "[%s] Camera: added %d entity(ies) for sources: %s",
        entry.entry_id, len(entities), enabled_sources,
    )


def _pick_resolution(jpeg_res: list[dict]) -> dict:
    """Pick best resolution ≤ 640×480; fall back to smallest available."""
    preferred = sorted(
        [r for r in jpeg_res if r.get("width", 0) <= 640],
        key=lambda r: r["width"] * r["height"],
        reverse=True,
    )
    if preferred:
        return preferred[0]
    return sorted(jpeg_res, key=lambda r: r["width"] * r["height"])[0]


class TwoNCameraEntity(Camera):
    """2N IP Intercom camera — serves JPEG snapshots on demand."""

    _attr_supported_features = CameraEntityFeature(0)

    def __init__(
        self,
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
        self._width          = resolution.get("width", DEFAULT_WIDTH)
        self._height         = resolution.get("height", DEFAULT_HEIGHT)
        self._all_resolutions = all_resolutions

        label = "Camera" if source == "internal" else f"Camera ({source.title()})"
        self._attr_name      = f"{device_name} {label}"
        self._attr_unique_id = f"{entry.entry_id}_camera_{source}"
        self._attr_icon      = "mdi:cctv"

        self._last_image:      bytes | None = None
        self._last_image_time: Any          = None
        self._lock = asyncio.Lock()

    async def async_camera_image(
        self,
        width: int | None = None,
        height: int | None = None,
    ) -> bytes | None:
        """Return a JPEG snapshot, short-lived cache prevents hammering the device."""
        now = dt_util.utcnow()

        async with self._lock:
            if (
                self._last_image is not None
                and self._last_image_time is not None
                and (now - self._last_image_time) < SNAPSHOT_CACHE_TTL
            ):
                return self._last_image

            snap_w, snap_h = self._clamp_resolution(
                width or self._width,
                height or self._height,
            )

            try:
                image = await self._api.get_camera_snapshot(
                    width=snap_w, height=snap_h, source=self._source
                )
                self._last_image      = image
                self._last_image_time = now
                return image
            except TwoNError as exc:
                _LOGGER.warning(
                    "[%s] Camera snapshot failed (source=%s): %s",
                    self._entry.entry_id, self._source, exc,
                )
                return self._last_image  # return stale rather than blank

    def _clamp_resolution(self, w: int, h: int) -> tuple[int, int]:
        if not self._all_resolutions:
            return self._width, self._height
        best = min(
            self._all_resolutions,
            key=lambda r: abs(r["width"] * r["height"] - w * h),
        )
        return best["width"], best["height"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "source":                self._source,
            "resolution":            f"{self._width}x{self._height}",
            "supported_resolutions": [
                f"{r['width']}x{r['height']}" for r in self._all_resolutions
            ],
            "entry_id":              self._entry.entry_id,
        }

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
