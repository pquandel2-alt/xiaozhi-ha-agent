"""XiaoZhi Conversation Agent integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, DATA_TTS_CACHE

PLATFORMS = [Platform.CONVERSATION, Platform.TTS]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up XiaoZhi Conversation from a config entry."""
    # Shared cache linking conversation replies to their XiaoZhi voice audio.
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(DATA_TTS_CACHE, {})

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
