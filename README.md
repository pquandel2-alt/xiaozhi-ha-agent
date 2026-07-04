# XiaoZhi Conversation Agent for Home Assistant

A Home Assistant custom integration that uses XiaoZhi AI as the Conversation Agent backend, enabling natural language control of your Home Assistant smart home.

## Features

- **Natural Language Control** — Ask questions and give commands in natural language
- **Context-Aware** — XiaoZhi understands smart home context when integrated with HA's MCP Server
- **Text-Based** — Works via Home Assistant Assist, no voice hardware required
- **Free** — Uses XiaoZhi Cloud (xiaozhi.me) free tier

## Installation

### Prerequisites

1. **XiaoZhi Account** — Register at https://xiaozhi.me (requires Chinese phone number for SMS verification)
2. **XiaoZhi Credentials** — You need:
   - `Device ID` (any stable MAC address, e.g., `aa:bb:cc:dd:ee:ff`)
   - `Client ID` (UUID, auto-generated in config)
   - `Access Token` (obtained from OTA endpoint)
   - `WebSocket URL` (obtained from OTA endpoint)

### Get Your XiaoZhi Credentials

Run the py-xiaozhi tool to get your tokens:

```bash
# If you have py-xiaozhi installed:
python -m xiaozhi check-device
```

This will output something like:
```
websocket_url: wss://api.tenclass.net/xiaozhi/v1/
access_token: eyJ0eXAiOiJKV1QiLCJhbGc...
```

### Install Integration

1. Copy the `custom_components/xiaozhi_conversation` directory to your Home Assistant `custom_components/` folder
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Create Automation**
4. Search for "XiaoZhi Conversation" and add the integration
5. Enter your credentials (Device ID, Client ID, Access Token, WebSocket URL)

## Configuration

After adding the integration:

1. Go to **Settings → Voice Assistants**
2. Edit your default voice assistant
3. Under "Conversation agent", select **XiaoZhi Conversation**
4. Save

Now your Home Assistant will use XiaoZhi AI to process natural language queries.

## Usage

Ask questions in your Home Assistant Assist:
- "What's the temperature in the living room?"
- "Turn on the lights"
- "Set the thermostat to 22 degrees"
- "What automations are running?"

## Integration with MCP Server (Advanced)

For XiaoZhi to control Home Assistant entities, you need to set up the MCP Server bridge:

1. Install the **Model Context Protocol** integration in Home Assistant
2. Get a **Long-Lived Access Token** from your profile settings
3. Install the `xiaozhi-mcp-ha` HACS integration (https://github.com/mac8005/xiaozhi-mcp-ha)
4. Configure it with your HA token and MCP endpoint

This allows XiaoZhi to:
- Query entity states (temperatures, device status, etc.)
- Call services (turn lights on/off, set temperatures, etc.)

## Troubleshooting

### "Connection refused" or "Timeout"

- Verify your WebSocket URL is correct
- Check that your access token is still valid
- Make sure you're connected to the internet
- Verify Home Assistant can reach `api.tenclass.net`

### "No response from XiaoZhi"

- The query might have timed out — try again
- Verify your credentials are correct
- Check the Home Assistant logs for detailed error messages

### Getting credentials (detailed)

If you need to get fresh credentials:

```bash
# Option 1: Use py-xiaozhi CLI
pip install py-xiaozhi
python -c "from xiaozhi import XiaoZhiApp; app = XiaoZhiApp(); print(app.config)"

# Option 2: Check your xiaozhi.me account
# Log in to https://xiaozhi.me and find your device settings
```

## Development

This integration uses:
- `websockets` — WebSocket communication with XiaoZhi Cloud
- Home Assistant's native `conversation` platform

### File Structure

```
custom_components/xiaozhi_conversation/
├── __init__.py           # Integration setup
├── manifest.json         # Integration metadata
├── config_flow.py        # Configuration UI
├── const.py              # Constants
├── conversation.py       # ConversationEntity implementation
├── xiaozhi_client.py     # WebSocket client
├── strings.json          # Localization strings
└── translations/         # Language translations
```

## License

MIT

## Support

For issues, feature requests, or contributions, visit:
https://github.com/pquandel2-alt/xiaozhi-ha-agent

## References

- [XiaoZhi AI Documentation](https://xiaozhi.dev/)
- [XiaoZhi WebSocket Protocol](https://xiaozhi.dev/en/docs/development/websocket/)
- [Home Assistant Conversation Integration](https://developers.home-assistant.io/docs/core/entity/conversation/)
