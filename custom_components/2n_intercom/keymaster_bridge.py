"""Keymaster → 2N automatic code sync bridge."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback

from .const import DATA_COORDINATOR, DOMAIN, EVENT_CODE_CHANGED, KEYMASTER_EVENT

_LOGGER = logging.getLogger(__name__)


def async_setup_keymaster_bridge(hass: HomeAssistant) -> None:
    """Register a listener that mirrors keymaster slot codes to 2N users."""

    @callback
    def _on_keymaster_event(event: Event) -> None:
        data: dict[str, Any]  = event.data
        slot_name: str        = data.get("code_slot_name", "")
        slot: int             = int(data.get("code_slot", 1))
        usercode: str         = data.get("usercode", "")
        action: str           = data.get("action", "")

        if not slot_name:
            return

        code_to_set = "" if action == "delete_usercode" else usercode

        for entry_data in hass.data.get(DOMAIN, {}).values():
            coord = entry_data.get(DATA_COORDINATOR)
            if coord is None:
                continue
            user = coord.get_user_by_name(slot_name)
            if user is None:
                continue

            user_uuid = user["uuid"]
            current: list[str] = list(
                user.get("access", {}).get("code", ["", "", "", ""])
            )
            while len(current) < 4:
                current.append("")
            current[max(0, min(slot - 1, 3))] = code_to_set

            async def _sync(coord=coord, uid=user_uuid, codes=current, name=slot_name, s=slot) -> None:
                try:
                    await coord.api.set_switch_codes(uid, codes)
                    await coord.async_request_refresh()
                    hass.bus.async_fire(EVENT_CODE_CHANGED, {
                        "user_uuid": uid, "user_name": name,
                        "slot": s,       "action": "keymaster_bridge",
                        "entry_id": coord.entry_id,
                    })
                    _LOGGER.info("Keymaster bridge: synced slot %d for user '%s'", s, name)
                except Exception as exc:  # pylint: disable=broad-except
                    _LOGGER.error("Keymaster bridge error for '%s': %s", name, exc)

            hass.async_create_task(_sync())

    hass.bus.async_listen(KEYMASTER_EVENT, _on_keymaster_event)
    _LOGGER.debug("2N Intercom: keymaster bridge active")
