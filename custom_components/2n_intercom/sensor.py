"""Sensor platform — 2N system info + directory user sensors."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_NAME, DATA_COORDINATOR, DOMAIN
from .coordinator import TwoNCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TwoNCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    device_name = entry.data.get(CONF_DEVICE_NAME, entry.title)

    # Static sensors registered once
    async_add_entities(
        [
            TwoNSystemSensor(coordinator, entry, device_name),
            TwoNUserCountSensor(coordinator, entry, device_name),
        ],
        update_before_add=True,
    )

    # Dynamic per-user sensors — grow as users are added
    known_uuids: set[str] = set()

    @callback
    def _handle_update() -> None:
        nonlocal known_uuids
        new_entities = []
        for uid in (coordinator.data.users if coordinator.data else {}):
            if uid not in known_uuids:
                known_uuids.add(uid)
                new_entities.append(
                    TwoNUserSensor(coordinator, entry, device_name, uid)
                )
        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_handle_update)
    _handle_update()


# ── System sensor ─────────────────────────────────────────────────────────

class TwoNSystemSensor(CoordinatorEntity, SensorEntity):
    """Reports device uptime; attributes carry full system info."""

    _attr_icon = "mdi:router-network"

    def __init__(self, coordinator: TwoNCoordinator, entry: ConfigEntry, device_name: str) -> None:
        super().__init__(coordinator)
        self._entry       = entry
        self._device_name = device_name
        self._attr_name      = f"{device_name} System"
        self._attr_unique_id = f"{entry.entry_id}_system"

    @property
    def native_value(self) -> str:
        d = self.coordinator.data
        if d and d.uptime:
            delta = datetime.now().replace(tzinfo=None) - d.uptime.replace(tzinfo=None)
            days  = delta.days
            hours, rem = divmod(delta.seconds, 3600)
            mins, _    = divmod(rem, 60)
            return f"{days}d {hours}h {mins}m"
        return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data
        if not d:
            return {}
        return {
            "model":       d.model,
            "serial":      d.serial,
            "firmware":    d.firmware,
            "hardware":    d.hardware,
            "mac":         d.mac,
            "uptime_ts":   d.uptime.isoformat() if d.uptime else None,
            "log_caps":    d.log_caps,
            "entry_id":    self._entry.entry_id,
        }

    @property
    def device_info(self) -> dict[str, Any]:
        d = self.coordinator.data
        return {
            "identifiers":  {(DOMAIN, self._entry.entry_id)},
            "name":         self._device_name,
            "manufacturer": "2N Telekomunikace",
            "model":        d.model if d else "IP Intercom",
            "sw_version":   d.firmware if d else None,
            "hw_version":   d.hardware if d else None,
        }


# ── User count sensor ─────────────────────────────────────────────────────

class TwoNUserCountSensor(CoordinatorEntity, SensorEntity):
    """Reports total active directory users."""

    _attr_icon          = "mdi:account-group"
    _attr_state_class   = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "users"

    def __init__(self, coordinator: TwoNCoordinator, entry: ConfigEntry, device_name: str) -> None:
        super().__init__(coordinator)
        self._entry       = entry
        self._device_name = device_name
        self._attr_name      = f"{device_name} Directory User Count"
        self._attr_unique_id = f"{entry.entry_id}_user_count"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.users) if self.coordinator.data else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data
        if not d:
            return {}
        return {
            "user_names": [u.get("name", "") for u in d.users.values()],
            "entry_id":   self._entry.entry_id,
        }

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers":  {(DOMAIN, self._entry.entry_id)},
            "name":         self._device_name,
            "manufacturer": "2N Telekomunikace",
            "model":        "IP Intercom",
        }


# ── Per-user sensor ───────────────────────────────────────────────────────

class TwoNUserSensor(CoordinatorEntity, SensorEntity):
    """One sensor per directory user. State = name. Attributes = access info."""

    _attr_icon = "mdi:account-key"

    def __init__(
        self,
        coordinator: TwoNCoordinator,
        entry: ConfigEntry,
        device_name: str,
        user_uuid: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry       = entry
        self._device_name = device_name
        self._user_uuid   = user_uuid
        self._attr_unique_id = f"{entry.entry_id}_user_{user_uuid}"

    @property
    def _user(self) -> dict:
        if self.coordinator.data:
            return self.coordinator.data.users.get(self._user_uuid, {})
        return {}

    @property
    def name(self) -> str:
        label = self._user.get("name") or self._user_uuid[:8]
        return f"{self._device_name} User: {label}"

    @property
    def native_value(self) -> str:
        return self._user.get("name") or self._user_uuid[:8]

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and bool(self.coordinator.data)
            and self._user_uuid in self.coordinator.data.users
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        user   = self._user
        access = user.get("access", {})
        codes  = access.get("code", [])
        return {
            "uuid":              self._user_uuid,
            "email":             user.get("email", ""),
            "virt_number":       user.get("virtNumber", ""),
            "treepath":          user.get("treepath", "/"),
            # Never expose actual PIN/code values — presence only
            "has_pin":           bool(access.get("pin")),
            "switch_code_slots": [bool(c) for c in codes],
            "has_card":          any(access.get("card", [])),
            "valid_from":        access.get("validFrom", "0"),
            "valid_to":          access.get("validTo", "0"),
            "call_peers": [
                cp.get("peer", "")
                for cp in user.get("callPos", [])
                if cp.get("peer")
            ],
            "entry_id": self._entry.entry_id,
        }

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers":  {(DOMAIN, self._entry.entry_id)},
            "name":         self._device_name,
            "manufacturer": "2N Telekomunikace",
            "model":        "IP Intercom",
        }
