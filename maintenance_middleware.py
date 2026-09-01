"""
Global System Maintenance Middleware for MELAX DIGITAL SHOP Telegram Bot.
Intercepts ALL Message & CallbackQuery events when maintenance mode is active,
allowing ONLY Admins through while presenting a rich localized maintenance banner to all other users.
"""

import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from config import ADMIN_IDS, emo
from db_client import db

logger = logging.getLogger(__name__)

class MaintenanceMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        maint_mode = bool(await db.get_setting("maintenance_mode", False))
        if not maint_mode:
            return await handler(event, data)

        # Extract user ID
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if not user_id:
            return await handler(event, data)

        # Check if user is an Admin
        if user_id in ADMIN_IDS or (await db.get_admin_role(user_id)):
            return await handler(event, data)

        # Non-admin user intercepted during maintenance
        maint_banner = (
            f"{emo('lightning', '🛠️')} <b>ቦቱ በጊዜያዊ ጥገና ላይ ነው (SYSTEM UNDER MAINTENANCE) ⚡</b>\n\n"
            f"የሲስተም ማሻሻያ እና የደህንነት ፍተሻ እየተደረገ ስለሆነ ለጊዜው አገልግሎት አቋርጠናል። እባክዎን ጥቂት ቆይተው እንደገና ይሞክሩ።\n\n"
            f"<i>We are performing routine maintenance. All services will be restored shortly. Thank you for your patience!</i>"
        )

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔄 እንደገና ሞክር / Refresh", callback_data="btn_refresh_maint")
        )

        if isinstance(event, CallbackQuery):
            try:
                await event.answer("🛠️ ቦቱ በጊዜያዊ ጥገና ላይ ነው (Under Maintenance) ⚡", show_alert=True)
                if event.message:
                    await event.message.edit_text(maint_banner, parse_mode="HTML", reply_markup=builder.as_markup())
            except Exception:
                pass
            return

        if isinstance(event, Message):
            try:
                await event.answer(maint_banner, parse_mode="HTML", reply_markup=builder.as_markup())
            except Exception:
                pass
            return
