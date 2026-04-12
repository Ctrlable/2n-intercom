"""
2N Intercom — unified Home Assistant integration.

Replaces both helios2n-hass and the separate 2n_directory_manager.
Zero external dependencies beyond aiohttp (ships with HA).

Covers:
  - Switch / relay control          → switch entities
  - IO input monitoring             → binary_sensor entities
  - Directory user CRUD             → sensor entities + services
  - PIN / switch-code management    → services
  - Real-time log events            → HA bus events
  - Keymaster bridge                → automatic code sync
  - System info / uptime            → sensor entity
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TwoNApi, TwoNAuthError, TwoNConnectionData, TwoNConnectionError
from .const import (
    CONF_AUTH_METHOD,
    CONF_DEVICE_NAME,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USE_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DATA_API,
    DATA_COORDINATOR,
    DEFAULT_AUTH_METHOD,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USE_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import TwoNCoordinator
from .keymaster_bridge import async_setup_keymaster_bridge
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one 2N Intercom config entry."""

    host        = entry.data[CONF_HOST]
    username    = entry.data[CONF_USERNAME]
    password    = entry.data[CONF_PASSWORD]
    use_ssl     = entry.data.get(CONF_USE_SSL,     DEFAULT_USE_SSL)
    verify_ssl  = entry.data.get(CONF_VERIFY_SSL,  DEFAULT_VERIFY_SSL)
    auth_method = entry.data.get(CONF_AUTH_METHOD,  DEFAULT_AUTH_METHOD)
    port        = entry.data.get(CONF_PORT)
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    conn    = TwoNConnectionData(host, username, password, use_ssl, verify_ssl, port, auth_method)
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    api     = TwoNApi(session, conn)

    # Verify connectivity before completing setup
    try:
        await api.test_connection()
    except TwoNAuthError as exc:
        # Auth errors are permanent — don't retry
        raise ConfigEntryNotReady(f"Authentication failed for {host}: {exc}") from exc
    except TwoNConnectionError as exc:
        raise ConfigEntryNotReady(f"Cannot connect to {host}: {exc}") from exc

    coordinator = TwoNCoordinator(hass, api, scan_interval, entry.entry_id)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_API:         api,
        DATA_COORDINATOR: coordinator,
    }

    # Register services (idempotent across multiple entries)
    async_register_services(hass)

    # Start log-push loop (real-time events)
    await coordinator.start_log_loop()

    # Keymaster bridge — register once globally
    if not hass.data[DOMAIN].get("_bridge_registered"):
        async_setup_keymaster_bridge(hass)
        hass.data[DOMAIN]["_bridge_registered"] = True

    # Set up all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload on options change
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    device_name = entry.data.get(CONF_DEVICE_NAME, host)
    d = coordinator.data
    _LOGGER.info(
        "2N Intercom ready: '%s' (%s)  switches=%d  ports=%d  users=%d",
        device_name, host,
        len(d.switches) if d else 0,
        len(d.ports)    if d else 0,
        len(d.users)    if d else 0,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Stop log loop
    coord: TwoNCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    await coord.stop_log_loop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    # Remove services only when last entry is gone
    remaining = [k for k in hass.data.get(DOMAIN, {}) if not k.startswith("_")]
    if not remaining:
        async_unregister_services(hass)
        hass.data.pop(DOMAIN, None)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)
