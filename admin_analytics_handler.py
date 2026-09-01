from aiogram import Router, F
from aiogram.types import CallbackQuery
from db_client import db
from keyboards import get_admin_keyboard

router = Router()

@router.callback_query(F.data.in_({"adm_overview", "adm_sales"}))
async def show_sales_analytics(query: CallbackQuery):
    """Display revenue, supplier cost, and net gross profit metrics."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    stats = await db.get_sales_analytics()

    text = (
        f"📊 <b>BUSINESS OVERVIEW & ANALYTICS</b>\n\n"
        f"💰 <b>Total Revenue:</b> <code>{stats['revenue']:,.2f} Birr</code>\n"
        f"💵 <b>Supplier Cost:</b> <code>{stats['supplier_cost']:,.2f} Birr</code>\n"
        f"📈 <b>Gross Profit:</b> <code>{stats['profit']:,.2f} Birr</code>\n\n"
        f"👥 <b>Total Customers:</b> <code>{stats['total_users']}</code>\n"
        f"📦 <b>Completed Orders:</b> <code>{stats['total_orders']}</code>\n"
        f"📥 <b>Pending Deposits:</b> <code>{stats['pending_payments']}</code>"
    )

    await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=get_admin_keyboard())
