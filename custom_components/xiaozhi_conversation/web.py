"""Serve the Live-Voice PWA and proxy its WebSocket to XiaoZhi through HA.

Browsers cannot set custom WebSocket headers, and XiaoZhi requires several
(Authorization, Device-Id, Client-Id, Protocol-Version). So the PWA connects to
a WebSocket endpoint hosted *inside* Home Assistant, which relays every frame
to XiaoZhi Cloud with the correct headers injected. This keeps the audio path
"through Home Assistant" and keeps the device credentials on the server side.

A random per-install token (?k=...) guards the proxy so that only someone with
the generated link (opened once from within authenticated HA) can use it.
"""

import asyncio
import json
import logging
import os

import aiohttp
from aiohttp import web

from homeassistant.components import persistent_notification
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import get_url

from .const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CONF_CLIENT_ID,
    CONF_ACCESS_TOKEN,
    CONF_WEBSOCKET_URL,
    CONF_WEB_TOKEN,
    FRONTEND_URL_PATH,
    WS_PROXY_PATH,
    DATA_WEB_REGISTERED,
    PROTOCOL_VERSION,
    WEBSOCKET_MESSAGE_SIZE,
)

_LOGGER = logging.getLogger(__name__)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")


async def async_setup_web(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register the static PWA files and the WebSocket proxy (once)."""
    if hass.data[DOMAIN].get(DATA_WEB_REGISTERED):
        return
    hass.data[DOMAIN][DATA_WEB_REGISTERED] = True

    # aiohttp's static handler 403s on a bare directory request (no filename),
    # which is exactly what "/xiaozhi_live/" is. Register an explicit index
    # view *first* so it wins the exact-path match; asset requests with a
    # real filename (styles.css, app.js, icons/...) still fall through to
    # the static resource registered below.
    hass.http.register_view(XiaoZhiIndexView())

    # iOS/Android drop the "?k=" query string on every home-screen launch and
    # instead open the manifest's start_url, so the token must be embedded
    # server-side into start_url — otherwise every standalone launch would
    # hit the token-entry fallback screen. Served dynamically (per entry)
    # for the same exact-path-wins-over-static reason as the index view.
    hass.http.register_view(XiaoZhiManifestView(entry))

    # Serve the PWA assets (plain HTML/JS/wasm, no secrets) as static files.
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL_PATH, FRONTEND_DIR, cache_headers=False)]
    )

    # Register the guarded WebSocket relay.
    hass.http.register_view(XiaoZhiWSProxyView(entry))

    # Surface the ready-to-open link (with token) via a persistent notification.
    token = entry.data.get(CONF_WEB_TOKEN)
    try:
        base = get_url(hass, prefer_external=True)
    except Exception:  # noqa: BLE001
        base = ""
    link = f"{base}{FRONTEND_URL_PATH}/?k={token}"
    persistent_notification.async_create(
        hass,
        (
            "Deine XiaoZhi Live-Voice App ist bereit.\n\n"
            f"Öffne diesen Link auf dem iPhone und lege ihn über *Teilen → "
            f"Zum Home-Bildschirm* ab:\n\n{link}\n\n"
            "Der Link enthält deinen persönlichen Zugriffs-Token — nicht teilen."
        ),
        title="XiaoZhi Live Voice",
        notification_id="xiaozhi_live_link",
    )
    _LOGGER.info("XiaoZhi Live Voice PWA available at %s", link)


class XiaoZhiIndexView(HomeAssistantView):
    """Serve index.html for the bare app URL (with or without trailing slash).

    aiohttp's static file resource 403s when the resolved path is a
    directory (no index-file fallback), so the app's entry URL needs its
    own explicit route instead of relying on the static path for "".
    """

    url = FRONTEND_URL_PATH
    extra_urls = [f"{FRONTEND_URL_PATH}/"]
    name = "xiaozhi_live:index"
    requires_auth = False

    async def get(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


class XiaoZhiManifestView(HomeAssistantView):
    """Serve manifest.webmanifest with the access token baked into start_url.

    Safari/Chrome open the manifest's start_url (not the last-viewed URL) on
    every home-screen-icon launch, stripping any "?k=" the original link
    had. Embedding the token here means standalone launches always carry it.
    """

    url = f"{FRONTEND_URL_PATH}/manifest.webmanifest"
    name = "xiaozhi_live:manifest"
    requires_auth = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def get(self, request: web.Request) -> web.Response:
        with open(os.path.join(FRONTEND_DIR, "manifest.webmanifest"), encoding="utf-8") as f:
            manifest = json.load(f)
        token = self._entry.data.get(CONF_WEB_TOKEN)
        manifest["start_url"] = f"./?k={token}"
        return web.json_response(
            manifest,
            content_type="application/manifest+json",
            headers={"Cache-Control": "no-store"},
        )


class XiaoZhiWSProxyView(HomeAssistantView):
    """Relay a browser WebSocket to XiaoZhi Cloud, adding required headers."""

    url = WS_PROXY_PATH
    name = "api:xiaozhi_live:ws"
    requires_auth = False  # guarded by the per-install ?k= token instead

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def get(self, request: web.Request) -> web.StreamResponse:
        """Handle the WebSocket upgrade and bidirectional relay."""
        data = self._entry.data
        if request.query.get("k") != data.get(CONF_WEB_TOKEN):
            return web.Response(status=401, text="invalid token")

        client_ws = web.WebSocketResponse(max_msg_size=WEBSOCKET_MESSAGE_SIZE, heartbeat=25)
        await client_ws.prepare(request)

        headers = {
            "Authorization": f"Bearer {data.get(CONF_ACCESS_TOKEN)}",
            "Protocol-Version": PROTOCOL_VERSION,
            "Device-Id": data.get(CONF_DEVICE_ID),
            "Client-Id": data.get(CONF_CLIENT_ID),
        }
        session = async_get_clientsession(request.app["hass"])

        try:
            async with session.ws_connect(
                data.get(CONF_WEBSOCKET_URL),
                headers=headers,
                max_msg_size=WEBSOCKET_MESSAGE_SIZE,
                heartbeat=25,
            ) as upstream:
                await asyncio.gather(
                    self._pump(client_ws, upstream, "c->x"),
                    self._pump(upstream, client_ws, "x->c"),
                )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("XiaoZhi proxy error: %s", err)
        finally:
            if not client_ws.closed:
                await client_ws.close()

        return client_ws

    @staticmethod
    async def _pump(src, dst, tag: str) -> None:
        """Forward text/binary frames from src to dst until either closes."""
        try:
            async for msg in src:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await dst.send_str(msg.data)
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    await dst.send_bytes(msg.data)
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    break
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("relay %s ended: %s", tag, err)
        finally:
            # Closing one side tears down the pair.
            if not dst.closed:
                await dst.close()
