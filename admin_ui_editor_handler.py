"""
Admin In-Place Visual UI Component Editor Handler.
Enables Main Admins to directly customize every user-facing UI component
(products, welcome messages, referral cards, wallet instructions, support guides, buttons)
in-place from Telegram with Three-Tier Override Hierarchy and server-side security.
"""

import logging
import html
import re
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db_client import db
from config import ADMIN_IDS, emo, animate_text, get_product_brand_icon
from security_util import sanitize_input, format_4digit_id
from channel_logger import log_to_channel

logger = logging.getLogger(__name__)
router = Router()

class AdminUIEditorStates(StatesGroup):
    waiting_for_product_field = State()
    waiting_for_ui_text = State()

async def is_main_admin(user_id: int) -> bool:
    """Strict server-side validation ensuring only authorized Main Admins can execute customization."""
    if user_id in ADMIN_IDS:
        return True
    role = await db.get_admin_role(user_id)
    return role is not None

# =========================================================================
# 1. IN-PLACE PRODUCT COMPONENT EDITOR
# =========================================================================

@router.callback_query(F.data.startswith("adm_edit_prod:"))
async def open_product_component_editor(query: CallbackQuery):
    """Open the in-place visual editor for a specific product component."""
    if not (await is_main_admin(query.from_user.id)):
        await query.answer("⛔ Access Denied. Admin only.", show_alert=True)
        return

    service_id = query.data.split(":", 1)[1]
    product = await db.get_effective_product(service_id)
    if not product:
        await query.answer("⚠️ Product not found.", show_alert=True)
        return

    short_id = format_4digit_id(service_id)
    brand_icon = product.get("emoji") or get_product_brand_icon(product["name"])
    has_override = bool(product.get("has_admin_override"))
    agent_comm = float(product.get("agent_commission_percent", 5.0) or 0.0)
    eff_comm = float(product.get("referral_commission_percent", 5.0) or 0.0)
    eff_price = float(product.get("selling_price", 0.0))
    calc_comm_amt = float(product.get("calculated_commission_amount", 0.0))

    override_badge = "👑 <b>MAIN ADMIN OVERRIDE ACTIVE</b>" if has_override else "⚙️ <b>DEFAULT AGENT CONFIGURATION</b>"

    editor_text = (
        f"✏️ <b>IN-PLACE PRODUCT EDITOR</b> 💎\n\n"
        f"{override_badge}\n\n"
        f"▪️ <b>Product Name:</b> <code>{product['name']}</code>\n"
        f"▪️ <b>Brand Emoji:</b> <code>{brand_icon}</code>\n"
        f"▪️ <b>Selling Price:</b> <code>{eff_price:,.2f} Birr</code> (Base: {product.get('agent_price', eff_price):,.2f} Birr)\n"
        f"▪️ <b>Commission %:</b> <code>{eff_comm}%</code> (Agent Base: <code>{agent_comm}%</code>)\n"
        f"▪️ <b>Calculated Earnings:</b> <code>+{calc_comm_amt:,.2f} Birr</code> / sale\n"
        f"▪️ <b>Custom Comm Note:</b> <i>{product.get('custom_commission_text') or '(Dynamic Auto-Generated)'}</i>\n"
        f"▪️ <b>Buy Button Label:</b> <code>{product.get('custom_button_text') or 'BUY NOW / አሁን ግዛ'}</code>\n"
        f"▪️ <b>Description:</b>\n<i>{product.get('description', 'No description')}</i>\n\n"
        f"👉 <i>Click any property below to edit it in-place:</i>"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📦 Digital Stock Vault (70+ Items) ⚡", callback_data=f"adm_stock_pool:{service_id}")
    )
    builder.row(
        InlineKeyboardButton(text="✏️ Edit Name", callback_data=f"adm_edit_field:{service_id}:name"),
        InlineKeyboardButton(text="💰 Edit Price", callback_data=f"adm_edit_field:{service_id}:price")
    )
    builder.row(
        InlineKeyboardButton(text="🎨 Edit Emoji", callback_data=f"adm_edit_field:{service_id}:emoji"),
        InlineKeyboardButton(text="🎁 Edit Commission %", callback_data=f"adm_edit_field:{service_id}:comm")
    )
    builder.row(
        InlineKeyboardButton(text="💬 Edit Comm Note", callback_data=f"adm_edit_field:{service_id}:comm_text"),
        InlineKeyboardButton(text="🔘 Edit Button Text", callback_data=f"adm_edit_field:{service_id}:btn_text")
    )
    builder.row(
        InlineKeyboardButton(text="📝 Edit Full Description", callback_data=f"adm_edit_field:{service_id}:desc")
    )

    if has_override:
        builder.row(
            InlineKeyboardButton(text="🔄 Reset to Agent Default", callback_data=f"adm_reset_prod:{service_id}")
        )

    builder.row(
        InlineKeyboardButton(text="🔙 Back to Product Card", callback_data=f"prod_select:{service_id}"),
        InlineKeyboardButton(text="❌ Close", callback_data="btn_cancel")
    )

    await query.message.edit_text(
        text=animate_text(editor_text),
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("adm_edit_field:"))
async def prompt_edit_product_field(query: CallbackQuery, state: FSMContext):
    """Prompt admin to enter the new value for a chosen product field."""
    if not (await is_main_admin(query.from_user.id)):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    parts = query.data.split(":")
    service_id = parts[1]
    field = parts[2]

    product = await db.get_effective_product(service_id)
    if not product:
        await query.answer("⚠️ Product not found.", show_alert=True)
        return

    field_labels = {
        "name": ("Product Title / Name", product["name"], "e.g. '✨ Gemini Pro 18 Months'"),
        "price": ("Selling Price in Birr", f"{product['selling_price']:,.2f} Birr", "e.g. '380' or '450'"),
        "emoji": ("Brand / Category Emoji", product.get("emoji", "✨"), "e.g. '✨', '🎬', '🤖', '🎧'"),
        "comm": ("Referral Commission %", f"{product['referral_commission_percent']}%", "e.g. '15' for 15%, '10' for 10%, or '0' for none"),
        "comm_text": ("Custom Commission Explanation Note", product.get("custom_commission_text", "(Dynamic)"), "e.g. '🎁 Earn 15% instant commission when friends buy this item!'"),
        "btn_text": ("Action Button Label", product.get("custom_button_text", "BUY NOW"), "e.g. '🛍️ BUY NOW' or '⚡ INSTANT BUY'"),
        "desc": ("Product Description / Features", product.get("description", ""), "Type full HTML-supported description:")
    }

    title, current_val, hint = field_labels.get(field, ("Property", "", "Type new value:"))

    await state.update_data(target_service_id=service_id, target_field=field, target_name=product["name"])
    await state.set_state(AdminUIEditorStates.waiting_for_product_field)

    prompt = (
        f"✏️ <b>EDIT PRODUCT PROPERTY: {title.upper()}</b>\n\n"
        f"▪️ <b>Product:</b> <code>{product['name']}</code>\n"
        f"▪️ <b>Current Value:</b> <code>{current_val}</code>\n\n"
        f"👉 <b>Please type and send the NEW value</b> ({hint}):"
    )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Back to Product Editor", callback_data=f"adm_edit_prod:{service_id}"))
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="btn_cancel"))

    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=builder.as_markup())

@router.message(AdminUIEditorStates.waiting_for_product_field)
async def save_product_field_override(message: Message, state: FSMContext, bot: Bot):
    """Receive and save the field override in Main Admin override storage."""
    user = message.from_user
    if not (await is_main_admin(user.id)):
        await state.clear()
        return

    data = await state.get_data()
    service_id = data["target_service_id"]
    field = data["target_field"]
    prod_name = data.get("target_name", service_id)
    raw_input = message.text.strip()

    is_safe, sanitized_text = sanitize_input(raw_input)
    if not is_safe:
        await message.answer("⚠️ Security Alert: Input contains unsafe characters. Rejected.")
        await state.clear()
        return

    # Field-specific parsing and mapping
    if field == "price":
        try:
            val = float(sanitized_text.replace(",", "").replace("Birr", "").strip())
            if val < 0:
                raise ValueError()
            db_field = "selling_price"
            db_val = val
        except ValueError:
            await message.answer("⚠️ Invalid price number. Please send a positive number (e.g. 380):")
            return
    elif field == "comm":
        try:
            val = float(sanitized_text.replace("%", "").strip())
            if val < 0 or val > 100:
                raise ValueError()
            db_field = "referral_commission_percent"
            db_val = val
        except ValueError:
            await message.answer("⚠️ Invalid commission %. Please send a number between 0 and 100 (e.g. 15):")
            return
    elif field == "name":
        db_field = "name"
        db_val = sanitized_text
    elif field == "emoji":
        db_field = "emoji"
        db_val = sanitized_text
    elif field == "comm_text":
        db_field = "commission_text"
        db_val = sanitized_text
    elif field == "btn_text":
        db_field = "button_text"
        db_val = sanitized_text
    elif field == "desc":
        db_field = "description"
        db_val = message.html_text if message.html_text else sanitized_text
    else:
        db_field = field
        db_val = sanitized_text

    # Set Three-Tier Main Admin Override (preserves baseline agent product)
    await db.set_product_override(service_id, db_field, db_val)
    await state.clear()

    # Re-fetch effective product
    effective_p = await db.get_effective_product(service_id)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Re-Open Component Editor", callback_data=f"adm_edit_prod:{service_id}"))
    builder.row(InlineKeyboardButton(text="👁️ View Product Card in Shop", callback_data=f"prod_select:{service_id}"))
    builder.row(InlineKeyboardButton(text="🔙 Back to Products", callback_data="btn_shop"))

    confirm_msg = (
        f"✅ <b>PROPERTY SAVED SUCCESSFULLY! 💎</b>\n\n"
        f"▪️ <b>Product:</b> <code>{effective_p['name']}</code>\n"
        f"▪️ <b>Updated Property:</b> <code>{db_field}</code>\n"
        f"▪️ <b>Effective Value:</b> <code>{db_val}</code>\n"
        f"▪️ <b>Calculated Commission:</b> <code>+{effective_p.get('calculated_commission_amount', 0):,.2f} Birr</code> / sale\n\n"
        f"<i>👑 Main Admin Override is now active and live across all cards!</i>"
    )
    await message.answer(text=confirm_msg, parse_mode="HTML", reply_markup=builder.as_markup())

    await log_to_channel(bot, "👑 ADMIN PRODUCT OVERRIDE SAVED", {
        "Admin": f"@{user.username}" if user.username else user.first_name,
        "Product": prod_name,
        "Service ID": service_id,
        "Field": db_field,
        "New Value": str(db_val)
    })

@router.callback_query(F.data.startswith("adm_reset_prod:"))
async def reset_product_overrides(query: CallbackQuery):
    """Reset all admin overrides on a product, cleanly falling back to Agent baseline value."""
    if not (await is_main_admin(query.from_user.id)):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    service_id = query.data.split(":", 1)[1]
    await db.remove_product_override(service_id)
    await query.answer("🔄 Reset to Agent Default successful!", show_alert=True)

    # Re-open product component editor
    query.data = f"adm_edit_prod:{service_id}"
    await open_product_component_editor(query)

# =========================================================================
# 2. IN-PLACE SYSTEM UI COMPONENT EDITOR (Welcome, Referral, Wallet, etc.)
# =========================================================================

UI_COMPONENT_MAP = {
    "welcome": {
        "title": "Welcome / Start Screen",
        "keys": ["welcome_body", "welcome_title"],
        "back_cb": "btn_main_menu"
    },
    "referral": {
        "title": "Referral Program Card & Rewards",
        "keys": ["referral_body", "referral_rules"],
        "back_cb": "btn_referral"
    },
    "wallet": {
        "title": "Wallet & Payment Instructions",
        "keys": ["wallet_body", "deposit_instructions"],
        "back_cb": "btn_wallet"
    },
    "support": {
        "title": "Support & Guide Content",
        "keys": ["support_guide_body", "support_faq"],
        "back_cb": "btn_support"
    },
    "profile": {
        "title": "My Profile Screen",
        "keys": ["profile_body"],
        "back_cb": "btn_profile"
    },
    "orders": {
        "title": "My Orders Screen",
        "keys": ["orders_empty_body"],
        "back_cb": "btn_orders"
    },
    "channels": {
        "title": "Official Channels & Proof Links",
        "keys": ["channel_banner_body"],
        "back_cb": "btn_main_menu"
    },
    "maintenance": {
        "title": "Maintenance Mode Alert",
        "keys": ["maintenance_alert"],
        "back_cb": "adm_dashboard"
    }
}

@router.callback_query(F.data.startswith("adm_edit_ui:"))
async def open_ui_component_editor(query: CallbackQuery):
    """Open in-place editor for system UI components (Welcome, Referral, Wallet, etc.)."""
    if not (await is_main_admin(query.from_user.id)):
        await query.answer("⛔ Access Denied. Admin only.", show_alert=True)
        return

    comp_id = query.data.split(":", 1)[1]
    comp = UI_COMPONENT_MAP.get(comp_id)
    if not comp:
        await query.answer("⚠️ Component not found.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for key in comp["keys"]:
        builder.row(
            InlineKeyboardButton(text=f"✏️ Edit AM ({key})", callback_data=f"adm_edit_txt:{key}:am:{comp_id}"),
            InlineKeyboardButton(text=f"✏️ Edit EN ({key})", callback_data=f"adm_edit_txt:{key}:en:{comp_id}")
        )
        builder.row(
            InlineKeyboardButton(text=f"🔄 Reset ({key})", callback_data=f"adm_reset_txt:{key}:{comp_id}")
        )

    builder.row(
        InlineKeyboardButton(text="🔙 Back to Component", callback_data=comp.get("back_cb", "btn_main_menu")),
        InlineKeyboardButton(text="❌ Close", callback_data="btn_cancel")
    )

    sample_am = await db.get_ui_text(comp["keys"][0], lang="am")
    sample_en = await db.get_ui_text(comp["keys"][0], lang="en")

    editor_card = (
        f"✏️ <b>IN-PLACE UI COMPONENT EDITOR: {comp['title'].upper()}</b> 💎\n\n"
        f"<b>Current Amharic (AM) Content:</b>\n<i>{html.escape(sample_am[:200])}...</i>\n\n"
        f"<b>Current English (EN) Content:</b>\n<i>{html.escape(sample_en[:200])}...</i>\n\n"
        f"👉 <i>Click a language button below to customize this text in-place:</i>"
    )

    await query.message.edit_text(
        text=animate_text(editor_card),
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("adm_edit_txt:"))
async def prompt_edit_ui_text(query: CallbackQuery, state: FSMContext):
    """Prompt admin to enter the new custom UI message text."""
    if not (await is_main_admin(query.from_user.id)):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    parts = query.data.split(":")
    ui_key = parts[1]
    lang = parts[2]
    comp_id = parts[3] if len(parts) > 3 else "welcome"

    current_text = await db.get_ui_text(ui_key, lang=lang)

    await state.update_data(target_ui_key=ui_key, target_lang=lang, target_comp_id=comp_id)
    await state.set_state(AdminUIEditorStates.waiting_for_ui_text)

    prompt = (
        f"✏️ <b>EDIT UI TEXT: <code>{ui_key}</code> ({lang.upper()})</b>\n\n"
        f"<b>Current Content:</b>\n<i>{html.escape(current_text)}</i>\n\n"
        f"👉 <b>Please type and send the NEW custom text</b> (HTML formatting allowed):\n"
        f"<i>(Use variables like {{name}}, {{balance}}, {{commission}} where appropriate)</i>"
    )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Back to Component Editor", callback_data=f"adm_edit_ui:{comp_id}"))
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="btn_cancel"))

    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=builder.as_markup())

@router.message(AdminUIEditorStates.waiting_for_ui_text)
async def save_ui_text_override(message: Message, state: FSMContext, bot: Bot):
    """Receive and save the custom UI text override."""
    user = message.from_user
    if not (await is_main_admin(user.id)):
        await state.clear()
        return

    data = await state.get_data()
    ui_key = data["target_ui_key"]
    lang = data["target_lang"]
    comp_id = data.get("target_comp_id", "welcome")

    custom_text = message.html_text if message.html_text else message.text.strip()
    await db.set_ui_text_override(ui_key, custom_text, lang=lang)
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Re-Open Component Editor", callback_data=f"adm_edit_ui:{comp_id}"))
    builder.row(InlineKeyboardButton(text="🔙 Back to Component", callback_data=UI_COMPONENT_MAP.get(comp_id, {}).get("back_cb", "btn_main_menu")))

    confirm_msg = (
        f"✅ <b>UI TEXT SAVED SUCCESSFULLY! 💎</b>\n\n"
        f"▪️ <b>Key:</b> <code>{ui_key}</code> ({lang.upper()})\n"
        f"▪️ <b>New Content Preview:</b>\n<i>{html.escape(custom_text)}</i>\n\n"
        f"<i>👑 Main Admin Override is now active live for all customers!</i>"
    )
    await message.answer(text=confirm_msg, parse_mode="HTML", reply_markup=builder.as_markup())

    await log_to_channel(bot, "👑 ADMIN UI TEXT OVERRIDE SAVED", {
        "Admin": f"@{user.username}" if user.username else user.first_name,
        "UI Key": ui_key,
        "Language": lang.upper()
    })

@router.callback_query(F.data.startswith("adm_reset_txt:"))
async def reset_ui_text_override(query: CallbackQuery):
    """Reset a UI text key back to system default."""
    if not (await is_main_admin(query.from_user.id)):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    parts = query.data.split(":")
    ui_key = parts[1]
    comp_id = parts[2] if len(parts) > 2 else "welcome"

    await db.remove_ui_text_override(ui_key)
    await query.answer(f"🔄 Key '{ui_key}' reset to default!", show_alert=True)

    query.data = f"adm_edit_ui:{comp_id}"
    await open_ui_component_editor(query)
