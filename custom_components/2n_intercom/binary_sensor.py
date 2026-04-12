"""Binary sensor platform — 2N IO input ports."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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

    # Input ports → binary sensors
    # Output ports → handled by switch platform (see note below)
    entities = [
        TwoNInputSensor(coordinator, entry, device_name, port["id"])
        for port in (coordinator.data.ports if coordinator.data else [])
        if port.get("type") == "input"
    ]
    async_add_entities(entities, update_before_add=True)


class TwoNInputSensor(CoordinatorEntity, BinarySensorEntity):
    """
    Represents one 2N IO input port as a binary sensor.

    The user can use HA's 'Show as' entity setting to change the device
    class to Door, Motion, Tamper etc. as appropriate for their wiring.
    """

    def __init__(
        self,
        coordinator: TwoNCoordinator,
        entry: ConfigEntry,
        device_name: str,
        port_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry       = entry
        self._device_name = device_name
        self._port_id     = port_id
        self._attr_unique_id = f"{entry.entry_id}_input_{port_id}"
        self._attr_icon      = "mdi:electric-switch-closed"

    @property
    def _port(self) -> dict | None:
        return self.coordinator.get_port(self._port_id)

    @property
    def name(self) -> str:
        return f"{self._device_name} Input {self._port_id}"

    @property
    def is_on(self) -> bool:
        return bool((self._port or {}).get("state", False))

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._port is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        port = self._port or {}
        return {
            "port_id":  self._port_id,
            "type":     port.get("type", "input"),
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
