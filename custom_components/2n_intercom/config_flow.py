"""Config flow for 2N Intercom."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
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
    DEFAULT_AUTH_METHOD,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USE_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME, default="admin"): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_USE_SSL,      default=DEFAULT_USE_SSL):     bool,
        vol.Optional(CONF_VERIFY_SSL,   default=DEFAULT_VERIFY_SSL):  bool,
        vol.Optional(CONF_AUTH_METHOD,  default=DEFAULT_AUTH_METHOD): vol.In(["basic", "digest"]),
        vol.Optional(CONF_PORT):        vol.Coerce(int),
        vol.Optional(CONF_DEVICE_NAME, default=""): str,
    }
)


class TwoNIntercomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for 2N Intercom."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host        = user_input[CONF_HOST].strip()
            username    = user_input[CONF_USERNAME].strip()
            password    = user_input[CONF_PASSWORD]
            use_ssl     = user_input.get(CONF_USE_SSL,    DEFAULT_USE_SSL)
            verify_ssl  = user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
            auth_method = user_input.get(CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD)
            port        = user_input.get(CONF_PORT)

            await self.async_set_unique_id(host.lower())
            self._abort_if_unique_id_configured()

            conn    = TwoNConnectionData(host, username, password, use_ssl, verify_ssl, port, auth_method)
            session = async_get_clientsession(self.hass, verify_ssl=verify_ssl)
            api     = TwoNApi(session, conn)

            try:
                info = await api.test_connection()
                device_name = (
                    user_input.get(CONF_DEVICE_NAME)
                    or info.get("deviceName")
                    or info.get("variant")
                    or host
                )
            except TwoNAuthError:
                errors["base"] = "invalid_auth"
            except TwoNConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during 2N setup")
                errors["base"] = "unknown"
            else:
                config_data = {
                    CONF_HOST:        host,
                    CONF_USERNAME:    username,
                    CONF_PASSWORD:    password,
                    CONF_USE_SSL:     use_ssl,
                    CONF_VERIFY_SSL:  verify_ssl,
                    CONF_AUTH_METHOD: auth_method,
                    CONF_DEVICE_NAME: device_name,
                }
                if port:
                    config_data[CONF_PORT] = port

                return self.async_create_entry(
                    title=device_name,
                    data=config_data,
                    options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TwoNOptionsFlow:
        return TwoNOptionsFlow(config_entry)


class TwoNOptionsFlow(config_entries.OptionsFlow):
    """Options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self._entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
                }
            ),
        )
