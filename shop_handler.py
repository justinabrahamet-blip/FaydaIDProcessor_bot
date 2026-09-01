import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from db_client import db
from api_client import api_client
from keyboards import (
    get_products_keyboard,
    get_product_detail_keyboard,
    get_buy_confirm_keyboard,
    get_back_keyboard
)
from channel_logger import log_purchase_to_channel, log_to_channel
from config import ADMIN_IDS, emo, animate_text
from i18n import t, REPLY_TEXT_SHOP

logger = logging.getLogger(__name__)
router = Router()

user_purchase_locks = {}

class ShopPromoStates(StatesGroup):
    waiting_for_promo_code = State()

@router.message(Command("products"))
@router.message(F.text.in_(REPLY_TEXT_SHOP))
@router.callback_query(F.data.in_(["btn_shop", "btn_products"]))
async def show_products_catalog(event: Message | CallbackQuery, bot: Bot):
    """Display product catalog imported from AIVerse API & Manual Products."""
    if isinstance(event, CallbackQuery):
        await event.answer()
        user = event.from_user
        message = event.message
    else:
        user = event.from_user
        message = event

    maint_mode = bool(await db.get_setting("maintenance_mode", False))
    shop_active = await db.get_service_status("shop", True)
    if (maint_mode or not shop_active) and not (await db.get_admin_role(user.id)):
        pause_title = "🛠️ <b>ቦቱ በጊዜያዊ ጥገና ላይ ነው (UNDER MAINTENANCE) ⚡</b>" if maint_mode else "🛒 <b>DIGITAL PRODUCTS SHOP ⚡</b>"
        pause_body = "የሲስተም ማሻሻያ እየተደረገ ስለሆነ ለጊዜው ግብይት አቋርጠናል። እባክዎን ትንሽ ቆይተው እንደገና ይሞክሩ።" if maint_mode else "⚠️ የዲጂታል እቃዎች ግብይት በጊዜያዊነት ቆሟል (Temporarily Offline)。 እባክዎን ትንሽ ቆይተው እንደገና ይሞክሩ!"
        maint_msg = animate_text(f"{pause_title}\n\n{pause_body}")
        if isinstance(event, CallbackQuery):
            await message.edit_text(maint_msg, parse_mode="HTML", reply_markup=get_back_keyboard())
        else:
            await message.answer(maint_msg, parse_mode="HTML", reply_markup=get_back_keyboard())
        return

    products = await db.get_all_products(enabled_only=True)
    if not products:
        api_prods = await api_client.get_products()
        if api_prods:
            await db.sync_products_from_api(api_prods)
        products = await db.get_all_products(enabled_only=True)

    user_lang = await db.get_user_language(user.id)

    if not products:
        unavail_text = animate_text("🔴 <b>CURRENTLY UNAVAILABLE</b>\n\nNo products are available in stock. Please try again later.")
        if isinstance(event, CallbackQuery):
            await message.edit_text(unavail_text, parse_mode="HTML", reply_markup=get_back_keyboard())
        else:
            await message.answer(unavail_text, parse_mode="HTML", reply_markup=get_back_keyboard())
        return

    u_db = await db.get_user_by_telegram_id(user.id)
    balance = u_db.get("wallet_balance", 0.00) if u_db else 0.00

    catalog_title = t("catalog_title", user_lang)
    catalog_subtitle = t("catalog_subtitle", user_lang)
    catalog_text = animate_text(
        f"{catalog_title}\n\n"
        f"💰 <b>Your Balance:</b> <code>{balance:,.2f} Birr</code> ✨\n\n"
        f"<i>{catalog_subtitle}</i>"
    )

    if isinstance(event, CallbackQuery):
        try:
            await message.edit_text(
                text=catalog_text,
                parse_mode="HTML",
                reply_markup=get_products_keyboard(products, lang=user_lang)
            )
        except Exception:
            await message.answer(
                text=catalog_text,
                parse_mode="HTML",
                reply_markup=get_products_keyboard(products, lang=user_lang)
            )
    else:
        await message.answer(
            text=catalog_text,
            parse_mode="HTML",
            reply_markup=get_products_keyboard(products, lang=user_lang)
        )

@router.callback_query(F.data.startswith("prod_select:"))
async def view_product_details(query: CallbackQuery):
    """View clean product description, price, status, and BUY NOW button with Flash Sale & Promo Code support."""
    await query.answer()
    user = query.from_user
    service_id = query.data.split(":", 1)[1]

    product = await db.get_effective_product(service_id)
    if not product:
        from config import emo
        await query.message.edit_text(f"{emo('cross', '🔴')} Product not found.", reply_markup=get_back_keyboard())
        return

    u_db = await db.get_user_by_telegram_id(user.id)
    user_id_uuid = u_db["id"] if u_db else ""
    is_vip = u_db.get("is_vip", False) if u_db else False

    base_price = await db.get_effective_price(user_id_uuid, is_vip, product)
    flash_percent = await db.get_global_discount_percent()

    from config import emo, get_product_brand_icon
    vip_badge = f" {emo('star', '⭐')} (VIP Price)" if is_vip else ""

    if flash_percent > 0:
        selling_price = max(0.0, round(base_price * (1.0 - (flash_percent / 100.0)), 2))
        price_str = f"<s>{base_price:,.0f}</s> ➡️ <code>{selling_price:,.0f} Birr</code> 🔥 <i>({flash_percent:.0f}% Flash Sale!)</i>"
    else:
        selling_price = base_price
        price_str = f"<code>{selling_price:,.0f} Birr</code>{vip_badge}"

    supplier_stock = int(product.get("supplier_stock", 0))
    is_enabled = bool(product.get("is_enabled", True))
    supplier_avail = bool(product.get("supplier_available", True))
    delivery_type = product.get("delivery_type", "AUTOMATIC")

    in_stock = supplier_stock > 0 and supplier_avail and is_enabled
    stock_str = f"<code>{supplier_stock} Available</code> {emo('check', '🟢')}" if in_stock else f"<code>Out of Stock</code> {emo('cross', '🔴')}"

    if delivery_type == "MANUAL":
        deliv_str = "<code>👨‍💻 Fast Manual Admin Delivery</code>"
    elif delivery_type == "HYBRID":
        deliv_str = "<code>🔄 Smart Instant / Manual Delivery</code>"
    else:
        deliv_str = "<code>⚡ Instant Automated Delivery</code>"

    user_lang = u_db.get("language_code", "am") if u_db else "am"

    comm_pct = float(product.get("referral_commission_percent", 5.0) or 0.0)
    comm_amount = round(selling_price * (comm_pct / 100.0), 2)
    custom_comm_note = product.get("custom_commission_text")

    if custom_comm_note:
        try:
            custom_note_formatted = custom_comm_note.format(comm_pct=comm_pct, comm_amount=comm_amount, price=selling_price)
        except Exception:
            custom_note_formatted = custom_comm_note
        comm_line = f"🎁 {custom_note_formatted}\n"
    elif user_lang == "am":
        comm_line = f"{emo('gift', '🎁')} <b>የሪፈራል ሽልማት:</b> <code>{comm_pct}% ኮሚሽን</code> (ጓደኛዎ ሲገዛ <code>+{comm_amount:,.2f} ብር</code> ያግኙ!)\n" if comm_pct > 0 else ""
    else:
        comm_line = f"{emo('gift', '🎁')} <b>Referral Reward:</b> <code>{comm_pct}% Commission</code> (Earn <code>+{comm_amount:,.2f} Birr</code> / sale)\n" if comm_pct > 0 else ""

    prod_emoji = product.get("emoji") or get_product_brand_icon(product["name"])
    title_line = f"{prod_emoji} <b>{product['name']}</b>" if prod_emoji else f"<b>{product['name']}</b>"

    detail_text = (
        f"{title_line}\n\n"
        f"{emo('money', '💰')} <b>Price:</b> {price_str}\n"
        f"{emo('box', '📦')} <b>Stock:</b> {stock_str}\n"
        f"{emo('lightning', '⚡')} <b>Delivery:</b> {deliv_str}\n"
        f"{comm_line}\n"
        f"📝 <b>Description / Features:</b>\n"
        f"{product.get('description', 'Instant automated delivery after purchase.')}"
    )

    is_admin = (await db.get_admin_role(user.id)) is not None
    custom_btn_label = product.get("custom_button_text", "")

    try:
        await query.message.edit_text(
            text=detail_text,
            parse_mode="HTML",
            reply_markup=get_product_detail_keyboard(
                service_id,
                is_purchasable=in_stock,
                is_admin=is_admin,
                is_enabled=is_enabled,
                buy_button_text=custom_btn_label
            )
        )
    except Exception as e:
        logger.warning(f"HTML parse issue in view_product_details: {e}, falling back to plain text")
        import re
        clean_desc = re.sub(r'<[^>]+>', '', product.get('description', '')).strip()
        fallback_text = (
            f"{product['name']}\n\n"
            f"💰 Price: {selling_price:,.0f} Birr\n"
            f"📦 Stock: {supplier_stock} Available\n"
            f"⚡ Delivery: {delivery_type}\n\n"
            f"📝 Description:\n{clean_desc}"
        )
        await query.message.edit_text(
            text=fallback_text,
            parse_mode=None,
            reply_markup=get_product_detail_keyboard(service_id, is_purchasable=in_stock, is_admin=is_admin, is_enabled=is_enabled)
        )

@router.callback_query(F.data.startswith("apply_promo:"))
async def prompt_apply_promo(query: CallbackQuery, state: FSMContext):
    """Prompt user to send a promo code."""
    if not (await db.get_service_status("discounts", True)):
        await query.answer("⚠️ የቅናሽ ኮድ ሲስተም ለጊዜው ተዘግቷል (Discounts disabled).", show_alert=True)
        return

    await query.answer()
    service_id = query.data.split(":", 1)[1]
    await state.update_data(promo_target_service_id=service_id)
    await state.set_state(ShopPromoStates.waiting_for_promo_code)

    prompt = (
        f"🎟️ <b>APPLY PROMO CODE / DISCOUNT VOUCHER</b>\n\n"
        f"👉 Please enter or send your <b>Promo Code</b> (e.g. <code>MELAX20</code>):\n\n"
        f"<i>To cancel, click the button below:</i>"
    )
    await query.message.edit_text(text=prompt, parse_mode="HTML", reply_markup=get_back_keyboard())

@router.message(ShopPromoStates.waiting_for_promo_code)
async def process_user_promo_code(message: Message, state: FSMContext):
    """Validate user promo code and display discounted confirmation screen."""
    user = message.from_user
    code = message.text.strip()
    data = await state.get_data()
    service_id = data.get("promo_target_service_id", "")
    await state.clear()

    if not service_id:
        await message.answer("⚠️ Session expired. Please select a product from the catalog:", reply_markup=get_back_keyboard())
        return

    product = await db.get_product_by_service_id(service_id)
    if not product:
        await message.answer("🔴 Product not found.", reply_markup=get_back_keyboard())
        return

    u_db = await db.get_or_create_user(user.id, user.username or "", user.first_name or "")
    user_id_uuid = u_db["id"]
    is_vip = u_db.get("is_vip", False)
    balance = float(u_db.get("wallet_balance", 0.00))

    base_price = await db.get_effective_price(user_id_uuid, is_vip, product)
    flash_percent = await db.get_global_discount_percent()
    if flash_percent > 0:
        base_price = max(0.0, round(base_price * (1.0 - (flash_percent / 100.0)), 2))

    is_valid, msg, discount_amount, final_price = await db.validate_and_apply_promo(code, user_id_uuid, base_price)

    if not is_valid:
        await message.answer(f"{msg}\n\nPrice remains: <code>{base_price:,.0f} Birr</code>", parse_mode="HTML", reply_markup=get_buy_confirm_keyboard(service_id))
        return

    balance_after = balance - final_price
    from config import emo
    confirm_text = (
        f"🎉 <b>PROMO CODE APPLIED! {emo('sparkle', '✨')}{emo('diamond', '💎')}</b>\n\n"
        f"📦 <b>Product:</b> {product['name']}\n"
        f"🎟️ <b>Promo Code:</b> <code>{code.upper()}</code>\n"
        f"💵 <b>Original Price:</b> <s>{base_price:,.0f} Birr</s>\n"
        f"🎁 <b>Discount:</b> <code>-{discount_amount:,.2f} Birr</code>\n"
        f"{emo('money', '💰')} <b>Final Price:</b> <code>{final_price:,.0f} Birr</code>\n\n"
        f"💳 <b>Current Balance:</b> <code>{balance:,.2f} Birr</code>\n"
        f"📉 <b>Balance After:</b> <code>{balance_after:,.2f} Birr</code>\n\n"
        f"<i>Click 'CONFIRM PURCHASE' to deduct balance and receive your account instantly!</i>"
    )

    await message.answer(
        text=confirm_text,
        parse_mode="HTML",
        reply_markup=get_buy_confirm_keyboard(service_id, promo_code=code.upper())
    )

@router.callback_query(F.data.startswith("buy_now:"))
async def confirm_purchase_action(query: CallbackQuery):
    """Prompt user with purchase confirmation card."""
    await query.answer()
    user = query.from_user
    service_id = query.data.split(":", 1)[1]

    product = await db.get_product_by_service_id(service_id)
    if not product:
        await query.message.edit_text("🔴 Product not found.", reply_markup=get_back_keyboard())
        return

    u_db = await db.get_user_by_telegram_id(user.id)
    user_id_uuid = u_db["id"]
    is_vip = u_db.get("is_vip", False)
    balance = float(u_db.get("wallet_balance", 0.00))

    base_price = await db.get_effective_price(user_id_uuid, is_vip, product)
    flash_percent = await db.get_global_discount_percent()
    if flash_percent > 0:
        selling_price = max(0.0, round(base_price * (1.0 - (flash_percent / 100.0)), 2))
    else:
        selling_price = base_price

    balance_after = balance - selling_price

    if balance < selling_price:
        insufficient_text = (
            f"❌ <b>INSUFFICIENT WALLET BALANCE 💳</b>\n\n"
            f"💎 <b>Product Price:</b> <code>{selling_price:,.0f} Birr</code>\n"
            f"💰 <b>Your Balance:</b> <code>{balance:,.2f} Birr</code>\n"
            f"📉 <b>Shortage:</b> <code>{selling_price - balance:,.2f} Birr</code>\n\n"
            f"👉 <i>Please top up your wallet via CBE or Telebirr to continue.</i>"
        )
        await query.message.edit_text(
            text=insufficient_text,
            parse_mode="HTML",
            reply_markup=get_back_keyboard()
        )
        return

    confirm_text = (
        f"⚠️ <b>CONFIRM YOUR PURCHASE 💎</b>\n\n"
        f"📦 <b>Product:</b> {product['name']}\n"
        f"🔢 <b>Quantity:</b> 1x\n"
        f"💰 <b>Price:</b> <code>{selling_price:,.0f} Birr</code>\n"
        f"💵 <b>Current Balance:</b> <code>{balance:,.2f} Birr</code>\n"
        f"📉 <b>Balance After:</b> <code>{balance_after:,.2f} Birr</code>\n\n"
        f"<i>Click 'CONFIRM PURCHASE' to deduct balance and receive your account instantly!</i>"
    )

    try:
        await query.message.edit_text(
            text=confirm_text,
            parse_mode="HTML",
            reply_markup=get_buy_confirm_keyboard(service_id)
        )
    except Exception as e:
        logger.warning(f"HTML parse issue in confirm_purchase_action: {e}, falling back to plain text")
        import re
        clean_name = re.sub(r'<[^>]+>', '', product['name']).strip()
        fallback_confirm = (
            f"CONFIRM YOUR PURCHASE\n\n"
            f"Product: {clean_name}\n"
            f"Quantity: 1x\n"
            f"Price: {selling_price:,.0f} Birr\n"
            f"Current Balance: {balance:,.2f} Birr\n"
            f"Balance After: {balance_after:,.2f} Birr\n\n"
            f"Click CONFIRM PURCHASE to deduct balance and receive your account instantly!"
        )
        await query.message.edit_text(
            text=fallback_confirm,
            parse_mode=None,
            reply_markup=get_buy_confirm_keyboard(service_id)
        )

@router.callback_query(F.data.startswith("confirm_buy:"))
async def execute_atomic_purchase(query: CallbackQuery, bot: Bot):
    """Execute atomic purchase workflow for both Manual products & API products with Promo Code support."""
    await query.answer()
    user = query.from_user
    
    # Parse callback data: confirm_buy:<service_id> or confirm_buy:<service_id>:<promo_code>
    parts = query.data.split(":")
    service_id = parts[1]
    applied_promo = parts[2] if len(parts) > 2 else ""

    if user.id not in user_purchase_locks:
        user_purchase_locks[user.id] = asyncio.Lock()

    if user_purchase_locks[user.id].locked():
        await query.answer("⚠️ Processing your previous request. Please wait!", show_alert=True)
        return

    async with user_purchase_locks[user.id]:
        maint_mode = bool(await db.get_setting("maintenance_mode", False))
        if maint_mode and not (await db.get_admin_role(user.id)):
            await query.message.edit_text("🛠️ <b>ቦቱ በጊዜያዊ ጥገና ላይ ነው (UNDER MAINTENANCE)</b>\n\nየሲስተም ማሻሻያ እየተደረገ ስለሆነ ለጊዜው ግብይት አቋርጠናል።", parse_mode="HTML", reply_markup=get_back_keyboard())
            return

        await query.message.edit_text("🔄 <i>Processing your order... Delivering instantly... ⚡</i>", parse_mode="HTML")

        product = await db.get_product_by_service_id(service_id)
        if not product or not product.get("is_enabled"):
            await query.message.edit_text("🔴 <b>PRODUCT UNAVAILABLE</b>\nThis product is currently disabled.", parse_mode="HTML", reply_markup=get_back_keyboard())
            return

        u_db = await db.get_or_create_user(user.id, user.username or "", user.first_name or "")
        user_id_uuid = u_db["id"]
        is_vip = u_db.get("is_vip", False)
        balance = float(u_db.get("wallet_balance", 0.00))
        base_price = await db.get_effective_price(user_id_uuid, is_vip, product)

        flash_percent = await db.get_global_discount_percent()
        if flash_percent > 0:
            base_price = max(0.0, round(base_price * (1.0 - (flash_percent / 100.0)), 2))

        selling_price = base_price
        if applied_promo:
            is_valid, _, _, final_price = await db.validate_and_apply_promo(applied_promo, user_id_uuid, base_price)
            if is_valid:
                selling_price = final_price

        if balance < selling_price:
            await query.message.edit_text("❌ <b>INSUFFICIENT BALANCE</b>\nPlease add balance to your wallet.", parse_mode="HTML", reply_markup=get_back_keyboard())
            return

        delivery_mode = product.get("delivery_type", "AUTOMATIC")

        # -------------------------------------------------------------
        # 1. DIRECT MANUAL MODE (Always routed to Admin Fulfillment)
        # -------------------------------------------------------------
        if delivery_mode == "MANUAL":
            deduct_res = await db.atomic_deduct_wallet(
                user_id=user_id_uuid,
                amount=selling_price,
                reference=f"MANUAL-{service_id}",
                description=f"Manual Purchase of {product['name']}"
            )
            if not deduct_res.get("success"):
                await query.message.edit_text(f"❌ <b>Payment deduction failed:</b> {deduct_res.get('error')}", reply_markup=get_back_keyboard())
                return

            order_record = await db.create_order(
                user_id=user_id_uuid,
                service_id=service_id,
                product_name=product["name"],
                quantity=1,
                selling_price=selling_price,
                supplier_cost=0.00,
                aiverse_order_id="MANUAL-PENDING",
                delivered_products="Waiting for Admin Fulfillment",
                status="PENDING_FULFILLMENT"
            )
            melax_order_id = order_record.get("melax_order_id", "MELAX-MANUAL")

            if applied_promo:
                await db.increment_promo_usage(applied_promo, user_id_uuid)

            from config import emo, get_product_brand_icon
            brand_icon = get_product_brand_icon(product["name"])
            holding_note = product.get("manual_fulfillment_note") or product.get("description") or "Our administrator has received your order and will send your account credentials directly in this chat shortly!"

            holding_card = (
                f"🎉 <b>ORDER RECEIVED & IN PROGRESS! 👨‍💻💎</b>\n\n"
                f"{brand_icon} <b>Product:</b> <code>{product['name']}</code>\n"
                f"🧾 <b>Order ID:</b> <code>{melax_order_id}</code>\n"
                f"{emo('money', '💰')} <b>Paid:</b> <code>{selling_price:,.0f} Birr</code>\n"
                f"🚚 <b>Delivery:</b> <code>👨‍💻 Manual Admin Delivery</code>\n\n"
                f"📝 <b>Message from Admin:</b>\n"
                f"<i>{holding_note}</i>\n\n"
                f"{emo('sparkle', '✨')} <i>You will receive your account details in this chat as soon as the admin delivers it!</i>"
            )
            await query.message.edit_text(text=holding_card, parse_mode="HTML", reply_markup=get_back_keyboard())
            await log_purchase_to_channel(bot, user.id, product["name"], 1, price=selling_price)

            # Alert Admins Privately
            admin_alert = (
                f"🔔 <b>NEW MANUAL ORDER #{melax_order_id[-6:]} WAITING FOR FULFILLMENT 👨‍💻</b>\n\n"
                f"📦 <b>Product:</b> {product['name']}\n"
                f"👤 <b>Customer:</b> @{user.username or user.first_name} (ID: <code>{user.id}</code>)\n"
                f"💰 <b>Amount:</b> <code>{selling_price:,.0f} Birr</code>\n\n"
                f"👉 Open <b>Admin Panel ➡️ Pending Manual Orders</b> to fulfill!"
            )
            for adm in ADMIN_IDS:
                try:
                    await bot.send_message(chat_id=adm, text=admin_alert, parse_mode="HTML")
                except Exception:
                    pass
            return

        # -------------------------------------------------------------
        # 2. MANUAL PRODUCT WITH AUTOMATIC / HYBRID DELIVERY
        # -------------------------------------------------------------
        if service_id.startswith("MANUAL_"):
            supplier_stock = int(product.get("supplier_stock", 0))
            
            # If stock is empty and HYBRID mode is active, switch smoothly to manual holding order
            if supplier_stock <= 0 and delivery_mode == "HYBRID":
                deduct_res = await db.atomic_deduct_wallet(
                    user_id=user_id_uuid,
                    amount=selling_price,
                    reference=f"HYBRID-FALLBACK-{service_id}",
                    description=f"Hybrid Fallback Purchase of {product['name']}"
                )
                if not deduct_res.get("success"):
                    await query.message.edit_text(f"❌ <b>Payment deduction failed:</b> {deduct_res.get('error')}", reply_markup=get_back_keyboard())
                    return

                order_record = await db.create_order(
                    user_id=user_id_uuid,
                    service_id=service_id,
                    product_name=product["name"],
                    quantity=1,
                    selling_price=selling_price,
                    supplier_cost=0.00,
                    aiverse_order_id="HYBRID-FALLBACK-MANUAL",
                    delivered_products="Waiting for Admin Fulfillment (Stock Fallback)",
                    status="PENDING_FULFILLMENT"
                )
                melax_order_id = order_record.get("melax_order_id", "MELAX-HYBRID")

                if applied_promo:
                    await db.increment_promo_usage(applied_promo, user_id_uuid)

                from config import emo, get_product_brand_icon
                brand_icon = get_product_brand_icon(product["name"])
                holding_card = (
                    f"🎉 <b>ORDER RECEIVED & BEING PREPARED! 🔄💎</b>\n\n"
                    f"{brand_icon} <b>Product:</b> <code>{product['name']}</code>\n"
                    f"🧾 <b>Order ID:</b> <code>{melax_order_id}</code>\n"
                    f"{emo('money', '💰')} <b>Paid:</b> <code>{selling_price:,.0f} Birr</code>\n"
                    f"🚚 <b>Delivery:</b> <code>🔄 Fast Admin Delivery (High Demand)</code>\n\n"
                    f"📝 <b>Status:</b>\n"
                    f"<i>Our administrator has received your order and will dispatch your private account directly in this chat shortly!</i>"
                )
                await query.message.edit_text(text=holding_card, parse_mode="HTML", reply_markup=get_back_keyboard())
                await log_purchase_to_channel(bot, user.id, product["name"], 1, price=selling_price)
                return

            if supplier_stock <= 0:
                await query.message.edit_text("🔴 <b>OUT OF STOCK</b>\nThis product is currently out of stock.", parse_mode="HTML", reply_markup=get_back_keyboard())
                return

            deduct_res = await db.atomic_deduct_wallet(
                user_id=user_id_uuid,
                amount=selling_price,
                reference=f"MANUAL-{service_id}",
                description=f"Purchase of {product['name']}"
            )

            if not deduct_res.get("success"):
                await query.message.edit_text(f"❌ <b>Payment deduction failed:</b> {deduct_res.get('error')}", reply_markup=get_back_keyboard())
                return

            # Decrement manual stock in database
            new_stock = max(0, supplier_stock - 1)
            if db.is_configured:
                db.client.table("products").update({
                    "supplier_stock": new_stock,
                    "supplier_available": True if new_stock > 0 else False
                }).eq("service_id", service_id).execute()

            temp_order_id = f"MELAX-{uuid.uuid4().hex[:8].upper()}"
            vault_item = await db.pop_next_stock_item(service_id, temp_order_id)
            if vault_item:
                delivery_content = vault_item
            else:
                delivery_content = product.get("manual_fulfillment_note") or product.get("description") or "Instant Delivery Completed."

            order_record = await db.create_order(
                user_id=user_id_uuid,
                service_id=service_id,
                product_name=product["name"],
                quantity=1,
                selling_price=selling_price,
                supplier_cost=0.00,
                aiverse_order_id="VAULT-FULFILLED" if vault_item else "MANUAL-FULFILLED",
                delivered_products=delivery_content,
                status="SUCCESS"
            )

            melax_order_id = order_record.get("melax_order_id", temp_order_id)

            from config import emo, get_product_brand_icon
            brand_icon = get_product_brand_icon(product["name"])

            success_text = (
                f"🎉 <b>ORDER COMPLETED SUCCESSFULLY! {emo('lightning', '⚡')}{emo('diamond', '💎')}</b>\n\n"
                f"{brand_icon} <b>Product:</b> <code>{product['name']}</code>\n"
                f"🧾 <b>Order ID:</b> <code>{melax_order_id}</code>\n"
                f"{emo('money', '💰')} <b>Paid:</b> <code>{selling_price:,.0f} Birr</code>\n\n"
                f"🔑 <b>Your Account Details / Access Code:</b>\n"
                f"<code>{delivery_content}</code>\n\n"
                f"{emo('sparkle', '✨')} <i>Thank you for shopping with MELAX DIGITAL SHOP!</i> {emo('crown', '👑')}"
            )

            if applied_promo:
                await db.increment_promo_usage(applied_promo, user_id_uuid)

            # Process Referral Purchase Commission
            try:
                comm_data = await db.process_purchase_referral_commission(
                    buyer_user_id=user_id_uuid,
                    product=product,
                    purchase_price=selling_price,
                    melax_order_id=melax_order_id
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
                logger.warning(f"Failed to process referral commission for {melax_order_id}: {e}")

            await query.message.edit_text(text=success_text, parse_mode="HTML", reply_markup=get_back_keyboard())
            await log_purchase_to_channel(bot, user.id, product["name"], 1, price=selling_price)
            return

        # -------------------------------------------------------------
        # 3. AIVERSE API PRODUCT FULFILLMENT (WITH HYBRID FALLBACK)
        # -------------------------------------------------------------
        supplier_me = await api_client.get_me()
        supplier_balance = float(supplier_me.get("wallet_balance", 0.00))
        supplier_cost = float(product.get("supplier_cost", 0.00))

        if supplier_balance < supplier_cost:
            if delivery_mode == "HYBRID":
                # Deduct and route to manual admin fulfillment
                deduct_res = await db.atomic_deduct_wallet(user_id_uuid, selling_price, f"HYBRID-API-FALLBACK-{service_id}", f"Hybrid fallback for {product['name']}")
                if deduct_res.get("success"):
                    order_record = await db.create_order(
                        user_id=user_id_uuid,
                        service_id=service_id,
                        product_name=product["name"],
                        quantity=1,
                        selling_price=selling_price,
                        supplier_cost=supplier_cost,
                        aiverse_order_id="HYBRID-API-PENDING",
                        delivered_products="Waiting for Admin Fulfillment (API Fallback)",
                        status="PENDING_FULFILLMENT"
                    )
                    melax_order_id = order_record.get("melax_order_id", "MELAX-HYBRID")
                    from config import emo, get_product_brand_icon
                    brand_icon = get_product_brand_icon(product["name"])
                    holding_card = (
                        f"🎉 <b>ORDER RECEIVED & BEING PREPARED! 🔄💎</b>\n\n"
                        f"{brand_icon} <b>Product:</b> <code>{product['name']}</code>\n"
                        f"🧾 <b>Order ID:</b> <code>{melax_order_id}</code>\n"
                        f"{emo('money', '💰')} <b>Paid:</b> <code>{selling_price:,.0f} Birr</code>\n"
                        f"🚚 <b>Delivery:</b> <code>🔄 Fast Admin Delivery</code>\n\n"
                        f"<i>Our administrator has received your order and will dispatch your private account directly in this chat shortly!</i>"
                    )
                    await query.message.edit_text(text=holding_card, parse_mode="HTML", reply_markup=get_back_keyboard())
                    return

            await query.message.edit_text(
                "🔴 <b>TEMPORARILY UNAVAILABLE</b>\n\nThis product is currently unavailable. Please try again later.",
                parse_mode="HTML",
                reply_markup=get_back_keyboard()
            )
            return

        api_res = await api_client.place_order(service_id=service_id, quantity=1)

        if not api_res.get("success") and "products" not in api_res:
            if delivery_mode == "HYBRID":
                # Fallback to manual admin fulfillment
                deduct_res = await db.atomic_deduct_wallet(user_id_uuid, selling_price, f"HYBRID-API-FALLBACK-{service_id}", f"Hybrid fallback for {product['name']}")
                if deduct_res.get("success"):
                    order_record = await db.create_order(
                        user_id=user_id_uuid,
                        service_id=service_id,
                        product_name=product["name"],
                        quantity=1,
                        selling_price=selling_price,
                        supplier_cost=supplier_cost,
                        aiverse_order_id="HYBRID-API-PENDING",
                        delivered_products="Waiting for Admin Fulfillment (API Fallback)",
                        status="PENDING_FULFILLMENT"
                    )
                    melax_order_id = order_record.get("melax_order_id", "MELAX-HYBRID")
                    from config import emo, get_product_brand_icon
                    brand_icon = get_product_brand_icon(product["name"])
                    holding_card = (
                        f"🎉 <b>ORDER RECEIVED & BEING PREPARED! 🔄💎</b>\n\n"
                        f"{brand_icon} <b>Product:</b> <code>{product['name']}</code>\n"
                        f"🧾 <b>Order ID:</b> <code>{melax_order_id}</code>\n"
                        f"{emo('money', '💰')} <b>Paid:</b> <code>{selling_price:,.0f} Birr</code>\n"
                        f"🚚 <b>Delivery:</b> <code>🔄 Fast Admin Delivery</code>\n\n"
                        f"<i>Our administrator has received your order and will dispatch your private account directly in this chat shortly!</i>"
                    )
                    await query.message.edit_text(text=holding_card, parse_mode="HTML", reply_markup=get_back_keyboard())
                    return

            err_msg = api_res.get("error", "Supplier order failed")
            await query.message.edit_text(
                "❌ <b>ORDER COULD NOT BE COMPLETED</b>\n\nYour wallet balance has not been charged. Please try again later or contact support @mr_melaku.",
                parse_mode="HTML",
                reply_markup=get_back_keyboard()
            )
            return

        delivered_codes = api_res.get("products", [])
        aiverse_order_id = api_res.get("order_id", "N/A")
        code_str = "\n".join(delivered_codes) if delivered_codes else "No code returned"

        deduct_res = await db.atomic_deduct_wallet(
            user_id=user_id_uuid,
            amount=selling_price,
            reference=aiverse_order_id,
            description=f"Purchase of {product['name']}"
        )

        order_record = await db.create_order(
            user_id=user_id_uuid,
            service_id=service_id,
            product_name=product["name"],
            quantity=1,
            selling_price=selling_price,
            supplier_cost=supplier_cost,
            aiverse_order_id=aiverse_order_id,
            delivered_products=code_str,
            status="SUCCESS"
        )

        melax_order_id = order_record.get("melax_order_id", "MELAX-ORDER")

        if applied_promo:
            await db.increment_promo_usage(applied_promo, user_id_uuid)

        # Process Referral Purchase Commission
        try:
            comm_data = await db.process_purchase_referral_commission(
                buyer_user_id=user_id_uuid,
                product=product,
                purchase_price=selling_price,
                melax_order_id=melax_order_id
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
            logger.warning(f"Failed to process referral commission for {melax_order_id}: {e}")

        from config import emo, get_product_brand_icon
        brand_icon = get_product_brand_icon(product["name"])

        success_text = (
            f"🎉 <b>ORDER COMPLETED SUCCESSFULLY! {emo('lightning', '⚡')}{emo('diamond', '💎')}</b>\n\n"
            f"{brand_icon} <b>Product:</b> <code>{product['name']}</code>\n"
            f"🧾 <b>Order ID:</b> <code>{melax_order_id}</code>\n"
            f"{emo('money', '💰')} <b>Paid:</b> <code>{selling_price:,.0f} Birr</code>\n\n"
            f"🔑 <b>Your Product Code / Link:</b>\n"
            f"<code>{code_str}</code>\n\n"
            f"{emo('sparkle', '✨')} <i>Thank you for shopping with MELAX DIGITAL SHOP!</i> {emo('crown', '👑')}"
        )

        await query.message.edit_text(
            text=success_text,
            parse_mode="HTML",
            reply_markup=get_back_keyboard()
        )

        await log_purchase_to_channel(bot, user.id, product["name"], 1, price=selling_price)
