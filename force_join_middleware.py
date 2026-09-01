import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, Message, CallbackQuery, Update
from config import SALES_CHANNEL_ID, LOGS_CHANNEL_ID, ADMIN_IDS
from db_client import db

logger = logging.getLogger(__name__)

SALES_CHANNEL_LINK = "https://t.me/melaxdigital"
LOGS_CHANNEL_LINK = "https://t.me/melaxlogs"

async def check_force_join(bot: Bot, user_id: int) -> bool:
    """Check if user is a member of the official sales channel."""
    if not (await db.get_service_status("force_join", True)):
        return True
    if not SALES_CHANNEL_ID:
        return True
    if user_id in ADMIN_IDS:
        return True
    try:
        if await db.get_admin_role(user_id):
            return True
    except Exception:
        pass
    try:
        member = await bot.get_chat_member(chat_id=SALES_CHANNEL_ID, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.warning(f"Channel check bypassed for {user_id}: {e}")
        return True

_LINK_CACHE = {"sales": SALES_CHANNEL_LINK, "logs": LOGS_CHANNEL_LINK, "cached": False}

async def resolve_channel_links(bot: Bot) -> tuple:
    """Resolve real invite links for both channels with instant in-memory cache."""
    global _LINK_CACHE
    if _LINK_CACHE["cached"]:
        return _LINK_CACHE["sales"], _LINK_CACHE["logs"]

    sales_link = SALES_CHANNEL_LINK
    logs_link = LOGS_CHANNEL_LINK
    if SALES_CHANNEL_ID:
        try:
            chat = await bot.get_chat(SALES_CHANNEL_ID)
            if chat.username:
                sales_link = f"https://t.me/{chat.username}"
            elif chat.invite_link:
                sales_link = chat.invite_link
        except Exception:
            pass
    if LOGS_CHANNEL_ID:
        try:
            chat2 = await bot.get_chat(LOGS_CHANNEL_ID)
            if chat2.username:
                logs_link = f"https://t.me/{chat2.username}"
            elif chat2.invite_link:
                logs_link = chat2.invite_link
        except Exception:
            pass
    _LINK_CACHE = {"sales": sales_link, "logs": logs_link, "cached": True}
    return sales_link, logs_link

class ForceJoinMiddleware(BaseMiddleware):
    """
    aiogram 3.x Middleware enforcing mandatory channel membership.
    Registered on dp.message and dp.callback_query (NOT dp.update).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        bot: Bot = data.get("bot")

        # Extract user from the actual event type
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
        else:
            return await handler(event, data)

        if not user or user.is_bot:
            return await handler(event, data)

        # Always allow "check_join_again" callback through
        if isinstance(event, CallbackQuery) and event.data == "check_join_again":
            return await handler(event, data)

        # Check banned status
        try:
            u_db = await db.get_user_by_telegram_id(user.id)
            if u_db and u_db.get("is_banned"):
                if isinstance(event, Message):
                    await event.answer(
                        "🚫 <b>Your account has been restricted.</b>\nContact support: @mr_melaku",
                        parse_mode="HTML"
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚫 Account restricted. Contact @mr_melaku", show_alert=True)
                return
        except Exception as e:
            logger.error(f"User DB check error: {e}")

        # Check Force Join
        is_joined = await check_force_join(bot, user.id)

        if not is_joined:
            sales_link, logs_link = await resolve_channel_links(bot)

            from keyboards import get_force_join_keyboard
            kb = get_force_join_keyboard(sales_link, logs_link)

            force_join_msg = (
                "📢 <b>ቻናሎቻችንን ይቀላቀሉ!</b>\n\n"
                "MELAX DIGITAL SHOP ቦትን ለመጠቀም የሚከተሉትን ቻናሎች መቀላቀል ግዴታ ነው!\n\n"
                "ከዚህ በታች ያሉትን አዝራሮች ተጫኑ። ከተቀላቀሉ በኋላ <b>✅ ተቀላቅያለሁ</b> የሚለውን ይጫኑ።"
            )

            if isinstance(event, Message):
                await event.answer(force_join_msg, parse_mode="HTML", reply_markup=kb)
            elif isinstance(event, CallbackQuery):
                await event.answer("❌ መጀመሪያ ቻናሎቻችንን ይቀላቀሉ!", show_alert=True)
                try:
                    await event.message.answer(force_join_msg, parse_mode="HTML", reply_markup=kb)
                except Exception:
                    pass
            return

        return await handler(event, data)
