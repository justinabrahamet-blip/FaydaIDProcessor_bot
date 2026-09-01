import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()

# AIVerse API configuration
AIVERSE_API_KEY = os.getenv("AIVERSE_API_KEY", "").strip()
AIVERSE_BASE_URL = os.getenv("AIVERSE_BASE_URL", "https://aiversehub.store").rstrip("/")

# Supabase PostgreSQL configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()

# Accepts SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY or SUPABASE_KEY
SUPABASE_SERVICE_ROLE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or 
    os.getenv("SUPABASE_SECRET_KEY", "") or 
    os.getenv("SUPABASE_KEY", "")
).strip()

# Mandatory Channel IDs & Support Username
def _format_channel_id(val: str) -> int:
    val = val.strip()
    if not val:
        return -1003787649556
    if not val.startswith("-"):
        val = f"-{val}" if val.startswith("100") else f"-100{val}"
    try:
        return int(val)
    except ValueError:
        return -1003787649556

SALES_CHANNEL_ID = _format_channel_id(os.getenv("SALES_CHANNEL_ID", "-1003787649556"))
LOGS_CHANNEL_ID = _format_channel_id(os.getenv("LOGS_CHANNEL_ID", "-1002786006091"))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "mr_melaku").lstrip("@")

# Admin IDs list
admin_ids_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_raw.split(",") if x.strip().isdigit()]

# 1. User-Facing Deposit Display Details (Full Numbers & Names shown to paying users)
DISPLAY_CBE_ACCOUNT = os.getenv("DISPLAY_CBE_ACCOUNT", "1000320563279").strip()
DISPLAY_CBE_HOLDER = os.getenv("DISPLAY_CBE_HOLDER", "MELAX DIGITAL").strip()
DISPLAY_TELEBIRR_NO = os.getenv("DISPLAY_TELEBIRR_NO", "0912345678").strip()
DISPLAY_TELEBIRR_HOLDER = os.getenv("DISPLAY_TELEBIRR_HOLDER", "MELAX DIGITAL").strip()

# 2. Internal Receipt Verifier Rules (Masked or Unmasked numbers/names used strictly for server receipt matching)
EXPECTED_CBE_ACCOUNT = os.getenv("EXPECTED_CBE_ACCOUNT", "1****7241").strip()
EXPECTED_CBE_HOLDER = os.getenv("EXPECTED_CBE_HOLDER", "MELAX DIGITAL").strip()
TELEBIRR_NO = os.getenv("TELEBIRR_NO", "0912***678").strip()
EXPECTED_TELEBIRR_HOLDER = os.getenv("EXPECTED_TELEBIRR_HOLDER", "MELAX DIGITAL").strip()
TELEBIRR_HOLDER_NAME = EXPECTED_TELEBIRR_HOLDER
CBE_NO = f"{DISPLAY_CBE_ACCOUNT} ({DISPLAY_CBE_HOLDER})"

MIN_DEPOSIT_AMOUNT = float(os.getenv("MIN_DEPOSIT_AMOUNT", "10.0"))
MAX_DEPOSIT_AMOUNT = float(os.getenv("MAX_DEPOSIT_AMOUNT", "100000.0"))

# Pricing & Referral Defaults
MARKUP_PERCENT = float(os.getenv("MARKUP_PERCENT", "10.0"))
REFERRAL_PERCENT = float(os.getenv("REFERRAL_PERCENT", "5.0"))

# Referral Milestone Tiers Defaults (Admin Customizable)
DEFAULT_REFERRAL_TIERS = [
    {
        "id": "tier_spotify",
        "invites": 20,
        "reward_name": "Spotify Premium Account (1 Month)",
        "icon": "🎧",
        "service_id": "spotify",
        "auto_deliver": True
    },
    {
        "id": "tier_gemini",
        "invites": 25,
        "reward_name": "Google Gemini Pro Account (1 Month)",
        "icon": "✨",
        "service_id": "gemini",
        "auto_deliver": True
    }
]

# Global Discount & Offer Defaults
DEFAULT_GLOBAL_DISCOUNT_PERCENT = 0.0
DEFAULT_VIP_DISCOUNT_PERCENT = 5.0

# Server / Webhook Settings
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
PORT = int(os.getenv("PORT", "8080"))

# Telebirr Merchant Server API Credentials (Optional)
TELEBIRR_APP_ID = os.getenv("TELEBIRR_APP_ID", "").strip()
TELEBIRR_APP_KEY = os.getenv("TELEBIRR_APP_KEY", "").strip()
TELEBIRR_SHORT_CODE = os.getenv("TELEBIRR_SHORT_CODE", "").strip()
TELEBIRR_PUBLIC_KEY = os.getenv("TELEBIRR_PUBLIC_KEY", "").strip()
TELEBIRR_SERVER_URL = os.getenv("TELEBIRR_SERVER_URL", "https://app.telebirr.et:8443").rstrip("/")

# Telegram Custom Animated Emoji IDs (Optional)
CUSTOM_EMOJI_GEMINI = os.getenv("CUSTOM_EMOJI_GEMINI", "").strip()
CUSTOM_EMOJI_SPOTIFY = os.getenv("CUSTOM_EMOJI_SPOTIFY", "").strip()
CUSTOM_EMOJI_NETFLIX = os.getenv("CUSTOM_EMOJI_NETFLIX", "").strip()
CUSTOM_EMOJI_CHATGPT = os.getenv("CUSTOM_EMOJI_CHATGPT", "").strip()
CUSTOM_EMOJI_DIAMOND = os.getenv("CUSTOM_EMOJI_DIAMOND", "").strip()
CUSTOM_EMOJI_VERIFIED = os.getenv("CUSTOM_EMOJI_VERIFIED", "").strip()
CUSTOM_EMOJI_FIRE = os.getenv("CUSTOM_EMOJI_FIRE", "").strip()
CUSTOM_EMOJI_STAR = os.getenv("CUSTOM_EMOJI_STAR", "").strip()

# Complete Dynamic Animated Emoji Registry (Loaded from Supabase & updated via Admin Dashboard)
DYNAMIC_EMOJIS = {
    # System UI Icons
    "diamond": {"id": CUSTOM_EMOJI_DIAMOND, "fallback": "💎"},
    "crown": {"id": os.getenv("CUSTOM_EMOJI_CROWN", "").strip(), "fallback": "👑"},
    "star": {"id": CUSTOM_EMOJI_STAR, "fallback": "⭐"},
    "money": {"id": os.getenv("CUSTOM_EMOJI_MONEY", "").strip(), "fallback": "💰"},
    "box": {"id": os.getenv("CUSTOM_EMOJI_BOX", "").strip(), "fallback": "📦"},
    "lightning": {"id": os.getenv("CUSTOM_EMOJI_LIGHTNING", "").strip(), "fallback": "⚡"},
    "wallet": {"id": os.getenv("CUSTOM_EMOJI_WALLET", "").strip(), "fallback": "💳"},
    "cart": {"id": os.getenv("CUSTOM_EMOJI_CART", "").strip(), "fallback": "🛒"},
    "profile": {"id": os.getenv("CUSTOM_EMOJI_PROFILE", "").strip(), "fallback": "👤"},
    "gift": {"id": os.getenv("CUSTOM_EMOJI_GIFT", "").strip(), "fallback": "🎁"},
    "support": {"id": os.getenv("CUSTOM_EMOJI_SUPPORT", "").strip(), "fallback": "❓"},
    "check": {"id": CUSTOM_EMOJI_VERIFIED, "fallback": "✅"},
    "cross": {"id": os.getenv("CUSTOM_EMOJI_CROSS", "").strip(), "fallback": "❌"},
    "fire": {"id": CUSTOM_EMOJI_FIRE, "fallback": "🔥"},
    "sparkle": {"id": os.getenv("CUSTOM_EMOJI_SPARKLE", "").strip(), "fallback": "✨"},
    "cbe": {"id": os.getenv("CUSTOM_EMOJI_CBE", "").strip(), "fallback": "🏦"},
    "bank": {"id": os.getenv("CUSTOM_EMOJI_BANK", "").strip(), "fallback": "🏦"},
    "telebirr": {"id": os.getenv("CUSTOM_EMOJI_TELEBIRR", "").strip(), "fallback": "📱"},
    "phone": {"id": os.getenv("CUSTOM_EMOJI_PHONE", "").strip(), "fallback": "📱"},
    "receipt": {"id": os.getenv("CUSTOM_EMOJI_RECEIPT", "").strip(), "fallback": "🧾"},
    "key": {"id": os.getenv("CUSTOM_EMOJI_KEY", "").strip(), "fallback": "🔑"},
    "time": {"id": os.getenv("CUSTOM_EMOJI_TIME", "").strip(), "fallback": "🕒"},
    "celebration": {"id": os.getenv("CUSTOM_EMOJI_CELEBRATION", "").strip(), "fallback": "🎉"},
    # Brand Icons
    "spotify": {"id": CUSTOM_EMOJI_SPOTIFY, "fallback": "🎧"},
    "gemini": {"id": CUSTOM_EMOJI_GEMINI, "fallback": "✨"},
    "netflix": {"id": CUSTOM_EMOJI_NETFLIX, "fallback": "🎬"},
    "chatgpt": {"id": CUSTOM_EMOJI_CHATGPT, "fallback": "🤖"},
    "canva": {"id": os.getenv("CUSTOM_EMOJI_CANVA", "").strip(), "fallback": "🎨"},
    "youtube": {"id": os.getenv("CUSTOM_EMOJI_YOUTUBE", "").strip(), "fallback": "📺"},
    "vpn": {"id": os.getenv("CUSTOM_EMOJI_VPN", "").strip(), "fallback": "🛡️"},
    "discord": {"id": os.getenv("CUSTOM_EMOJI_DISCORD", "").strip(), "fallback": "👾"},
    "apple": {"id": os.getenv("CUSTOM_EMOJI_APPLE", "").strip(), "fallback": "🍏"},
}

UNICODE_EMOJI_MAP = {
    "💎": "diamond",
    "👑": "crown",
    "⭐": "star",
    "💰": "money",
    "📦": "box",
    "⚡": "lightning",
    "💳": "wallet",
    "🛒": "cart",
    "👤": "profile",
    "🎁": "gift",
    "❓": "support",
    "✅": "check",
    "❌": "cross",
    "🔥": "fire",
    "✨": "sparkle",
    "🏦": "cbe",
    "📱": "telebirr",
    "🧾": "receipt",
    "🔑": "key",
    "🕒": "time",
    "🎉": "celebration",
    "🎧": "spotify",
    "🎬": "netflix",
    "🤖": "chatgpt",
    "🎨": "canva",
    "📺": "youtube",
    "🛡️": "vpn",
}

def emo(key_or_symbol: str, default_fallback: str = "") -> str:
    """Get fully animated <tg-emoji> tag for any UI key or unicode symbol, fallback to unicode."""
    sym = str(key_or_symbol).strip()
    k = UNICODE_EMOJI_MAP.get(sym, sym.lower())
    item = DYNAMIC_EMOJIS.get(k, {})
    custom_id = str(item.get("id", "")).strip()
    fallback = default_fallback or item.get("fallback", sym)
    if custom_id and custom_id.isdigit():
        return f'<tg-emoji emoji-id="{custom_id}">{fallback}</tg-emoji>'
    return fallback

def update_dynamic_emoji(key: str, emoji_id: str):
    """Update in-memory emoji mapping dynamically from Admin Dashboard."""
    k = UNICODE_EMOJI_MAP.get(key.strip(), key.strip().lower())
    if k not in DYNAMIC_EMOJIS:
        DYNAMIC_EMOJIS[k] = {"id": "", "fallback": "✨"}
    DYNAMIC_EMOJIS[k]["id"] = str(emoji_id).strip()

DYNAMIC_EMOJI_CACHE = DYNAMIC_EMOJIS

def animate_text(text: str) -> str:
    """Automatically convert all mapped unicode emojis and key tags in text into animated <tg-emoji> tags."""
    if not text:
        return ""
    result = str(text)
    for unicode_char, key in UNICODE_EMOJI_MAP.items():
        item = DYNAMIC_EMOJIS.get(key, {})
        custom_id = str(item.get("id", "")).strip()
        if custom_id and custom_id.isdigit():
            if f'emoji-id="{custom_id}"' not in result:
                result = result.replace(unicode_char, f'<tg-emoji emoji-id="{custom_id}">{unicode_char}</tg-emoji>')
    return result

def get_product_brand_icon(name: str) -> str:
    """Intelligently map product brand names to their animated custom emoji or rich brand icon."""
    n = name.lower()
    if "spotify" in n:
        return emo("spotify", "🎧")
    elif "gemini" in n or "bard" in n:
        return emo("gemini", "✨")
    elif "netflix" in n:
        return emo("netflix", "🎬")
    elif "chatgpt" in n or "openai" in n or "gpt" in n:
        return emo("chatgpt", "🤖")
    elif "claude" in n or "anthropic" in n:
        return emo("chatgpt", "🧠")
    elif "youtube" in n:
        return emo("youtube", "📺")
    elif "telegram" in n or "premium" in n:
        return emo("star", "⭐")
    elif "canva" in n:
        return emo("canva", "🎨")
    elif "midjourney" in n:
        return emo("sparkle", "🖼️")
    elif "vpn" in n or "nord" in n:
        return emo("vpn", "🛡️")
    elif "discord" in n or "nitro" in n:
        return emo("discord", "👾")
    elif "apple" in n or "icloud" in n:
        return emo("apple", "🍏")
    else:
        return emo("diamond", "💎")

def get_product_button_icon(name: str) -> str:
    """Get clean unicode button icon for Telegram inline keyboard buttons."""
    n = name.lower()
    if "spotify" in n:
        return "🎧"
    elif "gemini" in n or "bard" in n:
        return "✨"
    elif "netflix" in n:
        return "🎬"
    elif "chatgpt" in n or "openai" in n or "gpt" in n:
        return "🤖"
    elif "claude" in n or "anthropic" in n:
        return "🧠"
    elif "youtube" in n:
        return "📺"
    elif "telegram" in n or "premium" in n:
        return "⭐"
    elif "canva" in n:
        return "🎨"
    elif "midjourney" in n:
        return "🖼️"
    elif "vpn" in n:
        return "🛡️"
    elif "discord" in n:
        return "👾"
    elif "apple" in n:
        return "🍏"
    else:
        return "💎"
