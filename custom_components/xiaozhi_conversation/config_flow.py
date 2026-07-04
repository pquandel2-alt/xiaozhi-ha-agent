"""Config flow for XiaoZhi Conversation integration."""

import uuid
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN, CONF_DEVICE_ID, CONF_CLIENT_ID, CONF_ACCESS_TOKEN, CONF_WEBSOCKET_URL


class XiaoZhiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for XiaoZhi Conversation."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title="XiaoZhi", data=user_input)

        # Generate a default Client-Id if not provided
        default_client_id = str(uuid.uuid4())

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_ID): str,
                vol.Optional(CONF_CLIENT_ID, default=default_client_id): str,
                vol.Required(CONF_ACCESS_TOKEN): str,
                vol.Required(CONF_WEBSOCKET_URL): str,
            }),
            description_placeholders={
                "device_id_hint": "MAC address (e.g., 'aa:bb:cc:dd:ee:ff')",
                "client_id_hint": "UUID (auto-generated, keep if unsure)",
                "access_token_hint": "Bearer token from XiaoZhi OTA response",
                "ws_url_hint": "WebSocket URL from XiaoZhi OTA response",
            },
        )
