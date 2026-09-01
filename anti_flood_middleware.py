import time
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from config import ADMIN_IDS

logger = logging.getLogger(__name__)

# In-memory timestamp tracker for user rate-limiting
user_last_action: Dict[int, float] = {}
COOLDOWN_SECONDS = 0.2  # Ultra-fast responsive rate limit

class AntiFloodMiddleware(BaseMiddleware):
    """
    aiogram 3.x Middleware preventing extreme automated spam while keeping UI ultra-responsive.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
        else:
            return await handler(event, data)

        if not user or user.is_bot:
            return await handler(event, data)

        # Bypass rate limit for admins
        if user.id in ADMIN_IDS:
            return await handler(event, data)

        now = time.time()
        last_time = user_last_action.get(user.id, 0.0)

        if now - last_time < COOLDOWN_SECONDS:
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer()
                except Exception:
                    pass
            return

        user_last_action[user.id] = now
        return await handler(event, data)
