import logging
import uuid
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db_client import db
from api_client import api_client
from config import ADMIN_IDS
from keyboards import (
    get_admin_products_keyboard,
    get_admin_product_list_keyboard,
    get_admin_product_card_keyboard,
    get_stock_pool_keyboard,
    get_product_template_keyboard,
    get_created_product_actions_keyboard,
    get_delivery_mode_keyboard,
    get_delete_product_confirm_keyboard,
    get_product_detail_keyboard,
    get_back_keyboard,
    get_back_cancel_keyboard
)
from channel_logger import log_to_channel
from security_util import sanitize_input, format_4digit_id

logger = logging.getLogger(__name__)
router = Router()

class AdminProductStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_price = State()
    waiting_for_desc = State()
    waiting_for_commission_percent = State()
    waiting_for_stock_items = State()
    waiting_for_manual_name = State()
    waiting_for_manual_price = State()
    waiting_for_manual_stock = State()
    waiting_for_manual_delivery_type = State()
    waiting_for_manual_desc = State()
    waiting_for_manual_commission = State()
    waiting_for_manual_order_key = State()

@router.callback_query(F.data == "adm_view_all_prods")
async def view_all_admin_products(query: CallbackQuery):
    """Display interactive list of all products imported from AIVerse & Manual products."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    products = await db.get_all_products(enabled_only=False)
    if not products:
        await query.message.edit_text(
            "🛍️ <b>PRODUCT CATALOG IS EMPTY</b>\n\nClick '➕ ADD NEW MANUAL PRODUCT' or '🔄 SYNC PRODUCTS' to add products.",
            parse_mode="HTML",
            reply_markup=get_admin_products_keyboard()
        )
        return

    text = (
        f"📦 <b>MANAGE PRODUCTS CATALOG ({len(products)} Total Items)</b>\n\n"
        f"Select any product below to view its <b>4-Digit Service ID</b>, Supplier Cost, and edit selling price or description:"
    )
    await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=get_admin_product_list_keyboard(products))

@router.callback_query(F.data == "adm_add_manual_prod")
async def init_add_manual_product(query: CallbackQuery, state: FSMContext):
    """Step 1: Choose from popular pre-set templates or type custom product name."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    await state.set_state(AdminProductStates.waiting_for_manual_name)
    prompt_text = (
        "➕ <b>ADD NEW MANUAL PRODUCT (STEP 1/5)</b>\n\n"
        "<i>Select a popular digital product template below or type a custom product name:</i>\n\n"
        "👉 Click any template button, or send your custom name in the chat:"
    )
    await query.message.edit_text(
        text=prompt_text,
        parse_mode="HTML",
        reply_markup=get_product_template_keyboard()
    )

@router.callback_query(F.data.startswith("prod_tmpl:"))
async def process_product_template_choice(query: CallbackQuery, state: FSMContext):
    """Handle choice of pre-set product template."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    val = query.data.split(":", 1)[1]
    if val == "custom":
        await state.set_state(AdminProductStates.waiting_for_manual_name)
        prompt_text = (
            "✍️ <b>TYPE CUSTOM PRODUCT NAME</b>\n\n"
            "👉 Please type and send the <b>Product Name</b> (e.g. <code>ExpressVPN 1 Year</code> or <code>Steam Gift Card 50$</code>):"
        )
        await query.message.edit_text(text=prompt_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_add_manual_prod", cancel_callback="btn_cancel"))
        return

    # User selected a template
    await state.update_data(manual_name=val)
    await state.set_state(AdminProductStates.waiting_for_manual_price)

    prompt_text = (
        f"💰 <b>PRODUCT SELLING PRICE (STEP 2/5)</b>\n\n"
        f"▪️ <b>Product:</b> <code>{val}</code>\n\n"
        f"👉 Please type and send the <b>Selling Price in Birr</b> (e.g. <code>1200</code>):"
    )
    await query.message.edit_text(text=prompt_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_add_manual_prod", cancel_callback="btn_cancel"))

@router.message(AdminProductStates.waiting_for_manual_name)
async def process_manual_name(message: Message, state: FSMContext):
    """Step 2: Prompt admin for selling price."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    is_safe, sanitized_name = sanitize_input(message.text.strip())
    if not is_safe or len(sanitized_name) < 2:
        await message.answer("⚠️ Invalid product name. Please type a valid name:", reply_markup=get_back_cancel_keyboard(back_callback="adm_products", cancel_callback="btn_cancel"))
        return

    await state.update_data(manual_name=sanitized_name)
    await state.set_state(AdminProductStates.waiting_for_manual_price)

    prompt_text = (
        f"💰 <b>PRODUCT SELLING PRICE (STEP 2/4)</b>\n\n"
        f"▪️ <b>Product:</b> <code>{sanitized_name}</code>\n\n"
        f"👉 Please type and send the <b>Selling Price in Birr</b> (e.g. <code>1200</code>):"
    )
    await message.answer(text=prompt_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_products", cancel_callback="btn_cancel"))

@router.message(AdminProductStates.waiting_for_manual_price)
async def process_manual_price(message: Message, state: FSMContext):
    """Step 3: Prompt admin for stock quantity."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    try:
        price = float(message.text.strip().replace(",", ""))
        if price <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Invalid price. Please send a positive number (e.g. 1500):", reply_markup=get_back_cancel_keyboard(back_callback="adm_products", cancel_callback="btn_cancel"))
        return

    await state.update_data(manual_price=price)
    await state.set_state(AdminProductStates.waiting_for_manual_stock)

    data = await state.get_data()
    prompt_text = (
        f"📦 <b>PRODUCT STOCK QUANTITY (STEP 3/4)</b>\n\n"
        f"▪️ <b>Product:</b> <code>{data['manual_name']}</code>\n"
        f"▪️ <b>Price:</b> <code>{price:,.2f} Birr</code>\n\n"
        f"👉 Please type and send the <b>Available Stock Quantity</b> (e.g. <code>50</code> or <code>100</code>):"
    )
    await message.answer(text=prompt_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_products", cancel_callback="btn_cancel"))

@router.message(AdminProductStates.waiting_for_manual_stock)
async def process_manual_stock(message: Message, state: FSMContext):
    """Step 4: Prompt admin to choose product Delivery Mode (AUTOMATIC, MANUAL, HYBRID)."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    raw_stock = message.text.strip()
    if not raw_stock.isdigit():
        await message.answer("⚠️ Invalid stock number. Please type an integer (e.g. 25):", reply_markup=get_back_cancel_keyboard(back_callback="adm_products", cancel_callback="btn_cancel"))
        return

    stock = int(raw_stock)
    await state.update_data(manual_stock=stock)
    await state.set_state(AdminProductStates.waiting_for_manual_delivery_type)

    data = await state.get_data()
    prompt_text = (
        f"🚚 <b>CHOOSE PRODUCT DELIVERY MODE (STEP 4/5)</b>\n\n"
        f"▪️ <b>Product:</b> <code>{data['manual_name']}</code>\n"
        f"▪️ <b>Price:</b> <code>{data['manual_price']:,.2f} Birr</code>\n"
        f"▪️ <b>Stock:</b> <code>{stock}</code>\n\n"
        f"<b>Select how the bot will deliver this product to customers:</b>\n\n"
        f"⚡ <b>AUTOMATIC:</b> Instant auto-delivery after payment from pre-set message / stock keys.\n"
        f"👨‍💻 <b>MANUAL:</b> Customer pays ➡️ order is routed to Admin Dashboard for manual fulfillment.\n"
        f"🔄 <b>HYBRID:</b> Auto-delivers instantly, but if stock runs out, automatically routes to Admin Manual without canceling!\n\n"
        f"👉 <i>Click a delivery mode below:</i>"
    )
    await message.answer(text=prompt_text, parse_mode="HTML", reply_markup=get_delivery_mode_keyboard())

@router.callback_query(F.data.startswith("deliv_mode:"))
async def process_delivery_mode_selection(query: CallbackQuery, state: FSMContext):
    """Step 5: Receive chosen delivery mode and prompt for description / custom holding message."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    deliv_type = query.data.split(":", 1)[1]  # AUTOMATIC, MANUAL, or HYBRID
    await state.update_data(manual_delivery_type=deliv_type)
    await state.set_state(AdminProductStates.waiting_for_manual_desc)

    data = await state.get_data()
    
    if deliv_type == "AUTOMATIC":
        prompt_text = (
            f"📝 <b>INSTANT DELIVERY MESSAGE / CREDENTIALS FORMAT (STEP 5/5)</b>\n\n"
            f"▪️ <b>Product:</b> <code>{data['manual_name']}</code>\n"
            f"▪️ <b>Delivery Mode:</b> <code>⚡ AUTOMATIC</code>\n\n"
            f"👉 Please send the <b>Instant Account Details / Access Code / Link</b> delivered to customer immediately upon purchase:"
        )
    elif deliv_type == "MANUAL":
        prompt_text = (
            f"📝 <b>CUSTOMER HOLDING INSTRUCTIONS / NOTE (STEP 5/5)</b>\n\n"
            f"▪️ <b>Product:</b> <code>{data['manual_name']}</code>\n"
            f"▪️ <b>Delivery Mode:</b> <code>👨‍💻 MANUAL (Admin Fulfillment)</code>\n\n"
            f"👉 Please send the <b>Holding Message</b> shown to customers after they pay while waiting for admin delivery\n"
            f"<i>(e.g. 'Your order has been received! Our admin will send your login credentials here within 5-10 minutes.')</i>:"
        )
    else:  # HYBRID
        prompt_text = (
            f"📝 <b>HYBRID DELIVERY TEMPLATE & FALLBACK NOTE (STEP 5/5)</b>\n\n"
            f"▪️ <b>Product:</b> <code>{data['manual_name']}</code>\n"
            f"▪️ <b>Delivery Mode:</b> <code>🔄 HYBRID (Smart Auto + Manual Fallback)</code>\n\n"
            f"👉 Please send the <b>Delivery Template / Fallback Message</b>:"
        )

    await query.message.edit_text(text=prompt_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_products", cancel_callback="btn_cancel"))

@router.message(AdminProductStates.waiting_for_manual_desc)
async def process_manual_desc(message: Message, state: FSMContext, bot: Bot):
    """Step 5: Receive description and prompt for Referral Commission Percentage (Step 6/6)."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    is_safe, sanitized_desc = sanitize_input(message.text.strip())
    await state.update_data(manual_desc=sanitized_desc)
    await state.set_state(AdminProductStates.waiting_for_manual_commission)

    data = await state.get_data()
    prompt_text = (
        f"🎁 <b>REFERRAL PURCHASE COMMISSION (STEP 6/6)</b>\n\n"
        f"▪️ <b>Product:</b> <code>{data.get('manual_name', 'Product')}</code>\n"
        f"▪️ <b>Price:</b> <code>{data.get('manual_price', 0.0):,.2f} Birr</code>\n\n"
        f"👉 Please type and send the <b>Referral Commission %</b> awarded to the inviter when a referred user buys this item\n"
        f"<i>(e.g. Type <code>10</code> for 10%, <code>5</code> for 5%, or <code>0</code> for none)</i>:"
    )
    await message.answer(text=prompt_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_products", cancel_callback="btn_cancel"))

@router.message(AdminProductStates.waiting_for_manual_commission)
async def process_manual_commission(message: Message, state: FSMContext, bot: Bot):
    """Final Step 6: Save manual product with delivery mode and commission percentage."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    input_comm = message.text.strip().replace("%", "")
    try:
        comm_pct = float(input_comm)
        if comm_pct < 0 or comm_pct > 100:
            comm_pct = 5.0
    except ValueError:
        comm_pct = 5.0

    data = await state.get_data()
    await state.clear()

    name = data.get("manual_name", "Product")
    price = data.get("manual_price", 0.0)
    stock = data.get("manual_stock", 100)
    deliv_type = data.get("manual_delivery_type", "AUTOMATIC")
    sanitized_desc = data.get("manual_desc", "Instant delivery completed.")
    s_id = f"MANUAL_{uuid.uuid4().hex[:6].upper()}"

    res = await db.create_manual_product(
        name=name,
        selling_price=price,
        stock=stock,
        description=sanitized_desc,
        service_id=s_id,
        delivery_type=deliv_type,
        manual_fulfillment_note=sanitized_desc,
        referral_commission_percent=comm_pct
    )

    short_id = format_4digit_id(s_id)
    deliv_icon = "⚡" if deliv_type == "AUTOMATIC" else ("👨‍💻" if deliv_type == "MANUAL" else "🔄")
    comm_amount = round(price * (comm_pct / 100.0), 2)
    
    success_text = (
        f"🎉 <b>MANUAL PRODUCT CREATED SUCCESSFULLY!</b>\n\n"
        f"💎 <b>Product:</b> #{short_id} {name}\n"
        f"🆔 <b>Service ID:</b> <code>{s_id}</code>\n"
        f"🚚 <b>Delivery Mode:</b> <code>{deliv_icon} {deliv_type}</code>\n"
        f"💰 <b>Selling Price:</b> <code>{price:,.2f} Birr</code>\n"
        f"🎁 <b>Referral Commission:</b> <code>{comm_pct}%</code> (+{comm_amount:,.2f} Birr per sale)\n"
        f"📦 <b>Stock:</b> <code>{stock}</code>\n"
        f"🟢 <b>Status:</b> <code>Enabled & Live in Shop</code>\n\n"
        f"📝 <b>Delivery / Holding Note:</b>\n<i>{sanitized_desc}</i>"
    )
    await message.answer(text=success_text, parse_mode="HTML", reply_markup=get_created_product_actions_keyboard(s_id))
    await log_to_channel(bot, "🛍️ NEW MANUAL PRODUCT CREATED", {
        "Admin": f"@{user.username}" if user.username else user.first_name,
        "Product": name,
        "Service ID": s_id,
        "Delivery Mode": deliv_type,
        "Price": f"{price:,.2f} Birr",
        "Commission": f"{comm_pct}%",
        "Stock": stock
    })

@router.callback_query(F.data.startswith("adm_prod_view:"))
async def view_single_admin_product(query: CallbackQuery):
    """View detailed product admin card with 4-digit ID and interactive action buttons."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    service_id = query.data.split(":", 1)[1]
    product = await db.get_product_by_service_id(service_id)

    if not product:
        await query.message.edit_text("⚠️ Product not found.", reply_markup=get_admin_products_keyboard())
        return

    supplier_cost = float(product.get("supplier_cost", 0.0))
    selling_price = float(product.get("selling_price", 0.0))
    supplier_stock = int(product.get("supplier_stock", 0))
    is_enabled = bool(product.get("is_enabled", True))
    delivery_type = product.get("delivery_type", "AUTOMATIC")
    comm_pct = float(product.get("referral_commission_percent", 5.0) or 0.0)
    comm_amount = round(selling_price * (comm_pct / 100.0), 2)
    short_id = format_4digit_id(service_id)

    status_str = "🟢 Enabled (Active in Shop)" if is_enabled else "🔴 Disabled (Hidden from customers)"
    type_badge = "🛠️ Manual Product" if service_id.startswith("MANUAL_") else "🔌 AIVerse API Product"
    deliv_icon = "⚡" if delivery_type == "AUTOMATIC" else ("👨‍💻" if delivery_type == "MANUAL" else "🔄")

    card_text = (
        f"🤖 <b>#{short_id} {product['name']} 💎</b>\n\n"
        f"🏷️ <b>Product Type:</b> {type_badge}\n"
        f"🆔 <b>Service ID:</b> <code>{service_id}</code> (Display: <code>#{short_id}</code>)\n"
        f"🚚 <b>Delivery Mode:</b> <code>{deliv_icon} {delivery_type}</code>\n"
        f"💵 <b>Supplier Cost:</b> <code>${supplier_cost:.2f}</code>\n"
        f"📦 <b>Supplier Stock:</b> <code>{supplier_stock} Available</code>\n"
        f"💰 <b>MELAX Selling Price:</b> <code>{selling_price:,.2f} Birr</code>\n"
        f"🎁 <b>Referral Commission:</b> <code>{comm_pct}%</code> (+{comm_amount:,.2f} Birr per sale)\n"
        f"👁️ <b>Store Status:</b> {status_str}\n\n"
        f"📋 <b>100% FULL SUPPLIER / PRODUCT DESCRIPTION (ADMIN VIEW):</b>\n"
        f"<i>{product.get('description', 'No description set.')}</i>\n\n"
        f"<i>Click the buttons below to change price, edit commission %, or enable/disable:</i>"
    )

    await query.message.edit_text(
        text=card_text,
        parse_mode="HTML",
        reply_markup=get_admin_product_card_keyboard(service_id, is_enabled, delivery_type)
    )

@router.callback_query(F.data.startswith("adm_comm_init:"))
@router.callback_query(F.data.startswith("adm_quick_comm:"))
async def init_quick_edit_commission(query: CallbackQuery, state: FSMContext):
    """Initiate edit of Referral Commission % for a product (from admin card or shop)."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    is_shop = query.data.startswith("adm_quick_comm:")
    service_id = query.data.split(":", 1)[1]
    product = await db.get_product_by_service_id(service_id)
    if not product:
        await query.message.edit_text("⚠️ Product not found.")
        return

    cur_comm = float(product.get("referral_commission_percent", 5.0) or 0.0)
    await state.update_data(target_service_id=service_id, return_to_shop=is_shop)
    await state.set_state(AdminProductStates.waiting_for_commission_percent)

    back_cb = f"prod_select:{service_id}" if is_shop else f"adm_prod_view:{service_id}"
    prompt_text = (
        f"🎁 <b>EDIT REFERRAL COMMISSION PERCENTAGE</b>\n\n"
        f"▪️ <b>Product:</b> <code>{product['name']}</code>\n"
        f"▪️ <b>Current Commission:</b> <code>{cur_comm}%</code>\n\n"
        f"👉 <b>Please type and send the NEW Referral Commission %</b> (e.g. <code>5</code>, <code>10</code>, <code>15</code>, or <code>0</code> for none):"
    )
    await query.message.edit_text(text=prompt_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback=back_cb, cancel_callback="btn_cancel"))

@router.message(AdminProductStates.waiting_for_commission_percent)
async def process_commission_percent_input(message: Message, state: FSMContext, bot: Bot):
    """Receive and save new referral commission percentage for product."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    input_txt = message.text.strip().replace("%", "")
    try:
        pct = float(input_txt)
        if pct < 0 or pct > 100:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Invalid percentage. Please send a number between 0 and 100 (e.g. 5, 10, or 0):")
        return

    data = await state.get_data()
    service_id = data["target_service_id"]
    await db.update_product_commission(service_id, pct)
    await state.clear()

    product = await db.get_product_by_service_id(service_id)
    p_name = product.get("name", service_id) if product else service_id
    await message.answer(
        f"✅ <b>Referral Commission updated to {pct}% for {p_name}! 🎁</b>",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard(back_callback=f"prod_select:{service_id}" if data.get("return_to_shop") else "adm_products", cancel_callback="btn_cancel")
    )

@router.callback_query(F.data.startswith("adm_edit_deliv:"))
async def init_edit_delivery_mode(query: CallbackQuery):
    """Show delivery mode options to toggle for existing product."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    service_id = query.data.split(":", 1)[1]
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚡ SET TO AUTOMATIC", callback_data=f"adm_set_deliv:{service_id}:AUTOMATIC"))
    builder.row(InlineKeyboardButton(text="👨‍💻 SET TO MANUAL", callback_data=f"adm_set_deliv:{service_id}:MANUAL"))
    builder.row(InlineKeyboardButton(text="🔄 SET TO HYBRID", callback_data=f"adm_set_deliv:{service_id}:HYBRID"))
    builder.row(InlineKeyboardButton(text="BACK", callback_data=f"adm_prod_view:{service_id}"))

    await query.message.edit_text(
        text=f"🚚 <b>CHANGE DELIVERY MODE FOR PRODUCT #{format_4digit_id(service_id)}</b>\n\nSelect the new delivery mode:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("adm_set_deliv:"))
async def execute_set_delivery_mode(query: CallbackQuery):
    """Apply updated delivery mode to product."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    _, service_id, new_mode = query.data.split(":")
    await db.update_product_delivery_type(service_id, new_mode)
    await query.answer(f"✅ Delivery mode changed to {new_mode}!", show_alert=True)
    
    # Reload single product view
    query.data = f"adm_prod_view:{service_id}"
    await view_single_admin_product(query)

@router.callback_query(F.data.startswith("adm_name_init:"))
async def init_change_name(query: CallbackQuery, state: FSMContext):
    """Initiate product name edit via inline button (works for both API & Manual products)."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    service_id = query.data.split(":", 1)[1]
    product = await db.get_product_by_service_id(service_id)

    if not product:
        await query.message.edit_text("⚠️ Product not found.")
        return

    await state.update_data(target_service_id=service_id, old_name=product["name"])
    await state.set_state(AdminProductStates.waiting_for_name)

    short_id = format_4digit_id(service_id)
    prompt_text = (
        f"✏️ <b>EDIT PRODUCT DISPLAY NAME</b>\n\n"
        f"▪️ <b>Current Name:</b> #{short_id} {product['name']}\n"
        f"▪️ <b>Service ID:</b> <code>{service_id}</code>\n\n"
        f"👉 <b>Please type and send the NEW product name:</b>\n"
        f"<i>(You can include custom animated emoji tags or clean text)</i>"
    )
    await query.message.edit_text(text=prompt_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback=f"adm_prod_view:{service_id}", cancel_callback="btn_cancel"))

@router.message(AdminProductStates.waiting_for_name)
async def process_new_name_input(message: Message, state: FSMContext, bot: Bot):
    """Receive and save new product display name."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    is_safe, sanitized_name = sanitize_input(message.text.strip())
    if not is_safe or len(sanitized_name) < 2:
        await message.answer("⚠️ Invalid product name. Please send a valid name:")
        return

    data = await state.get_data()
    service_id = data["target_service_id"]
    old_name = data.get("old_name", "")

    await db.update_product_name(service_id, sanitized_name)
    await db.log_admin_action(user.id, "EDIT_NAME", "PRODUCT", service_id, old_name, sanitized_name, "Admin inline name edit")
    await state.clear()

    short_id = format_4digit_id(service_id)
    back_kb = get_back_cancel_keyboard(back_callback=f"prod_select:{service_id}" if data.get("return_to_shop") else "adm_products", cancel_callback="btn_cancel")
    await message.answer(
        f"✅ <b>SAVED SUCCESSFULLY! 💎</b>\n\n"
        f"▪️ <b>Product:</b> <b>{sanitized_name}</b>\n"
        f"▪️ <b>Service ID:</b> <code>#{short_id}</code>\n"
        f"▪️ <b>Old Name:</b> <s>{old_name}</s>\n\n"
        f"<i>Changes are live across the shop and channels!</i>",
        parse_mode="HTML",
        reply_markup=back_kb
    )

    await log_to_channel(bot, "✏️ PRODUCT NAME CHANGED", {
        "Admin": f"@{user.username}" if user.username else user.first_name,
        "Service ID": service_id,
        "Old Name": old_name,
        "New Name": sanitized_name
    })

@router.callback_query(F.data.startswith("adm_price_init:"))
async def init_change_price(query: CallbackQuery, state: FSMContext):
    """Initiate price change via inline button."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    service_id = query.data.split(":", 1)[1]
    product = await db.get_product_by_service_id(service_id)

    if not product:
        await query.message.edit_text("⚠️ Product not found.")
        return

    await state.update_data(target_service_id=service_id, target_name=product["name"], old_price=float(product.get("selling_price", 0.0)))
    await state.set_state(AdminProductStates.waiting_for_price)

    short_id = format_4digit_id(service_id)
    prompt_text = (
        f"💰 <b>CHANGE SELLING PRICE</b>\n\n"
        f"▪️ <b>Product:</b> #{short_id} {product['name']}\n"
        f"▪️ <b>Service ID:</b> <code>{service_id}</code>\n"
        f"▪️ <b>Current Price:</b> <code>{float(product.get('selling_price', 0.0)):,.2f} Birr</code>\n\n"
        f"👉 <b>Please type and send the NEW selling price in Birr:</b>"
    )
    await query.message.edit_text(text=prompt_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback=f"adm_prod_view:{service_id}", cancel_callback="btn_cancel"))

@router.message(AdminProductStates.waiting_for_price)
async def process_new_price_input(message: Message, state: FSMContext, bot: Bot):
    """Receive and save new selling price in FSM state with input validation."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    is_safe, sanitized_text = sanitize_input(message.text)
    if not is_safe:
        await message.answer("⚠️ Security Alert: Malicious code pattern detected. Input rejected.")
        await log_to_channel(bot, "⚠️ SECURITY WARNING", {"Admin": user.id, "Event": "Suspicious Price Input Blocked"})
        await state.clear()
        return

    raw_text = sanitized_text.replace(",", "")
    try:
        new_price = float(raw_text)
        if new_price < 0:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Invalid numeric value. Please send a positive number (e.g. 2500):")
        return

    data = await state.get_data()
    service_id = data["target_service_id"]
    product_name = data["target_name"]
    old_price = data["old_price"]

    await db.update_product_price(service_id, new_price)
    await db.log_admin_action(user.id, "CHANGE_PRICE", "PRODUCT", service_id, f"{old_price:.2f}", f"{new_price:.2f}", "Admin inline state edit")
    await state.clear()

    short_id = format_4digit_id(service_id)
    back_kb = get_back_cancel_keyboard(back_callback=f"prod_select:{service_id}" if data.get("return_to_shop") else "adm_products", cancel_callback="btn_cancel")
    await message.answer(
        f"✅ <b>PRICE SAVED SUCCESSFULLY! 💎</b>\n\n"
        f"▪️ <b>Product:</b> #{short_id} {product_name}\n"
        f"▪️ <b>Old Price:</b> <code>{old_price:,.2f} Birr</code>\n"
        f"▪️ <b>New Price:</b> <code>{new_price:,.2f} Birr</code>",
        parse_mode="HTML",
        reply_markup=back_kb
    )

    await log_to_channel(bot, "💰 PRODUCT PRICE CHANGED", {
        "Admin": f"@{user.username}" if user.username else user.first_name,
        "Product": product_name,
        "Service ID": service_id,
        "Old Price": f"{old_price:,.2f} Birr",
        "New Price": f"{new_price:,.2f} Birr"
    })

@router.callback_query(F.data.startswith("adm_desc_init:"))
async def init_change_desc(query: CallbackQuery, state: FSMContext):
    """Initiate description edit via inline button."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    service_id = query.data.split(":", 1)[1]
    product = await db.get_product_by_service_id(service_id)

    if not product:
        await query.message.edit_text("⚠️ Product not found.")
        return

    await state.update_data(target_service_id=service_id, target_name=product["name"])
    await state.set_state(AdminProductStates.waiting_for_desc)

    short_id = format_4digit_id(service_id)
    prompt_text = (
        f"📝 <b>EDIT PRODUCT DESCRIPTION</b>\n\n"
        f"▪️ <b>Product:</b> #{short_id} {product['name']}\n\n"
        f"Current Description:\n"
        f"<i>{product.get('description', 'None')}</i>\n\n"
        f"👉 <b>Please send the new description text below:</b>"
    )
    await query.message.edit_text(text=prompt_text, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback=f"adm_prod_view:{service_id}", cancel_callback="btn_cancel"))

@router.message(AdminProductStates.waiting_for_desc)
async def process_new_desc_input(message: Message, state: FSMContext, bot: Bot):
    """Receive and save new product description with strict input sanitization."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    is_safe, sanitized_desc = sanitize_input(message.html_text if message.html_text else message.text)
    if not is_safe:
        await message.answer("⚠️ Security Alert: Malicious code pattern detected. Input rejected.")
        await log_to_channel(bot, "⚠️ SECURITY WARNING", {"Admin": user.id, "Event": "Suspicious Description Input Blocked"})
        await state.clear()
        return

    data = await state.get_data()
    service_id = data["target_service_id"]
    product_name = data["target_name"]

    await db.update_product_description(service_id, sanitized_desc)
    await db.log_admin_action(user.id, "EDIT_DESC", "PRODUCT", service_id, "", sanitized_desc[:50], "Admin inline state edit")
    await state.clear()

    short_id = format_4digit_id(service_id)
    back_kb = get_back_cancel_keyboard(back_callback=f"prod_select:{service_id}" if data.get("return_to_shop") else "adm_products", cancel_callback="btn_cancel")
    await message.answer(
        f"✅ <b>DESCRIPTION SAVED SUCCESSFULLY! 💎</b>\n\n"
        f"▪️ <b>Product:</b> #{short_id} {product_name}\n"
        f"▪️ <b>New Description:</b>\n<i>{sanitized_desc}</i>",
        parse_mode="HTML",
        reply_markup=back_kb
    )

    await log_to_channel(bot, "📝 PRODUCT DESCRIPTION UPDATED", {
        "Admin": f"@{user.username}" if user.username else user.first_name,
        "Product": product_name,
        "Service ID": service_id
    })

@router.callback_query(F.data.startswith("adm_toggle_vis:"))
async def toggle_product_visibility_callback(query: CallbackQuery):
    """Toggle product enabled/disabled in shop."""
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    service_id = query.data.split(":", 1)[1]
    product = await db.get_product_by_service_id(service_id)

    if not product:
        await query.answer("⚠️ Product not found.", show_alert=True)
        return

    current_status = bool(product.get("is_enabled", True))
    new_status = not current_status

    await db.toggle_product_visibility(service_id, new_status)
    status_label = "🟢 ENABLED" if new_status else "🔴 DISABLED"

    await query.answer(f"Product status changed to {status_label}!", show_alert=True)

    product["is_enabled"] = new_status
    supplier_cost = float(product.get("supplier_cost", 0.0))
    selling_price = float(product.get("selling_price", 0.0))
    supplier_stock = int(product.get("supplier_stock", 0))
    short_id = format_4digit_id(service_id)

    status_str = "🟢 Enabled (Active in Shop)" if new_status else "🔴 Disabled (Hidden from customers)"

    card_text = (
        f"🤖 <b>#{short_id} {product['name']}</b>\n\n"
        f"🆔 <b>Service ID:</b> <code>{service_id}</code>\n"
        f"💵 <b>Supplier Cost:</b> <code>${supplier_cost:.2f}</code>\n"
        f"📦 <b>Stock:</b> <code>{supplier_stock}</code>\n"
        f"💰 <b>MELAX Selling Price:</b> <code>{selling_price:,.2f} Birr</code>\n"
        f"👁️ <b>Store Status:</b> {status_str}\n\n"
        f"📝 <b>Description / Delivery Content:</b>\n"
        f"{product.get('description', 'No description set.')}\n\n"
        f"<i>Click the buttons below to change price, edit description, or enable/disable:</i>"
    )

    await query.message.edit_text(
        text=card_text,
        parse_mode="HTML",
        reply_markup=get_admin_product_card_keyboard(service_id, new_status)
    )

@router.callback_query(F.data.startswith("adm_quick_name:"))
async def init_quick_edit_name(query: CallbackQuery, state: FSMContext):
    """Quick edit product name directly from customer shop card."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    service_id = query.data.split(":", 1)[1]
    product = await db.get_product_by_service_id(service_id)
    if not product:
        await query.answer("⚠️ Product not found.", show_alert=True)
        return

    await state.update_data(target_service_id=service_id, old_name=product["name"], return_to_shop=True)
    await state.set_state(AdminProductStates.waiting_for_name)

    prompt = (
        f"✏️ <b>QUICK EDIT PRODUCT NAME (ADMIN)</b>\n\n"
        f"▪️ <b>Current Name:</b> <code>{product['name']}</code>\n"
        f"▪️ <b>Service ID:</b> <code>{service_id}</code>\n\n"
        f"👉 <b>Type and send the new product name:</b>"
    )
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback=f"prod_select:{service_id}", cancel_callback="btn_cancel"))

@router.callback_query(F.data.startswith("adm_quick_price:"))
async def init_quick_edit_price(query: CallbackQuery, state: FSMContext):
    """Quick edit product price directly from customer shop card."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    service_id = query.data.split(":", 1)[1]
    product = await db.get_product_by_service_id(service_id)
    if not product:
        await query.answer("⚠️ Product not found.", show_alert=True)
        return

    await state.update_data(target_service_id=service_id, target_name=product["name"], old_price=float(product.get("selling_price", 0.0)), return_to_shop=True)
    await state.set_state(AdminProductStates.waiting_for_price)

    prompt = (
        f"💰 <b>QUICK EDIT SELLING PRICE (ADMIN)</b>\n\n"
        f"▪️ <b>Product:</b> <code>{product['name']}</code>\n"
        f"▪️ <b>Current Price:</b> <code>{float(product.get('selling_price', 0.0)):,.2f} Birr</code>\n\n"
        f"👉 <b>Type and send the new price in Birr:</b>"
    )
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback=f"prod_select:{service_id}", cancel_callback="btn_cancel"))

@router.callback_query(F.data.startswith("adm_quick_desc:"))
async def init_quick_edit_desc(query: CallbackQuery, state: FSMContext):
    """Quick edit product description directly from customer shop card."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    service_id = query.data.split(":", 1)[1]
    product = await db.get_product_by_service_id(service_id)
    if not product:
        await query.answer("⚠️ Product not found.", show_alert=True)
        return

    await state.update_data(target_service_id=service_id, target_name=product["name"], return_to_shop=True)
    await state.set_state(AdminProductStates.waiting_for_desc)

    prompt = (
        f"📝 <b>QUICK EDIT DESCRIPTION (ADMIN)</b>\n\n"
        f"▪️ <b>Product:</b> <code>{product['name']}</code>\n"
        f"▪️ <b>Current Desc:</b>\n<i>{product.get('description', '')}</i>\n\n"
        f"👉 <b>Type and send the new description:</b>"
    )
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback=f"prod_select:{service_id}", cancel_callback="btn_cancel"))

@router.callback_query(F.data.startswith("adm_quick_vis:"))
async def quick_toggle_vis(query: CallbackQuery):
    """Quick toggle visibility from customer shop card and refresh in place."""
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    service_id = query.data.split(":", 1)[1]
    product = await db.get_product_by_service_id(service_id)
    if not product:
        await query.answer("⚠️ Product not found.", show_alert=True)
        return

    new_status = not bool(product.get("is_enabled", True))
    await db.toggle_product_visibility(service_id, new_status)
    status_label = "🟢 ENABLED (Visible)" if new_status else "🔴 DISABLED (Hidden)"
    await query.answer(f"✅ Saved! {status_label}", show_alert=True)

    # Refresh the product card view
    product["is_enabled"] = new_status
    selling_price = float(product.get("selling_price", 0.0))
    supplier_stock = int(product.get("supplier_stock", 0))
    in_stock = supplier_stock > 0 and new_status

    from config import emo
    stock_str = f"<code>{supplier_stock} Available</code> {emo('check', '🟢')}" if in_stock else f"<code>Out of Stock</code> {emo('cross', '🔴')}"
    detail_text = (
        f"<b>{product['name']}</b>\n\n"
        f"{emo('money', '💰')} <b>Price:</b> <code>{selling_price:,.0f} Birr</code>\n"
        f"{emo('box', '📦')} <b>Stock:</b> {stock_str}\n"
        f"{emo('lightning', '⚡')} <b>Delivery:</b> <code>Instant Automated Delivery</code>\n\n"
        f"📝 <b>Description / Features:</b>\n"
        f"{product.get('description', 'Instant automated delivery after purchase.')}"
    )
    await query.message.edit_text(
        text=detail_text,
        parse_mode="HTML",
        reply_markup=get_product_detail_keyboard(service_id, is_purchasable=in_stock, is_admin=True, is_enabled=new_status)
    )

@router.callback_query(F.data.startswith("adm_del_prod_confirm:"))
async def confirm_delete_product_prompt(query: CallbackQuery):
    """Show confirmation prompt before permanently deleting a product."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    service_id = query.data.split(":", 1)[1]
    product = await db.get_product_by_service_id(service_id)
    if not product:
        await query.answer("⚠️ Product not found.", show_alert=True)
        return

    short_id = format_4digit_id(service_id)
    confirm_text = (
        f"⚠️ <b>ARE YOU SURE YOU WANT TO DELETE THIS PRODUCT?</b>\n\n"
        f"💎 <b>Product:</b> #{short_id} <code>{product['name']}</code>\n"
        f"🆔 <b>Service ID:</b> <code>{service_id}</code>\n"
        f"💰 <b>Price:</b> <code>{float(product.get('selling_price', 0)):,.2f} Birr</code>\n\n"
        f"🚨 <i>This action is permanent and cannot be undone! The product will be completely removed from the catalog.</i>"
    )
    await query.message.edit_text(
        text=confirm_text,
        parse_mode="HTML",
        reply_markup=get_delete_product_confirm_keyboard(service_id)
    )

@router.callback_query(F.data.startswith("adm_del_prod_exec:"))
async def execute_delete_product(query: CallbackQuery, bot: Bot):
    """Permanently delete product from database and memory."""
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        await query.answer("⛔ Access Denied", show_alert=True)
        return

    service_id = query.data.split(":", 1)[1]
    product = await db.get_product_by_service_id(service_id)
    prod_name = product.get("name", service_id) if product else service_id

    success = await db.delete_product(service_id)
    if success:
        await query.answer(f"🗑️ Product '{prod_name}' deleted successfully!", show_alert=True)
        await log_to_channel(bot, "🗑️ PRODUCT DELETED", {
            "Admin": f"@{user.username}" if user.username else user.first_name,
            "Product": prod_name,
            "Service ID": service_id
        })
    else:
        await query.answer("⚠️ Failed to delete product.", show_alert=True)

    # Return to Admin Product Catalog
    query.data = "adm_view_all_prods"
    await view_all_admin_products(query)

@router.callback_query(F.data == "adm_sync_prods")
async def sync_products_callback(query: CallbackQuery, bot: Bot):
    """Trigger manual product sync from AIVerse API and alert admins privately for new products."""
    await query.answer("🔄 Syncing products with AIVerse Hub...", show_alert=True)
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    api_prods = await api_client.get_products()
    res = await db.sync_products_from_api(api_prods)

    text = (
        f"🔄 <b>PRODUCT SYNC COMPLETED ⚡</b>\n\n"
        f"▪️ Added New API Products: <code>{res['added']}</code>\n"
        f"▪️ Updated Supplier Fields: <code>{res['updated']}</code>\n"
        f"▪️ Unavailable: <code>{res['unavailable']}</code>\n\n"
        f"🔒 <i>All newly added products are automatically <b>DISABLED (Hidden from customers)</b> until you review and enable them!</i>"
    )
    await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=get_admin_products_keyboard())

    # Send private alert exclusively to admins if new products were imported
    new_prods = res.get("new_products", [])
    if new_prods:
        alert_msg = (
            f"🔔 <b>NEW PRODUCTS IMPORTED ALERT (ADMIN ONLY) 💎</b>\n\n"
            f"✨ <b>{len(new_prods)} New Products</b> were imported from supplier:\n\n"
        )
        for p in new_prods:
            alert_msg += f"▫️ <b>{p['name']}</b>\n   💵 Supplier Cost: <code>${p['supplier_cost']:.2f}</code> | 📦 Stock: <code>{p['supplier_stock']} Available</code>\n\n"
        alert_msg += f"<i>🔒 Status: Disabled (Hidden from customers). Go to Admin Panel -> Products to review, adjust price, and enable.</i>"

        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(chat_id=admin_id, text=alert_msg, parse_mode="HTML")
            except Exception:
                pass

# =========================================================================
# ADMIN PENDING MANUAL ORDERS FULFILLMENT CONSOLE
# =========================================================================

@router.callback_query(F.data == "adm_pending_orders")
async def show_admin_pending_orders(query: CallbackQuery):
    """View and fulfill pending manual orders."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    orders = await db.get_pending_manual_orders()
    if not orders:
        await query.message.edit_text(
            "📦 <b>PENDING MANUAL ORDERS CONSOLE</b>\n\n✅ <b>Zero Pending Orders!</b> All manual and hybrid purchases have been fulfilled.",
            parse_mode="HTML",
            reply_markup=get_back_cancel_keyboard(back_callback="adm_products", cancel_callback="btn_cancel")
        )
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()

    for o in orders[:10]:
        o_id = o.get("melax_order_id", "ORDER")
        p_name = o.get("product_name", "Product")[:18]
        u_info = o.get("users", {}) or {}
        tg_id = u_info.get("telegram_id", "")
        price = float(o.get("selling_price", 0.0))
        builder.row(
            InlineKeyboardButton(
                text=f"🔑 Fulfill #{o_id[-6:]} - {p_name} ({price:,.0f} Birr)",
                callback_data=f"adm_fulfill_ord:{o_id}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="BACK TO PRODUCTS", callback_data="adm_products"),
        InlineKeyboardButton(text="CANCEL", callback_data="btn_cancel")
    )

    text = (
        f"📦 <b>PENDING MANUAL ORDERS CONSOLE ({len(orders)} Waiting) 🔔</b>\n\n"
        f"<i>Select an order below to enter/paste account credentials and instantly deliver to the customer:</i>"
    )
    await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("adm_fulfill_ord:"))
async def init_fulfill_manual_order(query: CallbackQuery, state: FSMContext):
    """Prompt admin to enter credentials for pending manual order."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    order_id = query.data.split(":", 1)[1]
    await state.update_data(target_manual_order_id=order_id)
    await state.set_state(AdminProductStates.waiting_for_manual_order_key)

    prompt = (
        f"🔑 <b>FULFILL MANUAL ORDER #{order_id}</b>\n\n"
        f"👉 Please type or paste the <b>Account Credentials / Access Code / License Key / Link</b>\n"
        f"<i>(This text will be sent directly to the customer in a formatted celebration card)</i>:"
    )
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_cancel_keyboard(back_callback="adm_pending_orders", cancel_callback="btn_cancel"))

@router.message(AdminProductStates.waiting_for_manual_order_key)
async def process_fulfill_manual_order_input(message: Message, state: FSMContext, bot: Bot):
    """Deliver credentials to customer and update order status."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    credentials_text = message.text.strip()
    data = await state.get_data()
    order_id = data.get("target_manual_order_id", "")
    await state.clear()

    if not order_id:
        await message.answer("⚠️ Session expired.", reply_markup=get_admin_products_keyboard())
        return

    success, msg, order_data = await db.fulfill_manual_order(order_id, user.id, credentials_text)
    if not success or not order_data:
        await message.answer(f"⚠️ Failed to fulfill order: {msg}", reply_markup=get_admin_products_keyboard())
        return

    # Dispatch to customer
    u_info = order_data.get("users", {}) or {}
    cust_tg_id = u_info.get("telegram_id")
    prod_name = order_data.get("product_name", "Digital Account")
    selling_price = float(order_data.get("selling_price", 0.0))

    if cust_tg_id:
        try:
            from config import emo, get_product_brand_icon
            brand_icon = get_product_brand_icon(prod_name)
            cust_card = (
                f"🎉 <b>YOUR ORDER IS COMPLETED & DELIVERED! {emo('lightning', '⚡')}{emo('diamond', '💎')}</b>\n\n"
                f"{brand_icon} <b>Product:</b> <code>{prod_name}</code>\n"
                f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n"
                f"{emo('money', '💰')} <b>Paid:</b> <code>{selling_price:,.0f} Birr</code>\n\n"
                f"🔑 <b>Your Account Details / Access Code:</b>\n"
                f"<code>{credentials_text}</code>\n\n"
                f"{emo('sparkle', '✨')} <i>Thank you for choosing MELAX DIGITAL SHOP!</i> {emo('crown', '👑')}"
            )
            await bot.send_message(chat_id=cust_tg_id, text=cust_card, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Could not message customer for manual fulfillment: {e}")

    # Process Referral Purchase Commission
    buyer_uuid = order_data.get("user_id") or str(cust_tg_id)
    service_id = order_data.get("service_id", "")
    prod_obj = await db.get_product_by_service_id(service_id) or {"name": prod_name, "referral_commission_percent": 5.0}

    try:
        comm_data = await db.process_purchase_referral_commission(
            buyer_user_id=buyer_uuid,
            product=prod_obj,
            purchase_price=selling_price,
            melax_order_id=order_id
        )
        if comm_data and comm_data.get("referrer_telegram_id"):
            ref_tg = comm_data["referrer_telegram_id"]
            comm_amt = comm_data["commission_amount"]
            comm_pct = comm_data["commission_percent"]
            p_name = comm_data["product_name"]
            new_bal = comm_data["new_balance"]
            ref_msg = (
                f"🎉 <b>የሪፈራል ኮሚሽን ገቢ ተደርጓል! (COMMISSION EARNED) 💰⚡</b>\n\n"
                f"🎁 በእርስዎ ግብዣ የተመዘገበ ደንበኛ <b>{p_name}</b> ገዝቷል!\n"
                f"💵 <b>የተገኘው ኮሚሽን ({comm_pct}%):</b> <code>+{comm_amt:,.2f} Birr</code>\n"
                f"💳 <b>አዲሱ የዋሌት ቀሪዎ:</b> <code>{new_bal:,.2f} Birr</code>\n\n"
                f"✨ <i>ተጨማሪ ሰዎችን በመጋበዝ የኮሚሽን ገቢዎን ያሳድጉ!</i> 👑"
            )
            await bot.send_message(chat_id=ref_tg, text=animate_text(ref_msg), parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Failed to process referral commission for manual order {order_id}: {e}")

    await message.answer(
        f"✅ <b>Order #{order_id} Fulfilled!</b>\nCredentials successfully delivered to customer.",
        parse_mode="HTML",
        reply_markup=get_admin_products_keyboard()
    )

# =========================================================================
# DIGITAL STOCK INVENTORY VAULT HANDLERS (BULK 70+ ACCOUNTS & KEYS)
# =========================================================================

@router.callback_query(F.data.startswith("adm_stock_pool:"))
async def view_product_stock_vault(query: CallbackQuery):
    """Display live Digital Stock Inventory Vault status and management options."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    service_id = query.data.split(":", 1)[1]
    product = await db.get_product_by_service_id(service_id)
    if not product:
        await query.message.edit_text("⚠️ Product not found.", reply_markup=get_admin_products_keyboard())
        return

    stats = await db.get_product_stock_stats(service_id)
    short_id = format_4digit_id(service_id)
    p_name = product.get("name", service_id)

    vault_text = (
        f"📦 <b>DIGITAL STOCK INVENTORY VAULT 💎</b>\n\n"
        f"🏷️ <b>Product:</b> #{short_id} {p_name}\n"
        f"🆔 <b>Service ID:</b> <code>{service_id}</code>\n\n"
        f"🟢 <b>Available Unused Items (ያልተሸጡ ፍሬዎች):</b> <code>{stats['available_count']} Items</code>\n"
        f"🔴 <b>Sold Items (የተሸጡ ፍሬዎች):</b> <code>{stats['used_count']} Items</code>\n"
        f"📊 <b>Total Registered:</b> <code>{stats['total_items']} Items</code>\n\n"
        f"💡 <b>Automated FIFO Key Dispenser:</b>\n"
        f"• Click <b>[ ➕ BULK ADD 70+ ITEMS ]</b> and paste your accounts (Email:Pass, Tokens, Links).\n"
        f"• Each customer who purchases this product will automatically and instantly receive 1 unique unused item.\n"
        f"• Once delivered, that specific item is permanently locked as SOLD and will never be given to another customer."
    )

    await query.message.edit_text(
        text=vault_text,
        parse_mode="HTML",
        reply_markup=get_stock_pool_keyboard(service_id, stats["available_count"], stats["used_count"])
    )

@router.callback_query(F.data.startswith("adm_stock_add:"))
async def init_bulk_add_stock(query: CallbackQuery, state: FSMContext):
    """Prompt admin to bulk paste 70+ stock items line by line."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    service_id = query.data.split(":", 1)[1]
    product = await db.get_product_by_service_id(service_id)
    if not product:
        await query.message.edit_text("⚠️ Product not found.")
        return

    await state.update_data(target_stock_service_id=service_id)
    await state.set_state(AdminProductStates.waiting_for_stock_items)

    prompt = (
        f"➕ <b>BULK ADD DIGITAL STOCK ITEMS (70+ እቃዎች አስገባ) 📦</b>\n\n"
        f"▪️ <b>Product:</b> <code>{product['name']}</code>\n"
        f"▪️ <b>Service ID:</b> <code>{service_id}</code>\n\n"
        f"👉 <b>Please copy-paste your stock items directly in this chat.</b>\n"
        f"<i>Paste one account / credential / key / link per line (e.g. 50 or 70 lines):</i>\n\n"
        f"<code>user1@gmail.com:password123\n"
        f"user2@gmail.com:password456\n"
        f"user3@gmail.com:password789</code>\n\n"
        f"<i>Every single line will be saved as an independent unused stock item!</i>"
    )

    await query.message.edit_text(
        text=prompt,
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard(back_callback=f"adm_stock_pool:{service_id}", cancel_callback="btn_cancel")
    )

@router.message(AdminProductStates.waiting_for_stock_items)
async def process_bulk_stock_input(message: Message, state: FSMContext, bot: Bot):
    """Receive bulk stock items lines, parse them, and store into product vault."""
    user = message.from_user
    if not (await db.get_admin_role(user.id)):
        await state.clear()
        return

    raw_text = message.text or ""
    if not raw_text.strip():
        await message.answer("⚠️ Empty input. Please paste your stock items (one per line):")
        return

    data = await state.get_data()
    service_id = data.get("target_stock_service_id")
    if not service_id:
        await state.clear()
        await message.answer("⚠️ Session expired. Please open the product vault again.")
        return

    res = await db.add_product_stock_items(service_id, raw_text)
    await state.clear()

    product = await db.get_product_by_service_id(service_id)
    p_name = product.get("name", service_id) if product else service_id

    confirm_text = (
        f"🎉 <b>STOCK ITEMS SUCCESSFULLY LOADED TO VAULT! 📦⚡</b>\n\n"
        f"💎 <b>Product:</b> <code>{p_name}</code>\n"
        f"➕ <b>New Items Added:</b> <code>+{res['added_count']} Items</code>\n"
        f"🟢 <b>Total Live Available Stock:</b> <code>{res['available_count']} Items</code>\n"
        f"📊 <b>Total Lifetime Vault Items:</b> <code>{res['total_items']} Items</code>\n\n"
        f"✨ <i>Customers can now buy immediately, and the bot will deliver each item automatically!</i>"
    )

    await message.answer(
        text=confirm_text,
        parse_mode="HTML",
        reply_markup=get_stock_pool_keyboard(service_id, res["available_count"], res["total_items"] - res["available_count"])
    )

@router.callback_query(F.data.startswith("adm_stock_view_avail:"))
async def view_available_stock_items(query: CallbackQuery):
    """Preview next available unused stock credentials in vault."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    service_id = query.data.split(":", 1)[1]
    stats = await db.get_product_stock_stats(service_id)
    avail = stats["available_items"]

    if not avail:
        await query.message.edit_text(
            f"📦 <b>NO AVAILABLE STOCK ITEMS</b>\n\nAll items have been sold or none added yet.",
            parse_mode="HTML",
            reply_markup=get_stock_pool_keyboard(service_id, 0, stats["used_count"])
        )
        return

    preview_lines = []
    for idx, it in enumerate(avail[:25], 1):
        content = it.get("content", "")
        preview_lines.append(f"{idx}. <code>{content}</code>")

    more_text = f"\n<i>... and {len(avail) - 25} more items available.</i>" if len(avail) > 25 else ""

    text = (
        f"🟢 <b>AVAILABLE STOCK ITEMS ({len(avail)} Total) 📦</b>\n"
        f"Service ID: <code>{service_id}</code>\n\n"
        + "\n".join(preview_lines) + more_text
    )

    await query.message.edit_text(
        text=text,
        parse_mode="HTML",
        reply_markup=get_stock_pool_keyboard(service_id, len(avail), stats["used_count"])
    )

@router.callback_query(F.data.startswith("adm_stock_view_used:"))
async def view_used_stock_items(query: CallbackQuery):
    """View sold stock items history."""
    await query.answer()
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    service_id = query.data.split(":", 1)[1]
    stats = await db.get_product_stock_stats(service_id)
    used = stats["used_items"]

    if not used:
        await query.message.edit_text(
            f"📜 <b>NO SOLD ITEMS YET</b>\n\nNo stock items have been delivered from this vault.",
            parse_mode="HTML",
            reply_markup=get_stock_pool_keyboard(service_id, stats["available_count"], 0)
        )
        return

    used_lines = []
    for idx, it in enumerate(used[:20], 1):
        content = it.get("content", "")
        ord_id = it.get("used_by_order_id", "N/A")
        date_str = str(it.get("used_at", ""))[:10]
        used_lines.append(f"{idx}. <code>{content}</code>\n   ↳ Order: <code>{ord_id}</code> ({date_str})")

    more_text = f"\n<i>... and {len(used) - 20} more sold items.</i>" if len(used) > 20 else ""

    text = (
        f"🔴 <b>SOLD STOCK ITEMS HISTORY ({len(used)} Total) 📜</b>\n"
        f"Service ID: <code>{service_id}</code>\n\n"
        + "\n".join(used_lines) + more_text
    )

    await query.message.edit_text(
        text=text,
        parse_mode="HTML",
        reply_markup=get_stock_pool_keyboard(service_id, stats["available_count"], len(used))
    )

@router.callback_query(F.data.startswith("adm_stock_clear_used:"))
async def clear_used_stock_items_history(query: CallbackQuery):
    """Purge sold items history."""
    user = query.from_user
    if not (await db.get_admin_role(user.id)):
        return

    service_id = query.data.split(":", 1)[1]
    cleared = await db.clear_used_stock_items(service_id)
    await query.answer(f"🧹 Cleared {cleared} sold items from history!", show_alert=True)
    stats = await db.get_product_stock_stats(service_id)

    query.data = f"adm_stock_pool:{service_id}"
    await view_product_stock_vault(query)
