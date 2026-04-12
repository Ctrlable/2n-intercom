"""Switch platform — 2N relay/switch control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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

    entities = [
        TwoNSwitch(coordinator, entry, device_name, sw["id"])
        for sw in (coordinator.data.switches if coordinator.data else [])
    ]
    async_add_entities(entities, update_before_add=True)


class TwoNSwitch(CoordinatorEntity, SwitchEntity):
    """Represents one 2N relay/switch."""

    def __init__(
        self,
        coordinator: TwoNCoordinator,
        entry: ConfigEntry,
        device_name: str,
        switch_id: int,
    ) -> None:
        super().__init__(coordinator)
        self._entry       = entry
        self._device_name = device_name
        self._switch_id   = switch_id
        self._attr_unique_id = f"{entry.entry_id}_switch_{switch_id}"
        self._attr_icon      = "mdi:electric-switch"

    @property
    def _switch(self) -> dict | None:
        return self.coordinator.get_switch(self._switch_id)

    @property
    def name(self) -> str:
        mode = (self._switch or {}).get("mode", "")
        label = f" ({mode})" if mode else ""
        return f"{self._device_name} Switch {self._switch_id}{label}"

    @property
    def is_on(self) -> bool:
        return (self._switch or {}).get("active", False)

    @property
    def available(self) -> bool:
        sw = self._switch
        return (
            self.coordinator.last_update_success
            and sw is not None
            and sw.get("enabled", False)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sw = self._switch or {}
        return {
            "switch_id": self._switch_id,
            "mode":      sw.get("mode"),
            "locked":    sw.get("locked", False),
            "enabled":   sw.get("enabled", False),
            "entry_id":  self._entry.entry_id,
        }

    @property
    def device_info(self) -> dict[str, Any]:
        return _device_info(self._entry, self._device_name)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.api.set_switch(self._switch_id, "on")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.api.set_switch(self._switch_id, "off")
        await self.coordinator.async_request_refresh()


def _device_info(entry: ConfigEntry, device_name: str) -> dict[str, Any]:
    return {
        "identifiers":  {(DOMAIN, entry.entry_id)},
        "name":         device_name,
        "manufacturer": "2N Telekomunikace",
        "model":        "IP Intercom",
    }
