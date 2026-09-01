from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from security_util import format_4digit_id

def get_main_reply_keyboard(
    is_admin: bool = False,
    sales_channel_link: str = "https://t.me/melaxdigital",
    logs_channel_link: str = "https://t.me/melaxlogs"
) -> ReplyKeyboardMarkup:
    """Persistent Bottom Reply Keyboard Menu for MELAX DIGITAL SHOP with channel links."""
    builder = ReplyKeyboardBuilder()
    
    builder.row(
        KeyboardButton(text="🛒 Digital Products"),
        KeyboardButton(text="💳 Wallet")
    )
    builder.row(
        KeyboardButton(text="📦 My Orders"),
        KeyboardButton(text="👤 My Profile")
    )
    builder.row(
        KeyboardButton(text="🎁 Refer & Earn"),
        KeyboardButton(text="❓ Support & Guide")
    )
    builder.row(
        KeyboardButton(text="📢 Our Channel"),
        KeyboardButton(text="📜 Proof Channel")
    )

    if is_admin:
        builder.row(KeyboardButton(text="⚙️ Admin Dashboard"))

    return builder.as_markup(resize_keyboard=True, persistent=True)

def get_force_join_keyboard(
    sales_channel_link: str = "https://t.me/melaxdigital",
    logs_channel_link: str = "https://t.me/melaxlogs"
) -> InlineKeyboardMarkup:
    """Force join keyboard with clean text buttons."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="JOIN OFFICIAL CHANNEL", url=sales_channel_link))
    builder.row(InlineKeyboardButton(text="PROOF & LOGS CHANNEL", url=logs_channel_link))
    builder.row(InlineKeyboardButton(text="I HAVE JOINED / ተቀላቅያለሁ", callback_data="check_join_again"))
    return builder.as_markup()

def get_main_menu_keyboard(bot_username: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    """Main Menu Inline Keyboard with clean plain text buttons."""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="Digital Products", callback_data="btn_shop"),
        InlineKeyboardButton(text="Wallet", callback_data="btn_wallet")
    )
    builder.row(
        InlineKeyboardButton(text="My Orders", callback_data="btn_orders"),
        InlineKeyboardButton(text="My Profile", callback_data="btn_profile")
    )
    builder.row(
        InlineKeyboardButton(text="Refer & Earn", callback_data="btn_referral"),
        InlineKeyboardButton(text="Support & Guide", callback_data="btn_support")
    )

    if is_admin:
        builder.row(InlineKeyboardButton(text="Admin Dashboard", callback_data="btn_admin"))

    return builder.as_markup()

from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from security_util import format_4digit_id

def get_main_reply_keyboard(
    is_admin: bool = False,
    sales_channel_link: str = "https://t.me/melaxdigital",
    logs_channel_link: str = "https://t.me/melaxlogs",
    lang: str = "am"
) -> ReplyKeyboardMarkup:
    """Persistent Bottom Reply Keyboard Menu for MELAX DIGITAL SHOP with multilingual AM/ENG support."""
    builder = ReplyKeyboardBuilder()
    
    if lang == "en":
        builder.row(KeyboardButton(text="🛒 Digital Products"), KeyboardButton(text="💳 Wallet"))
        builder.row(KeyboardButton(text="📦 My Orders"), KeyboardButton(text="👤 My Profile"))
        builder.row(KeyboardButton(text="🎁 Refer & Earn"), KeyboardButton(text="❓ Support & Guide"))
        builder.row(KeyboardButton(text="📢 Our Channel"), KeyboardButton(text="📜 Proof Channel"))
        if is_admin:
            builder.row(KeyboardButton(text="⚙️ Admin Dashboard"))
    else:
        builder.row(KeyboardButton(text="🛒 ዲጂታል እቃዎች"), KeyboardButton(text="💳 ዋሌት"))
        builder.row(KeyboardButton(text="📦 ትዕዛዞቼ"), KeyboardButton(text="👤 ፕሮፋይሌ"))
        builder.row(KeyboardButton(text="🎁 ይጋብዙና ያግኙ"), KeyboardButton(text="❓ እርዳታና መመሪያ"))
        builder.row(KeyboardButton(text="📢 ቻናላችን"), KeyboardButton(text="📜 የክፍያ ማረጋገጫ"))
        if is_admin:
            builder.row(KeyboardButton(text="⚙️ የአድሚን ዳሽቦርድ"))

    return builder.as_markup(resize_keyboard=True, persistent=True)

def get_force_join_keyboard(
    sales_channel_link: str = "https://t.me/melaxdigital",
    logs_channel_link: str = "https://t.me/melaxlogs"
) -> InlineKeyboardMarkup:
    """Force join keyboard with clean text buttons."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="JOIN OFFICIAL CHANNEL", url=sales_channel_link))
    builder.row(InlineKeyboardButton(text="PROOF & LOGS CHANNEL", url=logs_channel_link))
    builder.row(InlineKeyboardButton(text="I HAVE JOINED / ተቀላቅያለሁ", callback_data="check_join_again"))
    return builder.as_markup()

def get_main_menu_keyboard(bot_username: str, is_admin: bool = False, lang: str = "am") -> InlineKeyboardMarkup:
    """Main Menu Inline Keyboard with clean plain text buttons in AM or ENG."""
    builder = InlineKeyboardBuilder()

    if lang == "en":
        builder.row(
            InlineKeyboardButton(text="Digital Products", callback_data="btn_shop"),
            InlineKeyboardButton(text="Wallet", callback_data="btn_wallet")
        )
        builder.row(
            InlineKeyboardButton(text="My Orders", callback_data="btn_orders"),
            InlineKeyboardButton(text="My Profile", callback_data="btn_profile")
        )
        builder.row(
            InlineKeyboardButton(text="Refer & Earn", callback_data="btn_referral"),
            InlineKeyboardButton(text="Support & Guide", callback_data="btn_support")
        )
        if is_admin:
            builder.row(
                InlineKeyboardButton(text="✏️ Edit Welcome Screen", callback_data="adm_edit_ui:welcome"),
                InlineKeyboardButton(text="Admin Dashboard", callback_data="btn_admin")
            )
    else:
        builder.row(
            InlineKeyboardButton(text="ዲጂታል እቃዎች", callback_data="btn_shop"),
            InlineKeyboardButton(text="ዋሌት", callback_data="btn_wallet")
        )
        builder.row(
            InlineKeyboardButton(text="ትዕዛዞቼ", callback_data="btn_orders"),
            InlineKeyboardButton(text="ፕሮፋይሌ", callback_data="btn_profile")
        )
        builder.row(
            InlineKeyboardButton(text="ይጋብዙና ያግኙ", callback_data="btn_referral"),
            InlineKeyboardButton(text="እርዳታና መመሪያ", callback_data="btn_support")
        )
        if is_admin:
            builder.row(
                InlineKeyboardButton(text="✏️ Edit Welcome Screen", callback_data="adm_edit_ui:welcome"),
                InlineKeyboardButton(text="የአድሚን ዳሽቦርድ", callback_data="btn_admin")
            )

    return builder.as_markup()

def get_products_keyboard(products: list, custom_prices: dict = None, lang: str = "am") -> InlineKeyboardMarkup:
    """Product catalog inline buttons list displaying Product Name + Stock Quantity only."""
    import re
    builder = InlineKeyboardBuilder()

    for p in products:
        s_id = str(p.get("service_id") or p.get("id") or "").strip()
        raw_name = p.get("name", "Product")
        clean_name = re.sub(r'<[^>]+>', '', raw_name).strip() or raw_name
        stock = int(p.get("supplier_stock", 0))
        avail = p.get("supplier_available", True) and p.get("is_enabled", True)

        if stock > 0 and avail and s_id:
            stock_text = f"{stock} ፍሬ" if lang == "am" else f"Stock: {stock}"
            btn_text = f"{clean_name} | {stock_text}"
            builder.row(InlineKeyboardButton(text=btn_text, callback_data=f"prod_select:{s_id}"))
        else:
            unavail_text = "ያለቀ (Out of Stock)" if lang == "am" else "Out of Stock"
            btn_text = f"{clean_name} | {unavail_text}"
            builder.row(InlineKeyboardButton(text=btn_text, callback_data="noop"))

    back_text = "🔙 ወደ ዋና ማውጫ" if lang == "am" else "BACK TO MENU"
    cancel_text = "❌ ሰርዝ" if lang == "am" else "CANCEL"
    builder.row(
        InlineKeyboardButton(text=back_text, callback_data="btn_main_menu"),
        InlineKeyboardButton(text=cancel_text, callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_profile_keyboard(user_lang: str = "am", is_admin: bool = False) -> InlineKeyboardMarkup:
    """Customer profile menu with Language Switcher and in-place admin editor."""
    builder = InlineKeyboardBuilder()
    lang_tag = "🇪🇹 አማርኛ" if user_lang == "am" else "🇬🇧 English"
    other_lang = "English 🇬🇧" if user_lang == "am" else "አማርኛ 🇪🇹"
    
    builder.row(
        InlineKeyboardButton(text=f"🌐 ቋንቋ / Language: {lang_tag}", callback_data="btn_toggle_lang")
    )
    builder.row(
        InlineKeyboardButton(text=f"🔄 ወደ {other_lang} ቀይር", callback_data="btn_toggle_lang")
    )
    builder.row(
        InlineKeyboardButton(text="📜 MY ORDERS", callback_data="btn_orders"),
        InlineKeyboardButton(text="💳 WALLET", callback_data="btn_wallet")
    )
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="✏️ Edit Profile Screen", callback_data="adm_edit_ui:profile")
        )
    builder.row(
        InlineKeyboardButton(text="🔙 BACK TO MENU", callback_data="btn_main_menu"),
        InlineKeyboardButton(text="❌ CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_product_detail_keyboard(
    service_id: str,
    is_purchasable: bool = True,
    is_admin: bool = False,
    is_enabled: bool = True,
    buy_button_text: str = ""
) -> InlineKeyboardMarkup:
    """Clean Product detail view buttons with in-place Component Editor and Quick Edit controls for Admin."""
    builder = InlineKeyboardBuilder()
    btn_label = buy_button_text or "BUY NOW"
    if is_purchasable:
        builder.row(InlineKeyboardButton(text=btn_label, callback_data=f"buy_now:{service_id}"))
        builder.row(InlineKeyboardButton(text="🎟️ Apply Promo Code", callback_data=f"apply_promo:{service_id}"))
    else:
        builder.row(InlineKeyboardButton(text="TEMPORARILY UNAVAILABLE", callback_data="noop"))

    if is_admin:
        builder.row(
            InlineKeyboardButton(text="✏️ In-Place Component Editor", callback_data=f"adm_edit_prod:{service_id}")
        )
        builder.row(
            InlineKeyboardButton(text="Edit Name", callback_data=f"adm_quick_name:{service_id}"),
            InlineKeyboardButton(text="Edit Price", callback_data=f"adm_quick_price:{service_id}")
        )
        toggle_text = "Disable Product" if is_enabled else "Enable Product"
        builder.row(
            InlineKeyboardButton(text="Edit Desc", callback_data=f"adm_quick_desc:{service_id}"),
            InlineKeyboardButton(text=toggle_text, callback_data=f"adm_quick_vis:{service_id}")
        )
        builder.row(
            InlineKeyboardButton(text="🎁 Edit Commission %", callback_data=f"adm_quick_comm:{service_id}"),
            InlineKeyboardButton(text="🗑️ Delete Product", callback_data=f"adm_del_prod_confirm:{service_id}")
        )

    builder.row(
        InlineKeyboardButton(text="BACK", callback_data="btn_shop"),
        InlineKeyboardButton(text="CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_buy_confirm_keyboard(service_id: str, promo_code: str = "") -> InlineKeyboardMarkup:
    """Purchase confirmation keyboard with promo code support."""
    builder = InlineKeyboardBuilder()
    cb_data = f"confirm_buy:{service_id}:{promo_code}" if promo_code else f"confirm_buy:{service_id}"
    builder.row(
        InlineKeyboardButton(text="CONFIRM PURCHASE", callback_data=cb_data),
        InlineKeyboardButton(text="BACK", callback_data=f"prod_select:{service_id}"),
        InlineKeyboardButton(text="CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_wallet_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Customer wallet keyboard with in-place admin editor."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="ADD BALANCE", callback_data="btn_add_balance"),
        InlineKeyboardButton(text="TRANSACTION HISTORY", callback_data="btn_tx_history")
    )
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="✏️ Edit Wallet & Deposit Instructions", callback_data="adm_edit_ui:wallet")
        )
    builder.row(
        InlineKeyboardButton(text="BACK", callback_data="btn_main_menu"),
        InlineKeyboardButton(text="CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_deposit_approval_keyboard(payment_id: str) -> InlineKeyboardMarkup:
    """Admin deposit approval buttons."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="APPROVE DEPOSIT", callback_data=f"adm_dep_approve:{payment_id}"),
        InlineKeyboardButton(text="REJECT DEPOSIT", callback_data=f"adm_dep_reject:{payment_id}")
    )
    builder.row(
        InlineKeyboardButton(text="BACK", callback_data="adm_pending_payments"),
        InlineKeyboardButton(text="CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_referral_keyboard(tiers: list = None, available_invites: int = 0, lang: str = "am", is_admin: bool = False) -> InlineKeyboardMarkup:
    """Customer Referral Program keyboard with interactive reward claim, commission rates, and in-place admin editor."""
    builder = InlineKeyboardBuilder()
    tiers = tiers or []

    for t in tiers:
        req = int(t.get("invites", 20))
        r_name = t.get("reward_name", "Reward")
        t_id = t.get("id", "tier")
        icon = t.get("icon", "🎁")
        if available_invites >= req:
            builder.row(InlineKeyboardButton(
                text=f"{icon} CLAIM {r_name.upper()} ({req} Invites)",
                callback_data=f"ref_claim:{t_id}"
            ))

    comm_btn_text = "📊 የእቃዎች የኮሚሽን ዝርዝር እይ" if lang == "am" else "📊 View Product Commission Rates"
    builder.row(
        InlineKeyboardButton(text=comm_btn_text, callback_data="btn_ref_comm_rates")
    )
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="✏️ Edit Referral Program & Banners", callback_data="adm_edit_ui:referral")
        )
    back_text = "🔙 ወደ ዋና ማውጫ" if lang == "am" else "BACK TO MENU"
    cancel_text = "❌ ሰርዝ" if lang == "am" else "CANCEL"
    builder.row(
        InlineKeyboardButton(text=back_text, callback_data="btn_main_menu"),
        InlineKeyboardButton(text=cancel_text, callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_support_keyboard(is_admin: bool = False, lang: str = "am", support_username: str = "mr_melaku") -> InlineKeyboardMarkup:
    """Customer support keyboard with direct contact link and in-place admin editor."""
    builder = InlineKeyboardBuilder()
    contact_text = "🎧 የደንበኞች አገልግሎት (Contact Admin)" if lang == "am" else "🎧 Contact Support Admin"
    builder.row(
        InlineKeyboardButton(text=contact_text, url=f"https://t.me/{support_username}")
    )
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="✏️ Edit Support & Guide Content", callback_data="adm_edit_ui:support")
        )
    back_text = "🔙 ወደ ዋና ማውጫ" if lang == "am" else "BACK TO MENU"
    cancel_text = "❌ ሰርዝ" if lang == "am" else "CANCEL"
    builder.row(
        InlineKeyboardButton(text=back_text, callback_data="btn_main_menu"),
        InlineKeyboardButton(text=cancel_text, callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_orders_keyboard(is_admin: bool = False, lang: str = "am") -> InlineKeyboardMarkup:
    """Customer orders keyboard with in-place admin editor."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛒 ዲጂታል እቃዎች" if lang == "am" else "🛒 Digital Products", callback_data="btn_shop"),
        InlineKeyboardButton(text="💳 ዋሌት" if lang == "am" else "💳 Wallet", callback_data="btn_wallet")
    )
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="✏️ Edit Orders Screen", callback_data="adm_edit_ui:orders")
        )
    back_text = "🔙 ወደ ዋና ማውጫ" if lang == "am" else "BACK TO MENU"
    cancel_text = "❌ ሰርዝ" if lang == "am" else "CANCEL"
    builder.row(
        InlineKeyboardButton(text=back_text, callback_data="btn_main_menu"),
        InlineKeyboardButton(text=cancel_text, callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_admin_keyboard(maintenance_mode: bool = False) -> InlineKeyboardMarkup:
    """Admin Dashboard main menu keyboard with Services ON/OFF, Referral Rewards and Discounts & Sales."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Overview", callback_data="adm_overview"),
        InlineKeyboardButton(text="Products", callback_data="adm_products")
    )
    builder.row(
        InlineKeyboardButton(text="Customers", callback_data="adm_customers"),
        InlineKeyboardButton(text="Payments", callback_data="adm_payments")
    )
    builder.row(
        InlineKeyboardButton(text="Orders", callback_data="adm_orders"),
        InlineKeyboardButton(text="Sales & Profit", callback_data="adm_sales")
    )
    builder.row(
        InlineKeyboardButton(text="🎁 Referral Rewards", callback_data="adm_ref_tiers"),
        InlineKeyboardButton(text="🎟️ Discounts & Sales", callback_data="adm_discounts")
    )
    builder.row(
        InlineKeyboardButton(text="🎛️ Services ON / OFF Controls", callback_data="adm_services_manager")
    )
    builder.row(
        InlineKeyboardButton(text="Broadcast", callback_data="adm_broadcast"),
        InlineKeyboardButton(text="API Monitor", callback_data="adm_api_mon")
    )
    builder.row(
        InlineKeyboardButton(text="Custom Animated Emojis", callback_data="adm_emojis_manager")
    )
    
    maint_text = "Maintenance: ON (Click to Disable)" if maintenance_mode else "Maintenance: OFF (Click to Enable)"
    builder.row(
        InlineKeyboardButton(text=maint_text, callback_data="adm_toggle_maintenance")
    )
    
    builder.row(
        InlineKeyboardButton(text="MAIN MENU", callback_data="btn_main_menu"),
        InlineKeyboardButton(text="CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_admin_services_keyboard(services_status: dict) -> InlineKeyboardMarkup:
    """Keyboard for Master Bot Services ON/OFF Controls."""
    builder = InlineKeyboardBuilder()
    
    srv_list = [
        ("shop", "🛒 Digital Shop & Products", services_status.get("shop", True)),
        ("deposits", "💳 Instant Deposits (CBE/Telebirr)", services_status.get("deposits", True)),
        ("referrals", "🎁 Referral & Milestone Rewards", services_status.get("referrals", True)),
        ("discounts", "🎟️ Promo Codes & Flash Sales", services_status.get("discounts", True)),
        ("support", "🎧 Live Customer Support", services_status.get("support", True)),
        ("force_join", "🔒 Force Join Channel Verification", services_status.get("force_join", True)),
        ("maintenance", "🛠️ Global System Maintenance", services_status.get("maintenance", False)),
    ]

    for key, name, is_on in srv_list:
        status_tag = "🟢 ON (Active)" if is_on else "🔴 OFF (Disabled)"
        builder.row(
            InlineKeyboardButton(text=f"{name}: {status_tag}", callback_data=f"adm_toggle_srv:{key}")
        )

    builder.row(
        InlineKeyboardButton(text="BACK TO DASHBOARD", callback_data="btn_admin"),
        InlineKeyboardButton(text="CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_admin_referral_tiers_keyboard(tiers: list, pending_count: int = 0) -> InlineKeyboardMarkup:
    """Admin Referral Rewards & Tiers Manager keyboard."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text=f"📋 Pending Reward Claims ({pending_count})",
            callback_data="adm_view_claims"
        )
    )

    for t in tiers:
        t_id = t.get("id", "")
        r_name = t.get("reward_name", "Reward")
        inv = t.get("invites", 20)
        icon = t.get("icon", "🎁")
        builder.row(
            InlineKeyboardButton(
                text=f"{icon} {r_name} [{inv} Invites] ⚙️",
                callback_data=f"adm_view_tier:{t_id}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="➕ Add New Reward Tier", callback_data="adm_add_tier")
    )
    builder.row(
        InlineKeyboardButton(text="BACK TO DASHBOARD", callback_data="btn_admin"),
        InlineKeyboardButton(text="CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_admin_single_tier_keyboard(tier_id: str) -> InlineKeyboardMarkup:
    """Interactive actions for a single referral reward tier."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Change Reward Name", callback_data=f"adm_edit_tier_name:{tier_id}"),
        InlineKeyboardButton(text="🔢 Change Invites Required", callback_data=f"adm_edit_tier_inv:{tier_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🗑️ Delete This Tier", callback_data=f"adm_del_tier:{tier_id}")
    )
    builder.row(
        InlineKeyboardButton(text="BACK TO TIERS", callback_data="adm_ref_tiers"),
        InlineKeyboardButton(text="CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_admin_discounts_keyboard(promo_codes: list, flash_sale_percent: float = 0.0) -> InlineKeyboardMarkup:
    """Admin Discounts, Promo Codes & Flash Sales keyboard."""
    builder = InlineKeyboardBuilder()
    
    flash_label = f"🔥 Global Flash Sale: {flash_sale_percent:.0f}% OFF" if flash_sale_percent > 0 else "🔥 Global Flash Sale: OFF (0%)"
    builder.row(
        InlineKeyboardButton(text=f"{flash_label} ✏️", callback_data="adm_set_flash_sale")
    )
    builder.row(
        InlineKeyboardButton(text="➕ Create New Promo Code", callback_data="adm_add_promo")
    )

    for p in promo_codes:
        code = p.get("code", "")
        disc_type = p.get("discount_type", "PERCENT")
        val = p.get("value", 0.0)
        times_used = p.get("times_used", 0)
        max_uses = p.get("max_uses", 100)
        tag = f"{val:,.0f}%" if disc_type == "PERCENT" else f"{val:,.0f} Birr"
        builder.row(
            InlineKeyboardButton(
                text=f"🎟️ {code}: {tag} ({times_used}/{max_uses} used) [Delete 🗑️]",
                callback_data=f"adm_del_promo:{code}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="BACK TO DASHBOARD", callback_data="btn_admin"),
        InlineKeyboardButton(text="CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_admin_emojis_keyboard(current_emojis: dict = None) -> InlineKeyboardMarkup:
    """Inline keyboard for Admin 100% Full Custom Animated Emoji Manager."""
    current_emojis = current_emojis or {}
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🔄 MAP ANY UNICODE EMOJI TO ANIMATED", callback_data="adm_map_unicode")
    )
    builder.row(
        InlineKeyboardButton(text="🔍 EXTRACT ANY EMOJI ID & TAG", callback_data="adm_extract_emoji")
    )
    
    emoji_items = [
        # Main System UI Icons
        ("cbe", "CBE Bank Account", "🏦"),
        ("telebirr", "Telebirr Account", "📱"),
        ("diamond", "Logo / Diamond", "💎"),
        ("crown", "Crown / VIP", "👑"),
        ("money", "Money / Price", "💰"),
        ("box", "Box / Stock", "📦"),
        ("lightning", "Lightning / Delivery", "⚡"),
        ("wallet", "Wallet / Topup", "💳"),
        ("cart", "Cart / Shop", "🛒"),
        ("check", "Check / Success", "✅"),
        ("cross", "Cross / Failed", "❌"),
        ("fire", "Fire / Promo", "🔥"),
        # Brand Icons
        ("spotify", "Spotify", "🎧"),
        ("gemini", "Google Gemini", "✨"),
        ("netflix", "Netflix", "🎬"),
        ("chatgpt", "ChatGPT / OpenAI", "🤖"),
        ("canva", "Canva", "🎨"),
        ("youtube", "YouTube", "📺"),
    ]

    for key, label, fallback_icon in emoji_items:
        val = current_emojis.get(key, "")
        status_tag = "Active" if val else "Set"
        builder.row(
            InlineKeyboardButton(text=f"{label}: {status_tag}", callback_data=f"adm_set_emoji:{key}")
        )

    builder.row(
        InlineKeyboardButton(text="BACK TO DASHBOARD", callback_data="btn_admin"),
        InlineKeyboardButton(text="CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_delivery_mode_keyboard() -> InlineKeyboardMarkup:
    """Selectable delivery modes for product creation and editing."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⚡ AUTOMATIC (Instant Auto-Delivery)", callback_data="deliv_mode:AUTOMATIC")
    )
    builder.row(
        InlineKeyboardButton(text="👨‍💻 MANUAL (Admin Manual Delivery)", callback_data="deliv_mode:MANUAL")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 HYBRID (Auto with Manual Fallback)", callback_data="deliv_mode:HYBRID")
    )
    builder.row(
        InlineKeyboardButton(text="BACK", callback_data="adm_products"),
        InlineKeyboardButton(text="CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_admin_products_keyboard(pending_orders_count: int = 0) -> InlineKeyboardMarkup:
    """Admin Product Management main menu."""
    builder = InlineKeyboardBuilder()
    
    if pending_orders_count > 0:
        builder.row(
            InlineKeyboardButton(
                text=f"📦 PENDING MANUAL ORDERS ({pending_orders_count}) 🔔",
                callback_data="adm_pending_orders"
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="📦 VIEW PENDING MANUAL ORDERS",
                callback_data="adm_pending_orders"
            )
        )

    builder.row(
        InlineKeyboardButton(text="📦 VIEW & MANAGE ALL PRODUCTS", callback_data="adm_view_all_prods")
    )
    builder.row(
        InlineKeyboardButton(text="➕ ADD NEW MANUAL PRODUCT", callback_data="adm_add_manual_prod")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 SYNC PRODUCTS FROM AIVERSE", callback_data="adm_sync_prods")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 BACK TO DASHBOARD", callback_data="btn_admin"),
        InlineKeyboardButton(text="❌ CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_admin_product_list_keyboard(products: list) -> InlineKeyboardMarkup:
    """Interactive list of products for admin management with 4-digit ID display."""
    builder = InlineKeyboardBuilder()
    for p in products:
        s_id = str(p.get("service_id") or p.get("id") or "").strip()
        short_id = format_4digit_id(s_id)
        name = p.get("name", "Product")
        price = float(p.get("selling_price", 0.0))
        deliv = p.get("delivery_type", "AUTOMATIC")[:4]
        status_icon = "🟢" if p.get("is_enabled", True) else "🔴"
        btn_text = f"{status_icon} #{short_id} {name[:16]} | {price:,.0f} Birr [{deliv}]"
        builder.row(InlineKeyboardButton(text=btn_text, callback_data=f"adm_prod_view:{s_id}"))

    builder.row(
        InlineKeyboardButton(text="🔙 BACK TO PRODUCT MENU", callback_data="adm_products"),
        InlineKeyboardButton(text="❌ CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_admin_product_card_keyboard(service_id: str, is_enabled: bool, delivery_type: str = "AUTOMATIC") -> InlineKeyboardMarkup:
    """Interactive actions for a single product in Admin View with Stock Vault and Delivery Mode toggle."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📦 DIGITAL STOCK VAULT (70+ እቃዎች) ⚡", callback_data=f"adm_stock_pool:{service_id}")
    )
    builder.row(
        InlineKeyboardButton(text="✏️ EDIT NAME", callback_data=f"adm_name_init:{service_id}"),
        InlineKeyboardButton(text="💰 CHANGE PRICE", callback_data=f"adm_price_init:{service_id}")
    )
    builder.row(
        InlineKeyboardButton(text="📝 EDIT DESCRIPTION", callback_data=f"adm_desc_init:{service_id}"),
        InlineKeyboardButton(text=f"🚚 MODE: {delivery_type} ✏️", callback_data=f"adm_edit_deliv:{service_id}")
    )

    toggle_btn_text = "🔴 DISABLE (HIDE)" if is_enabled else "🟢 ENABLE (SHOW)"
    builder.row(
        InlineKeyboardButton(text="🎁 EDIT COMMISSION %", callback_data=f"adm_comm_init:{service_id}"),
        InlineKeyboardButton(text=toggle_btn_text, callback_data=f"adm_toggle_vis:{service_id}")
    )
    if str(service_id).upper().startswith("MANUAL_"):
        builder.row(
            InlineKeyboardButton(text="🗑️ DELETE PRODUCT", callback_data=f"adm_del_prod_confirm:{service_id}")
        )
    builder.row(
        InlineKeyboardButton(text="🔙 BACK TO PRODUCTS", callback_data="adm_view_all_prods"),
        InlineKeyboardButton(text="❌ CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_stock_pool_keyboard(service_id: str, available_count: int = 0, used_count: int = 0) -> InlineKeyboardMarkup:
    """Digital Stock Inventory Vault control buttons."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ BULK ADD 70+ ITEMS / እቃዎች አስገባ", callback_data=f"adm_stock_add:{service_id}")
    )
    builder.row(
        InlineKeyboardButton(text=f"🟢 VIEW AVAILABLE ({available_count})", callback_data=f"adm_stock_view_avail:{service_id}"),
        InlineKeyboardButton(text=f"🔴 VIEW SOLD ({used_count})", callback_data=f"adm_stock_view_used:{service_id}")
    )
    if used_count > 0:
        builder.row(
            InlineKeyboardButton(text="🧹 CLEAR SOLD ITEMS HISTORY", callback_data=f"adm_stock_clear_used:{service_id}")
        )
    builder.row(
        InlineKeyboardButton(text="🔙 BACK TO PRODUCT", callback_data=f"adm_prod_view:{service_id}"),
        InlineKeyboardButton(text="❌ CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_delete_product_confirm_keyboard(service_id: str) -> InlineKeyboardMarkup:
    """Confirmation keyboard for permanent product deletion."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🗑️ YES, DELETE PERMANENTLY", callback_data=f"adm_del_prod_exec:{service_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 BACK / CANCEL", callback_data=f"adm_prod_view:{service_id}")
    )
    return builder.as_markup()

def get_product_template_keyboard() -> InlineKeyboardMarkup:
    """Pre-set popular digital products template selection keyboard for Add Product."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🤖 ChatGPT Plus", callback_data="prod_tmpl:ChatGPT Plus 1 Month (Private)"),
        InlineKeyboardButton(text="🎧 Spotify Premium", callback_data="prod_tmpl:Spotify Premium 1 Month")
    )
    builder.row(
        InlineKeyboardButton(text="🎬 Netflix 4K UHD", callback_data="prod_tmpl:Netflix 4K UHD Profile"),
        InlineKeyboardButton(text="🎨 Canva Pro 1 Year", callback_data="prod_tmpl:Canva Pro 1 Year Private")
    )
    builder.row(
        InlineKeyboardButton(text="✨ Gemini Advanced", callback_data="prod_tmpl:Google Gemini Advanced 1 Month"),
        InlineKeyboardButton(text="✈️ Telegram Premium", callback_data="prod_tmpl:Telegram Premium 1 Month")
    )
    builder.row(
        InlineKeyboardButton(text="✍️ TYPE CUSTOM PRODUCT NAME", callback_data="prod_tmpl:custom")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 BACK", callback_data="adm_products"),
        InlineKeyboardButton(text="❌ CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_created_product_actions_keyboard(service_id: str) -> InlineKeyboardMarkup:
    """Action buttons shown immediately after creating a new product."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📦 VIEW ALL PRODUCTS LIST", callback_data="adm_view_all_prods"),
        InlineKeyboardButton(text="⚙️ MANAGE THIS PRODUCT", callback_data=f"adm_prod_view:{service_id}")
    )
    builder.row(
        InlineKeyboardButton(text="➕ ADD ANOTHER PRODUCT", callback_data="adm_add_manual_prod"),
        InlineKeyboardButton(text="🛒 VIEW IN SHOP", callback_data="btn_shop")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 BACK TO DASHBOARD", callback_data="btn_admin")
    )
    return builder.as_markup()

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Single back and cancel keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔙 BACK", callback_data="btn_main_menu"),
        InlineKeyboardButton(text="❌ CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

def get_back_cancel_keyboard(back_callback: str = "btn_main_menu", cancel_callback: str = "btn_cancel") -> InlineKeyboardMarkup:
    """Universal Back and Cancel inline navigation buttons."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔙 BACK", callback_data=back_callback),
        InlineKeyboardButton(text="❌ CANCEL", callback_data=cancel_callback)
    )
    return builder.as_markup()
