"""
2N Intercom — native async HTTP API client.

Covers:
  - System  : info, status, restart, audio test
  - Switch  : caps, status, control (up to 4 switches / relays)
  - IO      : caps, status, control (inputs + outputs)
  - Log     : caps, subscribe, unsubscribe, pull  (real-time events)
  - Dir     : template, create, update, delete, query
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_TIMEOUT     = 10
LOG_TIMEOUT_PAD = 5      # added to the requested log-pull timeout


# ── Exceptions ────────────────────────────────────────────────────────────

class TwoNError(Exception):
    """Base 2N error."""

class TwoNAuthError(TwoNError):
    """Authentication / authorisation failure."""

class TwoNConnectionError(TwoNError):
    """Network / connectivity failure."""

class TwoNApiError(TwoNError):
    """Device returned success=false."""
    def __init__(self, code: int, message: str = "") -> None:
        self.code = code
        super().__init__(f"API error {code}: {message}")

class TwoNUnsupportedError(TwoNError):
    """Endpoint not supported by this device / firmware."""


# ── Error code constants (mirrors py2n ApiError enum) ────────────────────

ERR_NOT_SUPPORTED       = 1
ERR_AUTHORIZATION       = 9
ERR_INSUFFICIENT_PRIV   = 10
ERR_MISSING_PARAM       = 11
ERR_INVALID_VALUE       = 12
ERR_PROCESSING          = 14


# ── Connection data ───────────────────────────────────────────────────────

class TwoNConnectionData:
    """Holds all connection parameters for one 2N device."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        use_ssl: bool = False,
        verify_ssl: bool = False,
        port: int | None = None,
        auth_method: str = "basic",
    ) -> None:
        self.host        = host
        self.username    = username
        self.password    = password
        self.use_ssl     = use_ssl
        self.verify_ssl  = verify_ssl
        self.auth_method = auth_method
        scheme = "https" if use_ssl else "http"
        self.base_url = (
            f"{scheme}://{host}:{port}" if port else f"{scheme}://{host}"
        )


# ── Low-level HTTP client ─────────────────────────────────────────────────

class TwoNClient:
    """Async HTTP client for the 2N device API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        conn: TwoNConnectionData,
    ) -> None:
        self._session = session
        self._conn    = conn
        self._auth    = aiohttp.BasicAuth(conn.username, conn.password)

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        timeout: int = API_TIMEOUT,
    ) -> dict[str, Any] | None:
        """Execute one HTTP request and return ``result`` dict or None."""
        # Normalise endpoint
        ep = endpoint.lstrip("/")
        if not ep.startswith("api/"):
            ep = "api/" + ep
        url = f"{self._conn.base_url}/{ep}"

        kwargs: dict[str, Any] = {
            "auth":   self._auth,
            "json":   json,
            "params": params,
        }
        if self._conn.use_ssl:
            kwargs["ssl"] = self._conn.verify_ssl

        try:
            async with asyncio.timeout(timeout):
                async with self._session.request(method, url, **kwargs) as resp:
                    if resp.status == 401:
                        raise TwoNAuthError("Invalid credentials")
                    if resp.status == 403:
                        raise TwoNAuthError("Insufficient privileges")

                    ct = resp.content_type or ""
                    if "json" not in ct and resp.status != 200:
                        raise TwoNUnsupportedError(
                            f"Unexpected content-type '{ct}' (HTTP {resp.status})"
                        )

                    data: dict = await resp.json(content_type=None)

        except aiohttp.ClientConnectorError as exc:
            raise TwoNConnectionError(
                f"Cannot connect to {self._conn.base_url}"
            ) from exc
        except asyncio.TimeoutError as exc:
            raise TwoNConnectionError(
                f"Timeout connecting to {self._conn.base_url}"
            ) from exc

        if "success" not in data:
            raise TwoNUnsupportedError("Response missing 'success' key — not a 2N device?")

        if not data["success"]:
            code = data.get("error", {}).get("code", -1)
            param = data.get("error", {}).get("param", "")
            if code in (ERR_AUTHORIZATION, ERR_INSUFFICIENT_PRIV):
                raise TwoNAuthError(f"Authorisation error (code {code})")
            raise TwoNApiError(code, param)

        return data.get("result")

    # convenience wrappers
    async def get(self, endpoint: str, **kw) -> dict | None:
        return await self.request("GET", endpoint, **kw)

    async def post(self, endpoint: str, **kw) -> dict | None:
        return await self.request("POST", endpoint, **kw)

    async def put(self, endpoint: str, **kw) -> dict | None:
        return await self.request("PUT", endpoint, **kw)


# ── High-level 2N API ─────────────────────────────────────────────────────

class TwoNApi:
    """
    Full 2N device API.

    Instantiate once per config entry; share the same aiohttp session
    that HA provides via async_get_clientsession().
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        conn: TwoNConnectionData,
    ) -> None:
        self._http = TwoNClient(session, conn)

    # ── System ────────────────────────────────────────────────────────────

    async def get_system_info(self) -> dict[str, Any]:
        """Return device info (name, model, serial, firmware …)."""
        return await self._http.get("/api/system/info") or {}

    async def get_system_status(self) -> dict[str, Any]:
        """Return device status (upTime, …)."""
        return await self._http.get("/api/system/status") or {}

    async def restart(self) -> None:
        """Reboot the device."""
        await self._http.get("/api/system/restart")

    async def audio_test(self) -> None:
        """Trigger audio test tone."""
        await self._http.get("/api/audio/test")

    # ── Switches ──────────────────────────────────────────────────────────

    async def get_switch_caps(self) -> list[dict]:
        """Return switch capability list."""
        try:
            result = await self._http.get("/api/switch/caps")
            return (result or {}).get("switches", [])
        except TwoNApiError as exc:
            if exc.code == ERR_NOT_SUPPORTED:
                return []
            raise

    async def get_switch_status(self) -> list[dict]:
        """Return current switch status list."""
        try:
            result = await self._http.get("/api/switch/status")
            return (result or {}).get("switches", [])
        except TwoNApiError as exc:
            if exc.code == ERR_NOT_SUPPORTED:
                return []
            raise

    async def get_switches(self) -> list[dict]:
        """Return merged caps+status for all switches."""
        caps     = await self.get_switch_caps()
        statuses = {s["switch"]: s for s in await self.get_switch_status()}
        result   = []
        for cap in caps:
            sid    = cap["switch"]
            status = statuses.get(sid, {})
            result.append({
                "id":      sid,
                "enabled": cap.get("enabled", False),
                "mode":    cap.get("mode") if cap.get("enabled") else None,
                "active":  status.get("active", False),
                "locked":  status.get("locked", False),
            })
        return result

    async def set_switch(self, switch_id: int, action: str) -> None:
        """Control a switch.  action: 'on' | 'off' | 'trigger'."""
        await self._http.get(
            f"/api/switch/ctrl?switch={switch_id}&action={action}"
        )

    # ── IO (inputs / outputs / relays) ────────────────────────────────────

    async def get_io_caps(self) -> list[dict]:
        """Return IO port capability list."""
        try:
            result = await self._http.get("/api/io/caps")
            return (result or {}).get("ports", [])
        except TwoNApiError as exc:
            if exc.code == ERR_NOT_SUPPORTED:
                return []
            raise

    async def get_io_status(self) -> list[dict]:
        """Return current IO port status list."""
        try:
            result = await self._http.get("/api/io/status")
            return (result or {}).get("ports", [])
        except TwoNApiError as exc:
            if exc.code == ERR_NOT_SUPPORTED:
                return []
            raise

    async def get_ports(self) -> list[dict]:
        """Return merged caps+status for all IO ports."""
        caps     = await self.get_io_caps()
        statuses = {p["port"]: p for p in await self.get_io_status()}
        result   = []
        for cap in caps:
            pid    = cap["port"]
            status = statuses.get(pid, {})
            result.append({
                "id":    pid,
                "type":  cap.get("type", "unknown"),
                "state": status.get("state", False),
            })
        return result

    async def set_port(self, port_id: str, on: bool) -> None:
        """Control an output port (outputs only)."""
        action = "on" if on else "off"
        await self._http.get(
            f"/api/io/ctrl?port={port_id}&action={action}"
        )

    # ── Log / real-time events ────────────────────────────────────────────

    async def get_log_caps(self) -> list[str]:
        """Return list of supported log event types."""
        try:
            result = await self._http.get("/api/log/caps")
            return (result or {}).get("events", [])
        except TwoNApiError as exc:
            if exc.code == ERR_NOT_SUPPORTED:
                return []
            raise

    async def log_subscribe(
        self,
        include: str = "new",
        filter_events: list[str] | None = None,
        duration: int = 90,
    ) -> int:
        """Subscribe to log stream; returns channel id."""
        filter_str = ""
        if filter_events:
            filter_str = f"&filter={','.join(filter_events)}"
        result = await self._http.get(
            f"/api/log/subscribe?include={include}&duration={duration}{filter_str}"
        )
        return (result or {}).get("id", -1)

    async def log_unsubscribe(self, channel_id: int) -> None:
        """Unsubscribe from log stream."""
        await self._http.get(f"/api/log/unsubscribe?id={channel_id}")

    async def log_pull(
        self,
        channel_id: int,
        timeout: int = 0,
    ) -> list[dict]:
        """Long-poll for new log events. Returns list of event dicts."""
        result = await self._http.get(
            f"/api/log/pull?id={channel_id}&timeout={timeout}",
            timeout=timeout + LOG_TIMEOUT_PAD,
        )
        return (result or {}).get("events", [])

    # ── Directory — read ──────────────────────────────────────────────────

    async def get_dir_template(self) -> dict:
        """Return the directory entry template for this device."""
        result = await self._http.get("/api/dir/template")
        users  = (result or {}).get("users", [])
        return users[0] if users else {}

    async def query_dir(
        self,
        fields: list[str] | None = None,
        series: str | None = None,
        since_timestamp: int | None = None,
    ) -> dict[str, Any]:
        """Query directory; returns {'series':…, 'users':[…]}."""
        payload: dict[str, Any] = {}
        if series:
            payload["series"] = series
        if fields:
            payload["fields"] = fields
        if since_timestamp is not None:
            payload["iterator"] = {"timestamp": since_timestamp}
        result = await self._http.post("/api/dir/query", json=payload)
        return result or {}

    async def list_users(self) -> list[dict]:
        """Return all non-deleted directory entries with key fields."""
        result = await self.query_dir(
            fields=[
                "name", "email", "virtNumber",
                "access.pin", "access.code", "access.card",
                "access.validFrom", "access.validTo",
                "access.accessPoints", "callPos",
                "deleted", "treepath",
            ]
        )
        return [u for u in result.get("users", []) if not u.get("deleted")]

    # ── Directory — create ────────────────────────────────────────────────

    async def create_user(self, user_data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new directory entry.

        ``user_data`` should include at minimum ``name``.
        A UUID is auto-generated if not supplied.
        Returns ``{'uuid': …, 'timestamp': …}`` on success.
        """
        if not user_data.get("uuid"):
            user_data = {**user_data, "uuid": str(uuid.uuid4()).upper()}

        result = await self._http.post(
            "/api/dir/create", json={"users": [user_data]}
        )
        users = (result or {}).get("users", [])
        if not users:
            raise TwoNError("Empty response from dir/create")
        entry = users[0]
        if "errors" in entry:
            raise TwoNApiError(ERR_PROCESSING, str(entry["errors"]))
        return entry

    # ── Directory — update ────────────────────────────────────────────────

    async def update_user(
        self, user_uuid: str, update_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Update an existing directory entry.

        Note: py2n uses PUT for this endpoint; we match that behaviour.
        """
        result = await self._http.put(
            "/api/dir/update",
            json={"users": [{**update_data, "uuid": user_uuid}]},
        )
        users = (result or {}).get("users", [])
        if not users:
            raise TwoNError("Empty response from dir/update")
        entry = users[0]
        if "errors" in entry:
            raise TwoNApiError(ERR_PROCESSING, str(entry["errors"]))
        return entry

    # ── Directory — delete ────────────────────────────────────────────────

    async def delete_user(self, user_uuid: str) -> bool:
        """Soft-delete a directory entry by UUID."""
        await self._http.post(
            "/api/dir/delete", json={"users": [{"uuid": user_uuid}]}
        )
        return True

    # ── Directory — convenience helpers ──────────────────────────────────

    async def set_pin(self, user_uuid: str, pin: str) -> dict:
        """Set a user's PIN (2–15 digits)."""
        if not (2 <= len(pin) <= 15 and pin.isdigit()):
            raise ValueError("PIN must be 2–15 digits")
        return await self.update_user(user_uuid, {"access": {"pin": pin}})

    async def clear_pin(self, user_uuid: str) -> dict:
        """Clear a user's PIN."""
        return await self.update_user(user_uuid, {"access": {"pin": ""}})

    async def set_switch_codes(
        self, user_uuid: str, codes: list[str]
    ) -> dict:
        """Set up to 4 switch codes (2–15 digits each, '' to skip slot)."""
        validated: list[str] = []
        for c in codes[:4]:
            if c and not (2 <= len(c) <= 15 and c.isdigit()):
                raise ValueError(f"Switch code '{c}' must be 2–15 digits or empty")
            validated.append(c)
        while len(validated) < 4:
            validated.append("")
        return await self.update_user(
            user_uuid, {"access": {"code": validated}}
        )

    async def set_access_validity(
        self, user_uuid: str, valid_from: int = 0, valid_to: int = 0
    ) -> dict:
        """Set access validity window (Unix timestamps; 0 = unlimited)."""
        return await self.update_user(
            user_uuid,
            {"access": {"validFrom": str(valid_from), "validTo": str(valid_to)}},
        )

    # ── Camera ────────────────────────────────────────────────────────────

    async def get_camera_caps(self) -> dict:
        """Return camera capabilities: available sources and JPEG resolutions."""
        try:
            result = await self._http.get("/api/camera/caps")
            return result or {}
        except TwoNApiError as exc:
            if exc.code == ERR_NOT_SUPPORTED:
                raise TwoNUnsupportedError("Camera not supported on this device")
            raise

    async def get_camera_snapshot(
        self,
        width: int = 640,
        height: int = 480,
        source: str | None = None,
        time_offset: int | None = None,
    ) -> bytes:
        """Fetch a JPEG snapshot from the device camera. Returns raw JPEG bytes."""
        import asyncio as _asyncio

        params: dict = {"width": str(width), "height": str(height)}
        if source:
            params["source"] = source
        if time_offset is not None:
            params["time"] = str(time_offset)

        ep  = "api/camera/snapshot"
        url = f"{self._http._conn.base_url}/{ep}"
        kwargs: dict = {"auth": self._http._auth, "params": params}
        if self._http._conn.use_ssl:
            kwargs["ssl"] = self._http._conn.verify_ssl

        try:
            async with _asyncio.timeout(15):
                async with self._http._session.get(url, **kwargs) as resp:
                    if resp.status == 401:
                        raise TwoNAuthError("Camera: invalid credentials")
                    if resp.status == 403:
                        raise TwoNAuthError("Camera: insufficient privileges")
                    ct = resp.content_type or ""
                    if "json" in ct:
                        data = await resp.json(content_type=None)
                        code = data.get("error", {}).get("code", -1)
                        raise TwoNApiError(code, "camera/snapshot error")
                    if "image" not in ct and "multipart" not in ct:
                        raise TwoNUnsupportedError(
                            f"Unexpected camera response content-type: {ct}"
                        )
                    return await resp.read()
        except aiohttp.ClientConnectorError as exc:
            raise TwoNConnectionError(f"Camera connection failed: {exc}") from exc
        except _asyncio.TimeoutError as exc:
            raise TwoNConnectionError("Camera snapshot timed out") from exc

    # ── Connection test ───────────────────────────────────────────────────

    async def test_connection(self) -> dict[str, Any]:
        """Verify connectivity and credentials; returns system info dict."""
        return await self.get_system_info()
