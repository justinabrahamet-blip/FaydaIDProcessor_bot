import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from db_client import db

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, bot: Bot):
    """Command: /broadcast <ANNOUNCEMENT_MESSAGE> preserving custom animated emojis and HTML formatting."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        return

    html_content = message.html_text
    parts = html_content.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("⚠️ Usage: <code>/broadcast Welcome to MELAX DIGITAL SHOP! New products added.</code>", parse_mode="HTML")
        return

    announcement = parts[1].strip()
    
    user_ids = []
    if db.is_configured:
        res = db.client.table("users").select("telegram_id").eq("is_banned", False).execute()
        if res.data:
            user_ids = [r["telegram_id"] for r in res.data]

    status_msg = await message.answer(f"🚀 <i>Broadcasting message to {len(user_ids)} users...</i>", parse_mode="HTML")
    sent, failed = 0, 0

    for uid in user_ids:
        try:
            await bot.send_message(
                chat_id=uid,
                text=f"📢 <b>ANNOUNCEMENT FROM MELAX DIGITAL SHOP</b>\n\n{announcement}",
                parse_mode="HTML"
            )
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ <b>BROADCAST COMPLETED</b>\n\n"
        f"▪️ Sent Successfully: <code>{sent}</code>\n"
        f"▪️ Blocked / Failed: <code>{failed}</code>",
        parse_mode="HTML"
    )
