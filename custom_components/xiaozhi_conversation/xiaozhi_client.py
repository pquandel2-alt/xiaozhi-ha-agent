"""XiaoZhi WebSocket client for text-based conversation."""

import asyncio
import json
import logging
from typing import Optional

import websockets

from .const import (
    PROTOCOL_VERSION,
    AUDIO_FORMAT,
    SAMPLE_RATE,
    CHANNELS,
    FRAME_DURATION,
    WEBSOCKET_MESSAGE_SIZE,
    WEBSOCKET_PING_INTERVAL,
    WEBSOCKET_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class XiaoZhiClient:
    """XiaoZhi WebSocket client."""

    def __init__(
        self,
        device_id: str,
        client_id: str,
        access_token: str,
        websocket_url: str,
    ):
        """Initialize the client."""
        self.device_id = device_id
        self.client_id = client_id
        self.access_token = access_token
        self.websocket_url = websocket_url

    async def query(self, text: str) -> str:
        """Send a text query to XiaoZhi and get response."""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Protocol-Version": PROTOCOL_VERSION,
            "Device-Id": self.device_id,
            "Client-Id": self.client_id,
        }

        try:
            async with asyncio.timeout(WEBSOCKET_TIMEOUT):
                async with websockets.connect(
                    self.websocket_url,
                    additional_headers=headers,
                    ping_interval=WEBSOCKET_PING_INTERVAL,
                    max_size=WEBSOCKET_MESSAGE_SIZE,
                ) as ws:
                    session_id = await self._handshake(ws)
                    return await self._query_text(ws, session_id, text)
        except asyncio.TimeoutError:
            _LOGGER.error("XiaoZhi query timeout")
            raise
        except Exception as err:
            _LOGGER.error("XiaoZhi query error: %s", err)
            raise

    async def _handshake(self, ws) -> str:
        """Perform WebSocket handshake and get session_id."""
        hello_message = {
            "type": "hello",
            "version": 1,
            "features": {"mcp": True},
            "transport": "websocket",
            "audio_params": {
                "format": AUDIO_FORMAT,
                "sample_rate": SAMPLE_RATE,
                "channels": CHANNELS,
                "frame_duration": FRAME_DURATION,
            },
        }
        await ws.send(json.dumps(hello_message))

        session_id = None
        async for msg in ws:
            if isinstance(msg, bytes):
                continue

            data = json.loads(msg)
            msg_type = data.get("type")

            if msg_type == "hello":
                session_id = data.get("session_id")
                _LOGGER.debug("Handshake successful, session_id=%s", session_id)
                return session_id

            if msg_type == "error":
                error_msg = data.get("message", "Unknown error")
                raise RuntimeError(f"XiaoZhi handshake error: {error_msg}")

        raise RuntimeError("Handshake failed: no hello response from server")

    async def _query_text(self, ws, session_id: str, text: str) -> str:
        """Send text query and collect response."""
        listen_message = {
            "session_id": session_id,
            "type": "listen",
            "state": "detect",
            "text": text,
        }
        await ws.send(json.dumps(listen_message))

        response_parts = []
        response_complete = False

        try:
            async with asyncio.timeout(WEBSOCKET_TIMEOUT):
                async for msg in ws:
                    if isinstance(msg, bytes):
                        continue

                    data = json.loads(msg)
                    msg_type = data.get("type")

                    if msg_type == "stt":
                        recognized_text = data.get("text")
                        _LOGGER.debug("STT recognized: %s", recognized_text)

                    elif msg_type == "tts":
                        # TTS message contains LLM response text
                        state = data.get("state")
                        response_text = data.get("text")

                        if response_text:
                            response_parts.append(response_text)
                            _LOGGER.debug("TTS response: %s", response_text)

                        if state == "stop" and response_parts:
                            # Response is complete
                            response_complete = True
                            break

                    elif msg_type == "error":
                        error_msg = data.get("message", "Unknown error")
                        raise RuntimeError(f"XiaoZhi error: {error_msg}")

                    elif msg_type == "mcp":
                        # MCP tool call — for future implementation
                        _LOGGER.debug("MCP tool call received: %s", data)

        except asyncio.TimeoutError:
            _LOGGER.error("Response collection timeout")
            if response_parts:
                return "".join(response_parts)
            raise RuntimeError("Timeout waiting for response from XiaoZhi")

        if not response_complete or not response_parts:
            _LOGGER.warning("Response not complete, got parts: %s", response_parts)
            return "".join(response_parts) if response_parts else "No response from XiaoZhi"

        return "".join(response_parts)
