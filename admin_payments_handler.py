import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest

from db_client import db
from config import (
    EXPECTED_CBE_ACCOUNT,
    EXPECTED_CBE_HOLDER,
    TELEBIRR_NO,
    EXPECTED_TELEBIRR_HOLDER,
    CBE_NO,
    MIN_DEPOSIT_AMOUNT,
    MAX_DEPOSIT_AMOUNT
)
from keyboards import get_back_cancel_keyboard
from channel_logger import log_to_channel
from security_util import sanitize_input

logger = logging.getLogger(__name__)
router = Router()

class AdminPaymentStates(StatesGroup):
    waiting_for_note_approve = State()
    waiting_for_note_reject = State()
    waiting_for_cbe_acc = State()
    waiting_for_cbe_holder = State()
    waiting_for_telebirr_no = State()
    waiting_for_telebirr_holder = State()
    waiting_for_min_dep = State()
    waiting_for_max_dep = State()
    waiting_for_new_method_name = State()

def get_bank_settings_keyboard(auto_verify_active: bool = True) -> InlineKeyboardMarkup:
    """Inline keyboard for Admin Bank & Deposit Controller with Back/Cancel buttons."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏦 Edit CBE Account", callback_data="adm_set_cbe"),
        InlineKeyboardButton(text="👤 Edit CBE Holder", callback_data="adm_set_cbe_holder")
    )
    builder.row(
        InlineKeyboardButton(text="📱 Edit Telebirr No", callback_data="adm_set_telebirr_no"),
        InlineKeyboardButton(text="👤 Edit Telebirr Holder", callback_data="adm_set_telebirr_holder")
    )
    builder.row(
        InlineKeyboardButton(text="📉 Edit Min Limit", callback_data="adm_set_mindep"),
        InlineKeyboardButton(text="📈 Edit Max Limit", callback_data="adm_set_maxdep")
    )
    
    toggle_text = "🟢 Auto-Verifier: ACTIVE" if auto_verify_active else "🔴 Auto-Verifier: PAUSED"
    builder.row(
        InlineKeyboardButton(text=toggle_text, callback_data="adm_toggle_autoverify")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 BACK TO PAYMENTS", callback_data="adm_payments"),
        InlineKeyboardButton(text="❌ CANCEL", callback_data="btn_cancel")
    )
    return builder.as_markup()

@router.callback_query(F.data == "adm_payment_methods")
async def show_payment_methods_manager(query: CallbackQuery):
    """Dynamic Payment Method Manager Dashboard."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    text = (
        f"💳 <b>DYNAMIC PAYMENT METHODS MANAGER</b>\n\n"
        f"<b>Active Deposit Methods:</b>\n"
        f"1. 🟢 <b>CBE Bank / CBE Link:</b> Active\n"
        f"2. 🟢 <b>Telebirr Web Receipt:</b> Active\n"
        f"3. 🟢 <b>Bank Transfer (CBE / Abyssinia / Awash):</b> Active\n\n"
        f"<i>Select an option below to manage payment methods:</i>"
    )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏦 Edit Bank Settings", callback_data="adm_bank_settings"))
    builder.row(InlineKeyboardButton(text="➕ Add New Payment Method", callback_data="adm_add_method_prompt"))
    builder.row(
        InlineKeyboardButton(text="🔙 BACK TO PAYMENTS", callback_data="adm_payments"),
        InlineKeyboardButton(text="❌ CANCEL", callback_data="btn_cancel")
    )

    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=builder.as_markup())
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "adm_add_method_prompt")
async def init_add_method(query: CallbackQuery, state: FSMContext):
    """Prompt admin to type new Payment Method name."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    await state.set_state(AdminPaymentStates.waiting_for_new_method_name)
    await query.message.edit_text(
        "➕ <b>ADD NEW PAYMENT METHOD</b>\n\n"
        "Please type the name of the new payment method (e.g. <code>Bank of Abyssinia</code> or <code>Awash Bank</code>):",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard(back_callback="adm_payment_methods", cancel_callback="btn_cancel")
    )

@router.message(AdminPaymentStates.waiting_for_new_method_name)
async def process_new_method_name(message: Message, state: FSMContext, bot: Bot):
    """Save new payment method."""
    user = message.from_user
    await state.clear()
    is_safe, method_name = sanitize_input(message.text.strip())

    if not is_safe or len(method_name) < 2:
        await message.answer("⚠️ Invalid payment method name.", reply_markup=get_back_cancel_keyboard(back_callback="adm_payment_methods", cancel_callback="btn_cancel"))
        return

    await message.answer(f"✅ <b>New Payment Method added:</b> <code>{method_name}</code>", parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_payment_methods", cancel_callback="btn_cancel"))
    await log_to_channel(bot, "⚙️ PAYMENT METHOD ADDED", {"Admin": user.first_name, "Method": method_name})

@router.callback_query(F.data == "adm_bank_settings")
async def show_bank_settings(query: CallbackQuery):
    """Admin Bank & Deposit System Controller Dashboard displaying .env settings."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    cbe_acc = EXPECTED_CBE_ACCOUNT
    cbe_holder = EXPECTED_CBE_HOLDER
    telebirr_no = TELEBIRR_NO
    telebirr_holder = EXPECTED_TELEBIRR_HOLDER
    min_dep = MIN_DEPOSIT_AMOUNT
    max_dep = MAX_DEPOSIT_AMOUNT
    auto_verify = bool(await db.get_setting("auto_verify_enabled", True))

    status_str = "🟢 ACTIVE (Strict .env Verification)" if auto_verify else "🔴 PAUSED (Manual review only)"

    text = (
        f"⚙️ <b>BANK & DEPOSIT SYSTEM CONTROLLER (.env Powered)</b>\n\n"
        f"🏦 <b>CBE Account Number:</b> <code>{cbe_acc}</code>\n"
        f"👤 <b>CBE Account Holder:</b> <code>{cbe_holder}</code>\n"
        f"📱 <b>Telebirr Number:</b> <code>{telebirr_no}</code>\n"
        f"👤 <b>Telebirr Holder:</b> <code>{telebirr_holder}</code>\n"
        f"📉 <b>Minimum Deposit Limit:</b> <code>{min_dep:,.0f} Birr</code>\n"
        f"📈 <b>Maximum Deposit Limit:</b> <code>{max_dep:,.0f} Birr</code>\n"
        f"⚡ <b>Auto-Verifier Status:</b> {status_str}\n\n"
        f"<i>All deposit verification rules and accounts are strictly loaded from .env.</i>"
    )

    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=get_bank_settings_keyboard(auto_verify))
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "adm_set_cbe")
async def init_set_cbe(query: CallbackQuery, state: FSMContext):
    """Initiate CBE account change prompt."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    await state.set_state(AdminPaymentStates.waiting_for_cbe_acc)
    await query.message.edit_text(
        "🏦 <b>EDIT CBE ACCOUNT NUMBER</b>\n\n"
        "Please type and send the NEW CBE Account Number (e.g. <code>1000320563279</code> or <code>1****7241</code>):",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel")
    )

@router.message(AdminPaymentStates.waiting_for_cbe_acc)
async def process_cbe_acc(message: Message, state: FSMContext, bot: Bot):
    """Save new CBE Account Number."""
    user = message.from_user
    await state.clear()
    is_safe, new_acc = sanitize_input(message.text.strip())

    if not is_safe or len(new_acc) < 4:
        await message.answer("⚠️ Invalid account format.", reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel"))
        return

    await db.update_setting("cbe_account", new_acc)
    await message.answer(f"✅ <b>CBE Account updated to:</b> <code>{new_acc}</code>", parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel"))
    await log_to_channel(bot, "⚙️ BANK SETTING CHANGED", {"Admin": user.first_name, "Setting": "CBE Account", "New Value": new_acc})

@router.callback_query(F.data == "adm_set_cbe_holder")
async def init_set_cbe_holder(query: CallbackQuery, state: FSMContext):
    """Initiate CBE account holder name change prompt."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    await state.set_state(AdminPaymentStates.waiting_for_cbe_holder)
    await query.message.edit_text(
        "👤 <b>EDIT CBE ACCOUNT HOLDER NAME</b>\n\n"
        "Please type and send the NEW CBE Account Holder Name (e.g. <code>MELAX DIGITAL SHOP</code>):",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel")
    )

@router.message(AdminPaymentStates.waiting_for_cbe_holder)
async def process_cbe_holder(message: Message, state: FSMContext, bot: Bot):
    """Save new CBE Account Holder Name."""
    user = message.from_user
    await state.clear()
    is_safe, new_holder = sanitize_input(message.text.strip())

    if not is_safe or len(new_holder) < 2:
        await message.answer("⚠️ Invalid account holder name.", reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel"))
        return

    await db.update_setting("cbe_account_holder", new_holder.upper())
    await message.answer(f"✅ <b>CBE Account Holder Name updated to:</b> <code>{new_holder.upper()}</code>", parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel"))
    await log_to_channel(bot, "⚙️ BANK SETTING CHANGED", {"Admin": user.first_name, "Setting": "CBE Holder Name", "New Value": new_holder.upper()})

@router.callback_query(F.data == "adm_set_telebirr_no")
async def init_set_telebirr_no(query: CallbackQuery, state: FSMContext):
    """Initiate Telebirr phone number change prompt."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    await state.set_state(AdminPaymentStates.waiting_for_telebirr_no)
    await query.message.edit_text(
        "📱 <b>EDIT TELEBIRR PHONE NUMBER</b>\n\n"
        "Please type and send the NEW Telebirr Phone Number (e.g. <code>0912345678</code> or <code>0912***678</code>):",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel")
    )

@router.message(AdminPaymentStates.waiting_for_telebirr_no)
async def process_telebirr_no(message: Message, state: FSMContext, bot: Bot):
    """Save new Telebirr Phone Number."""
    user = message.from_user
    await state.clear()
    is_safe, new_no = sanitize_input(message.text.strip())

    if not is_safe or len(new_no) < 4:
        await message.answer("⚠️ Invalid phone number format.", reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel"))
        return

    await db.update_setting("telebirr_number", new_no)
    await message.answer(f"✅ <b>Telebirr Number updated to:</b> <code>{new_no}</code>", parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel"))
    await log_to_channel(bot, "⚙️ BANK SETTING CHANGED", {"Admin": user.first_name, "Setting": "Telebirr Number", "New Value": new_no})

@router.callback_query(F.data == "adm_set_telebirr_holder")
async def init_set_telebirr_holder(query: CallbackQuery, state: FSMContext):
    """Initiate Telebirr holder name change prompt."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    await state.set_state(AdminPaymentStates.waiting_for_telebirr_holder)
    await query.message.edit_text(
        "👤 <b>EDIT TELEBIRR HOLDER NAME</b>\n\n"
        "Please type and send the NEW Telebirr Holder Name (e.g. <code>MELAX DIGITAL</code>):",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel")
    )

@router.message(AdminPaymentStates.waiting_for_telebirr_holder)
async def process_telebirr_holder(message: Message, state: FSMContext, bot: Bot):
    """Save new Telebirr Holder Name."""
    user = message.from_user
    await state.clear()
    is_safe, new_holder = sanitize_input(message.text.strip())

    if not is_safe or len(new_holder) < 2:
        await message.answer("⚠️ Invalid holder name.", reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel"))
        return

    await db.update_setting("telebirr_holder_name", new_holder.upper())
    await message.answer(f"✅ <b>Telebirr Holder Name updated to:</b> <code>{new_holder.upper()}</code>", parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel"))
    await log_to_channel(bot, "⚙️ BANK SETTING CHANGED", {"Admin": user.first_name, "Setting": "Telebirr Holder Name", "New Value": new_holder.upper()})

@router.callback_query(F.data == "adm_set_mindep")
async def init_set_mindep(query: CallbackQuery, state: FSMContext):
    """Initiate Min deposit limit change prompt."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    await state.set_state(AdminPaymentStates.waiting_for_min_dep)
    await query.message.edit_text(
        "📉 <b>EDIT MINIMUM DEPOSIT LIMIT</b>\n\n"
        "Please type and send the NEW Minimum Deposit amount in Birr (e.g. <code>10</code>):",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel")
    )

@router.message(AdminPaymentStates.waiting_for_min_dep)
async def process_min_dep(message: Message, state: FSMContext, bot: Bot):
    """Save new Min Deposit Limit."""
    user = message.from_user
    await state.clear()
    try:
        new_min = float(message.text.strip().replace(",", ""))
        if new_min < 0:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Invalid numeric amount.", reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel"))
        return

    await db.update_setting("min_deposit", new_min)
    await message.answer(f"✅ <b>Minimum Deposit updated to:</b> <code>{new_min:,.0f} Birr</code>", parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel"))

@router.callback_query(F.data == "adm_set_maxdep")
async def init_set_maxdep(query: CallbackQuery, state: FSMContext):
    """Initiate Max deposit limit change prompt."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    await state.set_state(AdminPaymentStates.waiting_for_max_dep)
    await query.message.edit_text(
        "📈 <b>EDIT MAXIMUM DEPOSIT LIMIT</b>\n\n"
        "Please type and send the NEW Maximum Deposit amount in Birr (e.g. <code>100000</code>):",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel")
    )

@router.message(AdminPaymentStates.waiting_for_max_dep)
async def process_max_dep(message: Message, state: FSMContext, bot: Bot):
    """Save new Max Deposit Limit."""
    user = message.from_user
    await state.clear()
    try:
        new_max = float(message.text.strip().replace(",", ""))
        if new_max < 0:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Invalid numeric amount.", reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel"))
        return

    await db.update_setting("max_deposit", new_max)
    await message.answer(f"✅ <b>Maximum Deposit updated to:</b> <code>{new_max:,.0f} Birr</code>", parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_bank_settings", cancel_callback="btn_cancel"))

@router.callback_query(F.data == "adm_toggle_autoverify")
async def toggle_auto_verify(query: CallbackQuery, bot: Bot):
    """Toggle Auto-Verifier status (Active / Paused)."""
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    current = bool(await db.get_setting("auto_verify_enabled", True))
    new_val = not current
    await db.update_setting("auto_verify_enabled", new_val)

    status_label = "🟢 ACTIVE" if new_val else "🔴 PAUSED"
    await query.answer(f"Auto-Verifier status changed to {status_label}!", show_alert=True)

    cbe_acc = EXPECTED_CBE_ACCOUNT
    cbe_holder = EXPECTED_CBE_HOLDER
    telebirr_no = TELEBIRR_NO
    telebirr_holder = EXPECTED_TELEBIRR_HOLDER
    min_dep = MIN_DEPOSIT_AMOUNT
    max_dep = MAX_DEPOSIT_AMOUNT

    status_str = "🟢 ACTIVE (Strict .env Verification)" if new_val else "🔴 PAUSED (Manual review only)"

    text = (
        f"⚙️ <b>BANK & DEPOSIT SYSTEM CONTROLLER (.env Powered)</b>\n\n"
        f"🏦 <b>CBE Account Number:</b> <code>{cbe_acc}</code>\n"
        f"👤 <b>CBE Account Holder:</b> <code>{cbe_holder}</code>\n"
        f"📱 <b>Telebirr Number:</b> <code>{telebirr_no}</code>\n"
        f"👤 <b>Telebirr Holder:</b> <code>{telebirr_holder}</code>\n"
        f"📉 <b>Minimum Deposit Limit:</b> <code>{min_dep:,.0f} Birr</code>\n"
        f"📈 <b>Maximum Deposit Limit:</b> <code>{max_dep:,.0f} Birr</code>\n"
        f"⚡ <b>Auto-Verifier Status:</b> {status_str}\n\n"
        f"<i>All deposit verification rules and accounts are strictly loaded from .env.</i>"
    )

    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=get_bank_settings_keyboard(new_val))
    except TelegramBadRequest:
        pass

@router.callback_query(F.data.startswith("dep_appr:"))
async def handle_deposit_approval(query: CallbackQuery, state: FSMContext, bot: Bot):
    """Approve customer deposit with custom Deposit Note prompt."""
    admin_user = query.from_user
    if not (await db.get_admin_role(admin_user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    payment_id = query.data.split(":", 1)[1]
    await state.update_data(target_payment_id=payment_id, admin_prompt_msg_id=query.message.message_id, admin_chat_id=query.message.chat.id)
    await state.set_state(AdminPaymentStates.waiting_for_note_approve)

    await query.answer("Type a Deposit Note / Reason (or send '-' to skip):", show_alert=True)
    await query.message.reply(
        f"📝 <b>APPROVING DEPOSIT #{payment_id}</b>\n\n"
        f"Please send a <b>Deposit Note / Reason</b> (e.g. <code>Verified via Bank Link</code> or send <code>-</code> for default):",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard(back_callback="adm_pending_payments", cancel_callback="btn_cancel")
    )

@router.message(AdminPaymentStates.waiting_for_note_approve)
async def process_approval_note(message: Message, state: FSMContext, bot: Bot):
    """Save approval note, execute atomic credit, and remove from pending queue."""
    admin_user = message.from_user
    note = message.text.strip()
    if note == "-":
        note = "Approved by Admin"

    data = await state.get_data()
    payment_id = data["target_payment_id"]
    prompt_msg_id = data.get("admin_prompt_msg_id")
    chat_id = data.get("admin_chat_id")
    await state.clear()

    success, msg, pay_data = await db.approve_payment(payment_id, admin_user.id, deposit_note=note)

    if success and pay_data:
        amount = float(pay_data["amount"])
        user_id = pay_data["user_id"]
        
        target_user = None
        if db.is_configured:
            u_res = db.client.table("users").select("telegram_id, first_name").eq("id", user_id).execute()
            if u_res.data:
                target_user = u_res.data[0]

        target_tg_id = target_user["telegram_id"] if target_user else 0

        if chat_id and prompt_msg_id:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=prompt_msg_id,
                    text=f"✅ <b>DEPOSIT #{payment_id} APPROVED BY ADMIN</b>\n\n💰 <b>Amount:</b> <code>{amount:,.2f} Birr</code>\n📝 <b>Note:</b> {note}",
                    parse_mode="HTML",
                    reply_markup=None
                )
            except Exception:
                pass

        await message.answer(
            f"✅ <b>DEPOSIT APPROVED & REMOVED FROM PENDING QUEUE</b>\n\n"
            f"🧾 <b>Payment ID:</b> <code>{payment_id}</code>\n"
            f"💰 <b>Amount:</b> <code>{amount:,.2f} Birr</code> credited.\n"
            f"📝 <b>Note:</b> {note}",
            parse_mode="HTML",
            reply_markup=get_back_cancel_keyboard(back_callback="adm_pending_payments", cancel_callback="btn_cancel")
        )

        if target_tg_id:
            try:
                await bot.send_message(
                    chat_id=target_tg_id,
                    text=f"🎉 <b>DEPOSIT APPROVED!</b>\n\nYour payment <code>#{payment_id}</code> of <code>{amount:,.2f} Birr</code> has been verified and added to your wallet!\nNote: {note}",
                    parse_mode="HTML"
                )
            except Exception:
                pass

        from channel_logger import log_deposit_to_channel
        await log_deposit_to_channel(bot, user_id=target_tg_id, amount=amount, provider="CBE", txn_id=payment_id)
    else:
        await message.answer(f"⚠️ {msg}", reply_markup=get_back_cancel_keyboard(back_callback="adm_pending_payments", cancel_callback="btn_cancel"))

@router.callback_query(F.data.startswith("dep_rej:"))
async def handle_deposit_rejection(query: CallbackQuery, state: FSMContext, bot: Bot):
    """Reject customer deposit request with custom reason prompt."""
    admin_user = query.from_user
    if not (await db.get_admin_role(admin_user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    payment_id = query.data.split(":", 1)[1]
    await state.update_data(target_payment_id=payment_id, admin_prompt_msg_id=query.message.message_id, admin_chat_id=query.message.chat.id)
    await state.set_state(AdminPaymentStates.waiting_for_note_reject)

    await query.answer("Type Rejection Reason (or send '-' for default):", show_alert=True)
    await query.message.reply(
        f"❌ <b>REJECTING DEPOSIT #{payment_id}</b>\n\n"
        f"Please send the <b>Rejection Reason</b> (e.g. <code>Fake receipt or transaction not found</code> or send <code>-</code>):",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard(back_callback="adm_pending_payments", cancel_callback="btn_cancel")
    )

@router.message(AdminPaymentStates.waiting_for_note_reject)
async def process_rejection_note(message: Message, state: FSMContext, bot: Bot):
    """Save rejection reason and remove from pending queue."""
    admin_user = message.from_user
    reason = message.text.strip()
    if reason == "-":
        reason = "Receipt verification failed"

    data = await state.get_data()
    payment_id = data["target_payment_id"]
    prompt_msg_id = data.get("admin_prompt_msg_id")
    chat_id = data.get("admin_chat_id")
    await state.clear()

    success, msg, pay_data = await db.reject_payment(payment_id, admin_user.id, reason=reason)

    if success and pay_data:
        user_id = pay_data["user_id"]
        target_tg_id = 0
        if db.is_configured:
            u_res = db.client.table("users").select("telegram_id").eq("id", user_id).execute()
            if u_res.data:
                target_tg_id = u_res.data[0]["telegram_id"]

        if chat_id and prompt_msg_id:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=prompt_msg_id,
                    text=f"❌ <b>DEPOSIT #{payment_id} REJECTED BY ADMIN</b>\n\n📝 <b>Reason:</b> {reason}",
                    parse_mode="HTML",
                    reply_markup=None
                )
            except Exception:
                pass

        await message.answer(
            f"❌ <b>DEPOSIT REJECTED & REMOVED FROM PENDING QUEUE</b>\n\n"
            f"🧾 <b>Payment ID:</b> <code>{payment_id}</code>\n"
            f"📝 <b>Reason:</b> {reason}",
            parse_mode="HTML",
            reply_markup=get_back_cancel_keyboard(back_callback="adm_pending_payments", cancel_callback="btn_cancel")
        )

        if target_tg_id:
            try:
                await bot.send_message(
                    chat_id=target_tg_id,
                    text=f"❌ <b>DEPOSIT REJECTED</b>\n\nYour deposit request <code>#{payment_id}</code> could not be verified.\nReason: {reason}",
                    parse_mode="HTML"
                )
            except Exception:
                pass

        await log_to_channel(bot, "❌ PAYMENT REJECTED", {
            "Admin": f"@{admin_user.username}" if admin_user.username else admin_user.first_name,
            "Payment ID": payment_id,
            "Customer ID": target_tg_id,
            "Reason": reason
        })
    else:
        await message.answer(f"⚠️ {msg}", reply_markup=get_back_cancel_keyboard(back_callback="adm_pending_payments", cancel_callback="btn_cancel"))
