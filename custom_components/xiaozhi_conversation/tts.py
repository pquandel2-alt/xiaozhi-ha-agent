"""XiaoZhi Text-to-Speech entity.

This does NOT synthesize arbitrary text on its own — the XiaoZhi cloud protocol
has no verbatim-TTS command. Instead it replays the audio XiaoZhi already
produced for a conversation reply (cached by the conversation entity). In the
Assist pipeline this means: conversation agent answers -> its spoken audio is
cached -> this entity returns that exact audio, so you hear XiaoZhi's own voice.

On a cache miss (e.g. an automation calling TTS with novel text) it falls back
to querying XiaoZhi live and returning whatever audio comes back. Note that in
that case XiaoZhi *responds* to the text rather than reading it verbatim.
"""

import logging

from homeassistant.components.tts import TextToSpeechEntity, TtsAudioType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CONF_CLIENT_ID,
    CONF_ACCESS_TOKEN,
    CONF_WEBSOCKET_URL,
    DATA_TTS_CACHE,
    TTS_LANGUAGES,
)
from .xiaozhi_client import XiaoZhiClient
from .opus_ogg import frames_to_ogg
from .util import tts_cache_key

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the XiaoZhi TTS entity."""
    async_add_entities([XiaoZhiTTSEntity(config_entry)])


class XiaoZhiTTSEntity(TextToSpeechEntity):
    """Replays XiaoZhi's own voice audio as a Home Assistant TTS engine."""

    _attr_has_entity_name = True
    _attr_name = "XiaoZhi TTS"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the TTS entity."""
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_tts"
        self.client = XiaoZhiClient(
            device_id=entry.data.get(CONF_DEVICE_ID),
            client_id=entry.data.get(CONF_CLIENT_ID),
            access_token=entry.data.get(CONF_ACCESS_TOKEN),
            websocket_url=entry.data.get(CONF_WEBSOCKET_URL),
        )

    @property
    def default_language(self) -> str:
        """Return the default language."""
        return "de"

    @property
    def supported_languages(self) -> list[str]:
        """Return the list of supported languages."""
        return TTS_LANGUAGES

    @property
    def supported_options(self) -> list[str]:
        """Return the list of supported options."""
        return []

    async def async_get_tts_audio(
        self, message: str, language: str, options: dict | None = None
    ) -> TtsAudioType:
        """Return audio for a message — cached XiaoZhi voice, or live fallback."""
        cache: dict[str, bytes] = self.hass.data[DOMAIN][DATA_TTS_CACHE]
        key = tts_cache_key(message)

        ogg = cache.get(key)
        if ogg is not None:
            _LOGGER.debug("TTS cache hit (%d bytes)", len(ogg))
            return ("ogg", ogg)

        # Cache miss — query XiaoZhi live. This produces a *response* to the
        # text, not verbatim speech, but yields XiaoZhi-voiced audio.
        _LOGGER.debug("TTS cache miss for %r — querying XiaoZhi live", message)
        try:
            _text, frames = await self.client.query(message)
            ogg = frames_to_ogg(frames)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("XiaoZhi TTS live query failed: %s", err)
            return (None, None)

        if ogg is None:
            _LOGGER.warning("XiaoZhi returned no audio for TTS request")
            return (None, None)

        return ("ogg", ogg)
