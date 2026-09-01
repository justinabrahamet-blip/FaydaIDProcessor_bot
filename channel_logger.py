import logging
import datetime
import re
from aiogram import Bot
from config import LOGS_CHANNEL_ID, SALES_CHANNEL_ID

logger = logging.getLogger(__name__)

def mask_user_id(user_id: int | str) -> str:
    """Mask Telegram User ID (e.g. 805123454 -> 805*****4)."""
    val_str = str(user_id).strip()
    if len(val_str) > 4:
        return f"{val_str[:3]}*****{val_str[-1:]}"
    return "***"

def mask_txn_id(txn_id: str) -> str:
    """Mask transaction ID (e.g. FT262429XYZK1 -> FT262429****K*)."""
    val = str(txn_id).strip()
    if len(val) >= 10:
        return f"{val[:8]}****{val[-2:]}"
    elif len(val) >= 6:
        return f"{val[:4]}****{val[-1:]}"
    return f"{val[:2]}****"

def mask_sensitive_data(text: str) -> str:
    """Regex helper to mask phone numbers, accounts, and usernames in log messages."""
    if not text:
        return text
    s = str(text)
    # Mask 1000... account numbers (e.g. 1000320563279 -> 10003*****279)
    s = re.sub(r'\b(1000\d{2})\d+(\d{3})\b', r'\1*****\2', s)
    # Mask phone numbers (e.g. 0912345678 -> 0912***678)
    s = re.sub(r'\b(09\d{2}|07\d{2})\d{3}(\d{3})\b', r'\1***\2', s)
    # Mask Telegram User IDs
    s = re.sub(r'\b(\d{3})\d{3,4}(\d{3})\b', r'\1***\2', s)
    return s

def mask_admin_handle(val: str) -> str:
    """Mask admin handle/username so admin activities remain strictly private."""
    return "[SYSTEM ADMIN]"

async def log_deposit_to_channel(bot: Bot, user_id: int | str, amount: float, provider: str = "CBE", txn_id: str = ""):
    """
    Send verified auto-deposit log to Proof/Logs Channel in exact format requested by admin:
    ⚡ ⚡ AUTO-DEPOSIT VERIFIED 💎
    ▪️ User ID: 805*****4
    ▪️ Provider: CBE
    ▪️ Txn ID: FT262429****K*
    ▪️ Amount: 50.00 Birr
    Admin note: Thank you about purchasing add friend and get commission and giveaway 
    🕒 Timestamp: 30-Aug-2026 10:48 AM
    """
    if not bot or not LOGS_CHANNEL_ID:
        return

    now_str = datetime.datetime.now().strftime("%d-%b-%Y %I:%M %p")
    masked_uid = mask_user_id(user_id)
    masked_txn = mask_txn_id(txn_id) if txn_id else "FT2624****K*"
    prov_name = str(provider).upper() if provider else "CBE"

    from config import emo
    lightning = emo("lightning", "⚡")
    diamond = emo("diamond", "💎")

    msg = (
        f"{lightning} {lightning} <b>AUTO-DEPOSIT VERIFIED {diamond}</b>\n"
        f"▪️ <b>User ID:</b> <code>{masked_uid}</code>\n"
        f"▪️ <b>Provider:</b> <code>{prov_name}</code>\n"
        f"▪️ <b>Txn ID:</b> <code>{masked_txn}</code>\n"
        f"▪️ <b>Amount:</b> <code>{amount:,.2f} Birr</code>\n"
        f"<b>Admin note:</b> Thank you about purchasing add friend and get commission and giveaway\n"
        f"🕒 <b>Timestamp:</b> <code>{now_str}</code>"
    )

    try:
        await bot.send_message(chat_id=LOGS_CHANNEL_ID, text=msg, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Could not send deposit log to logs channel {LOGS_CHANNEL_ID}: {e}")

async def log_purchase_to_channel(bot: Bot, user_id: int | str, product_name: str, quantity: int = 1, price: float = 0.0):
    """
    Send animated styled purchase log to both Sales Channel and Proof/Logs Channel.
    User ID and sensitive credentials are 100% strictly masked.
    """
    if not bot:
        return

    now_str = datetime.datetime.now().strftime("%d-%b-%Y %I:%M %p")
    masked_id = mask_user_id(user_id)

    # 1. Main / Sales Channel Announcement
    sales_msg = (
        f"💎 <b>MELAX DIGITAL SHOP | NEW ORDER DELIVERED ⚡</b>\n\n"
        f"✨ <b>Product:</b> 🤖 <code>{product_name}</code>\n"
        f"📦 <b>Quantity:</b> <code>{quantity}x</code>\n"
        f"💰 <b>Amount:</b> <code>{price:,.0f} Birr</code>\n"
        f"👤 <b>Customer:</b> <code>{masked_id}</code>\n"
        f"🚀 <b>Delivery:</b> 🟢 <b>Instant Automated Delivery</b>\n"
        f"🕒 <b>Date:</b> <code>{now_str}</code>\n\n"
        f"👑 <i>Thank you for choosing MELAX DIGITAL SHOP!</i> 🌟"
    )

    # 2. Proof & Logs Channel Entry
    logs_msg = (
        f"⚡ <b>VERIFIED PURCHASE & INSTANT DELIVERY LOG 🛡️</b>\n\n"
        f"🆔 <b>Customer ID:</b> <code>{masked_id}</code>\n"
        f"🤖 <b>Product:</b> <code>{product_name}</code>\n"
        f"📦 <b>Quantity:</b> <code>{quantity}x</code>\n"
        f"💰 <b>Price:</b> <code>{price:,.0f} Birr</code>\n"
        f"🔑 <b>Key/Credentials:</b> <code>[SECURELY DELIVERED IN BOT]</code>\n"
        f"🕒 <b>Timestamp:</b> <code>{now_str}</code>\n"
        f"🟢 <b>Status:</b> <code>SUCCESS (100% AUTOMATED)</code>"
    )

    if SALES_CHANNEL_ID:
        try:
            await bot.send_message(chat_id=SALES_CHANNEL_ID, text=sales_msg, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Could not send purchase announcement to sales channel {SALES_CHANNEL_ID}: {e}")

    if LOGS_CHANNEL_ID:
        try:
            await bot.send_message(chat_id=LOGS_CHANNEL_ID, text=logs_msg, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Could not send purchase log to channel {LOGS_CHANNEL_ID}: {e}")

async def log_to_channel(bot: Bot, event_title: str, details: dict):
    """
    Send general event log to Logs Channel with animated styling.
    All sensitive details, admin actions, and IDs are strictly masked.
    """
    if not bot or not LOGS_CHANNEL_ID:
        return

    # Suppress all internal admin actions, setting edits, and product changes from public logs channel
    if any(k in event_title.upper() for k in ["ADMIN", "BANK SETTING", "PRICE CHANGED", "NAME CHANGED", "PRODUCT", "DESCRIPTION", "BANNED", "UNBANNED", "MAINTENANCE", "SECURITY", "PAYMENT METHOD"]):
        logger.info(f"Internal Admin log '{event_title}' suppressed from public logs channel.")
        return

    now_str = datetime.datetime.now().strftime("%d-%b-%Y %I:%M %p")
    msg = f"⚡ <b>{event_title} 💎</b>\n\n"
    
    for k, v in details.items():
        val_str = str(v)
        if "Admin" in k:
            val_str = mask_admin_handle(val_str)
        elif "User" in k or "Customer" in k:
            val_str = mask_user_id(v)
        elif "ID" in k and isinstance(v, (int, str)) and str(v).isdigit():
            val_str = mask_user_id(v)
        elif "Code" in k or "Delivered" in k or "Key" in k:
            val_str = "[SECURELY DELIVERED TO USER]"
        else:
            val_str = mask_sensitive_data(val_str)
            
        msg += f"▪️ <b>{k}:</b> <code>{val_str}</code>\n"
        
    msg += f"\n🕒 <b>Timestamp:</b> <code>{now_str}</code>"

    try:
        await bot.send_message(
            chat_id=LOGS_CHANNEL_ID,
            text=msg,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Could not send event log to channel {LOGS_CHANNEL_ID}: {e}")
