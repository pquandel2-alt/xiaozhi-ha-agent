"""XiaoZhi Conversation Agent integration."""

import secrets

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, DATA_TTS_CACHE, CONF_WEB_TOKEN
from .web import async_setup_web

PLATFORMS = [Platform.CONVERSATION, Platform.TTS]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up XiaoZhi Conversation from a config entry."""
    # Shared cache linking conversation replies to their XiaoZhi voice audio.
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(DATA_TTS_CACHE, {})

    # Ensure a stable per-install token exists for the Live-Voice web app.
    if not entry.data.get(CONF_WEB_TOKEN):
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_WEB_TOKEN: secrets.token_urlsafe(16)},
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_web(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
