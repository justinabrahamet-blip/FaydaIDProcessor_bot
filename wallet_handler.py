import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

from db_client import db
from verifier import verify_payment
from config import (
    DISPLAY_CBE_ACCOUNT,
    DISPLAY_CBE_HOLDER,
    DISPLAY_TELEBIRR_NO,
    DISPLAY_TELEBIRR_HOLDER,
    EXPECTED_CBE_ACCOUNT,
    EXPECTED_CBE_HOLDER,
    TELEBIRR_NO,
    EXPECTED_TELEBIRR_HOLDER,
    CBE_NO,
    ADMIN_IDS,
    MIN_DEPOSIT_AMOUNT,
    MAX_DEPOSIT_AMOUNT,
    emo,
    animate_text
)
from keyboards import get_wallet_keyboard, get_deposit_approval_keyboard, get_back_keyboard, get_back_cancel_keyboard
from channel_logger import log_to_channel
from i18n import t, REPLY_TEXT_WALLET, ALL_REPLY_BUTTON_TEXTS

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("wallet"))
@router.message(F.text.in_(REPLY_TEXT_WALLET))
@router.callback_query(F.data == "btn_wallet")
async def show_wallet_menu(event: Message | CallbackQuery):
    """Display customer wallet overview with clean user-facing display details and animated styling."""
    if isinstance(event, CallbackQuery):
        await event.answer()
        user = event.from_user
        message = event.message
    else:
        user = event.from_user
        message = event

    u_db = await db.get_user_by_telegram_id(user.id)
    balance = u_db.get("wallet_balance", 0.00) if u_db else 0.00

    from config import emo
    wallet_text = (
        f"{emo('wallet', '💳')} <b>MY WALLET & INSTANT DEPOSITS</b> {emo('diamond', '💎')}\n\n"
        f"{emo('money', '💰')} <b>Current Balance:</b> <code>{balance:,.2f} Birr</code> {emo('sparkle', '✨')}\n\n"
        f"<b>Official Deposit Accounts:</b>\n"
        f"{emo('cbe', '🏦')} <b>CBE Account:</b> <code>{DISPLAY_CBE_ACCOUNT}</code> ({DISPLAY_CBE_HOLDER})\n"
        f"{emo('telebirr', '📱')} <b>Telebirr Number:</b> <code>{DISPLAY_TELEBIRR_NO}</code> ({DISPLAY_TELEBIRR_HOLDER})\n\n"
        f"{emo('lightning', '⚡')} <b>100% Instant Automated Verification:</b>\n"
        f"Send funds to either account and copy-paste the official <b>CBE Link or Telebirr Receipt / Txn ID</b> directly in this chat!"
    )

    is_admin = (await db.get_admin_role(user.id)) is not None
    if isinstance(event, CallbackQuery):
        try:
            await message.edit_text(text=wallet_text, parse_mode="HTML", reply_markup=get_wallet_keyboard(is_admin=is_admin))
        except TelegramBadRequest:
            pass
    else:
        await message.answer(text=wallet_text, parse_mode="HTML", reply_markup=get_wallet_keyboard(is_admin=is_admin))

@router.callback_query(F.data == "btn_add_balance")
async def add_balance_instructions(query: CallbackQuery):
    """Show detailed deposit instructions with full display numbers and Back/Cancel buttons."""
    user = query.from_user
    if not (await db.get_service_status("deposits", True)) and not (await db.get_admin_role(user.id)):
        await query.answer("⚠️ የሒሳብ መሙያ (Deposit) ሲስተም ለጊዜው ተዘግቷል (Deposits disabled).", show_alert=True)
        return

    await query.answer()

    from config import emo
    text = (
        f"➕ <b>ADD WALLET BALANCE {emo('lightning', '⚡')}{emo('diamond', '💎')}</b>\n\n"
        f"Please send your payment to our official accounts:\n"
        f"• {emo('cbe', '🏦')} <b>CBE Account:</b> <code>{DISPLAY_CBE_ACCOUNT}</code> (Holder: <b>{DISPLAY_CBE_HOLDER}</b>)\n"
        f"• {emo('telebirr', '📱')} <b>Telebirr Number:</b> <code>{DISPLAY_TELEBIRR_NO}</code> (Holder: <b>{DISPLAY_TELEBIRR_HOLDER}</b>)\n\n"
        f"{emo('money', '💰')} <b>Minimum Deposit:</b> <code>{MIN_DEPOSIT_AMOUNT:,.0f} Birr</code>\n"
        f"{emo('money', '📈')} <b>Maximum Deposit:</b> <code>{MAX_DEPOSIT_AMOUNT:,.0f} Birr</code>\n\n"
        f"⚠️ <b>ማሳሰቢያ፦</b> ፎቶ አይቀበልም! ክፍያ ከፈፀሙ በኋላ የ <b>CBE Link ወይም የ Telebirr Receipt/Txn ID</b> ጽሑፍ ብቻ ኮፒ አድርገው እዚህ ይላኩ! {emo('lightning', '⚡')}"
    )
    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="btn_wallet", cancel_callback="btn_cancel"))
    except TelegramBadRequest:
        pass

@router.message(F.photo)
async def decline_photo_receipt(message: Message):
    """Decline photo receipt uploads and instruct user to send CBE/Telebirr text receipt only."""
    decline_text = (
        f"⚠️ <b>ፎቶ አይቀበልም! ❌</b>\n\n"
        f"እባክዎን የክፍያ ማረጋገጫ የ <b>CBE Link ወይም የ Telebirr Txn ID / Link</b> ጽሑፍ ብቻ ኮፒ አድርገው በላኩት ጽሑፍ መልክ ይላኩ። ⚡"
    )
    await message.answer(text=decline_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="btn_wallet", cancel_callback="btn_cancel"))

@router.message(F.text & ~F.text.startswith("/") & ~F.text.in_(ALL_REPLY_BUTTON_TEXTS))
async def process_text_receipt(message: Message, bot: Bot):
    """Process incoming text with CBE & Telebirr Web Receipt Verifier Engine strictly using .env masked/unmasked verification rules."""
    user = message.from_user
    u_db = await db.get_user_by_telegram_id(user.id)
    if not u_db or u_db.get("is_banned"):
        return

    input_text = message.text.strip()

    if len(input_text) < 5 or not (any(char.isdigit() for char in input_text) or "http" in input_text.lower()):
        return

    # Strictly use .env verifier rules (which support masked patterns like 1****7241 or 0912***678)
    cbe_acc = EXPECTED_CBE_ACCOUNT
    cbe_holder = EXPECTED_CBE_HOLDER
    telebirr_phone = TELEBIRR_NO
    telebirr_name = EXPECTED_TELEBIRR_HOLDER
    min_dep = MIN_DEPOSIT_AMOUNT
    max_dep = MAX_DEPOSIT_AMOUNT

    status_msg = await message.answer("🔄 <i>Verifying payment receipt text automatically... ⚡</i>", parse_mode="HTML")

    res = await verify_payment(
        input_text,
        expected_cbe_account=cbe_acc,
        expected_cbe_holder=cbe_holder,
        expected_telebirr_phone=telebirr_phone,
        expected_telebirr_holder=telebirr_name
    )

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
    except Exception:
        pass

    # 1. SUCCESSFUL VERIFICATION
    if res.get("ok"):
        txn_id = res.get("transaction_id", "UNKNOWN")
        amount = float(res.get("amount", 0.0))
        provider = res.get("provider", "CBE")
        payer_name = res.get("payer_name", "Customer")
        rec_name = res.get("receiver_name", cbe_holder)

        # Check Anti-Reuse
        if await db.is_transaction_id_used(txn_id):
            already_used_text = (
                f"⚠️ <b>የተደጋገመ ደረሰኝ (RECEIPT ALREADY USED) ❌</b>\n\n"
                f"ይህ የክፍያ ማረጋገጫ (Txn ID: <code>{txn_id}</code>) አስቀድሞ አገልግሎት ላይ ውሏል!\n"
                f"አንድ የክፍያ ደረሰኝ ከአንድ ጊዜ በላይ መጠቀም አይቻልም።"
            )
            await message.answer(text=already_used_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="btn_wallet", cancel_callback="btn_cancel"))
            return

        # Check Min/Max Limits
        if amount < min_dep or amount > max_dep:
            limit_text = (
                f"📉 <b>የክፍያ መጠን ህግ (AMOUNT OUT OF RANGE)</b>\n\n"
                f"አነስተኛው የተቀባይ ሂሳብ መጠን: <code>{min_dep:,.0f} Birr</code>\n"
                f"ከፍተኛው የተቀባይ ሂሳብ መጠን: <code>{max_dep:,.0f} Birr</code>\n"
                f"እርስዎ የላኩት የክፍያ መጠን: <code>{amount:,.2f} Birr</code>"
            )
            await message.answer(text=limit_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="btn_wallet", cancel_callback="btn_cancel"))
            return

        # Atomic Credit Wallet
        cred_res = await db.atomic_credit_wallet(
            user_id=u_db["id"],
            amount=amount,
            tx_type="DEPOSIT",
            reference=txn_id,
            description=f"Automated {provider} Receipt Verification ({payer_name} -> {rec_name})"
        )

        if cred_res.get("success"):
            new_bal = cred_res.get("balance_after", 0.00)
            
            await db.create_payment_request(
                user_id=u_db["id"],
                amount=amount,
                method=provider,
                reference=txn_id,
                status="APPROVED",
                deposit_note=f"Auto-Verified via {provider} ({rec_name})"
            )

            success_text = (
                f"🎉 <b>AUTOMATIC DEPOSIT VERIFIED! ⚡💎</b>\n\n"
                f"🏦 <b>Payment Provider:</b> <code>{provider}</code>\n"
                f"👤 <b>Account Holder:</b> <code>{rec_name}</code>\n"
                f"🧾 <b>Transaction ID:</b> <code>{txn_id}</code>\n"
                f"💰 <b>Credited Amount:</b> <code>+{amount:,.2f} Birr</code> ✨\n"
                f"💵 <b>New Balance:</b> <code>{new_bal:,.2f} Birr</code> 💳\n\n"
                f"👑 <i>Your wallet has been updated instantly. Thank you!</i>"
            )

            await message.answer(text=success_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="btn_wallet", cancel_callback="btn_cancel"))

            from channel_logger import log_deposit_to_channel
            await log_deposit_to_channel(bot, user_id=user.id, amount=amount, provider=provider, txn_id=txn_id)
            return

    # 2. SPECIFIC REJECTION REASONS
    err_code = res.get("code", "")
    err_desc = res.get("error", "የደረሰኝ ፍተሻ አልተሳካም።")

    if err_code in ("ACCOUNT_MISMATCH", "HOLDER_MISMATCH", "EXPIRED_RECEIPT", "INVALID_DOMAIN", "MISSING_LINK", "MISSING_TXN_ID", "NOT_FOUND"):
        await message.answer(text=err_desc, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="btn_wallet", cancel_callback="btn_cancel"))
        return

    # 3. FALLBACK FOR UNRECOGNIZED FORMATS -> QUEUE FOR MANUAL ADMIN REVIEW
    payment_rec = await db.create_payment_request(
        user_id=u_db["id"],
        amount=100.00,
        method="Manual Review Receipt",
        reference=input_text[:50],
        status="PENDING",
        deposit_note="Failed auto-verify receipt, queued for admin"
    )

    pay_id = payment_rec.get("payment_id", "DEP-NEW")

    fallback_text = (
        f"📥 <b>DEPOSIT SENT FOR ADMIN REVIEW 🛡️</b>\n\n"
        f"🧾 <b>Payment Ref:</b> <code>{pay_id}</code>\n"
        f"📌 <i>{err_desc}</i>\n\n"
        f"An administrator has received your receipt text and will manually verify it shortly."
    )
    await message.answer(text=fallback_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="btn_wallet", cancel_callback="btn_cancel"))

    for admin_id in ADMIN_IDS:
        try:
            admin_msg = (
                f"📥 <b>MANUAL DEPOSIT REVIEW REQUIRED</b>\n\n"
                f"👤 <b>Customer:</b> {user.first_name} (@{user.username})\n"
                f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n"
                f"🧾 <b>Payment ID:</b> <code>{pay_id}</code>\n"
                f"⚠️ <b>Auto-Verify Note:</b> {err_desc}\n\n"
                f"📄 <b>Customer Text Input:</b>\n"
                f"<code>{input_text}</code>"
            )
            await bot.send_message(
                chat_id=admin_id,
                text=admin_msg,
                parse_mode="HTML",
                reply_markup=get_deposit_approval_keyboard(pay_id)
            )
        except Exception:
            pass

@router.callback_query(F.data == "btn_tx_history")
async def show_transaction_history(query: CallbackQuery):
    """Display wallet ledger transactions with Back and Cancel buttons."""
    await query.answer()
    user = query.from_user
    u_db = await db.get_user_by_telegram_id(user.id)
    if not u_db:
        return

    txs = await db.get_wallet_transactions(u_db["id"], limit=15)
    if not txs:
        try:
            await query.message.edit_text("📜 <b>No wallet transactions found.</b>", parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="btn_wallet", cancel_callback="btn_cancel"))
        except TelegramBadRequest:
            pass
        return

    text = "📜 <b>WALLET TRANSACTIONS LEDGER 💎</b>\n\n"
    for tx in txs:
        sign = "+" if float(tx["amount"]) > 0 else ""
        text += (
            f"▫️ <b>{tx['type']}</b> | <code>{sign}{float(tx['amount']):,.2f} Birr</code>\n"
            f"   Balance: <code>{float(tx['balance_after']):,.2f} Birr</code>\n"
            f"   Ref: <code>{tx.get('reference', 'N/A')}</code> | <code>{tx['created_at'][:16]}</code>\n\n"
        )

    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="btn_wallet", cancel_callback="btn_cancel"))
    except TelegramBadRequest:
        pass
