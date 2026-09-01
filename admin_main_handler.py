import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db_client import db
from config import DYNAMIC_EMOJI_CACHE, update_dynamic_emoji
from keyboards import (
    get_admin_keyboard,
    get_admin_products_keyboard,
    get_admin_emojis_keyboard,
    get_admin_referral_tiers_keyboard,
    get_admin_single_tier_keyboard,
    get_admin_services_keyboard,
    get_admin_discounts_keyboard,
    get_back_keyboard,
    get_back_cancel_keyboard
)

from i18n import REPLY_TEXT_ADMIN

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "noop")
async def noop_handler(query: CallbackQuery):
    """Handle noop buttons."""
    await query.answer("⚠️ This item is currently unavailable.", show_alert=True)

@router.message(Command("admin"))
@router.message(F.text.in_(REPLY_TEXT_ADMIN))
@router.callback_query(F.data == "btn_admin")
async def show_admin_dashboard(event: Message | CallbackQuery):
    """Display Admin Dashboard main menu with Maintenance Mode toggle."""
    if isinstance(event, CallbackQuery):
        await event.answer()
        user = event.from_user
        message = event.message
    else:
        user = event.from_user
        message = event

    role = await db.get_admin_role(user.id)
    if not role:
        denied_msg = "⛔ <b>ACCESS DENIED</b>\n\nYou do not have administrative privileges."
        if isinstance(event, CallbackQuery):
            await event.answer("⛔ Access Denied", show_alert=True)
        else:
            await message.answer(denied_msg, parse_mode="HTML", reply_markup=get_back_keyboard())
        return

    maint_mode = bool(await db.get_setting("maintenance_mode", False))
    maint_status = "🟢 ON (Under Maintenance)" if maint_mode else "🔴 OFF (Live & Active)"

    admin_text = (
        f"⚙️ <b>MELAX DIGITAL SHOP - ADMIN DASHBOARD</b>\n\n"
        f"👤 <b>Admin:</b> {user.first_name}\n"
        f"🔑 <b>Role:</b> <code>{role}</code>\n"
        f"🛠️ <b>Maintenance Mode:</b> {maint_status}\n\n"
        f"Select a module below:"
    )

    kb = get_admin_keyboard(maintenance_mode=maint_mode)

    if isinstance(event, CallbackQuery):
        try:
            await message.edit_text(text=admin_text, parse_mode="HTML", reply_markup=kb)
        except TelegramBadRequest:
            pass
    else:
        await message.answer(text=admin_text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "adm_toggle_maintenance")
async def toggle_maintenance_mode(query: CallbackQuery):
    """Toggle Maintenance Mode ON/OFF from Admin Panel."""
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    current = bool(await db.get_setting("maintenance_mode", False))
    new_mode = not current
    await db.update_setting("maintenance_mode", new_mode)

    status_alert = "🛠️ Maintenance Mode is now ENABLED! Users cannot place orders." if new_mode else "🟢 Maintenance Mode is now DISABLED! Bot is Live for all users."
    await query.answer(status_alert, show_alert=True)

    role = await db.get_admin_role(user.id)
    maint_status = "🟢 ON (Under Maintenance)" if new_mode else "🔴 OFF (Live & Active)"

    admin_text = (
        f"⚙️ <b>MELAX DIGITAL SHOP - ADMIN DASHBOARD</b>\n\n"
        f"👤 <b>Admin:</b> {user.first_name}\n"
        f"🔑 <b>Role:</b> <code>{role}</code>\n"
        f"🛠️ <b>Maintenance Mode:</b> {maint_status}\n\n"
        f"Select a module below:"
    )
    try:
        await query.message.edit_text(text=admin_text, parse_mode="HTML", reply_markup=get_admin_keyboard(maintenance_mode=new_mode))
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "adm_products")
async def show_admin_products_menu(query: CallbackQuery):
    """Display Products management submenu."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    text = (
        "🛍️ <b>PRODUCT MANAGEMENT</b>\n\n"
        "View, edit prices, edit descriptions, enable/disable, or sync products from AIVerse."
    )
    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=get_admin_products_keyboard())
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "adm_customers")
async def show_admin_customers(query: CallbackQuery):
    """Display Customers list with interactive individual action buttons."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    stats = await db.get_sales_analytics()
    total_users = stats.get("total_users", 0)

    recent_users = []
    if db.is_configured:
        res = db.client.table("users").select("telegram_id, first_name, username, is_banned, created_at").order("created_at", desc=True).limit(10).execute()
        if res.data:
            recent_users = res.data

    text = (
        f"👥 <b>CUSTOMER MANAGEMENT ({total_users} Total Registered)</b>\n\n"
        f"📊 <b>Total Registered Users:</b> <code>{total_users}</code>\n\n"
        f"<b>Recent Registered Customers:</b>\n"
    )

    for u in recent_users:
        banned_badge = "🚫" if u.get("is_banned") else "🟢"
        uname = f"@{u['username']}" if u.get("username") else "N/A"
        fname = u.get("first_name", "User")
        text += f"{banned_badge} <code>{u['telegram_id']}</code> | <b>{fname}</b> ({uname})\n"

    text += (
        "\n<i>Click individual buttons below to inspect user card, credit/deduct balance, or ban/unban user:</i>\n\n"
        "<b>Admin Commands:</b>\n"
        "• <code>/customer &lt;TELEGRAM_ID&gt;</code>\n"
        "• <code>/credit &lt;ID&gt; &lt;AMOUNT&gt; &lt;REASON&gt;</code>\n"
        "• <code>/debit &lt;ID&gt; &lt;AMOUNT&gt; &lt;REASON&gt;</code>\n"
        "• <code>/ban &lt;TELEGRAM_ID&gt;</code>\n"
        "• <code>/unban &lt;TELEGRAM_ID&gt;</code>"
    )

    builder = InlineKeyboardBuilder()
    
    for u in recent_users[:6]:
        tg_id = u["telegram_id"]
        name_short = (u.get("first_name") or "User")[:12]
        builder.row(
            InlineKeyboardButton(text=f"👤 {name_short} ({tg_id})", callback_data=f"adm_cust_view:{tg_id}"),
            InlineKeyboardButton(text="➕ Credit", callback_data=f"adm_cust_cred_init:{tg_id}")
        )

    builder.row(InlineKeyboardButton(text="🔍 Search Customer by ID", callback_data="adm_cust_search_prompt"))
    builder.row(
        InlineKeyboardButton(text="🔙 BACK TO DASHBOARD", callback_data="btn_admin"),
        InlineKeyboardButton(text="❌ CANCEL", callback_data="btn_cancel")
    )

    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=builder.as_markup())
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "adm_payments")
async def show_admin_payments(query: CallbackQuery):
    """Display dedicated payments menu separating Pending Queue from Processed History."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    pending_count = 0
    if db.is_configured:
        p_res = db.client.table("payments").select("id", count="exact").eq("status", "PENDING").execute()
        pending_count = p_res.count if p_res.count is not None else len(p_res.data or [])

    text = (
        f"💳 <b>PAYMENTS & DEPOSITS CENTER</b>\n\n"
        f"🟡 <b>Current Pending Requests:</b> <code>{pending_count}</code>\n\n"
        f"Select a dedicated view below:"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"🟡 PENDING DEPOSITS QUEUE ({pending_count})", callback_data="adm_pending_payments")
    )
    builder.row(
        InlineKeyboardButton(text="📜 PROCESSED PAYMENTS HISTORY", callback_data="adm_payments_history")
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ BANK & DEPOSIT SETTINGS", callback_data="adm_bank_settings")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 BACK TO DASHBOARD", callback_data="btn_admin"),
        InlineKeyboardButton(text="❌ CANCEL", callback_data="btn_cancel")
    )

    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=builder.as_markup())
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "adm_pending_payments")
async def show_pending_deposits_queue(query: CallbackQuery):
    """Isolated Dedicated Pending Deposits Queue (Never mixed with history logs)."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    pending_list = []
    if db.is_configured:
        res = db.client.table("payments").select("payment_id, amount, method, status, reference, created_at").eq("status", "PENDING").order("created_at", desc=True).limit(20).execute()
        if res.data:
            pending_list = res.data

    text = f"🟡 <b>PENDING DEPOSITS QUEUE ({len(pending_list)} Total Pending)</b>\n\n"

    if not pending_list:
        text += "🟢 <i>All deposits processed! No pending payments in queue.</i>\n"
    else:
        text += "<i>Review pending requests and click individual Approve/Reject buttons below:</i>\n\n"
        for p in pending_list:
            text += (
                f"▪️ <code>{p['payment_id']}</code> | "
                f"<b>{float(p['amount']):,.0f} Birr</b> | "
                f"{p.get('method', 'N/A')} | "
                f"<code>{p.get('created_at', '')[:16]}</code>\n"
                f"   Ref/Text: <code>{p.get('reference', 'N/A')[:40]}</code>\n\n"
            )

    builder = InlineKeyboardBuilder()
    for p in pending_list[:6]:
        pid = p["payment_id"]
        builder.row(
            InlineKeyboardButton(text=f"✅ Approve {pid}", callback_data=f"dep_appr:{pid}"),
            InlineKeyboardButton(text=f"❌ Reject {pid}", callback_data=f"dep_rej:{pid}")
        )

    builder.row(
        InlineKeyboardButton(text="🔙 BACK TO PAYMENTS", callback_data="adm_payments"),
        InlineKeyboardButton(text="❌ CANCEL", callback_data="btn_cancel")
    )

    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=builder.as_markup())
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "adm_payments_history")
async def show_processed_payments_history(query: CallbackQuery):
    """Isolated Dedicated Processed Payments History (Approved/Rejected/Refunded)."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    history_list = []
    if db.is_configured:
        res = db.client.table("payments").select("payment_id, amount, method, status, reference, created_at").neq("status", "PENDING").order("created_at", desc=True).limit(20).execute()
        if res.data:
            history_list = res.data

    text = f"📜 <b>PROCESSED PAYMENTS HISTORY ({len(history_list)} Recent)</b>\n\n"

    if not history_list:
        text += "<i>No processed payments history found.</i>\n"
    else:
        for p in history_list:
            status_icon = "🟢" if p.get("status") == "APPROVED" else ("🔴" if p.get("status") == "REJECTED" else "🔄")
            text += (
                f"{status_icon} <code>{p['payment_id']}</code> | "
                f"<b>{float(p['amount']):,.0f} Birr</b> | "
                f"{p.get('method', 'N/A')} | "
                f"<b>{p.get('status')}</b>\n"
                f"   Date: <code>{p.get('created_at', '')[:16]}</code>\n\n"
            )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔙 BACK TO PAYMENTS", callback_data="adm_payments"),
        InlineKeyboardButton(text="❌ CANCEL", callback_data="btn_cancel")
    )

    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=builder.as_markup())
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "adm_orders")
async def show_admin_orders(query: CallbackQuery):
    """Display recent orders overview."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    orders = []
    if db.is_configured:
        res = db.client.table("orders").select("melax_order_id, product_name, selling_price, status, created_at").order("created_at", desc=True).limit(15).execute()
        if res.data:
            orders = res.data

    text = f"📦 <b>ORDERS HISTORY ({len(orders)} Recent)</b>\n\n"

    if not orders:
        text += "<i>No orders placed yet.</i>"
    else:
        for o in orders:
            status_icon = {"SUCCESS": "✅", "PENDING": "🟡", "FAILED": "❌", "REFUNDED": "🔄"}.get(o.get("status", ""), "⚪")
            text += (
                f"{status_icon} <code>{o['melax_order_id']}</code> | "
                f"{o['product_name']} | "
                f"<code>{float(o['selling_price']):,.0f} Birr</code>\n"
            )

    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="btn_admin", cancel_callback="btn_cancel"))
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "adm_broadcast")
async def show_admin_broadcast(query: CallbackQuery):
    """Show broadcast instructions."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    text = (
        "📢 <b>BROADCAST ENGINE</b>\n\n"
        "Send an announcement to ALL registered users.\n\n"
        "<b>Usage:</b>\n"
        "<code>/broadcast Your announcement message here</code>\n\n"
        "<b>Example:</b>\n"
        "<code>/broadcast 🔥 New AI Accounts added! Check our shop now.</code>"
    )
    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="btn_admin", cancel_callback="btn_cancel"))
    except TelegramBadRequest:
        pass

class AdminEmojiStates(StatesGroup):
    waiting_for_emoji_input = State()
    waiting_for_extraction = State()
    waiting_for_unicode_symbol = State()
    waiting_for_replacement_anim = State()

@router.callback_query(F.data == "adm_emojis_manager")
async def show_emojis_manager(query: CallbackQuery):
    """Admin Custom Animated Emoji Manager Dashboard."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    from config import DYNAMIC_EMOJIS, update_dynamic_emoji
    # Load active emojis from DB/Cache
    current_emojis = {}
    for key in DYNAMIC_EMOJIS.keys():
        db_val = await db.get_setting(f"custom_emoji_{key}", DYNAMIC_EMOJIS.get(key, {}).get("id", ""))
        if db_val:
            current_emojis[key] = str(db_val)
            update_dynamic_emoji(key, str(db_val))

    text = (
        f"🎨 <b>100% CUSTOM ANIMATED EMOJI CUSTOMIZER 💎</b>\n\n"
        f"<i>Customize EVERY single icon in the bot with your favorite Telegram animated emojis!</i>\n\n"
        f"Click on any section icon or brand below to set or update its animated emoji by simply sending the emoji from your Telegram keyboard:"
    )

    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=get_admin_emojis_keyboard(current_emojis))
    except TelegramBadRequest:
        pass

@router.callback_query(F.data.startswith("adm_set_emoji:"))
async def init_set_brand_emoji(query: CallbackQuery, state: FSMContext):
    """Prompt admin to send custom animated emoji for a brand or UI element."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    brand = query.data.split(":", 1)[1]
    await state.update_data(target_brand=brand)
    await state.set_state(AdminEmojiStates.waiting_for_emoji_input)

    brand_titles = {
        "diamond": "💎 Logo / Diamond",
        "crown": "👑 Crown / VIP",
        "money": "💰 Money / Price",
        "box": "📦 Box / Stock",
        "lightning": "⚡ Lightning / Delivery",
        "wallet": "💳 Wallet / Topup",
        "cart": "🛒 Cart / Shop",
        "check": "✅ Check / Success",
        "cross": "❌ Cross / Failed",
        "fire": "🔥 Fire / Promo",
        "spotify": "🟢 Spotify",
        "gemini": "✨ Google Gemini",
        "netflix": "🎬 Netflix",
        "chatgpt": "🤖 ChatGPT / OpenAI",
        "canva": "🎨 Canva",
        "youtube": "📺 YouTube",
    }

    title = brand_titles.get(brand, brand.capitalize())

    prompt = (
        f"🎨 <b>SET CUSTOM ANIMATED EMOJI FOR {title.upper()}</b>\n\n"
        f"👉 <b>Please send the Custom Animated Emoji</b> from your Telegram Premium keyboard (or send its numeric Emoji ID):\n\n"
        f"<i>To cancel or return, click the buttons below:</i>"
    )

    await query.message.edit_text(
        text=prompt,
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard(back_callback="adm_emojis_manager", cancel_callback="btn_cancel")
    )

@router.message(AdminEmojiStates.waiting_for_emoji_input)
async def process_admin_emoji_input(message: Message, state: FSMContext, bot: Bot):
    """Capture custom emoji ID from message entities or numeric text and save to DB."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    data = await state.get_data()
    brand = data.get("target_brand", "diamond")
    await state.clear()

    emoji_id = None
    emoji_char = "✨"

    if message.entities:
        for entity in message.entities:
            if entity.type == "custom_emoji" and hasattr(entity, "custom_emoji_id") and entity.custom_emoji_id:
                emoji_id = str(entity.custom_emoji_id)
                emoji_char = message.text[entity.offset:entity.offset + entity.length]
                break

    if not emoji_id:
        raw_text = message.text.strip()
        if raw_text.isdigit():
            emoji_id = raw_text

    if not emoji_id:
        await message.answer("⚠️ Could not detect a valid Custom Emoji ID. Please send an animated emoji from your Telegram Premium panel:", reply_markup=get_back_cancel_keyboard(back_callback="adm_emojis_manager", cancel_callback="btn_cancel"))
        return

    # Persist to Supabase and update in-memory cache
    await db.update_setting(f"custom_emoji_{brand}", emoji_id)
    update_dynamic_emoji(brand, emoji_id)

    success_text = (
        f"✅ <b>ANIMATED EMOJI SAVED SUCCESSFULLY! 💎</b>\n\n"
        f"🏷️ <b>Item / Brand:</b> <code>{brand.upper()}</code>\n"
        f"🆔 <b>Emoji ID:</b> <code>{emoji_id}</code>\n"
        f"✨ <b>Live Preview:</b> <tg-emoji emoji-id=\"{emoji_id}\">{emoji_char}</tg-emoji>\n\n"
        f"<i>All matching sections in the shop, cards, receipts and logs will now automatically display this animated emoji!</i>"
    )

    await message.answer(text=success_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_emojis_manager", cancel_callback="btn_cancel"))

@router.callback_query(F.data == "adm_extract_emoji")
async def init_extract_emoji(query: CallbackQuery, state: FSMContext):
    """Prompt admin to send any custom animated emoji to extract its ID & HTML tag."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    await state.set_state(AdminEmojiStates.waiting_for_extraction)
    prompt = (
        f"🔍 <b>CUSTOM ANIMATED EMOJI EXTRACTOR 💎</b>\n\n"
        f"👉 <b>Please send ANY Custom Animated Emoji</b> from your Telegram Premium keyboard (or multiple emojis):\n\n"
        f"<i>The bot will instantly output its exact Emoji ID, live animation, and ready-to-copy HTML tag!</i>"
    )
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_emojis_manager", cancel_callback="btn_cancel"))

@router.message(AdminEmojiStates.waiting_for_extraction)
async def process_emoji_extraction(message: Message, state: FSMContext):
    """Extract and display Telegram Custom Emoji IDs and tags on sent emoji."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    await state.clear()
    custom_emojis = []
    if message.entities:
        for entity in message.entities:
            if entity.type == "custom_emoji" and hasattr(entity, "custom_emoji_id") and entity.custom_emoji_id:
                emoji_char = message.text[entity.offset:entity.offset + entity.length]
                custom_emojis.append({"char": emoji_char, "id": str(entity.custom_emoji_id)})

    if not custom_emojis:
        await message.answer("⚠️ No custom animated emoji detected in your message. Please send an emoji from your Telegram Premium keyboard:", reply_markup=get_back_cancel_keyboard(back_callback="adm_emojis_manager", cancel_callback="btn_cancel"))
        return

    res_text = (
        f"✨ <b>CUSTOM ANIMATED EMOJI DETECTED ({len(custom_emojis)} Found) 💎</b>\n\n"
        f"<i>Here are the exact Telegram Custom Emoji IDs and ready-to-use HTML tags:</i>\n\n"
    )

    for idx, e in enumerate(custom_emojis, 1):
        res_text += (
            f"<b>{idx}. Live Preview:</b> <tg-emoji emoji-id=\"{e['id']}\">{e['char']}</tg-emoji>\n"
            f"   🆔 <b>Emoji ID:</b> <code>{e['id']}</code>\n"
            f"   🏷️ <b>HTML Tag:</b> <code>&lt;tg-emoji emoji-id=\"{e['id']}\"&gt;{e['char']}&lt;/tg-emoji&gt;</code>\n\n"
        )

    res_text += (
        f"💡 <b>How to use:</b>\n"
        f"• Copy the <b>HTML Tag</b> and paste it directly in any product name or description!\n"
        f"• Or paste the <b>Emoji ID</b> in the customizer above to animate that button!"
    )

    await message.answer(text=res_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_emojis_manager", cancel_callback="btn_cancel"))

@router.callback_query(F.data == "adm_map_unicode")
async def init_map_unicode(query: CallbackQuery, state: FSMContext):
    """Prompt admin to enter any unicode emoji they want to replace with an animated one."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    await state.set_state(AdminEmojiStates.waiting_for_unicode_symbol)
    prompt = (
        f"🔄 <b>UNIVERSAL UNICODE TO ANIMATED MAPPER 💎</b>\n\n"
        f"👉 <b>Step 1:</b> Please send the <b>Unicode Emoji</b> or keyword you want to replace\n"
        f"<i>(e.g. 🏦, 📱, 💰, 💎, ⚡, 💳, 🛒, 📦, 🎁, ❓, 👑, ⭐, 🎧, 🎬, 🤖, etc.)</i>:"
    )
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_emojis_manager", cancel_callback="btn_cancel"))

@router.message(AdminEmojiStates.waiting_for_unicode_symbol)
async def process_unicode_selection(message: Message, state: FSMContext):
    """Receive unicode emoji symbol and ask for replacement animated emoji."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    symbol = message.text.strip()
    if not symbol:
        await message.answer("⚠️ Please send an emoji symbol:")
        return

    await state.update_data(chosen_symbol=symbol)
    await state.set_state(AdminEmojiStates.waiting_for_replacement_anim)

    prompt = (
        f"🎯 <b>Target Emoji Selected:</b> <code>{symbol}</code>\n\n"
        f"👉 <b>Step 2:</b> Now please send the <b>Custom Animated Emoji</b> from your Telegram Premium keyboard to replace <code>{symbol}</code> with:"
    )
    await message.answer(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_emojis_manager", cancel_callback="btn_cancel"))

@router.message(AdminEmojiStates.waiting_for_replacement_anim)
async def process_replacement_animated_emoji(message: Message, state: FSMContext, bot: Bot):
    """Extract animated emoji ID and map it to target unicode symbol."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    data = await state.get_data()
    chosen_symbol = data.get("chosen_symbol", "💎")
    await state.clear()

    emoji_id = None
    emoji_char = "✨"

    if message.entities:
        for entity in message.entities:
            if entity.type == "custom_emoji" and hasattr(entity, "custom_emoji_id") and entity.custom_emoji_id:
                emoji_id = str(entity.custom_emoji_id)
                emoji_char = message.text[entity.offset:entity.offset + entity.length]
                break

    if not emoji_id:
        raw_text = message.text.strip()
        if raw_text.isdigit():
            emoji_id = raw_text

    if not emoji_id:
        await message.answer("⚠️ Could not detect a valid Custom Emoji ID. Please send an animated emoji from your Telegram Premium keyboard:", reply_markup=get_back_cancel_keyboard(back_callback="adm_emojis_manager", cancel_callback="btn_cancel"))
        return

    from config import UNICODE_EMOJI_MAP, update_dynamic_emoji
    key = UNICODE_EMOJI_MAP.get(chosen_symbol, chosen_symbol.lower())

    await db.update_setting(f"custom_emoji_{key}", emoji_id)
    update_dynamic_emoji(key, emoji_id)
    update_dynamic_emoji(chosen_symbol, emoji_id)

    success_text = (
        f"✅ <b>EMOJI REPLACED & SAVED SUCCESSFULLY! 💎</b>\n\n"
        f"▪️ <b>Target Emoji:</b> <code>{chosen_symbol}</code>\n"
        f"▪️ <b>Mapped Section Key:</b> <code>{key}</code>\n"
        f"▪️ <b>Emoji ID:</b> <code>{emoji_id}</code>\n"
        f"▪️ <b>New Animated Preview:</b> <tg-emoji emoji-id=\"{emoji_id}\">{emoji_char}</tg-emoji>\n\n"
        f"<i>Every time <code>{chosen_symbol}</code> appears across all bot cards, receipts, and menus, it will now automatically animate!</i>"
    )
    await message.answer(text=success_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_emojis_manager", cancel_callback="btn_cancel"))

# =========================================================================
# ADMIN REFERRAL REWARD TIERS & CLAIMS MANAGEMENT
# =========================================================================

class AdminRefTierStates(StatesGroup):
    waiting_for_tier_invites = State()
    waiting_for_tier_name = State()
    waiting_for_claim_key = State()
    waiting_for_new_tier_name = State()
    waiting_for_new_tier_invites = State()

@router.callback_query(F.data == "adm_ref_tiers")
async def show_admin_referral_tiers(query: CallbackQuery):
    """Display Referral Reward Tiers & Claims management menu."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    tiers = await db.get_referral_tiers()
    pending_claims = await db.get_pending_referral_claims()

    text = (
        f"🎁 <b>REFERRAL REWARDS & MILESTONE TIERS MANAGER 💎</b>\n\n"
        f"<i>Configure reward items (Spotify, Gemini, Netflix, Wallet Birr, etc.), set required invites, or add new reward milestones:</i>\n\n"
        f"📋 <b>Pending Reward Claims:</b> <code>{len(pending_claims)} Waiting</code>\n"
        f"🏆 <b>Configured Reward Tiers:</b> <code>{len(tiers)} Active</code>\n\n"
        f"Click a tier below to change its reward name/invites, or click 'Pending Claims' to fulfill customer rewards:"
    )

    try:
        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=get_admin_referral_tiers_keyboard(tiers, len(pending_claims))
        )
    except Exception:
        pass

@router.callback_query(F.data.startswith("adm_view_tier:"))
async def view_single_referral_tier(query: CallbackQuery):
    """Display details and customization options for a single reward tier."""
    await query.answer()
    tier_id = query.data.split(":", 1)[1]
    tiers = await db.get_referral_tiers()
    target = next((t for t in tiers if t.get("id") == tier_id), None)
    if not target:
        await query.answer("Tier not found", show_alert=True)
        return

    text = (
        f"🎁 <b>REWARD TIER SETTINGS</b>\n\n"
        f"▪️ <b>Reward Name:</b> <code>{target.get('reward_name')}</code>\n"
        f"▪️ <b>Required Invites:</b> <code>{target.get('invites')} Invites</code>\n"
        f"▪️ <b>Reward Type:</b> <code>{target.get('reward_type', 'DIGITAL_ACCOUNT')}</code>\n\n"
        f"<i>Select an action below to customize what the reward is or change required invites:</i>"
    )
    await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=get_admin_single_tier_keyboard(tier_id))

@router.callback_query(F.data.startswith("adm_edit_tier_name:"))
async def init_edit_tier_name(query: CallbackQuery, state: FSMContext):
    """Prompt admin for new reward name."""
    await query.answer()
    tier_id = query.data.split(":", 1)[1]
    await state.update_data(target_tier_id=tier_id)
    await state.set_state(AdminRefTierStates.waiting_for_tier_name)

    prompt = (
        f"✏️ <b>CHANGE REWARD NAME</b>\n\n"
        f"👉 Send the <b>New Reward Name</b> (e.g. <code>Spotify Premium 1 Month</code>, <code>Google Gemini Pro</code>, <code>Netflix 4K UHD</code>, <code>50 Birr Wallet Balance</code>):"
    )
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback=f"adm_view_tier:{tier_id}", cancel_callback="btn_cancel"))

@router.message(AdminRefTierStates.waiting_for_tier_name)
async def process_edit_tier_name(message: Message, state: FSMContext):
    """Save new reward name."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    new_name = message.text.strip()
    if not new_name:
        await message.answer("⚠️ Please send a valid reward name:")
        return

    data = await state.get_data()
    tier_id = data.get("target_tier_id", "")
    await state.clear()

    await db.update_referral_tier_details(tier_id=tier_id, reward_name=new_name)
    await message.answer(f"✅ Reward name updated to: <b>{new_name}</b>!", parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_ref_tiers", cancel_callback="btn_cancel"))

@router.callback_query(F.data.startswith("adm_edit_tier_inv:"))
@router.callback_query(F.data.startswith("adm_edit_tier:"))
async def init_edit_tier_invites(query: CallbackQuery, state: FSMContext):
    """Prompt admin to edit required invites for a tier."""
    await query.answer()
    tier_id = query.data.split(":", 1)[1]
    tiers = await db.get_referral_tiers()
    target = next((t for t in tiers if t.get("id") == tier_id), None)
    if not target:
        await query.answer("Tier not found", show_alert=True)
        return

    await state.update_data(target_tier_id=tier_id)
    await state.set_state(AdminRefTierStates.waiting_for_tier_invites)

    prompt = (
        f"🔢 <b>CHANGE REQUIRED INVITES: {target.get('reward_name')}</b>\n\n"
        f"Current: <code>{target.get('invites')} Invites</code>\n\n"
        f"👉 Send the <b>New Number of Required Invites</b> (e.g. 15, 20, 25, 30):"
    )
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback=f"adm_view_tier:{tier_id}", cancel_callback="btn_cancel"))

@router.message(AdminRefTierStates.waiting_for_tier_invites)
async def process_edit_tier_invites(message: Message, state: FSMContext):
    """Save new invite threshold for tier."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ Please send a valid positive number of invites:")
        return

    new_inv = int(text)
    data = await state.get_data()
    tier_id = data.get("target_tier_id", "")
    await state.clear()

    await db.update_referral_tier_details(tier_id=tier_id, invites=new_inv)
    await message.answer(f"✅ Required invites for tier updated to <b>{new_inv} Invites</b>!", parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_ref_tiers", cancel_callback="btn_cancel"))

@router.callback_query(F.data.startswith("adm_del_tier:"))
async def delete_referral_tier_handler(query: CallbackQuery):
    """Delete a referral reward tier."""
    await query.answer()
    tier_id = query.data.split(":", 1)[1]
    await db.delete_referral_tier(tier_id)
    await query.answer("🗑️ Reward tier deleted!", show_alert=True)
    await show_admin_referral_tiers(query)

@router.callback_query(F.data == "adm_add_tier")
async def init_add_tier(query: CallbackQuery, state: FSMContext):
    """Prompt admin to create a new reward tier."""
    await query.answer()
    await state.set_state(AdminRefTierStates.waiting_for_new_tier_name)

    prompt = (
        f"➕ <b>ADD NEW REFERRAL REWARD TIER</b>\n\n"
        f"👉 <b>Step 1:</b> Send the <b>Reward Name / Product</b> (e.g. <code>Netflix Premium 1 Month</code>, <code>Canva Pro</code>, <code>100 Birr Wallet Bonus</code>):"
    )
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_ref_tiers", cancel_callback="btn_cancel"))

@router.message(AdminRefTierStates.waiting_for_new_tier_name)
async def process_new_tier_name(message: Message, state: FSMContext):
    """Save new tier name and ask for required invites."""
    name = message.text.strip()
    if not name:
        await message.answer("⚠️ Please send a valid reward name:")
        return

    await state.update_data(new_tier_name=name)
    await state.set_state(AdminRefTierStates.waiting_for_new_tier_invites)

    prompt = (
        f"🎯 <b>Reward:</b> <code>{name}</code>\n\n"
        f"👉 <b>Step 2:</b> Send the <b>Required Number of Invites</b> (e.g. <code>10</code>, <code>20</code>, <code>30</code>):"
    )
    await message.answer(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_ref_tiers", cancel_callback="btn_cancel"))

@router.message(AdminRefTierStates.waiting_for_new_tier_invites)
async def process_new_tier_invites(message: Message, state: FSMContext):
    """Save new tier in database."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ Please send a valid positive number of invites:")
        return

    inv = int(text)
    data = await state.get_data()
    name = data.get("new_tier_name", "Reward")
    await state.clear()

    await db.add_referral_tier(reward_name=name, invites=inv)
    success_text = (
        f"🎉 <b>NEW REFERRAL REWARD TIER CREATED! 🎁💎</b>\n\n"
        f"▪️ <b>Reward:</b> {name}\n"
        f"▪️ <b>Required Invites:</b> {inv} Invites\n\n"
        f"<i>Customers who reach {inv} successful referrals can now claim this reward!</i>"
    )
    await message.answer(text=success_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_ref_tiers", cancel_callback="btn_cancel"))

@router.callback_query(F.data == "adm_view_claims")
async def show_pending_referral_claims(query: CallbackQuery):
    """View and fulfill pending referral claims."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    claims = await db.get_pending_referral_claims()
    if not claims:
        await query.message.edit_text(
            "📋 <b>PENDING REWARD CLAIMS</b>\n\nThere are no pending reward claims waiting for fulfillment.",
            parse_mode="HTML",
            reply_markup=get_back_cancel_keyboard(back_callback="adm_ref_tiers", cancel_callback="btn_cancel")
        )
        return

    builder = InlineKeyboardBuilder()
    for c in claims[:10]:
        builder.row(
            InlineKeyboardButton(
                text=f"✅ Fulfill {c.get('tier_name')} (ID: {c.get('telegram_id')})",
                callback_data=f"adm_fulfill_claim:{c.get('claim_id')}"
            )
        )
    builder.row(
        InlineKeyboardButton(text="BACK", callback_data="adm_ref_tiers"),
        InlineKeyboardButton(text="CANCEL", callback_data="btn_cancel")
    )

    text = f"📋 <b>PENDING REWARD CLAIMS ({len(claims)})</b>\n\nSelect a claim below to provide credentials/key and send to the customer:"
    await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("adm_fulfill_claim:"))
async def init_fulfill_claim(query: CallbackQuery, state: FSMContext):
    """Prompt admin to enter the delivery credentials for a claim."""
    await query.answer()
    claim_id = query.data.split(":", 1)[1]
    await state.update_data(target_claim_id=claim_id)
    await state.set_state(AdminRefTierStates.waiting_for_claim_key)

    prompt = (
        f"🔑 <b>FULFILL REWARD CLAIM</b>\n\n"
        f"Claim ID: <code>{claim_id}</code>\n\n"
        f"👉 Please send the <b>Account Credentials / Key / Link</b> to deliver to the customer:"
    )
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_view_claims", cancel_callback="btn_cancel"))

@router.message(AdminRefTierStates.waiting_for_claim_key)
async def process_fulfill_claim_input(message: Message, state: FSMContext, bot: Bot):
    """Deliver key to user and mark claim resolved."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    data = await state.get_data()
    claim_id = data.get("target_claim_id", "")
    key_text = message.text.strip()
    await state.clear()

    success, msg, target = await db.resolve_referral_claim(claim_id, "DELIVERED", delivery_code=key_text)
    if not success or not target:
        await message.answer(f"⚠️ {msg}", reply_markup=get_back_cancel_keyboard(back_callback="adm_ref_tiers", cancel_callback="btn_cancel"))
        return

    # Notify customer directly via Bot
    cust_tg_id = target.get("telegram_id")
    tier_name = target.get("tier_name", "Reward")
    if cust_tg_id:
        try:
            from config import emo
            cust_text = (
                f"🎉 <b>YOUR REFERRAL REWARD IS READY! {emo('sparkle', '✨')}{emo('diamond', '💎')}</b>\n\n"
                f"🎁 <b>Reward:</b> {tier_name}\n"
                f"🔑 <b>Account Credentials / Access Code:</b>\n"
                f"<code>{key_text}</code>\n\n"
                f"<i>Thank you for inviting your friends to MELAX DIGITAL SHOP!</i>"
            )
            await bot.send_message(chat_id=cust_tg_id, text=cust_text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Could not message customer about claim fulfillment: {e}")

    await message.answer(f"✅ Reward claim <code>{claim_id}</code> fulfilled and delivered to customer!", parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_ref_tiers", cancel_callback="btn_cancel"))

# =========================================================================
# MASTER BOT SERVICES ON / OFF CONTROLS
# =========================================================================

@router.callback_query(F.data == "adm_services_manager")
async def show_services_manager(query: CallbackQuery):
    """Display Master Services ON / OFF Switchboard."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    srv_status = await db.get_all_services_status()

    text = (
        f"🎛️ <b>MASTER SERVICES ON / OFF CONTROLS 💎</b>\n\n"
        f"<i>Toggle any feature or service in real time across the entire bot:</i>\n\n"
        f"▪️ <b>Digital Shop:</b> {'🟢 Active' if srv_status.get('shop') else '🔴 Disabled'}\n"
        f"▪️ <b>Instant Deposits:</b> {'🟢 Active' if srv_status.get('deposits') else '🔴 Disabled'}\n"
        f"▪️ <b>Referral Rewards:</b> {'🟢 Active' if srv_status.get('referrals') else '🔴 Disabled'}\n"
        f"▪️ <b>Promo Codes:</b> {'🟢 Active' if srv_status.get('discounts') else '🔴 Disabled'}\n"
        f"▪️ <b>Customer Support:</b> {'🟢 Active' if srv_status.get('support') else '🔴 Disabled'}\n"
        f"▪️ <b>Force Join:</b> {'🟢 Active' if srv_status.get('force_join') else '🔴 Disabled'}\n"
        f"▪️ <b>Maintenance Mode:</b> {'🔴 Active (Locked)' if srv_status.get('maintenance') else '🟢 Normal (Open)'}\n\n"
        f"<i>Click any button below to toggle that service ON or OFF instantly:</i>"
    )

    try:
        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=get_admin_services_keyboard(srv_status)
        )
    except Exception:
        pass

@router.callback_query(F.data.startswith("adm_toggle_srv:"))
async def toggle_service_handler(query: CallbackQuery):
    """Toggle a specific service on or off."""
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("Unauthorized", show_alert=True)
        return

    srv_key = query.data.split(":", 1)[1]

    if srv_key == "maintenance":
        current = bool(await db.get_setting("maintenance_mode", False))
        new_val = not current
        await db.update_setting("maintenance_mode", new_val)
        status_word = "ACTIVATED (Bot Locked)" if new_val else "DISABLED (Bot Open)"
        await query.answer(f"🛠️ System Maintenance: {status_word}!", show_alert=True)
    else:
        current = await db.get_service_status(srv_key, True)
        new_val = not current
        await db.set_service_status(srv_key, new_val)
        status_word = "ENABLED 🟢" if new_val else "DISABLED 🔴"
        await query.answer(f"Service {srv_key.upper()} is now {status_word}!", show_alert=True)

    await show_services_manager(query)

# =========================================================================
# ADMIN DISCOUNTS, PROMO CODES & FLASH SALES MANAGEMENT
# =========================================================================

class AdminDiscountStates(StatesGroup):
    waiting_for_flash_percent = State()
    waiting_for_promo_code = State()
    waiting_for_promo_val = State()
    waiting_for_promo_max = State()

@router.callback_query(F.data == "adm_discounts")
async def show_admin_discounts(query: CallbackQuery):
    """Display Discounts, Promo Codes & Flash Sales management dashboard."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    codes = await db.get_promo_codes()
    flash_percent = await db.get_global_discount_percent()

    text = (
        f"🎟️ <b>DISCOUNTS, PROMO CODES & FLASH SALES MANAGER 💎</b>\n\n"
        f"🔥 <b>Global Flash Sale:</b> <code>{flash_percent:.0f}% OFF</code> (Store-wide)\n"
        f"🎟️ <b>Active Promo Codes:</b> <code>{len(codes)} Created</code>\n\n"
        f"<i>Create discount vouchers for marketing campaigns, or toggle a store-wide flash sale percentage across all items:</i>"
    )

    try:
        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=get_admin_discounts_keyboard(codes, flash_percent)
        )
    except Exception:
        pass

@router.callback_query(F.data == "adm_set_flash_sale")
async def init_set_flash_sale(query: CallbackQuery, state: FSMContext):
    """Prompt admin to set store-wide flash sale percentage."""
    await query.answer()
    await state.set_state(AdminDiscountStates.waiting_for_flash_percent)

    prompt = (
        f"🔥 <b>SET GLOBAL STORE-WIDE FLASH SALE</b>\n\n"
        f"👉 Please send the <b>Discount Percentage</b> to apply across all products\n"
        f"<i>(Send <code>0</code> to turn OFF flash sales, or e.g. <code>10</code> for 10% OFF, <code>20</code> for 20% OFF)</i>:"
    )
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_discounts", cancel_callback="btn_cancel"))

@router.message(AdminDiscountStates.waiting_for_flash_percent)
async def process_flash_sale_percent(message: Message, state: FSMContext):
    """Save flash sale percentage."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    text = message.text.strip().replace("%", "")
    try:
        pct = float(text)
        if pct < 0 or pct > 90:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Please enter a valid percentage between 0 and 90:")
        return

    await state.clear()
    await db.set_global_discount_percent(pct)

    status_str = f"🟢 <b>ACTIVE ({pct:.0f}% OFF all items)</b>" if pct > 0 else "🔴 <b>OFF (0%)</b>"
    await message.answer(f"✅ Global Store-Wide Flash Sale set to: {status_str}", parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_discounts", cancel_callback="btn_cancel"))

@router.callback_query(F.data == "adm_add_promo")
async def init_add_promo(query: CallbackQuery, state: FSMContext):
    """Prompt admin for new promo code name."""
    await query.answer()
    await state.set_state(AdminDiscountStates.waiting_for_promo_code)

    prompt = (
        f"➕ <b>CREATE NEW PROMO CODE</b>\n\n"
        f"👉 <b>Step 1:</b> Send the <b>Code Name</b> (e.g. <code>MELAX20</code>, <code>WELCOME10</code>, <code>SAVE50</code>):"
    )
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_discounts", cancel_callback="btn_cancel"))

@router.message(AdminDiscountStates.waiting_for_promo_code)
async def process_promo_code_name(message: Message, state: FSMContext):
    """Save code name and ask for discount value."""
    code = message.text.strip().upper()
    if not code:
        await message.answer("⚠️ Please send a valid code name:")
        return

    await state.update_data(new_promo_code=code)
    await state.set_state(AdminDiscountStates.waiting_for_promo_val)

    prompt = (
        f"🎯 <b>Promo Code:</b> <code>{code}</code>\n\n"
        f"👉 <b>Step 2:</b> Send the <b>Discount Percentage</b> (e.g. <code>15</code> for 15% OFF, <code>20</code> for 20% OFF):"
    )
    await message.answer(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_discounts", cancel_callback="btn_cancel"))

@router.message(AdminDiscountStates.waiting_for_promo_val)
async def process_promo_code_val(message: Message, state: FSMContext):
    """Save discount value and prompt admin for maximum user limit (ለስንት ሰው)."""
    text = message.text.strip().replace("%", "")
    try:
        val = float(text)
        if val <= 0 or val > 90:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Please enter a valid discount percentage between 1 and 90:")
        return

    data = await state.get_data()
    code = data.get("new_promo_code", "PROMO")
    await state.update_data(new_promo_val=val)
    await state.set_state(AdminDiscountStates.waiting_for_promo_max)

    prompt = (
        f"🎯 <b>Promo Code:</b> <code>{code}</code> (<b>{val:.0f}% OFF</b>)\n\n"
        f"👉 <b>Step 3:</b> Send the <b>Maximum Number of Users / Uses (ለስንት ሰው / ለስንት ግዢ እንዲሰራ ይፈልጋሉ?)</b>\n"
        f"<i>(e.g. Type <code>10</code> for 10 people, <code>25</code> for 25 people, <code>50</code> for 50 people, <code>100</code>)</i>:"
    )
    await message.answer(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_discounts", cancel_callback="btn_cancel"))

@router.message(AdminDiscountStates.waiting_for_promo_max)
async def process_promo_code_max_users(message: Message, state: FSMContext):
    """Save max users limit and create promo code."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ Please send a valid positive number of users (e.g. 20, 50, 100):")
        return

    max_uses = int(text)
    data = await state.get_data()
    code = data.get("new_promo_code", "PROMO")
    val = data.get("new_promo_val", 10.0)
    await state.clear()

    await db.create_or_update_promo_code(code=code, discount_type="PERCENT", value=val, max_uses=max_uses)
    success_text = (
        f"🎉 <b>PROMO CODE CREATED SUCCESSFULLY! 🎟️💎</b>\n\n"
        f"▪️ <b>Code Name:</b> <code>{code}</code>\n"
        f"▪️ <b>Discount:</b> <code>{val:.0f}% OFF</code>\n"
        f"▪️ <b>User Limit:</b> <code>ለ {max_uses} ሰው ብቻ (Max {max_uses} Uses)</code>\n\n"
        f"<i>Customers can now type this code during checkout to claim the discount!</i>"
    )
    await message.answer(text=success_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_discounts", cancel_callback="btn_cancel"))

@router.callback_query(F.data.startswith("adm_del_promo:"))
async def delete_promo_code_handler(query: CallbackQuery):
    """Delete a promo code."""
    await query.answer()
    code = query.data.split(":", 1)[1]
    await db.delete_promo_code(code)
    await query.answer(f"🗑️ Promo code {code} deleted!", show_alert=True)
    await show_admin_discounts(query)
