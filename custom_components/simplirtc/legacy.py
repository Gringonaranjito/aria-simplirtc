"""Loopback FLV bridge for legacy SimpliSafe doorbell cameras.

The SimpliSafe bearer token is sent only to the upstream SimpliSafe server,
never to FFmpeg, dashboards, diagnostics, or a stream URL.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from typing import TYPE_CHECKING

from aiohttp import ClientError, ClientTimeout, web
from homeassistant.components.http import HomeAssistantView, KEY_HASS
from homeassistant.helpers.aiohttp_client import async_get_clientsession

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
ROUTE = "/api/simplirtc/legacy/{camera_id}/{secret}"
# This is a local-only source consumed by Home Assistant's FFmpeg worker.
_CAMERAS: dict[str, tuple[str, object]] = {}
_LOCK = asyncio.Lock()


class LegacyDoorbellView(HomeAssistantView):
    """Serve upstream camera bytes to local FFmpeg; no public bearer tokens."""

    url = ROUTE
    name = "api:simplirtc:legacy"
    requires_auth = False

    async def get(self, request: web.Request, camera_id: str, secret: str) -> web.StreamResponse:
        registration = _CAMERAS.get(camera_id)
        if registration is None or not secrets.compare_digest(registration[0], secret):
            raise web.HTTPNotFound()
        # Never allow LAN clients through this unauthenticated internal bridge.
        if request.remote not in ("127.0.0.1", "::1"):
            raise web.HTTPForbidden()
        api = registration[1]
        bearer = getattr(api, "access_token", None)
        if not isinstance(bearer, str) or not bearer:
            raise web.HTTPServiceUnavailable()

        upstream_url = f"https://media.simplisafe.com/v1/{camera_id}/flv?x=640&audioEncoding=AAC"
        session = async_get_clientsession(request.app[KEY_HASS])
        try:
            async with session.get(
                upstream_url,
                headers={"Authorization": f"Bearer {bearer}"},
                timeout=ClientTimeout(total=None, sock_connect=15, sock_read=45),
            ) as upstream:
                if upstream.status != 200:
                    _LOGGER.warning("Legacy doorbell upstream returned HTTP %d", upstream.status)
                    raise web.HTTPBadGateway()
                response = web.StreamResponse(
                    status=200, headers={"Content-Type": "video/x-flv", "Cache-Control": "no-store"}
                )
                await response.prepare(request)
                async for chunk in upstream.content.iter_chunked(65536):
                    await response.write(chunk)
                await response.write_eof()
                return response
        except (ClientError, asyncio.TimeoutError, ConnectionResetError):
            _LOGGER.debug("Legacy doorbell FLV connection ended")
            raise web.HTTPBadGateway() from None


def register_legacy_view(hass: HomeAssistant) -> None:
    """Register once per Home Assistant lifetime."""
    if hass.data.get("simplirtc_legacy_view_registered"):
        return
    hass.http.register_view(LegacyDoorbellView())
    hass.data["simplirtc_legacy_view_registered"] = True


def legacy_stream_source(hass: HomeAssistant, camera_id: str, api: object) -> str:
    """Create a fresh unguessable local stream URL for the active camera."""
    secret = secrets.token_urlsafe(32)
    _CAMERAS[camera_id] = (secret, api)
    return f"http://127.0.0.1:{hass.http.server_port}/api/simplirtc/legacy/{camera_id}/{secret}"
