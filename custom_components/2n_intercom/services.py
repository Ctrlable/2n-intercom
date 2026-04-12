"""Service handlers for 2N Intercom."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .api import TwoNError
from .const import (
    ATTR_ACTION,
    ATTR_CALL_PEER,
    ATTR_CODE,
    ATTR_ENTRY_ID,
    ATTR_PIN,
    ATTR_SLOT,
    ATTR_SWITCH_CODES,
    ATTR_SWITCH_ID,
    ATTR_TREEPATH,
    ATTR_USER_EMAIL,
    ATTR_USER_NAME,
    ATTR_USER_UUID,
    ATTR_USER_VIRT_NUMBER,
    ATTR_VALID_FROM,
    ATTR_VALID_TO,
    DATA_COORDINATOR,
    DOMAIN,
    EVENT_CODE_CHANGED,
    EVENT_USER_CREATED,
    EVENT_USER_DELETED,
    EVENT_USER_UPDATED,
    SERVICE_AUDIO_TEST,
    SERVICE_CLEAR_PIN,
    SERVICE_CREATE_USER,
    SERVICE_DELETE_USER,
    SERVICE_RESTART_DEVICE,
    SERVICE_SET_ACCESS_VALIDITY,
    SERVICE_SET_PIN,
    SERVICE_SET_SWITCH_CODES,
    SERVICE_SYNC_FROM_KEYMASTER,
    SERVICE_TRIGGER_SWITCH,
    SERVICE_UPDATE_USER,
)

_LOGGER = logging.getLogger(__name__)

# ── Schemas ───────────────────────────────────────────────────────────────

_OPT_ENTRY = vol.Optional(ATTR_ENTRY_ID)

CREATE_USER_SCHEMA = vol.Schema({
    _OPT_ENTRY: str,
    vol.Required(ATTR_USER_NAME): cv.string,
    vol.Optional(ATTR_USER_EMAIL,        default=""): cv.string,
    vol.Optional(ATTR_USER_VIRT_NUMBER,  default=""): cv.string,
    vol.Optional(ATTR_PIN,               default=""): cv.string,
    vol.Optional(ATTR_SWITCH_CODES,      default=[]): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(ATTR_CALL_PEER,         default=""): cv.string,
    vol.Optional(ATTR_TREEPATH,          default="/"): cv.string,
    vol.Optional(ATTR_VALID_FROM,        default=0): vol.Coerce(int),
    vol.Optional(ATTR_VALID_TO,          default=0): vol.Coerce(int),
})

UPDATE_USER_SCHEMA = vol.Schema({
    _OPT_ENTRY: str,
    vol.Required(ATTR_USER_UUID): cv.string,
    vol.Optional(ATTR_USER_NAME):        cv.string,
    vol.Optional(ATTR_USER_EMAIL):       cv.string,
    vol.Optional(ATTR_USER_VIRT_NUMBER): cv.string,
    vol.Optional(ATTR_PIN):              cv.string,
    vol.Optional(ATTR_SWITCH_CODES):     vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(ATTR_CALL_PEER):        cv.string,
    vol.Optional(ATTR_TREEPATH):         cv.string,
    vol.Optional(ATTR_VALID_FROM):       vol.Coerce(int),
    vol.Optional(ATTR_VALID_TO):         vol.Coerce(int),
})

DELETE_USER_SCHEMA = vol.Schema({
    _OPT_ENTRY: str,
    vol.Required(ATTR_USER_UUID): cv.string,
})

SET_PIN_SCHEMA = vol.Schema({
    _OPT_ENTRY: str,
    vol.Required(ATTR_USER_UUID): cv.string,
    vol.Required(ATTR_PIN): cv.string,
})

CLEAR_PIN_SCHEMA = vol.Schema({
    _OPT_ENTRY: str,
    vol.Required(ATTR_USER_UUID): cv.string,
})

SET_SWITCH_CODES_SCHEMA = vol.Schema({
    _OPT_ENTRY: str,
    vol.Required(ATTR_USER_UUID): cv.string,
    vol.Required(ATTR_SWITCH_CODES): vol.All(
        cv.ensure_list, vol.Length(min=1, max=4), [cv.string]
    ),
})

SET_ACCESS_VALIDITY_SCHEMA = vol.Schema({
    _OPT_ENTRY: str,
    vol.Required(ATTR_USER_UUID): cv.string,
    vol.Optional(ATTR_VALID_FROM, default=0): vol.Coerce(int),
    vol.Optional(ATTR_VALID_TO,   default=0): vol.Coerce(int),
})

SYNC_FROM_KEYMASTER_SCHEMA = vol.Schema({
    _OPT_ENTRY: str,
    vol.Required(ATTR_USER_NAME): cv.string,
    vol.Required(ATTR_SLOT): vol.Coerce(int),
    vol.Required(ATTR_CODE): cv.string,
})

TRIGGER_SWITCH_SCHEMA = vol.Schema({
    _OPT_ENTRY: str,
    vol.Required(ATTR_SWITCH_ID): vol.Coerce(int),
    vol.Optional(ATTR_ACTION, default="trigger"): vol.In(["on", "off", "trigger"]),
})

DEVICE_ONLY_SCHEMA = vol.Schema({_OPT_ENTRY: str})


# ── Helpers ───────────────────────────────────────────────────────────────

def _get_coordinator(hass: HomeAssistant, entry_id: str | None):
    domain_data: dict = hass.data.get(DOMAIN, {})
    if entry_id:
        entry = domain_data.get(entry_id)
        if not entry:
            raise HomeAssistantError(f"No 2N entry with id '{entry_id}'")
        return entry[DATA_COORDINATOR]
    for entry_data in domain_data.values():
        if DATA_COORDINATOR in entry_data:
            return entry_data[DATA_COORDINATOR]
    raise HomeAssistantError("No 2N Intercom entries configured")


def _build_user_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if name    := data.get(ATTR_USER_NAME):     payload["name"]       = name
    if email   := data.get(ATTR_USER_EMAIL):    payload["email"]      = email
    if virt    := data.get(ATTR_USER_VIRT_NUMBER): payload["virtNumber"] = virt
    if tree    := data.get(ATTR_TREEPATH):      payload["treepath"]   = tree

    access: dict[str, Any] = {}
    if (pin := data.get(ATTR_PIN)) is not None:           access["pin"]  = pin
    if codes := data.get(ATTR_SWITCH_CODES):
        access["code"] = (list(codes) + ["", "", "", ""])[:4]
    if (vf := data.get(ATTR_VALID_FROM)) is not None:     access["validFrom"] = str(vf)
    if (vt := data.get(ATTR_VALID_TO))   is not None:     access["validTo"]   = str(vt)
    if access:
        payload["access"] = access

    if peer := data.get(ATTR_CALL_PEER):
        payload["callPos"] = [
            {"peer": peer, "profiles": "", "grouped": False, "ipEye": ""},
            {"peer": "",   "profiles": "", "grouped": False, "ipEye": ""},
            {"peer": "",   "profiles": "", "grouped": False, "ipEye": ""},
        ]
    return payload


# ── Registration ──────────────────────────────────────────────────────────

def async_register_services(hass: HomeAssistant) -> None:
    """Register all 2N Intercom services (idempotent)."""

    # ── create_user ───────────────────────────────────────────────────────
    async def handle_create_user(call: ServiceCall) -> None:
        coord   = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        payload = _build_user_payload(call.data)
        try:
            result = await coord.api.create_user(payload)
        except TwoNError as exc:
            raise HomeAssistantError(f"Failed to create user: {exc}") from exc
        hass.bus.async_fire(EVENT_USER_CREATED, {
            ATTR_USER_UUID: result.get("uuid"),
            ATTR_USER_NAME: call.data.get(ATTR_USER_NAME),
            ATTR_ENTRY_ID:  coord.entry_id,
        })
        await coord.async_request_refresh()
        _LOGGER.info("Created 2N user '%s' uuid=%s", call.data.get(ATTR_USER_NAME), result.get("uuid"))

    hass.services.async_register(DOMAIN, SERVICE_CREATE_USER, handle_create_user, schema=CREATE_USER_SCHEMA)

    # ── update_user ───────────────────────────────────────────────────────
    async def handle_update_user(call: ServiceCall) -> None:
        coord     = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        user_uuid = call.data[ATTR_USER_UUID]
        payload   = _build_user_payload(call.data)
        try:
            await coord.api.update_user(user_uuid, payload)
        except TwoNError as exc:
            raise HomeAssistantError(f"Failed to update user: {exc}") from exc
        hass.bus.async_fire(EVENT_USER_UPDATED, {ATTR_USER_UUID: user_uuid, ATTR_ENTRY_ID: coord.entry_id})
        await coord.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_UPDATE_USER, handle_update_user, schema=UPDATE_USER_SCHEMA)

    # ── delete_user ───────────────────────────────────────────────────────
    async def handle_delete_user(call: ServiceCall) -> None:
        coord     = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        user_uuid = call.data[ATTR_USER_UUID]
        try:
            await coord.api.delete_user(user_uuid)
        except TwoNError as exc:
            raise HomeAssistantError(f"Failed to delete user: {exc}") from exc
        hass.bus.async_fire(EVENT_USER_DELETED, {ATTR_USER_UUID: user_uuid, ATTR_ENTRY_ID: coord.entry_id})
        await coord.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_DELETE_USER, handle_delete_user, schema=DELETE_USER_SCHEMA)

    # ── set_pin ───────────────────────────────────────────────────────────
    async def handle_set_pin(call: ServiceCall) -> None:
        coord     = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        user_uuid = call.data[ATTR_USER_UUID]
        try:
            await coord.api.set_pin(user_uuid, call.data[ATTR_PIN])
        except (TwoNError, ValueError) as exc:
            raise HomeAssistantError(f"Failed to set PIN: {exc}") from exc
        hass.bus.async_fire(EVENT_CODE_CHANGED, {ATTR_USER_UUID: user_uuid, "action": "set_pin", ATTR_ENTRY_ID: coord.entry_id})
        await coord.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_SET_PIN, handle_set_pin, schema=SET_PIN_SCHEMA)

    # ── clear_pin ─────────────────────────────────────────────────────────
    async def handle_clear_pin(call: ServiceCall) -> None:
        coord     = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        user_uuid = call.data[ATTR_USER_UUID]
        try:
            await coord.api.clear_pin(user_uuid)
        except TwoNError as exc:
            raise HomeAssistantError(f"Failed to clear PIN: {exc}") from exc
        hass.bus.async_fire(EVENT_CODE_CHANGED, {ATTR_USER_UUID: user_uuid, "action": "clear_pin", ATTR_ENTRY_ID: coord.entry_id})
        await coord.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_CLEAR_PIN, handle_clear_pin, schema=CLEAR_PIN_SCHEMA)

    # ── set_switch_codes ──────────────────────────────────────────────────
    async def handle_set_switch_codes(call: ServiceCall) -> None:
        coord     = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        user_uuid = call.data[ATTR_USER_UUID]
        try:
            await coord.api.set_switch_codes(user_uuid, call.data[ATTR_SWITCH_CODES])
        except (TwoNError, ValueError) as exc:
            raise HomeAssistantError(f"Failed to set switch codes: {exc}") from exc
        hass.bus.async_fire(EVENT_CODE_CHANGED, {ATTR_USER_UUID: user_uuid, "action": "set_switch_codes", ATTR_ENTRY_ID: coord.entry_id})
        await coord.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_SET_SWITCH_CODES, handle_set_switch_codes, schema=SET_SWITCH_CODES_SCHEMA)

    # ── set_access_validity ───────────────────────────────────────────────
    async def handle_set_access_validity(call: ServiceCall) -> None:
        coord     = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        user_uuid = call.data[ATTR_USER_UUID]
        try:
            await coord.api.set_access_validity(
                user_uuid,
                call.data.get(ATTR_VALID_FROM, 0),
                call.data.get(ATTR_VALID_TO, 0),
            )
        except TwoNError as exc:
            raise HomeAssistantError(f"Failed to set access validity: {exc}") from exc
        hass.bus.async_fire(EVENT_USER_UPDATED, {ATTR_USER_UUID: user_uuid, "action": "set_access_validity", ATTR_ENTRY_ID: coord.entry_id})
        await coord.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_SET_ACCESS_VALIDITY, handle_set_access_validity, schema=SET_ACCESS_VALIDITY_SCHEMA)

    # ── sync_from_keymaster ───────────────────────────────────────────────
    async def handle_sync_from_keymaster(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        name  = call.data[ATTR_USER_NAME]
        slot  = call.data[ATTR_SLOT]
        code  = call.data[ATTR_CODE]
        user  = coord.get_user_by_name(name)
        if not user:
            raise HomeAssistantError(f"No 2N user found with name '{name}'")
        user_uuid = user["uuid"]
        current_codes: list[str] = list(user.get("access", {}).get("code", ["", "", "", ""]))
        while len(current_codes) < 4:
            current_codes.append("")
        current_codes[max(0, min(slot - 1, 3))] = code
        try:
            await coord.api.set_switch_codes(user_uuid, current_codes)
        except (TwoNError, ValueError) as exc:
            raise HomeAssistantError(f"Keymaster sync failed: {exc}") from exc
        hass.bus.async_fire(EVENT_CODE_CHANGED, {
            ATTR_USER_UUID: user_uuid, ATTR_USER_NAME: name,
            ATTR_SLOT: slot, "action": "sync_from_keymaster",
            ATTR_ENTRY_ID: coord.entry_id,
        })
        await coord.async_request_refresh()
        _LOGGER.info("Keymaster sync: slot %d for user '%s'", slot, name)

    hass.services.async_register(DOMAIN, SERVICE_SYNC_FROM_KEYMASTER, handle_sync_from_keymaster, schema=SYNC_FROM_KEYMASTER_SCHEMA)

    # ── trigger_switch ────────────────────────────────────────────────────
    async def handle_trigger_switch(call: ServiceCall) -> None:
        coord     = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        switch_id = call.data[ATTR_SWITCH_ID]
        action    = call.data.get(ATTR_ACTION, "trigger")
        try:
            await coord.api.set_switch(switch_id, action)
        except TwoNError as exc:
            raise HomeAssistantError(f"Failed to trigger switch: {exc}") from exc
        await coord.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_TRIGGER_SWITCH, handle_trigger_switch, schema=TRIGGER_SWITCH_SCHEMA)

    # ── restart_device ────────────────────────────────────────────────────
    async def handle_restart(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        try:
            await coord.api.restart()
        except TwoNError as exc:
            raise HomeAssistantError(f"Failed to restart device: {exc}") from exc

    hass.services.async_register(DOMAIN, SERVICE_RESTART_DEVICE, handle_restart, schema=DEVICE_ONLY_SCHEMA)

    # ── audio_test ────────────────────────────────────────────────────────
    async def handle_audio_test(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        try:
            await coord.api.audio_test()
        except TwoNError as exc:
            raise HomeAssistantError(f"Failed to run audio test: {exc}") from exc

    hass.services.async_register(DOMAIN, SERVICE_AUDIO_TEST, handle_audio_test, schema=DEVICE_ONLY_SCHEMA)


def async_unregister_services(hass: HomeAssistant) -> None:
    for svc in (
        SERVICE_CREATE_USER, SERVICE_UPDATE_USER, SERVICE_DELETE_USER,
        SERVICE_SET_PIN, SERVICE_CLEAR_PIN, SERVICE_SET_SWITCH_CODES,
        SERVICE_SET_ACCESS_VALIDITY, SERVICE_SYNC_FROM_KEYMASTER,
        SERVICE_TRIGGER_SWITCH, SERVICE_RESTART_DEVICE, SERVICE_AUDIO_TEST,
    ):
        if hass.services.has_service(DOMAIN, svc):
            hass.services.async_remove(DOMAIN, svc)
