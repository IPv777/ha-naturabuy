"""Constants for the NaturaBuy integration."""

DOMAIN = "naturabuy"

# Configuration keys
CONF_URL = "url"
CONF_NAME = "name"
CONF_MAX_PRICE = "max_price"
CONF_MIN_PRICE = "min_price"
CONF_SALE_TYPE = "sale_type"
CONF_NO_RESERVE = "no_reserve"
CONF_CONDITION = "condition"
CONF_SELLER_TYPE = "seller_type"
CONF_KEYWORDS_EXCLUDE = "keywords_exclude"
CONF_KEYWORDS_INCLUDE = "keywords_include"
CONF_MAX_PAGES = "max_pages"
CONF_NOTIFY_NEW = "notify_new"
CONF_NOTIFY_ENDING = "notify_ending"
CONF_ALERT_MINUTES = "alert_minutes"
CONF_NOTIFY_TARGETS = "notify_targets"
CONF_SCAN_INTERVAL = "scan_interval"

# Sale types
SALE_TYPE_ALL = "all"
SALE_TYPE_AUCTION = "auction"
SALE_TYPE_BUY_NOW = "buy_now"
SALE_TYPES = [SALE_TYPE_ALL, SALE_TYPE_AUCTION, SALE_TYPE_BUY_NOW]

# Conditions
CONDITION_ALL = "all"
CONDITION_USED = "used"
CONDITION_NEW = "new"
CONDITIONS = [CONDITION_ALL, CONDITION_USED, CONDITION_NEW]

# Seller types
SELLER_ALL = "all"
SELLER_PARTICULIER = "particulier"
SELLER_PRO = "pro"
SELLER_TYPES = [SELLER_ALL, SELLER_PARTICULIER, SELLER_PRO]

# Default values
DEFAULT_NAME = "NaturaBuy Watch"
DEFAULT_MAX_PRICE = 600.0
DEFAULT_MIN_PRICE = 0.0
DEFAULT_SALE_TYPE = SALE_TYPE_ALL
DEFAULT_NO_RESERVE = False
DEFAULT_CONDITION = CONDITION_ALL
DEFAULT_SELLER_TYPE = SELLER_ALL
DEFAULT_KEYWORDS_EXCLUDE = "crosse seule, canon seul, boitier seul, chargeur seul, rail seul, embases"
DEFAULT_KEYWORDS_INCLUDE = ""
DEFAULT_MAX_PAGES = 1
DEFAULT_NOTIFY_NEW = True
DEFAULT_NOTIFY_ENDING = True
DEFAULT_ALERT_MINUTES = 60
DEFAULT_SCAN_INTERVAL = 10  # in minutes

# Services and events
SERVICE_REFRESH = "refresh"
EVENT_NEW_LISTING = "naturabuy_new_listing"
EVENT_AUCTION_ENDING_SOON = "naturabuy_auction_ending_soon"

# HTTP User-Agent
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
