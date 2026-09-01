"""
Internationalization (i18n) Module for MELAX DIGITAL SHOP Telegram Bot.
Supports seamless Amharic (am) and English (en) switching.
"""

from typing import Dict, Any, Optional

DEFAULT_LANGUAGE = "am"

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # ----------------- MAIN MENU & START -----------------
    "welcome_title": {
        "am": "💎 <b>ሜላክስ ዲጂታል ሾፕ (MELAX DIGITAL SHOP)</b> ⚡",
        "en": "💎 <b>MELAX DIGITAL SHOP</b> ⚡"
    },
    "welcome_body": {
        "am": "👋 ሰላም <b>{name}</b>! ✨\nወደ ሜላክስ ዲጂታል ሾፕ እንኳን በደህና መጡ።\nፕሪሚየም ዲጂታል አካውንቶችን በ<b>100% ፈጣን አውቶማቲክ አቅርቦት</b> ይግዙ።\n\n💰 <b>የሒሳብ ቀሪዎ:</b> <code>{balance:,.2f} ብር</code> 💳\n\n👑 <i>ለመጀመር ከታች ካሉት አማራጮች አንዱን ይምረጡ:</i>",
        "en": "👋 Welcome <b>{name}</b>! ✨\nWelcome to MELAX DIGITAL SHOP.\nBuy premium digital accounts with <b>100% Instant Automated Delivery</b>.\n\n💰 <b>Your Balance:</b> <code>{balance:,.2f} Birr</code> 💳\n\n👑 <i>Choose an option below to start:</i>"
    },
    "menu_loaded": {
        "am": "📱 <b>ዋና ማውጫ ተከፍቷል! ⚡</b>",
        "en": "📱 <b>Main Menu Loaded! ⚡</b>"
    },

    # ----------------- REPLY BUTTONS -----------------
    "btn_reply_shop": {"am": "🛒 ዲጂታል እቃዎች", "en": "🛒 Digital Products"},
    "btn_reply_wallet": {"am": "💳 ዋሌት", "en": "💳 Wallet"},
    "btn_reply_orders": {"am": "📦 ትዕዛዞቼ", "en": "📦 My Orders"},
    "btn_reply_profile": {"am": "👤 ፕሮፋይሌ", "en": "👤 My Profile"},
    "btn_reply_referral": {"am": "🎁 ይጋብዙና ያግኙ", "en": "🎁 Refer & Earn"},
    "btn_reply_support": {"am": "❓ እርዳታና መመሪያ", "en": "❓ Support & Guide"},
    "btn_reply_channel": {"am": "📢 ቻናላችን", "en": "📢 Our Channel"},
    "btn_reply_proof": {"am": "📜 የክፍያ ማረጋገጫ", "en": "📜 Proof Channel"},
    "btn_reply_admin": {"am": "⚙️ የአድሚን ዳሽቦርድ", "en": "⚙️ Admin Dashboard"},

    # ----------------- INLINE BUTTONS -----------------
    "btn_inline_shop": {"am": "ዲጂታል እቃዎች", "en": "Digital Products"},
    "btn_inline_wallet": {"am": "ዋሌት", "en": "Wallet"},
    "btn_inline_orders": {"am": "ትዕዛዞቼ", "en": "My Orders"},
    "btn_inline_profile": {"am": "ፕሮፋይሌ", "en": "My Profile"},
    "btn_inline_referral": {"am": "ይጋብዙና ያግኙ", "en": "Refer & Earn"},
    "btn_inline_support": {"am": "እርዳታና መመሪያ", "en": "Support & Guide"},
    "btn_inline_admin": {"am": "የአድሚን ዳሽቦርድ", "en": "Admin Dashboard"},
    "btn_back": {"am": "🔙 ተመለስ", "en": "🔙 BACK"},
    "btn_cancel": {"am": "❌ ሰርዝ", "en": "❌ CANCEL"},
    "btn_back_to_menu": {"am": "🔙 ወደ ዋና ማውጫ", "en": "🔙 BACK TO MENU"},
    "btn_buy_now": {"am": "🛍️ አሁን ግዛ", "en": "🛍️ BUY NOW"},
    "btn_apply_promo": {"am": "🎟️ የቅናሽ ኮድ አስገባ", "en": "🎟️ Apply Promo Code"},
    "btn_confirm_buy": {"am": "✅ ግዢውን አረጋግጥ", "en": "✅ CONFIRM PURCHASE"},
    "btn_add_balance": {"am": "➕ ሒሳብ ሙላ", "en": "➕ ADD BALANCE"},
    "btn_tx_history": {"am": "📜 የግብይት ታሪክ", "en": "📜 TRANSACTION HISTORY"},
    "btn_lang_toggle": {"am": "🌐 ቋንቋ ቀይር / Switch Language", "en": "🌐 Switch Language / ቋንቋ ቀይር"},
    "btn_claim_reward": {"am": "🎁 ሽልማት ውሰድ", "en": "🎁 Claim Reward"},

    # ----------------- MAINTENANCE -----------------
    "maintenance_alert": {
        "am": "🛠️ <b>ቦቱ በጊዜያዊ ጥገና ላይ ነው (SYSTEM UNDER MAINTENANCE) ⚡</b>\n\nየሲስተም ማሻሻያ እና የደህንነት ፍተሻ እየተደረገ ስለሆነ ለጊዜው አገልግሎት አቋርጠናል። እባክዎን ጥቂት ቆይተው እንደገና ይሞክሩ።\n\n<i>System is currently under maintenance. Please try again shortly.</i>",
        "en": "🛠️ <b>SYSTEM UNDER MAINTENANCE ⚡</b>\n\nWe are performing routine system improvements and security updates. All services are temporarily paused. Please check back shortly!\n\n<i>ቦቱ በጊዜያዊ ጥገና ላይ ነው። እባክዎ ትንሽ ቆይተው ይሞክሩ።</i>"
    },

    # ----------------- SHOP & PRODUCTS -----------------
    "catalog_title": {
        "am": "🛒 <b>የዲጂታል እቃዎች ካታሎግ</b> 💎",
        "en": "🛒 <b>DIGITAL PRODUCTS CATALOG</b> 💎"
    },
    "catalog_subtitle": {
        "am": "የሚፈልጉትን እቃ ከታች ካለው ዝርዝር ይምረጡ:",
        "en": "Select your desired product from the list below:"
    },
    "stock_label": {"am": "ክምችት", "en": "Stock"},
    "out_of_stock": {"am": "ያለቀ", "en": "Out of Stock"},
    "in_stock": {"am": "ፍሬ አለ", "en": "in Stock"},
}

# ALL Recognized Reply Keyboard Button Variations (English + Amharic + Emojiless)
REPLY_TEXT_SHOP = {
    "🛒 Digital Products", "Digital Products", "🛒 ዲጂታል እቃዎች", "ዲጂታል እቃዎች",
    "Products", "Shop", "🛒 Products", "🛒 Shop"
}

REPLY_TEXT_WALLET = {
    "💳 Wallet", "Wallet", "💳 ዋሌት", "ዋሌት", "💳 My Wallet", "My Wallet"
}

REPLY_TEXT_ORDERS = {
    "📦 My Orders", "My Orders", "📦 ትዕዛዞቼ", "ትዕዛዞቼ", "Orders", "📦 Orders"
}

REPLY_TEXT_PROFILE = {
    "👤 My Profile", "My Profile", "👤 ፕሮፋይሌ", "ፕሮፋይሌ", "Profile", "👤 Profile"
}

REPLY_TEXT_REFERRAL = {
    "🎁 Refer & Earn", "Refer & Earn", "🎁 ይጋብዙና ያግኙ", "ይጋብዙና ያግኙ",
    "Referral", "🎁 Referral", "🎁 ይጋብዙ"
}

REPLY_TEXT_SUPPORT = {
    "❓ Support & Guide", "Support & Guide", "❓ እርዳታና መመሪያ", "እርዳታና መመሪያ",
    "Support", "❓ Support", "Help", "Guide"
}

REPLY_TEXT_CHANNEL = {
    "📢 Our Channel", "Our Channel", "📢 ቻናላችን", "ቻናላችን", "Channel", "📢 Channel"
}

REPLY_TEXT_PROOF = {
    "📜 Proof Channel", "Proof Channel", "📜 የክፍያ ማረጋገጫ", "የክፍያ ማረጋገጫ",
    "Proof", "📜 Proof", "Logs Channel"
}

REPLY_TEXT_ADMIN = {
    "⚙️ Admin Dashboard", "Admin Dashboard", "⚙️ የአድሚን ዳሽቦርድ", "የአድሚን ዳሽቦርድ",
    "Admin", "⚙️ Admin"
}

ALL_REPLY_BUTTON_TEXTS = (
    REPLY_TEXT_SHOP |
    REPLY_TEXT_WALLET |
    REPLY_TEXT_ORDERS |
    REPLY_TEXT_PROFILE |
    REPLY_TEXT_REFERRAL |
    REPLY_TEXT_SUPPORT |
    REPLY_TEXT_CHANNEL |
    REPLY_TEXT_PROOF |
    REPLY_TEXT_ADMIN
)

def t(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    lang_code = "am" if str(lang).lower().startswith("am") else "en"
    item = TRANSLATIONS.get(key, {})
    text = item.get(lang_code, item.get("am", item.get("en", key)))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
