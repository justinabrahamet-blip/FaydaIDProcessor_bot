import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db_client import db
from channel_logger import log_to_channel
from security_util import sanitize_input

logger = logging.getLogger(__name__)
router = Router()

class AdminCustomerStates(StatesGroup):
    waiting_for_credit_amount = State()
    waiting_for_debit_amount = State()
    waiting_for_search_id = State()

def get_admin_customer_card_keyboard(telegram_id: int, is_banned: bool = False) -> InlineKeyboardMarkup:
    """Inline action buttons for customer management card with Back/Cancel."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Credit Balance", callback_data=f"adm_cust_cred_init:{telegram_id}"),
        InlineKeyboardButton(text="➖ Deduct Balance", callback_data=f"adm_cust_deb_init:{telegram_id}")
    )
    
    ban_btn_text = "🔓 UNBAN CUSTOMER" if is_banned else "🚫 BAN CUSTOMER"
    ban_cb_data = f"adm_cust_unban:{telegram_id}" if is_banned else f"adm_cust_ban:{telegram_id}"
    
    builder.row(
        InlineKeyboardButton(text=ban_btn_text, callback_data=ban_cb_data)
    )
    builder.row(
        InlineKeyboardButton(text="🔙 BACK TO CUSTOMERS", callback_data="adm_customers"),
        InlineKeyboardButton(text="❌ CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

@router.message(Command("customer"))
async def cmd_customer_info(message: Message):
    """Command: /customer <TELEGRAM_ID> - View customer details with interactive balance credit/debit buttons."""
    admin_user = message.from_user
    if not (await db.get_admin_role(admin_user.id)):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("⚠️ Usage: <code>/customer 123456789</code>", parse_mode="HTML")
        return

    target_id = int(args[1].strip())
    u = await db.get_user_by_telegram_id(target_id)

    if not u:
        await message.answer(f"⚠️ Customer <code>{target_id}</code> not found.", parse_mode="HTML")
        return

    balance = float(u.get("wallet_balance", 0.00))
    is_banned = u.get("is_banned", False)
    is_vip = u.get("is_vip", False)
    ban_status = "🚫 Banned" if is_banned else "🟢 Active"
    vip_status = "⭐ VIP" if is_vip else "Standard"

    orders = await db.get_user_orders(u["id"], limit=5)
    order_count = len(orders) if orders else 0

    text = (
        f"👤 <b>CUSTOMER DETAILS & WALLET CONTROL</b>\n\n"
        f"▪️ <b>Telegram ID:</b> <code>{target_id}</code>\n"
        f"▪️ <b>Name:</b> {u.get('first_name', 'N/A')}\n"
        f"▪️ <b>Username:</b> @{u.get('username', 'N/A')}\n"
        f"▪️ <b>Status:</b> {ban_status}\n"
        f"▪️ <b>Type:</b> {vip_status}\n"
        f"💰 <b>Wallet Balance:</b> <code>{balance:,.2f} Birr</code>\n"
        f"📦 <b>Recent Orders:</b> <code>{order_count}</code>\n"
        f"📅 <b>Joined:</b> <code>{u.get('created_at', 'N/A')[:10]}</code>\n\n"
        f"<i>Click buttons below to credit balance, deduct balance, or ban/unban user:</i>"
    )

    await message.answer(text=text, parse_mode="HTML", reply_markup=get_admin_customer_card_keyboard(target_id, is_banned))

@router.callback_query(F.data.startswith("adm_cust_view:"))
async def callback_view_customer_info(query: CallbackQuery):
    """Callback: 1-click view customer details card from Users List."""
    await query.answer()
    admin_user = query.from_user
    if not (await db.get_admin_role(admin_user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    target_id = int(query.data.split(":", 1)[1])
    u = await db.get_user_by_telegram_id(target_id)
    if not u:
        await query.answer("⚠️ Customer not found", show_alert=True)
        return

    balance = float(u.get("wallet_balance", 0.00))
    is_banned = u.get("is_banned", False)
    is_vip = u.get("is_vip", False)
    ban_status = "🚫 Banned" if is_banned else "🟢 Active"
    vip_status = "⭐ VIP" if is_vip else "Standard"

    orders = await db.get_user_orders(u["id"], limit=5)
    order_count = len(orders) if orders else 0

    text = (
        f"👤 <b>CUSTOMER DETAILS & WALLET CONTROL</b>\n\n"
        f"▪️ <b>Telegram ID:</b> <code>{target_id}</code>\n"
        f"▪️ <b>Name:</b> {u.get('first_name', 'N/A')}\n"
        f"▪️ <b>Username:</b> @{u.get('username', 'N/A')}\n"
        f"▪️ <b>Status:</b> {ban_status}\n"
        f"▪️ <b>Type:</b> {vip_status}\n"
        f"💰 <b>Wallet Balance:</b> <code>{balance:,.2f} Birr</code>\n"
        f"📦 <b>Recent Orders:</b> <code>{order_count}</code>\n"
        f"📅 <b>Joined:</b> <code>{u.get('created_at', 'N/A')[:10]}</code>\n\n"
        f"<i>Click buttons below to credit balance, deduct balance, or ban/unban user:</i>"
    )

    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=get_admin_customer_card_keyboard(target_id, is_banned))
    except Exception:
        await query.message.answer(text=text, parse_mode="HTML", reply_markup=get_admin_customer_card_keyboard(target_id, is_banned))

@router.callback_query(F.data.startswith("adm_cust_cred_init:"))
async def init_credit_customer(query: CallbackQuery, state: FSMContext):
    """Initiate customer balance credit prompt via inline button."""
    await query.answer()
    admin_user = query.from_user
    role = await db.get_admin_role(admin_user.id)
    if role not in ("OWNER", "MANAGER", "FINANCE"):
        await query.answer("⛔ Access Denied: Requires FINANCE/OWNER role", show_alert=True)
        return

    target_id = int(query.data.split(":", 1)[1])
    u = await db.get_user_by_telegram_id(target_id)
    if not u:
        await query.message.edit_text("⚠️ Customer not found.")
        return

    await state.update_data(target_telegram_id=target_id, target_uuid=u["id"], target_name=u.get("first_name", "Customer"))
    await state.set_state(AdminCustomerStates.waiting_for_credit_amount)

    prompt = (
        f"➕ <b>CREDIT CUSTOMER WALLET BALANCE</b>\n\n"
        f"👤 <b>Customer:</b> {u.get('first_name')} (<code>{target_id}</code>)\n"
        f"💰 <b>Current Balance:</b> <code>{float(u.get('wallet_balance', 0.0)):,.2f} Birr</code>\n\n"
        f"👉 <b>Please type and send the amount to ADD (e.g. 500):</b>"
    )
    from keyboards import get_back_cancel_keyboard
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback=f"adm_cust_view:{target_id}", cancel_callback="btn_cancel"))

@router.message(AdminCustomerStates.waiting_for_credit_amount)
async def process_credit_amount(message: Message, state: FSMContext, bot: Bot):
    """Execute customer balance credit."""
    admin_user = message.from_user
    data = await state.get_data()
    target_id = data["target_telegram_id"]
    target_uuid = data["target_uuid"]
    target_name = data["target_name"]
    await state.clear()

    try:
        amount = float(message.text.strip().replace(",", ""))
        if amount <= 0:
            raise ValueError()
    except ValueError:
        from keyboards import get_back_cancel_keyboard
        await message.answer("⚠️ Invalid numeric amount. Must be positive.", reply_markup=get_back_cancel_keyboard(back_callback=f"adm_cust_view:{target_id}", cancel_callback="btn_cancel"))
        return

    res = await db.atomic_credit_wallet(
        user_id=target_uuid,
        amount=amount,
        tx_type="ADMIN_CREDIT",
        reference="ADMIN-CREDIT",
        description="Admin manual credit",
        created_by=str(admin_user.id)
    )

    if res.get("success"):
        new_bal = res.get("balance_after", 0.00)
        from keyboards import get_back_cancel_keyboard
        await message.answer(
            f"✅ <b>WALLET BALANCE CREDITED!</b>\n\n"
            f"👤 <b>Customer:</b> {target_name} (<code>{target_id}</code>)\n"
            f"➕ <b>Added:</b> <code>+{amount:,.2f} Birr</code>\n"
            f"💵 <b>New Balance:</b> <code>{new_bal:,.2f} Birr</code>",
            parse_mode="HTML",
            reply_markup=get_back_cancel_keyboard(back_callback=f"adm_cust_view:{target_id}", cancel_callback="btn_cancel")
        )
        try:
            await bot.send_message(
                chat_id=target_id,
                text=f"🎉 <b>WALLET CREDIT</b>\n\nYour wallet has been credited with <code>+{amount:,.2f} Birr</code> by admin.\nNew Balance: <code>{new_bal:,.2f} Birr</code>.",
                parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        await message.answer(f"⚠️ Credit error: {res.get('error')}")

@router.callback_query(F.data.startswith("adm_cust_deb_init:"))
async def init_debit_customer(query: CallbackQuery, state: FSMContext):
    """Initiate customer balance deduction prompt via inline button."""
    await query.answer()
    admin_user = query.from_user
    role = await db.get_admin_role(admin_user.id)
    if role not in ("OWNER", "MANAGER", "FINANCE"):
        await query.answer("⛔ Access Denied: Requires FINANCE/OWNER role", show_alert=True)
        return

    target_id = int(query.data.split(":", 1)[1])
    u = await db.get_user_by_telegram_id(target_id)
    if not u:
        await query.message.edit_text("⚠️ Customer not found.")
        return

    await state.update_data(target_telegram_id=target_id, target_uuid=u["id"], target_name=u.get("first_name", "Customer"))
    await state.set_state(AdminCustomerStates.waiting_for_debit_amount)

    prompt = (
        f"➖ <b>DEDUCT CUSTOMER WALLET BALANCE</b>\n\n"
        f"👤 <b>Customer:</b> {u.get('first_name')} (<code>{target_id}</code>)\n"
        f"💰 <b>Current Balance:</b> <code>{float(u.get('wallet_balance', 0.0)):,.2f} Birr</code>\n\n"
        f"👉 <b>Please type and send the amount to DEDUCT (e.g. 200):</b>"
    )
    from keyboards import get_back_cancel_keyboard
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback=f"adm_cust_view:{target_id}", cancel_callback="btn_cancel"))

@router.callback_query(F.data == "adm_cust_search_prompt")
async def init_search_customer(query: CallbackQuery, state: FSMContext):
    """Initiate customer search prompt."""
    await query.answer()
    admin_user = query.from_user
    if not (await db.get_admin_role(admin_user.id)):
        return

    await state.set_state(AdminCustomerStates.waiting_for_search_id)
    from keyboards import get_back_cancel_keyboard
    await query.message.edit_text(
        "🔍 <b>SEARCH CUSTOMER BY TELEGRAM ID</b>\n\n"
        "Please type and send the customer's numeric <b>Telegram ID</b> (e.g. <code>645123022</code>):",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard(back_callback="adm_customers", cancel_callback="btn_cancel")
    )

@router.message(AdminCustomerStates.waiting_for_search_id)
async def process_search_customer_id(message: Message, state: FSMContext, bot: Bot):
    """Search and display customer card from user input."""
    admin_user = message.from_user
    if not (await db.get_admin_role(admin_user.id)):
        await state.clear()
        return

    await state.clear()
    raw_id = message.text.strip()
    if not raw_id.isdigit():
        from keyboards import get_back_cancel_keyboard
        await message.answer("⚠️ Invalid numeric Telegram ID.", reply_markup=get_back_cancel_keyboard(back_callback="adm_customers", cancel_callback="btn_cancel"))
        return

    target_id = int(raw_id)
    u = await db.get_user_by_telegram_id(target_id)
    if not u:
        from keyboards import get_back_cancel_keyboard
        await message.answer(f"⚠️ Customer <code>{target_id}</code> not found.", parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_customers", cancel_callback="btn_cancel"))
        return

    balance = float(u.get("wallet_balance", 0.00))
    is_banned = u.get("is_banned", False)
    is_vip = u.get("is_vip", False)
    ban_status = "🚫 Banned" if is_banned else "🟢 Active"
    vip_status = "⭐ VIP" if is_vip else "Standard"

    orders = await db.get_user_orders(u["id"], limit=5)
    order_count = len(orders) if orders else 0

    text = (
        f"👤 <b>CUSTOMER DETAILS & WALLET CONTROL</b>\n\n"
        f"▪️ <b>Telegram ID:</b> <code>{target_id}</code>\n"
        f"▪️ <b>Name:</b> {u.get('first_name', 'N/A')}\n"
        f"▪️ <b>Username:</b> @{u.get('username', 'N/A')}\n"
        f"▪️ <b>Status:</b> {ban_status}\n"
        f"▪️ <b>Type:</b> {vip_status}\n"
        f"💰 <b>Wallet Balance:</b> <code>{balance:,.2f} Birr</code>\n"
        f"📦 <b>Recent Orders:</b> <code>{order_count}</code>\n"
        f"📅 <b>Joined:</b> <code>{u.get('created_at', 'N/A')[:10]}</code>\n\n"
        f"<i>Click buttons below to credit balance, deduct balance, or ban/unban user:</i>"
    )

    await message.answer(text=text, parse_mode="HTML", reply_markup=get_admin_customer_card_keyboard(target_id, is_banned))

@router.message(AdminCustomerStates.waiting_for_debit_amount)
async def process_debit_amount(message: Message, state: FSMContext, bot: Bot):
    """Execute customer balance deduction."""
    admin_user = message.from_user
    data = await state.get_data()
    target_id = data["target_telegram_id"]
    target_uuid = data["target_uuid"]
    target_name = data["target_name"]
    await state.clear()

    try:
        amount = float(message.text.strip().replace(",", ""))
        if amount <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Invalid numeric amount. Must be positive.")
        return

    res = await db.atomic_credit_wallet(
        user_id=target_uuid,
        amount=-amount,
        tx_type="ADMIN_DEBIT",
        reference="ADMIN-DEBIT",
        description="Admin manual deduction",
        created_by=str(admin_user.id)
    )

    if res.get("success"):
        new_bal = res.get("balance_after", 0.00)
        await message.answer(
            f"✅ <b>WALLET BALANCE DEDUCTED!</b>\n\n"
            f"👤 <b>Customer:</b> {target_name} (<code>{target_id}</code>)\n"
            f"➖ <b>Deducted:</b> <code>-{amount:,.2f} Birr</code>\n"
            f"💵 <b>New Balance:</b> <code>{new_bal:,.2f} Birr</code>",
            parse_mode="HTML"
        )
        try:
            await bot.send_message(
                chat_id=target_id,
                text=f"⚠️ <b>WALLET DEDUCTION</b>\n\nYour wallet balance has been adjusted by <code>-{amount:,.2f} Birr</code> by admin.\nNew Balance: <code>{new_bal:,.2f} Birr</code>.",
                parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        await message.answer(f"⚠️ Deduction error: {res.get('error')}")

@router.message(Command("addbalance"))
@router.message(Command("credit"))
async def cmd_add_balance(message: Message, bot: Bot):
    """Command: /credit or /addbalance <TELEGRAM_ID> <AMOUNT> <REASON>"""
    admin_user = message.from_user
    role = await db.get_admin_role(admin_user.id)
    if role not in ("OWNER", "MANAGER", "FINANCE"):
        await message.answer("⛔ Access Denied: Requires FINANCE/OWNER role.", parse_mode="HTML")
        return

    args = message.text.split(maxsplit=3)
    if len(args) < 3 or not args[1].isdigit():
        await message.answer("⚠️ Usage: <code>/credit 123456789 500 Verified manual deposit</code>", parse_mode="HTML")
        return

    target_telegram_id = int(args[1])
    try:
        amount = float(args[2])
    except ValueError:
        await message.answer("⚠️ Invalid numeric amount.", parse_mode="HTML")
        return

    reason = args[3] if len(args) > 3 else "Manual Admin credit"

    target_user = await db.get_user_by_telegram_id(target_telegram_id)
    if not target_user:
        await message.answer(f"⚠️ Customer with Telegram ID <code>{target_telegram_id}</code> not found.", parse_mode="HTML")
        return

    res = await db.atomic_credit_wallet(
        user_id=target_user["id"],
        amount=amount,
        tx_type="ADMIN_CREDIT" if amount > 0 else "ADMIN_DEBIT",
        reference="ADMIN-ADJUST",
        description=reason,
        created_by=str(admin_user.id)
    )

    if res.get("success"):
        new_bal = res.get("balance_after", 0.00)
        await message.answer(
            f"✅ <b>WALLET BALANCE ADJUSTED</b>\n\n"
            f"👤 <b>Customer:</b> {target_user['first_name']} (<code>{target_telegram_id}</code>)\n"
            f"💰 <b>Adjustment:</b> <code>+{amount:,.2f} Birr</code>\n"
            f"💵 <b>New Balance:</b> <code>{new_bal:,.2f} Birr</code>\n"
            f"📝 <b>Reason:</b> {reason}",
            parse_mode="HTML"
        )

        try:
            await bot.send_message(
                chat_id=target_telegram_id,
                text=f"➕ <b>WALLET BALANCE UPDATE</b>\n\nYour wallet has been updated by <code>+{amount:,.2f} Birr</code>.\nNew Balance: <code>{new_bal:,.2f} Birr</code>.",
                parse_mode="HTML"
            )
        except Exception:
            pass

@router.message(Command("debit"))
@router.message(Command("deductbalance"))
async def cmd_deduct_balance(message: Message, bot: Bot):
    """Command: /debit or /deductbalance <TELEGRAM_ID> <AMOUNT> <REASON>"""
    admin_user = message.from_user
    role = await db.get_admin_role(admin_user.id)
    if role not in ("OWNER", "MANAGER", "FINANCE"):
        await message.answer("⛔ Access Denied: Requires FINANCE/OWNER role.", parse_mode="HTML")
        return

    args = message.text.split(maxsplit=3)
    if len(args) < 3 or not args[1].isdigit():
        await message.answer("⚠️ Usage: <code>/debit 123456789 200 Balance correction</code>", parse_mode="HTML")
        return

    target_telegram_id = int(args[1])
    try:
        amount = abs(float(args[2]))  # Ensure positive number for deduction
    except ValueError:
        await message.answer("⚠️ Invalid numeric amount.", parse_mode="HTML")
        return

    reason = args[3] if len(args) > 3 else "Manual Admin debit"

    target_user = await db.get_user_by_telegram_id(target_telegram_id)
    if not target_user:
        await message.answer(f"⚠️ Customer with Telegram ID <code>{target_telegram_id}</code> not found.", parse_mode="HTML")
        return

    res = await db.atomic_credit_wallet(
        user_id=target_user["id"],
        amount=-amount,
        tx_type="ADMIN_DEBIT",
        reference="ADMIN-DEBIT",
        description=reason,
        created_by=str(admin_user.id)
    )

    if res.get("success"):
        new_bal = res.get("balance_after", 0.00)
        await message.answer(
            f"✅ <b>WALLET BALANCE DEDUCTED</b>\n\n"
            f"👤 <b>Customer:</b> {target_user['first_name']} (<code>{target_telegram_id}</code>)\n"
            f"➖ <b>Deduction:</b> <code>-{amount:,.2f} Birr</code>\n"
            f"💵 <b>New Balance:</b> <code>{new_bal:,.2f} Birr</code>\n"
            f"📝 <b>Reason:</b> {reason}",
            parse_mode="HTML"
        )

        try:
            await bot.send_message(
                chat_id=target_telegram_id,
                text=f"⚠️ <b>WALLET BALANCE UPDATE</b>\n\nYour wallet balance has been adjusted by <code>-{amount:,.2f} Birr</code>.\nNew Balance: <code>{new_bal:,.2f} Birr</code>.",
                parse_mode="HTML"
            )
        except Exception:
            pass

@router.callback_query(F.data.startswith("adm_cust_ban:"))
async def callback_ban_customer(query: CallbackQuery):
    """Ban customer via inline button."""
    admin_user = query.from_user
    if not (await db.get_admin_role(admin_user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    target_id = int(query.data.split(":", 1)[1])
    if db.is_configured:
        db.client.table("users").update({"is_banned": True}).eq("telegram_id", target_id).execute()

    await query.answer(f"Customer {target_id} Banned!", show_alert=True)
    await query.message.edit_text(f"🚫 Customer <code>{target_id}</code> has been banned.", parse_mode="HTML")

@router.callback_query(F.data.startswith("adm_cust_unban:"))
async def callback_unban_customer(query: CallbackQuery):
    """Unban customer via inline button."""
    admin_user = query.from_user
    if not (await db.get_admin_role(admin_user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    target_id = int(query.data.split(":", 1)[1])
    if db.is_configured:
        db.client.table("users").update({"is_banned": False}).eq("telegram_id", target_id).execute()

    await query.answer(f"Customer {target_id} Unbanned!", show_alert=True)
    await query.message.edit_text(f"🔓 Customer <code>{target_id}</code> has been unbanned.", parse_mode="HTML")

@router.message(Command("ban"))
async def cmd_ban_user(message: Message, bot: Bot):
    """Command: /ban <TELEGRAM_ID>"""
    admin_user = message.from_user
    if not (await db.get_admin_role(admin_user.id)):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Usage: <code>/ban 123456789</code>", parse_mode="HTML")
        return

    target_id = int(args[1])
    if db.is_configured:
        db.client.table("users").update({"is_banned": True}).eq("telegram_id", target_id).execute()

    await message.answer(f"🚫 Customer <code>{target_id}</code> has been banned.", parse_mode="HTML")

@router.message(Command("unban"))
async def cmd_unban_user(message: Message, bot: Bot):
    """Command: /unban <TELEGRAM_ID>"""
    admin_user = message.from_user
    if not (await db.get_admin_role(admin_user.id)):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Usage: <code>/unban 123456789</code>", parse_mode="HTML")
        return

    target_id = int(args[1])
    if db.is_configured:
        db.client.table("users").update({"is_banned": False}).eq("telegram_id", target_id).execute()

    await message.answer(f"🔓 Customer <code>{target_id}</code> has been unbanned.", parse_mode="HTML")
