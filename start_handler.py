from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db_client import db
from config import ADMIN_IDS, SALES_CHANNEL_ID, emo, animate_text
from force_join_middleware import check_force_join, resolve_channel_links, SALES_CHANNEL_LINK, LOGS_CHANNEL_LINK
from keyboards import (
    get_main_menu_keyboard,
    get_main_reply_keyboard,
    get_force_join_keyboard,
    get_profile_keyboard,
    get_back_keyboard
)
from i18n import t, REPLY_TEXT_PROFILE, REPLY_TEXT_CHANNEL, REPLY_TEXT_PROOF

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, state: FSMContext):
    """Handle /start command with referral link support and clear FSM state."""
    await state.clear()
    user = message.from_user
    args = message.text.split(maxsplit=1)
    
    referrer_telegram_id = None
    if len(args) > 1:
        ref_payload = args[1].replace("ref_", "").strip()
        if ref_payload.isdigit():
            referrer_telegram_id = int(ref_payload)

    u_db = await db.get_or_create_user(
        telegram_id=user.id,
        username=user.username or "",
        first_name=user.first_name or "User",
        last_name=user.last_name or "",
        referrer_telegram_id=referrer_telegram_id
    )

    bot_info = await bot.get_me()
    is_admin = (await db.get_admin_role(user.id)) is not None
    balance = u_db.get("wallet_balance", 0.00)
    user_lang = await db.get_user_language(user.id)

    sales_link, logs_link = await resolve_channel_links(bot)

    welcome_title = await db.get_ui_text("welcome_title", user_lang)
    welcome_body = await db.get_ui_text("welcome_body", user_lang, name=user.first_name, balance=balance)
    welcome_text = animate_text(f"{welcome_title}\n\n{welcome_body}")

    # Send persistent bottom reply keyboard in preferred language
    await message.answer(animate_text(t("menu_loaded", user_lang)), parse_mode="HTML", reply_markup=get_main_reply_keyboard(is_admin, sales_link, logs_link, lang=user_lang))

    # Send inline main menu card
    await message.answer(
        text=welcome_text,
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(bot_info.username, is_admin, lang=user_lang)
    )

@router.message(F.text == "📢 Our Channel")
@router.message(F.text.in_(REPLY_TEXT_CHANNEL))
async def reply_btn_sales_channel(message: Message, bot: Bot):
    """Handle Reply Keyboard 'Our Channel' button - instant 1-tap redirect card."""
    sales_link, _ = await resolve_channel_links(bot)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📢 OPEN OFFICIAL CHANNEL ↗️", url=sales_link))
    card = animate_text(
        f"💎 <b>MELAX DIGITAL OFFICIAL CHANNEL</b> ⚡\n\n"
        f"✨ Tap the button below to open our official channel for latest updates & discounts! 👇"
    )
    await message.answer(card, parse_mode="HTML", reply_markup=builder.as_markup())

@router.message(F.text.in_(REPLY_TEXT_PROOF))
async def reply_btn_proof_channel(message: Message, bot: Bot):
    """Handle Reply Keyboard 'Proof Channel' button - instant 1-tap redirect card."""
    _, logs_link = await resolve_channel_links(bot)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📜 OPEN PROOF & LOGS CHANNEL ↗️", url=logs_link))
    card = animate_text(
        f"🛡️ <b>PROOF & DELIVERY LOGS CHANNEL</b> ⚡\n\n"
        f"✨ Tap the button below to open our live proof channel for verified deliveries! 👇"
    )
    await message.answer(card, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(F.data == "check_join_again")
async def callback_check_join(query: CallbackQuery, bot: Bot):
    """Re-verify force join channel membership: Approve or Reject."""
    await query.answer()
    user = query.from_user
    is_joined = await check_force_join(bot, user.id)

    if is_joined:
        bot_info = await bot.get_me()
        u_db = await db.get_or_create_user(user.id, user.username or "", user.first_name or "")
        balance = u_db.get("wallet_balance", 0.00)
        is_admin = (await db.get_admin_role(user.id)) is not None
        user_lang = await db.get_user_language(user.id)

        sales_link, logs_link = await resolve_channel_links(bot)

        welcome_text = animate_text(
            f"✅ <b>ቻናሎቹን በተሳካ ሁኔታ ተቀላቅለዋል! 🎉</b>\n\n"
            f"💎 <b>MELAX DIGITAL SHOP</b> ⚡\n\n"
            f"👋 Welcome <b>{user.first_name}</b>! ✨\n\n"
            f"💰 <b>Your Balance:</b> <code>{balance:,.2f} Birr</code> 💳\n\n"
            f"👑 <i>Choose an option below to start:</i>"
        )

        await query.message.answer(animate_text(t("menu_loaded", user_lang)), parse_mode="HTML", reply_markup=get_main_reply_keyboard(is_admin, sales_link, logs_link, lang=user_lang))

        try:
            await query.message.edit_text(
                text=welcome_text,
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard(bot_info.username, is_admin, lang=user_lang)
            )
        except TelegramBadRequest:
            await query.message.answer(
                text=welcome_text,
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard(bot_info.username, is_admin, lang=user_lang)
            )
    else:
        await query.answer(
            "❌ ገና ቻናሎቹን አልተቀላቀሉም!\n\nእባክዎ ከላይ ያሉትን ቻናሎች ይቀላቀሉና እንደገና ይሞክሩ።",
            show_alert=True
        )

@router.callback_query(F.data == "btn_main_menu")
async def callback_main_menu(query: CallbackQuery, bot: Bot, state: FSMContext):
    """Return to main menu repeatedly without freezing."""
    await query.answer()
    await state.clear()
    user = query.from_user
    bot_info = await bot.get_me()
    u_db = await db.get_or_create_user(user.id, user.username or "", user.first_name or "")
    balance = u_db.get("wallet_balance", 0.00)
    is_admin = (await db.get_admin_role(user.id)) is not None
    user_lang = await db.get_user_language(user.id)

    menu_text = animate_text(
        f"💎 <b>MELAX DIGITAL SHOP - MAIN MENU</b> ⚡\n\n"
        f"💰 <b>Your Balance:</b> <code>{balance:,.2f} Birr</code> ✨\n\n"
        f"👑 <i>Choose an option below:</i>"
    )

    try:
        await query.message.edit_text(
            text=menu_text,
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(bot_info.username, is_admin, lang=user_lang)
        )
    except TelegramBadRequest:
        pass

@router.callback_query(F.data.in_({"btn_cancel", "btn_cancel_fsm", "cancel_process"}))
async def callback_cancel_process(query: CallbackQuery, bot: Bot, state: FSMContext):
    """Universal Cancel Button Handler: clears active state and returns cleanly."""
    await query.answer("❌ Process cancelled.", show_alert=False)
    await state.clear()
    user = query.from_user
    bot_info = await bot.get_me()
    u_db = await db.get_or_create_user(user.id, user.username or "", user.first_name or "")
    balance = u_db.get("wallet_balance", 0.00)
    is_admin = (await db.get_admin_role(user.id)) is not None
    user_lang = await db.get_user_language(user.id)

    menu_text = animate_text(
        f"💎 <b>MELAX DIGITAL SHOP - MAIN MENU</b> ⚡\n\n"
        f"❌ <i>Process was cancelled.</i>\n\n"
        f"💰 <b>Your Balance:</b> <code>{balance:,.2f} Birr</code> ✨\n\n"
        f"👑 <i>Choose an option below:</i>"
    )

    try:
        await query.message.edit_text(
            text=menu_text,
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(bot_info.username, is_admin, lang=user_lang)
        )
    except TelegramBadRequest:
        pass

@router.message(Command("profile"))
@router.message(F.text.in_(REPLY_TEXT_PROFILE))
@router.callback_query(F.data == "btn_profile")
async def callback_profile(event: Message | CallbackQuery):
    """Display customer profile with animated emoji badges and Language Switcher."""
    if isinstance(event, CallbackQuery):
        await event.answer()
        user = event.from_user
        message = event.message
    else:
        user = event.from_user
        message = event

    u_db = await db.get_or_create_user(user.id, user.username or "", user.first_name or "")
    balance = u_db.get("wallet_balance", 0.00) if u_db else 0.00
    is_vip = u_db.get("is_vip", False) if u_db else False
    user_lang = await db.get_user_language(user.id)

    orders = await db.get_user_orders(u_db["id"], limit=10) if u_db and "id" in u_db else []
    order_count = len(orders)

    tier_str = "👑 VIP Customer" if is_vip else "🟢 Standard Customer"
    lang_str = "🇪🇹 አማርኛ (Amharic)" if user_lang == "am" else "🇬🇧 English"

    profile_text = animate_text(
        f"👤 <b>CUSTOMER PROFILE (MY PROFILE)</b> 💎\n\n"
        f"▪️ <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"▪️ <b>Name:</b> {user.first_name}\n"
        f"▪️ <b>Username:</b> @{user.username if user.username else 'N/A'}\n"
        f"▪️ <b>Account Tier:</b> {tier_str}\n"
        f"▪️ <b>Wallet Balance:</b> <code>{balance:,.2f} Birr</code> 💳\n"
        f"▪️ <b>Total Orders:</b> <code>{order_count}</code> 📦\n"
        f"▪️ <b>Language / ቋንቋ:</b> <code>{lang_str}</code>\n\n"
        f"<i>Tap below to switch between Amharic and English anytime:</i>"
    )

    is_admin = (await db.get_admin_role(user.id)) is not None
    if isinstance(event, CallbackQuery):
        try:
            await message.edit_text(text=profile_text, parse_mode="HTML", reply_markup=get_profile_keyboard(user_lang, is_admin=is_admin))
        except TelegramBadRequest:
            pass
    else:
        await message.answer(text=profile_text, parse_mode="HTML", reply_markup=get_profile_keyboard(user_lang, is_admin=is_admin))

@router.callback_query(F.data.in_({"btn_toggle_lang", "toggle_language"}))
async def callback_toggle_language(query: CallbackQuery, bot: Bot):
    """Toggle language between Amharic (am) and English (en)."""
    user = query.from_user
    cur_lang = await db.get_user_language(user.id)
    new_lang = "en" if cur_lang == "am" else "am"
    await db.set_user_language(user.id, new_lang)

    new_lang_name = "English 🇬🇧" if new_lang == "en" else "አማርኛ 🇪🇹"
    await query.answer(f"🌐 ቋንቋ ተቀይሯል / Language set to {new_lang_name}!", show_alert=True)

    sales_link, logs_link = await resolve_channel_links(bot)
    is_admin = (await db.get_admin_role(user.id)) is not None

    # Update bottom persistent keyboard in new language
    await query.message.answer(
        animate_text(f"🌐 <b>ቋንቋው ወደ {new_lang_name} ተቀይሯል! ⚡\nLanguage updated to {new_lang_name}!</b>"),
        parse_mode="HTML",
        reply_markup=get_main_reply_keyboard(is_admin, sales_link, logs_link, lang=new_lang)
    )

    # Refresh Profile card
    await callback_profile(query)
