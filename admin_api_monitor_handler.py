import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from db_client import db
from api_client import api_client
from keyboards import get_admin_keyboard

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "adm_api_mon")
async def show_api_monitor(query: CallbackQuery):
    """Admin-only API Health & Supplier Balance Monitor."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    me_info = await api_client.get_me()
    products = await api_client.get_products()
    supplier_bal = me_info.get("wallet_balance", "N/A")

    status_badge = "🟢 Connected & Healthy" if isinstance(supplier_bal, (int, float)) or (isinstance(supplier_bal, str) and supplier_bal != "N/A") else "🔴 Error"

    monitor_text = (
        f"🔌 <b>AIVERSE HUB API MONITOR</b>\n\n"
        f"▪️ <b>Status:</b> {status_badge}\n"
        f"▪️ <b>Supplier Balance:</b> <code>${supplier_bal}</code>\n"
        f"▪️ <b>Live Products Count:</b> <code>{len(products)}</code>\n"
        f"▪️ <b>Rate Limit:</b> 3 requests/sec (Async Token Bucket Active)\n\n"
        f"<i>Note: Customers never see supplier cost or supplier balance.</i>"
    )

    await query.message.edit_text(text=monitor_text, parse_mode="HTML", reply_markup=get_admin_keyboard())
