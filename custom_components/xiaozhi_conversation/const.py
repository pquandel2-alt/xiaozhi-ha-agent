"""Constants for XiaoZhi Conversation integration."""

DOMAIN = "xiaozhi_conversation"

CONF_DEVICE_ID = "device_id"
CONF_CLIENT_ID = "client_id"
CONF_ACCESS_TOKEN = "access_token"
CONF_WEBSOCKET_URL = "websocket_url"
CONF_LANGUAGE = "language"

DEFAULT_LANGUAGE = "zh"

OTA_ENDPOINT = "https://api.tenclass.net/xiaozhi/ota/"
APP_VERSION = "2.0.6"
BOARD_TYPE = "bread-compact-wifi"
USER_AGENT = f"{BOARD_TYPE}/py-xiaozhi-{APP_VERSION}"

PROTOCOL_VERSION = "1"
AUDIO_FORMAT = "opus"
SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_DURATION = 60

WEBSOCKET_TIMEOUT = 30
WEBSOCKET_MESSAGE_SIZE = 10 * 1024 * 1024
WEBSOCKET_PING_INTERVAL = 20
