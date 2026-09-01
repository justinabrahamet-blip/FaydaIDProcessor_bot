import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from config import SUPPORT_USERNAME, CBE_NO, emo, animate_text
from keyboards import get_support_keyboard, get_back_keyboard
from i18n import t, REPLY_TEXT_SUPPORT

from db_client import db

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("support"))
@router.message(F.text.in_(REPLY_TEXT_SUPPORT))
@router.callback_query(F.data == "btn_support")
async def show_support_guide(event: Message | CallbackQuery):
    """Display customer support and user guide with in-place admin edit options."""
    if isinstance(event, CallbackQuery):
        await event.answer()
        user = event.from_user
        message = event.message
    else:
        user = event.from_user
        message = event

    is_admin = (await db.get_admin_role(user.id)) is not None
    user_lang = await db.get_user_language(user.id)

    if not (await db.get_service_status("support", True)) and not is_admin:
        off_msg = (
            "🎧 <b>CUSTOMER SUPPORT DESK</b>\n\n"
            "⚠️ የደንበኞች አገልግሎት ዴስክ ለጊዜው ተዘግቷል (Temporarily Offline)。\n"
            f"<i>ለአስቸኳይ ጥያቄዎች እባክዎን በቀጥታ በ @{SUPPORT_USERNAME} ያግኙን።</i>"
        )
        if isinstance(event, CallbackQuery):
            await message.edit_text(off_msg, parse_mode="HTML", reply_markup=get_back_keyboard())
        else:
            await message.answer(off_msg, parse_mode="HTML", reply_markup=get_back_keyboard())
        return

    from config import emo
    support_text = (
        f"{emo('support', '❓')} <b>SUPPORT & USER GUIDE</b> {emo('diamond', '💎')}\n\n"
        f"Welcome to <b>MELAX DIGITAL SHOP</b>!\n\n"
        f"📖 <b>How to Buy Digital Products:</b>\n"
        f"1. Go to <b>{emo('wallet', '💳')} Wallet</b> and send your payment to CBE Account: <code>{CBE_NO}</code>\n"
        f"2. Copy-paste the official <b>mbreciept.cbe.com.et/...</b> receipt link SMS in the chat.\n"
        f"3. Your wallet balance will be credited automatically in 1 second! {emo('lightning', '⚡')}\n"
        f"4. Go to <b>{emo('cart', '🛒')} Digital Products</b>, select your desired item, and click <b>BUY NOW</b>.\n"
        f"5. Your digital product code/link will be delivered instantly! {emo('sparkle', '✨')}\n\n"
        f"☎️ <b>Customer Support Administrator:</b>\n"
        f"Username: @{SUPPORT_USERNAME}\n\n"
        f"<i>We are available 24/7 to assist you!</i>"
    )

    kb = get_support_keyboard(is_admin=is_admin, lang=user_lang, support_username=SUPPORT_USERNAME)
    if isinstance(event, CallbackQuery):
        await message.edit_text(text=support_text, parse_mode="HTML", reply_markup=kb)
    else:
        await message.answer(text=support_text, parse_mode="HTML", reply_markup=kb)
