"""XiaoZhi Conversation Entity for Home Assistant."""

import logging
from typing import Literal

from homeassistant.components import conversation
from homeassistant.components.conversation import (
    ConversationEntity,
    ConversationEntityFeature,
    ConversationInput,
    ConversationResult,
)
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.config_entries import ConfigEntry

from .const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CONF_CLIENT_ID,
    CONF_ACCESS_TOKEN,
    CONF_WEBSOCKET_URL,
    DEFAULT_LANGUAGE,
)
from .xiaozhi_client import XiaoZhiClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up XiaoZhi Conversation Entity."""
    async_add_entities([XiaoZhiConversationEntity(config_entry)])


class XiaoZhiConversationEntity(ConversationEntity):
    """XiaoZhi AI Conversation Entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = ConversationEntityFeature.CONTROL

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the entity."""
        self.entry = entry
        self._attr_unique_id = entry.entry_id

        # Create XiaoZhi client
        self.client = XiaoZhiClient(
            device_id=entry.data.get(CONF_DEVICE_ID),
            client_id=entry.data.get(CONF_CLIENT_ID),
            access_token=entry.data.get(CONF_ACCESS_TOKEN),
            websocket_url=entry.data.get(CONF_WEBSOCKET_URL),
        )

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages."""
        return MATCH_ALL

    async def async_added_to_hass(self) -> None:
        """Entity added to hass — register as conversation agent."""
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self.entry, self)
        _LOGGER.debug("XiaoZhi Conversation Agent registered")

    async def async_will_remove_from_hass(self) -> None:
        """Entity removed from hass — unregister agent."""
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()
        _LOGGER.debug("XiaoZhi Conversation Agent unregistered")

    async def async_process(self, user_input: ConversationInput) -> ConversationResult:
        """Process a conversation message."""
        text = user_input.text
        language = user_input.language or DEFAULT_LANGUAGE

        _LOGGER.debug("Processing message: %s (language: %s)", text, language)

        try:
            # Query XiaoZhi
            response_text = await self.client.query(text)
            _LOGGER.debug("XiaoZhi response: %s", response_text)

        except Exception as err:
            _LOGGER.error("XiaoZhi query failed: %s", err)
            intent_response = intent.IntentResponse(language=language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"XiaoZhi error: {err}",
            )
            return ConversationResult(
                response=intent_response,
                conversation_id=user_input.conversation_id,
            )

        # Create successful response
        intent_response = intent.IntentResponse(language=language)
        intent_response.async_set_speech(response_text)

        return ConversationResult(
            response=intent_response,
            conversation_id=user_input.conversation_id,
            continue_conversation=False,
        )
