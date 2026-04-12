"""Constants for 2N Intercom integration."""

DOMAIN = "2n_intercom"

# ── Config entry keys ──────────────────────────────────────────────────────
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_USE_SSL = "use_ssl"
CONF_VERIFY_SSL = "verify_ssl"
CONF_PORT = "port"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_DEVICE_NAME = "device_name"
CONF_AUTH_METHOD = "auth_method"

# ── Defaults ───────────────────────────────────────────────────────────────
DEFAULT_USE_SSL = False
DEFAULT_VERIFY_SSL = False
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_AUTH_METHOD = "basic"

# ── Platforms ──────────────────────────────────────────────────────────────
PLATFORMS = ["sensor", "switch", "binary_sensor", "camera"]

# ── Data store keys ────────────────────────────────────────────────────────
DATA_COORDINATOR = "coordinator"
DATA_API = "api"

# ── 2N HTTP API endpoints ──────────────────────────────────────────────────
API_SYSTEM_INFO     = "/api/system/info"
API_SYSTEM_STATUS   = "/api/system/status"
API_SYSTEM_RESTART  = "/api/system/restart"
API_AUDIO_TEST      = "/api/audio/test"

API_SWITCH_CAPS     = "/api/switch/caps"
API_SWITCH_STATUS   = "/api/switch/status"
API_SWITCH_CTRL     = "/api/switch/ctrl"

API_IO_CAPS         = "/api/io/caps"
API_IO_STATUS       = "/api/io/status"
API_IO_CTRL         = "/api/io/ctrl"

API_LOG_CAPS        = "/api/log/caps"
API_LOG_SUBSCRIBE   = "/api/log/subscribe"
API_LOG_UNSUBSCRIBE = "/api/log/unsubscribe"
API_LOG_PULL        = "/api/log/pull"

API_DIR_TEMPLATE    = "/api/dir/template"
API_DIR_CREATE      = "/api/dir/create"
API_DIR_UPDATE      = "/api/dir/update"
API_DIR_DELETE      = "/api/dir/delete"
API_DIR_QUERY       = "/api/dir/query"
API_DIR_GET         = "/api/dir/get"

# ── Services ───────────────────────────────────────────────────────────────
SERVICE_CREATE_USER          = "create_user"
SERVICE_UPDATE_USER          = "update_user"
SERVICE_DELETE_USER          = "delete_user"
SERVICE_SET_PIN              = "set_pin"
SERVICE_CLEAR_PIN            = "clear_pin"
SERVICE_SET_SWITCH_CODES     = "set_switch_codes"
SERVICE_SET_ACCESS_VALIDITY  = "set_access_validity"
SERVICE_SYNC_FROM_KEYMASTER  = "sync_from_keymaster"
SERVICE_RESTART_DEVICE       = "restart_device"
SERVICE_AUDIO_TEST           = "audio_test"
SERVICE_TRIGGER_SWITCH       = "trigger_switch"

# ── Events ─────────────────────────────────────────────────────────────────
EVENT_USER_CREATED   = f"{DOMAIN}_user_created"
EVENT_USER_UPDATED   = f"{DOMAIN}_user_updated"
EVENT_USER_DELETED   = f"{DOMAIN}_user_deleted"
EVENT_CODE_CHANGED   = f"{DOMAIN}_code_changed"
EVENT_DOORBELL       = f"{DOMAIN}_doorbell"
EVENT_ACCESS_GRANTED = f"{DOMAIN}_access_granted"
EVENT_ACCESS_DENIED  = f"{DOMAIN}_access_denied"
EVENT_CALL_STATE     = f"{DOMAIN}_call_state"
EVENT_DEVICE_LOG     = f"{DOMAIN}_device_log"

# ── Keymaster ──────────────────────────────────────────────────────────────
KEYMASTER_DOMAIN = "keymaster"
KEYMASTER_EVENT  = "keymaster_lock_state_changed"

# ── Service / attribute keys ───────────────────────────────────────────────
ATTR_USER_UUID      = "user_uuid"
ATTR_USER_NAME      = "user_name"
ATTR_USER_EMAIL     = "user_email"
ATTR_USER_VIRT_NUMBER = "virt_number"
ATTR_PIN            = "pin"
ATTR_SWITCH_CODES   = "switch_codes"
ATTR_VALID_FROM     = "valid_from"
ATTR_VALID_TO       = "valid_to"
ATTR_CALL_PEER      = "call_peer"
ATTR_TREEPATH       = "treepath"
ATTR_SLOT           = "slot"
ATTR_CODE           = "code"
ATTR_ENTRY_ID       = "entry_id"
ATTR_SWITCH_ID      = "switch_id"
ATTR_ACTION         = "action"
