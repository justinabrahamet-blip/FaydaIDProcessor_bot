import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from db_client import db
from keyboards import get_orders_keyboard, get_back_keyboard

from config import emo, animate_text
from i18n import t, REPLY_TEXT_ORDERS

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("orders"))
@router.message(F.text.in_(REPLY_TEXT_ORDERS))
@router.callback_query(F.data == "btn_orders")
async def show_user_orders(event: Message | CallbackQuery):
    """Display user's purchase history with in-place admin edit options."""
    if isinstance(event, CallbackQuery):
        await event.answer()
        user = event.from_user
        message = event.message
    else:
        user = event.from_user
        message = event

    is_admin = (await db.get_admin_role(user.id)) is not None
    u_db = await db.get_user_by_telegram_id(user.id)
    user_lang = u_db.get("language_code", "am") if u_db else "am"
    kb = get_orders_keyboard(is_admin=is_admin, lang=user_lang)

    if not u_db:
        await message.answer("🔴 User account not found.", reply_markup=kb)
        return

    orders = await db.get_user_orders(u_db["id"], limit=10)

    from config import emo
    if not orders:
        no_orders_text = f"{emo('box', '📦')} <b>MY ORDERS HISTORY</b>\n\nYou have not placed any orders yet."
        if isinstance(event, CallbackQuery):
            await message.edit_text(no_orders_text, parse_mode="HTML", reply_markup=kb)
        else:
            await message.answer(no_orders_text, parse_mode="HTML", reply_markup=kb)
        return

    text = f"{emo('box', '📦')} <b>MY ORDERS HISTORY ({len(orders)} Recent) {emo('diamond', '💎')}</b>\n\n"

    for ord_rec in orders:
        price = float(ord_rec.get("selling_price", 0.0))
        delivered = ord_rec.get("delivered_products", "N/A")
        text += (
            f"▫️ <b>Product:</b> {ord_rec['product_name']}\n"
            f"   <b>Order ID:</b> <code>{ord_rec['melax_order_id']}</code>\n"
            f"   {emo('money', '💰')} <b>Paid:</b> <code>{price:,.2f} Birr</code> | <b>Date:</b> {ord_rec['created_at'][:10]}\n"
            f"   🔑 <b>Code/Key:</b> <code>{delivered}</code>\n\n"
        )

    if isinstance(event, CallbackQuery):
        await message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
    else:
        await message.answer(text=text, parse_mode="HTML", reply_markup=kb)
