"""Data update coordinator for 2N Intercom."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import TwoNApi, TwoNConnectionError, TwoNError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class TwoNCoordinatorData:
    """Snapshot of all polled device state."""

    def __init__(self) -> None:
        # System
        self.device_name: str = ""
        self.model: str = ""
        self.serial: str = ""
        self.firmware: str = ""
        self.hardware: str = ""
        self.mac: str = ""
        self.uptime: datetime | None = None

        # Switches  — list of dicts:
        #   {id, enabled, mode, active, locked}
        self.switches: list[dict[str, Any]] = []

        # IO ports  — list of dicts:
        #   {id, type, state}
        self.ports: list[dict[str, Any]] = []

        # Log event types supported by this device
        self.log_caps: list[str] = []

        # Directory users  — keyed by UUID
        self.users: dict[str, dict[str, Any]] = {}


class TwoNCoordinator(DataUpdateCoordinator[TwoNCoordinatorData]):
    """
    Central coordinator.

    Polls system info, switches, IO ports, and directory every
    ``scan_interval`` seconds.  Log events are pushed separately via
    the log-pull loop started in async_setup_entry.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: TwoNApi,
        scan_interval: int,
        entry_id: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry_id}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api       = api
        self.entry_id  = entry_id
        self._log_task: asyncio.Task | None = None

    # ── Poll ──────────────────────────────────────────────────────────────

    async def _async_update_data(self) -> TwoNCoordinatorData:
        data = TwoNCoordinatorData()
        try:
            # System info
            info = await self.api.get_system_info()
            data.device_name = info.get("deviceName", "2N Device")
            data.model       = info.get("variant", "")
            data.serial      = info.get("serialNumber", "")
            data.firmware    = (
                f"{info.get('swVersion', '')}-{info.get('buildType', '')}"
            )
            data.hardware    = info.get("hwVersion", "")
            data.mac         = info.get("macAddr", "")

            # Uptime
            try:
                status   = await self.api.get_system_status()
                up_secs  = status.get("upTime", 0)
                data.uptime = (
                    datetime.now(timezone.utc).replace(microsecond=0)
                    - timedelta(seconds=up_secs)
                )
            except TwoNError:
                data.uptime = None

            # Switches
            data.switches = await self.api.get_switches()

            # IO ports
            data.ports = await self.api.get_ports()

            # Log caps — optional feature, not all devices/firmware support it
            try:
                data.log_caps = await self.api.get_log_caps()
            except TwoNError as exc:
                _LOGGER.debug("Log API not available on this device: %s", exc)
                data.log_caps = []

            # Directory
            users = await self.api.list_users()
            data.users = {u["uuid"]: u for u in users if "uuid" in u}

        except TwoNConnectionError as exc:
            raise UpdateFailed(f"Cannot reach 2N device: {exc}") from exc
        except TwoNError as exc:
            raise UpdateFailed(f"2N API error: {exc}") from exc

        return data

    # ── Convenience accessors ─────────────────────────────────────────────

    @property
    def device_data(self) -> TwoNCoordinatorData | None:
        return self.data

    def get_switch(self, switch_id: int) -> dict | None:
        if not self.data:
            return None
        for sw in self.data.switches:
            if sw["id"] == switch_id:
                return sw
        return None

    def get_port(self, port_id: str) -> dict | None:
        if not self.data:
            return None
        for port in self.data.ports:
            if port["id"] == port_id:
                return port
        return None

    def get_user_by_name(self, name: str) -> dict | None:
        if not self.data:
            return None
        for user in self.data.users.values():
            if user.get("name", "").lower() == name.lower():
                return user
        return None

    # ── Log-push loop ─────────────────────────────────────────────────────

    async def start_log_loop(self) -> None:
        """Start background task that long-polls device log events."""
        if not self.data or not self.data.log_caps:
            _LOGGER.debug("[%s] log API not supported, skipping log loop", self.entry_id)
            return
        if self._log_task and not self._log_task.done():
            return
        self._log_task = self.hass.async_create_background_task(
            self._log_loop(), name=f"2n_log_{self.entry_id}"
        )

    async def stop_log_loop(self) -> None:
        """Cancel the log-poll background task."""
        if self._log_task and not self._log_task.done():
            self._log_task.cancel()
            try:
                await self._log_task
            except asyncio.CancelledError:
                pass
        self._log_task = None

    async def _log_loop(self) -> None:
        """
        Continuously subscribe → pull → fire HA events → repeat.

        Subscribes with a 90-second duration window.  On expiry or error,
        re-subscribes automatically.
        """
        from .events import async_fire_log_event  # avoid circular import

        PULL_TIMEOUT  = 30   # seconds to wait for new events each pull
        SUB_DURATION  = 90   # device-side subscription window

        _LOGGER.debug("[%s] log loop started", self.entry_id)
        channel_id: int | None = None

        while True:
            try:
                # (Re)subscribe
                channel_id = await self.api.log_subscribe(
                    include="new",
                    duration=SUB_DURATION,
                )
                if channel_id == -1:
                    _LOGGER.debug("[%s] log subscribe returned no channel, stopping loop", self.entry_id)
                    return
                _LOGGER.debug(
                    "[%s] log subscribed, channel=%s", self.entry_id, channel_id
                )

                while True:
                    events = await self.api.log_pull(
                        channel_id, timeout=PULL_TIMEOUT
                    )
                    for event in events:
                        async_fire_log_event(
                            self.hass, self.entry_id, event
                        )

            except asyncio.CancelledError:
                # Clean shutdown
                if channel_id is not None:
                    try:
                        await self.api.log_unsubscribe(channel_id)
                    except TwoNError:
                        pass
                _LOGGER.debug("[%s] log loop stopped", self.entry_id)
                return

            except TwoNError as exc:
                _LOGGER.debug(
                    "[%s] log loop error (%s), retrying in 10 s", self.entry_id, exc
                )
                await asyncio.sleep(10)

            except Exception as exc:  # pylint: disable=broad-except
                _LOGGER.warning(
                    "[%s] unexpected log loop error: %s", self.entry_id, exc
                )
                await asyncio.sleep(30)
