"""
2N log event → Home Assistant event bridge.

Translates raw 2N log event dicts (from /api/log/pull) into
typed HA bus events that automations can trigger on.

2N log event types (from /api/log/caps):
  KeyPressed, KeyReleased, InputChanged, OutputChanged,
  CardEntered, CardFailed, PinEntered, PinFailed,
  FingerprintEntered, FingerprintFailed,
  CallStateChanged, AudioLoopTest,
  UserAuthenticated, DoorOpened, DoorOpenTooLong, DoorClosed,
  TamperOn, TamperOff, ...  (device-dependent)
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    EVENT_DOORBELL,
    EVENT_ACCESS_GRANTED,
    EVENT_ACCESS_DENIED,
    EVENT_CALL_STATE,
    EVENT_DEVICE_LOG,
    ATTR_ENTRY_ID,
)

_LOGGER = logging.getLogger(__name__)

# Map 2N event names → HA event names
_ACCESS_GRANTED_EVENTS = {
    "CardEntered",
    "PinEntered",
    "FingerprintEntered",
    "UserAuthenticated",
    "DoorOpened",
}

_ACCESS_DENIED_EVENTS = {
    "CardFailed",
    "PinFailed",
    "FingerprintFailed",
}

_DOORBELL_EVENTS = {
    "KeyPressed",
}

_CALL_EVENTS = {
    "CallStateChanged",
}


def async_fire_log_event(
    hass: HomeAssistant,
    entry_id: str,
    raw_event: dict[str, Any],
) -> None:
    """
    Parse one raw 2N log event and fire the appropriate HA event(s).

    Always fires the generic ``2n_intercom_device_log`` event so
    automations can catch everything.  Also fires a specific event
    (doorbell / access_granted / access_denied / call_state) when
    the event type matches.
    """
    event_name: str = raw_event.get("event", "")
    base_data: dict[str, Any] = {
        ATTR_ENTRY_ID: entry_id,
        "event_type":  event_name,
        "raw":         raw_event,
    }

    # ── Always fire the generic log event ────────────────────────────────
    hass.bus.async_fire(EVENT_DEVICE_LOG, base_data)

    # ── Doorbell / button press ───────────────────────────────────────────
    if event_name in _DOORBELL_EVENTS:
        hass.bus.async_fire(
            EVENT_DOORBELL,
            {
                ATTR_ENTRY_ID: entry_id,
                "button":      raw_event.get("params", {}).get("buttonIndex"),
                "raw":         raw_event,
            },
        )
        _LOGGER.debug("[%s] doorbell event: %s", entry_id, raw_event)

    # ── Access granted ────────────────────────────────────────────────────
    elif event_name in _ACCESS_GRANTED_EVENTS:
        params = raw_event.get("params", {})
        hass.bus.async_fire(
            EVENT_ACCESS_GRANTED,
            {
                ATTR_ENTRY_ID:  entry_id,
                "event_type":   event_name,
                "user_name":    params.get("userName", ""),
                "user_uuid":    params.get("userId", ""),
                "direction":    params.get("direction", ""),
                "switch":       params.get("switch"),
                "raw":          raw_event,
            },
        )
        _LOGGER.debug("[%s] access granted: %s", entry_id, raw_event)

    # ── Access denied ─────────────────────────────────────────────────────
    elif event_name in _ACCESS_DENIED_EVENTS:
        params = raw_event.get("params", {})
        hass.bus.async_fire(
            EVENT_ACCESS_DENIED,
            {
                ATTR_ENTRY_ID: entry_id,
                "event_type":  event_name,
                "direction":   params.get("direction", ""),
                "raw":         raw_event,
            },
        )
        _LOGGER.debug("[%s] access denied: %s", entry_id, raw_event)

    # ── Call state ────────────────────────────────────────────────────────
    elif event_name in _CALL_EVENTS:
        params = raw_event.get("params", {})
        hass.bus.async_fire(
            EVENT_CALL_STATE,
            {
                ATTR_ENTRY_ID: entry_id,
                "state":       params.get("state", ""),
                "direction":   params.get("direction", ""),
                "raw":         raw_event,
            },
        )
        _LOGGER.debug("[%s] call state: %s", entry_id, raw_event)
