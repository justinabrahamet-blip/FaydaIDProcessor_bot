import asyncio
import logging
import os
import re
import sqlite3
from datetime import datetime

import requests
from flask import Flask, request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
CBE_VERIFIER_URL = os.environ.get(
    "CBE_VERIFIER_URL", "https://cbe-verifier-python.onrender.com/verify"
)
CBE_EXPECTED_ACCOUNT = os.environ.get("CBE_EXPECTED_ACCOUNT", "").strip()
DB_PATH = os.environ.get("DB_PATH", "bot_data.db")
COOLDOWN_SECONDS = 5
WEBHOOK_URL = os.environ.get("WEBHOOK_URL") or os.environ.get("RENDER_EXTERNAL_URL")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)
bot_app = None
bot_ready = False
last_receipt_time: dict[int, float] = {}


# Database helpers

def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db() -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL NOT NULL DEFAULT 0.0
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                raw_text TEXT UNIQUE,
                cbe_link TEXT UNIQUE,
                reference TEXT UNIQUE,
                amount REAL NOT NULL,
                receiver_account TEXT,
                receiver_name TEXT,
                status TEXT NOT NULL,
                approved_by INTEGER,
                manual_note TEXT,
                verified_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            ("pdf_to_id_price", "10"),
        )
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            ("fan_to_id_price", "15"),
        )
        conn.commit()


def get_setting(key: str, default: str) -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def get_service_price(service: str) -> float:
    raw_value = get_setting(service, "0")
    try:
        return float(raw_value)
    except ValueError:
        return 0.0


def get_user_balance(user_id: int) -> float:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return float(row[0]) if row else 0.0


def update_user_balance(user_id: int, amount: float) -> float:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return float(row[0]) if row else 0.0


def receipt_already_used(raw_text: str, cbe_link: str | None, reference: str | None) -> bool:
    query = """
        SELECT 1 FROM receipts
        WHERE raw_text = ?
           OR (? IS NOT NULL AND cbe_link = ?)
           OR (? IS NOT NULL AND reference = ?)
        LIMIT 1
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (raw_text, cbe_link, cbe_link, reference, reference))
        return cursor.fetchone() is not None


def create_receipt_record(
    user_id: int,
    raw_text: str,
    cbe_link: str | None,
    reference: str | None,
    amount: float,
    receiver_account: str | None,
    receiver_name: str | None,
    status: str,
    manual_note: str | None = None,
) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO receipts (user_id, raw_text, cbe_link, reference, amount, receiver_account, receiver_name, status, manual_note, verified_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                raw_text,
                cbe_link,
                reference,
                amount,
                receiver_account,
                receiver_name,
                status,
                manual_note,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def mark_receipt_verified(receipt_id: int, approver_id: int | None = None) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE receipts SET status = 'VERIFIED', approved_by = ?, verified_at = ? WHERE id = ?",
            (approver_id, datetime.utcnow().isoformat(), receipt_id),
        )
        conn.commit()


def mark_receipt_rejected(receipt_id: int, approver_id: int | None = None) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE receipts SET status = 'REJECTED', approved_by = ?, verified_at = ? WHERE id = ?",
            (approver_id, datetime.utcnow().isoformat(), receipt_id),
        )
        conn.commit()


def fetch_pending_receipt(receipt_id: int | None = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        if receipt_id is not None:
            cursor.execute("SELECT * FROM receipts WHERE id = ? AND status = 'PENDING'", (receipt_id,))
        else:
            cursor.execute("SELECT * FROM receipts WHERE status = 'PENDING' ORDER BY id ASC LIMIT 1")
        return cursor.fetchone()


def parse_cbe_receipt(text: str) -> dict[str, str | None] | None:
    normalized = text.strip()
    link_match = re.search(r"(https?://(?:www\.)?mbreciept\.cbe\.com\.et\S*)", normalized, re.IGNORECASE)
    ft_match = re.search(r"\bFT[0-9]{4,}\b", normalized, re.IGNORECASE)
    if not link_match and not ft_match:
        return None

    cbe_link = link_match.group(1).strip() if link_match else None
    if cbe_link:
        cbe_link = cbe_link.rstrip(".,;\n\r ")
    reference = ft_match.group(0).upper() if ft_match else None
    return {
        "raw_text": normalized,
        "cbe_link": cbe_link,
        "reference": reference,
    }


def verify_cbe_receipt(raw_text: str, reference: str | None) -> requests.Response:
    payload = {
        "input": raw_text,
        "ft": reference,
    }
    headers = {"Content-Type": "application/json"}
    return requests.post(CBE_VERIFIER_URL, json=payload, headers=headers, timeout=20)


def format_success_message(amount: float, date_text: str, balance: float) -> str:
    return (
        "✅ CBE receipt verified.\n"
        f"💰 Amount: {int(amount) if amount.is_integer() else amount} ETB\n"
        f"📅 Date: {date_text}\n\n"
        f"💳 New balance: {int(balance) if balance.is_integer() else balance} ETB"
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📄 PDF to ID", callback_data="pdf_to_id")],
            [InlineKeyboardButton("🔑 FAN to ID", callback_data="fan_to_id")],
            [InlineKeyboardButton("💳 Deposit", callback_data="deposit")],
            [InlineKeyboardButton("💰 Balance", callback_data="balance")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
        ]
    )


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Pending receipts", callback_data="admin_pending")],
            [InlineKeyboardButton("Set PDF price", callback_data="admin_set_pdf_price")],
            [InlineKeyboardButton("Set FAN price", callback_data="admin_set_fan_price")],
            [InlineKeyboardButton("View stats", callback_data="admin_stats")],
            [InlineKeyboardButton("Back", callback_data="back")],
        ]
    )


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Back", callback_data="back")]]
    )


def receipt_action_keyboard(receipt_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve_{receipt_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_{receipt_id}"),
            ],
            [InlineKeyboardButton("Next", callback_data="admin_pending")],
            [InlineKeyboardButton("Back", callback_data="back")],
        ]
    )


# Bot handlers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Welcome! Use the buttons below to deposit CBE receipts and manage your balance.",
        reply_markup=main_menu_keyboard(),
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "deposit":
        context.user_data.clear()
        context.user_data["pending_deposit"] = True
        await query.edit_message_text(
            "Send your CBE receipt text or mbreciept.cbe.com.et link.\n"
            "Example: https://mbreciept.cbe.com.et/v2-hfFiuioHOUGiogiuyOIh",
            reply_markup=main_menu_keyboard(),
        )
        return

    if data == "balance":
        balance = get_user_balance(user_id)
        await query.edit_message_text(
            f"Your balance: {int(balance) if balance.is_integer() else balance} ETB.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if data == "help":
        await query.edit_message_text(
            "Use the buttons to deposit, check balance, or convert services. "
            "Send a receipt link or FT number to top up your wallet.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if data == "pdf_to_id":
        context.user_data.clear()
        context.user_data["expect_pdf"] = True
        price = get_service_price("pdf_to_id_price")
        balance = get_user_balance(user_id)
        await query.edit_message_text(
            f"PDF to ID costs {int(price) if price.is_integer() else price} ETB. "
            f"Your balance: {int(balance) if balance.is_integer() else balance} ETB.\n"
            "Send your PDF document now.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if data == "fan_to_id":
        context.user_data.clear()
        context.user_data["expect_fan"] = True
        price = get_service_price("fan_to_id_price")
        balance = get_user_balance(user_id)
        await query.edit_message_text(
            f"FAN to ID costs {int(price) if price.is_integer() else price} ETB. "
            f"Your balance: {int(balance) if balance.is_integer() else balance} ETB.\n"
            "Send your FAN or FIN number now.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if data == "admin_panel":
        if user_id != ADMIN_ID:
            await query.edit_message_text("Unauthorized.", reply_markup=main_menu_keyboard())
            return
        await query.edit_message_text(
            "Admin dashboard.", reply_markup=admin_menu_keyboard()
        )
        return

    if data == "admin_stats" and user_id == ADMIN_ID:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM receipts")
            total_receipts = cursor.fetchone()[0]
            cursor.execute("SELECT SUM(amount) FROM receipts")
            total_amount = cursor.fetchone()[0] or 0.0
            cursor.execute("SELECT COUNT(*) FROM receipts WHERE status = 'PENDING'")
            pending_count = cursor.fetchone()[0]

        await query.edit_message_text(
            f"Admin stats:\n"
            f"Users: {total_users}\n"
            f"Pending receipts: {pending_count}\n"
            f"All verified receipts: {total_receipts - pending_count}\n"
            f"Total credited: {int(total_amount) if total_amount.is_integer() else total_amount} ETB",
            reply_markup=admin_menu_keyboard(),
        )
        return

    if data == "admin_pending" and user_id == ADMIN_ID:
        receipt = fetch_pending_receipt()
        if not receipt:
            await query.edit_message_text(
                "No pending receipts.", reply_markup=admin_menu_keyboard(),
            )
            return

        (receipt_id, payer_id, raw_text, cbe_link, reference, amount, receiver_account, receiver_name, status, approved_by, manual_note, verified_at) = receipt
        details = (
            f"Receipt #{receipt_id}\n"
            f"User ID: {payer_id}\n"
            f"Amount: {amount} ETB\n"
            f"Status: {status}\n"
            f"Reference: {reference or 'N/A'}\n"
            f"Link: {cbe_link or 'N/A'}\n"
            f"Receiver: {receiver_name or 'N/A'}\n"
            f"Account: {receiver_account or 'N/A'}\n"
            f"Note: {manual_note or 'None'}\n"
            f"Text:\n{raw_text}"
        )
        await query.edit_message_text(details, reply_markup=receipt_action_keyboard(receipt_id))
        return

    if data.startswith("admin_approve_") and user_id == ADMIN_ID:
        receipt_id = int(data.split("_")[2])
        receipt = fetch_pending_receipt(receipt_id)
        if not receipt:
            await query.edit_message_text("Receipt not found or already processed.", reply_markup=admin_menu_keyboard())
            return
        (_, payer_id, raw_text, cbe_link, reference, amount, receiver_account, receiver_name, status, _, _, _) = receipt
        if status != "PENDING":
            await query.edit_message_text("Receipt already processed.", reply_markup=admin_menu_keyboard())
            return
        mark_receipt_verified(receipt_id, approver_id=user_id)
        new_balance = update_user_balance(payer_id, float(amount))
        await query.edit_message_text(
            f"Receipt approved and credited. User {payer_id} balance is now {int(new_balance) if new_balance.is_integer() else new_balance} ETB.",
            reply_markup=admin_menu_keyboard(),
        )
        try:
            await context.bot.send_message(
                chat_id=payer_id,
                text=(
                    "✅ Your payment receipt has been approved by the admin.\n"
                    f"💰 Amount credited: {int(amount) if float(amount).is_integer() else amount} ETB\n"
                    f"💳 New balance: {int(new_balance) if new_balance.is_integer() else new_balance} ETB"
                ),
            )
        except Exception:
            logger.warning("Could not notify user %s after approval.", payer_id)
        return

    if data.startswith("admin_reject_") and user_id == ADMIN_ID:
        receipt_id = int(data.split("_")[2])
        receipt = fetch_pending_receipt(receipt_id)
        if not receipt:
            await query.edit_message_text("Receipt not found or already processed.", reply_markup=admin_menu_keyboard())
            return
        mark_receipt_rejected(receipt_id, approver_id=user_id)
        await query.edit_message_text("Receipt rejected.", reply_markup=admin_menu_keyboard())
        return

    if data == "admin_set_pdf_price" and user_id == ADMIN_ID:
        context.user_data.clear()
        context.user_data["price_update"] = "pdf_to_id_price"
        await query.edit_message_text("Send the new PDF to ID price in ETB.", reply_markup=admin_menu_keyboard())
        return

    if data == "admin_set_fan_price" and user_id == ADMIN_ID:
        context.user_data.clear()
        context.user_data["price_update"] = "fan_to_id_price"
        await query.edit_message_text("Send the new FAN to ID price in ETB.", reply_markup=admin_menu_keyboard())
        return

    if data == "back":
        context.user_data.clear()
        await query.edit_message_text("Back to the main menu.", reply_markup=main_menu_keyboard())
        return

    await query.edit_message_text("Unknown action.", reply_markup=main_menu_keyboard())


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    user_id = update.message.from_user.id

    if context.user_data.get("price_update") and user_id == ADMIN_ID:
        price_key = context.user_data.pop("price_update")
        try:
            new_price = float(text)
            if new_price < 0:
                raise ValueError
            set_setting(price_key, str(new_price))
            await update.message.reply_text(
                f"Updated {price_key.replace('_', ' ')} to {int(new_price) if new_price.is_integer() else new_price} ETB.",
                reply_markup=admin_menu_keyboard(),
            )
        except ValueError:
            await update.message.reply_text("Send a valid positive number for the new price.")
        return

    receipt_data = parse_cbe_receipt(text)
    if receipt_data:
        if receipt_already_used(receipt_data["raw_text"], receipt_data.get("cbe_link"), receipt_data.get("reference")):
            await update.message.reply_text("This receipt or link has already been used.")
            return

        now = datetime.utcnow().timestamp()
        last_time = last_receipt_time.get(user_id, 0)
        if now - last_time < COOLDOWN_SECONDS:
            wait = int(COOLDOWN_SECONDS - (now - last_time))
            await update.message.reply_text(
                f"Please wait {wait} second(s) before sending another receipt."
            )
            return

        last_receipt_time[user_id] = now
        await process_deposit(update, context, receipt_data)
        return

    if context.user_data.get("expect_fan"):
        if not re.fullmatch(r"\d{12,16}", text):
            await update.message.reply_text("Send a valid FAN or FIN number (12-16 digits).")
            return

        price = get_service_price("fan_to_id_price")
        balance = get_user_balance(user_id)
        if balance < price:
            await update.message.reply_text(
                f"Insufficient balance. FAN to ID costs {int(price) if price.is_integer() else price} ETB. "
                f"Your balance: {int(balance) if balance.is_integer() else balance} ETB."
            )
            return

        update_user_balance(user_id, -price)
        context.user_data.clear()
        await update.message.reply_text(
            f"✅ FAN to ID request accepted. {int(price) if price.is_integer() else price} ETB has been deducted. "
            f"Remaining balance: {int(balance - price) if (balance - price).is_integer() else balance - price} ETB.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if context.user_data.get("pending_deposit"):
        await update.message.reply_text(
            "Please send a valid CBE receipt link or text containing an FT number.",
            reply_markup=back_keyboard(),
        )
        return

    await update.message.reply_text(
        "Send a receipt link to top up, or use the buttons to select a service.",
        reply_markup=main_menu_keyboard(),
    )


async def process_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE, receipt_data: dict[str, str | None]) -> None:
    user_id = update.message.from_user.id
    raw_text = receipt_data["raw_text"]
    cbe_link = receipt_data.get("cbe_link")
    reference = receipt_data.get("reference")

    await update.message.reply_text("⏳ Verifying your receipt, please wait...")
    try:
        response = await asyncio.to_thread(verify_cbe_receipt, raw_text, reference)
    except requests.RequestException as exc:
        logger.exception("CBE verifier API request failed")
        create_receipt_record(
            user_id=user_id,
            raw_text=raw_text,
            cbe_link=cbe_link,
            reference=reference,
            amount=0.0,
            receiver_account=None,
            receiver_name=None,
            status="PENDING",
            manual_note=str(exc),
        )
        await update.message.reply_text(
            "Automatic verification failed. Your receipt has been submitted for admin review.",
            reply_markup=main_menu_keyboard(),
        )
        await notify_admin_new_receipt(user_id, raw_text, cbe_link, reference, None, None, "Verifier unavailable")
        return

    if response.status_code != 200:
        error_message = None
        try:
            payload = response.json()
            error_message = payload.get("error") or payload.get("message") or response.text
        except ValueError:
            error_message = response.text or f"HTTP {response.status_code}"
        create_receipt_record(
            user_id=user_id,
            raw_text=raw_text,
            cbe_link=cbe_link,
            reference=reference,
            amount=0.0,
            receiver_account=None,
            receiver_name=None,
            status="PENDING",
            manual_note=error_message,
        )
        await update.message.reply_text(
            f"Verification failed: {error_message}. Your receipt has been sent for admin review.",
            reply_markup=main_menu_keyboard(),
        )
        await notify_admin_new_receipt(user_id, raw_text, cbe_link, reference, None, None, error_message)
        return

    try:
        payload = response.json()
    except ValueError:
        logger.error("Invalid JSON from CBE verifier: %s", response.text)
        create_receipt_record(
            user_id=user_id,
            raw_text=raw_text,
            cbe_link=cbe_link,
            reference=reference,
            amount=0.0,
            receiver_account=None,
            receiver_name=None,
            status="PENDING",
            manual_note="Invalid verifier response",
        )
        await update.message.reply_text(
            "Verifier returned invalid data. Your receipt has been submitted for manual review.",
            reply_markup=main_menu_keyboard(),
        )
        await notify_admin_new_receipt(user_id, raw_text, cbe_link, reference, None, None, "Invalid JSON")
        return

    receiver_account = payload.get("receiverAccount")
    receiver_name = payload.get("receiverName")
    amount = payload.get("amount")
    verified_reference = payload.get("reference") or reference
    date_text = payload.get("date")

    if amount is None or date_text is None:
        error_message = "Missing required fields in verifier response"
        create_receipt_record(
            user_id=user_id,
            raw_text=raw_text,
            cbe_link=cbe_link,
            reference=reference,
            amount=0.0,
            receiver_account=receiver_account,
            receiver_name=receiver_name,
            status="PENDING",
            manual_note=error_message,
        )
        await update.message.reply_text(
            "Verifier returned incomplete data. Your receipt has been submitted for manual review.",
            reply_markup=main_menu_keyboard(),
        )
        await notify_admin_new_receipt(user_id, raw_text, cbe_link, verified_reference, receiver_account, receiver_name, error_message)
        return

    try:
        amount_value = float(amount)
    except (TypeError, ValueError):
        error_message = "Invalid amount returned by verifier"
        create_receipt_record(
            user_id=user_id,
            raw_text=raw_text,
            cbe_link=cbe_link,
            reference=verified_reference,
            amount=0.0,
            receiver_account=receiver_account,
            receiver_name=receiver_name,
            status="PENDING",
            manual_note=error_message,
        )
        await update.message.reply_text(
            "Verifier returned invalid amount. Your receipt has been submitted for manual review.",
            reply_markup=main_menu_keyboard(),
        )
        await notify_admin_new_receipt(user_id, raw_text, cbe_link, verified_reference, receiver_account, receiver_name, error_message)
        return

    if CBE_EXPECTED_ACCOUNT and receiver_account and receiver_account != CBE_EXPECTED_ACCOUNT:
        manual_note = f"Receiver account mismatch: expected {CBE_EXPECTED_ACCOUNT}, got {receiver_account}"
        create_receipt_record(
            user_id=user_id,
            raw_text=raw_text,
            cbe_link=cbe_link,
            reference=verified_reference,
            amount=amount_value,
            receiver_account=receiver_account,
            receiver_name=receiver_name,
            status="PENDING",
            manual_note=manual_note,
        )
        await update.message.reply_text(
            "Receipt needs manual review due receiver account mismatch.",
            reply_markup=main_menu_keyboard(),
        )
        await notify_admin_new_receipt(user_id, raw_text, cbe_link, verified_reference, receiver_account, receiver_name, manual_note)
        return

    create_receipt_record(
        user_id=user_id,
        raw_text=raw_text,
        cbe_link=cbe_link,
        reference=verified_reference,
        amount=amount_value,
        receiver_account=receiver_account,
        receiver_name=receiver_name,
        status="VERIFIED",
    )
    balance = update_user_balance(user_id, amount_value)
    await update.message.reply_text(
        format_success_message(amount_value, date_text, balance),
        reply_markup=main_menu_keyboard(),
    )


async def notify_admin_new_receipt(
    user_id: int,
    raw_text: str,
    cbe_link: str | None,
    reference: str | None,
    receiver_account: str | None,
    receiver_name: str | None,
    note: str,
) -> None:
    if ADMIN_ID == 0:
        return
    text = (
        f"🔔 New receipt requires review\n"
        f"User: {user_id}\n"
        f"Reference: {reference or 'N/A'}\n"
        f"Link: {cbe_link or 'N/A'}\n"
        f"Receiver: {receiver_name or 'N/A'}\n"
        f"Account: {receiver_account or 'N/A'}\n"
        f"Note: {note}\n"
        f"Text:\n{raw_text}"
    )
    try:
        await bot_app.bot.send_message(
            chat_id=ADMIN_ID,
            text=text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Review pending receipts", callback_data="admin_pending")]]
            ),
        )
    except Exception:
        logger.exception("Failed to notify admin about pending receipt")


async def handle_pdf_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if not context.user_data.get("expect_pdf"):
        await update.message.reply_text(
            "Please select PDF to ID from the buttons before sending a PDF.",
            reply_markup=main_menu_keyboard(),
        )
        return

    price = get_service_price("pdf_to_id_price")
    balance = get_user_balance(user_id)
    if balance < price:
        await update.message.reply_text(
            f"Insufficient balance. PDF to ID costs {int(price) if price.is_integer() else price} ETB. "
            f"Your balance: {int(balance) if balance.is_integer() else balance} ETB.",
            reply_markup=main_menu_keyboard(),
        )
        return

    update_user_balance(user_id, -price)
    context.user_data.clear()
    await update.message.reply_text(
        f"✅ PDF received and converted. {int(price) if price.is_integer() else price} ETB has been deducted. "
        f"Remaining balance: {int(balance - price) if (balance - price).is_integer() else balance - price} ETB.",
        reply_markup=main_menu_keyboard(),
    )


# Flask webhook integration

@flask_app.route("/", methods=["GET"])
def health_check():
    return "OK", 200


@flask_app.route("/webhook", methods=["POST"])
async def webhook() -> str:
    global bot_app, bot_ready
    if bot_app is None:
        bot_app = create_bot_application()

    if not bot_ready:
        await bot_app.initialize()
        await bot_app.start()
        bot_ready = True

    data = request.get_json(force=True)
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return "ok"


def create_bot_application() -> object:
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.DOCUMENT.PDF, handle_pdf_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app


async def ensure_bot_ready() -> None:
    global bot_app, bot_ready
    if bot_app is None:
        bot_app = create_bot_application()
    if not bot_ready:
        await bot_app.initialize()
        await bot_app.start()
        bot_ready = True
        if WEBHOOK_URL:
            await bot_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
            logger.info("Webhook registered at %s/webhook", WEBHOOK_URL)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use admin controls.")
        return
    await update.message.reply_text("Admin dashboard.", reply_markup=admin_menu_keyboard())


if __name__ == "__main__":
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required")
    init_db()
    bot_app = create_bot_application()
    if WEBHOOK_URL:
        logger.info("Starting webhook server with URL %s", WEBHOOK_URL)
        asyncio.run(ensure_bot_ready())
        flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    else:
        logger.info("Starting polling bot")
        bot_app.run_polling()
