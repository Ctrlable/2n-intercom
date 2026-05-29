"""Diagnostics support for 2N Intercom."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, DATA_COORDINATOR, DOMAIN
from .coordinator import TwoNCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: TwoNCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    data = coordinator.data

    config = dict(entry.data)
    config.pop(CONF_PASSWORD, None)
    config.pop(CONF_USERNAME, None)

    return {
        "config": config,
        "device": {
            "model": data.model if data else None,
            "serial": data.serial if data else None,
            "firmware": data.firmware if data else None,
            "hardware": data.hardware if data else None,
            "uptime": data.uptime.isoformat() if data and data.uptime else None,
        },
        "switches_count": len(data.switches) if data else 0,
        "ports_count": len(data.ports) if data else 0,
        "users_count": len(data.users) if data else 0,
        "log_caps": data.log_caps if data else [],
    }
