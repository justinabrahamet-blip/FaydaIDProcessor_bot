import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from db_client import db
from keyboards import get_referral_keyboard, get_back_keyboard
from config import emo, animate_text, get_product_brand_icon
from i18n import t, REPLY_TEXT_REFERRAL

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("referral"))
@router.message(F.text.in_(REPLY_TEXT_REFERRAL))
@router.callback_query(F.data == "btn_referral")
async def show_referral_program(event: Message | CallbackQuery, bot: Bot):
    """Display referral link, earnings stats, milestone progress, and interactive claim buttons."""
    if isinstance(event, CallbackQuery):
        await event.answer()
        user = event.from_user
        message = event.message
    else:
        user = event.from_user
        message = event

    if not (await db.get_service_status("referrals", True)) and not (await db.get_admin_role(user.id)):
        off_msg = (
            "🎁 <b>REFERRAL & MILESTONE REWARDS 💎</b>\n\n"
            "⚠️ የግብዣ ሽልማቶች ፕሮግራም በጊዜያዊነት ቆሟል (Temporarily Paused)。\n"
            "<i>እባክዎን ትንሽ ቆይተው እንደገና ይመልከቱ!</i>"
        )
        if isinstance(event, CallbackQuery):
            await message.edit_text(off_msg, parse_mode="HTML", reply_markup=get_back_keyboard())
        else:
            await message.answer(off_msg, parse_mode="HTML", reply_markup=get_back_keyboard())
        return

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"

    u_db = await db.get_or_create_user(user.id, user.username or "", user.first_name or "")
    milestones = await db.get_referral_milestones(u_db["id"])
    tiers = await db.get_referral_tiers()

    total_invites = milestones["total_invites"]
    available_invites = milestones["available_invites"]
    claimed_invites = milestones["claimed_invites"]
    earned = milestones["total_earned"]

    # Calculate next milestone progress bar
    next_tier = None
    sorted_tiers = sorted(tiers, key=lambda x: int(x.get("invites", 20)))
    for t in sorted_tiers:
        if int(t.get("invites", 20)) > available_invites:
            next_tier = t
            break

    if next_tier:
        req = int(next_tier.get("invites", 20))
        ratio = min(1.0, available_invites / req) if req > 0 else 1.0
        filled = int(ratio * 10)
        bar = "█" * filled + "░" * (10 - filled)
        remaining = req - available_invites
        milestone_text = (
            f"🎯 <b>Next Reward Goal:</b> {next_tier.get('reward_name', 'Reward')}\n"
            f"📊 <code>[{bar}]</code> <b>{available_invites}/{req}</b> (Invite <b>{remaining}</b> more!)\n"
        )
    else:
        milestone_text = f"👑 <b>All current milestone tiers unlocked! Claim your rewards below!</b>\n"

    # Reward tiers list
    tiers_text = ""
    for t in sorted_tiers:
        t_req = int(t.get("invites", 20))
        t_name = t.get("reward_name", "Reward")
        t_icon = t.get("icon", "🎁")
        status_badge = "✅ READY TO CLAIM!" if available_invites >= t_req else f"({t_req - available_invites} more invites needed)"
        tiers_text += f"• {t_icon} <b>{t_name}</b> [<code>{t_req} Invites</code>] - <i>{status_badge}</i>\n"

    text = (
        f"{emo('gift', '🎁')} <b>REFERRAL & MILESTONE REWARDS PROGRAM</b> {emo('diamond', '💎')}\n\n"
        f"Invite your friends to <b>MELAX DIGITAL SHOP</b> and unlock <b>Dual Referral Rewards</b>:\n"
        f"1. 🎁 <b>Free Premium Accounts</b> by reaching invite milestones!\n"
        f"2. 💵 <b>Instant Cash Commission:</b> Whenever your invited friends purchase any product, you instantly earn cash commission directly credited to your wallet!\n\n"
        f"{emo('profile', '👥')} <b>Total Friends Invited:</b> <code>{total_invites} Users</code>\n"
        f"🎟️ <b>Available Reward Points:</b> <code>{available_invites} Invites</code> (Claimed: {claimed_invites})\n"
        f"{emo('money', '💰')} <b>Total Cash Commission Earned:</b> <code>{earned:,.2f} Birr</code> {emo('sparkle', '✨')}\n\n"
        f"{milestone_text}\n"
        f"🏆 <b>Available Milestone Rewards:</b>\n"
        f"{tiers_text}\n"
        f"🔗 <b>Your Exclusive Referral Link:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"<i>Tap your link to copy & share! When you claim a free account, your points reset so you can earn again!</i>"
    )

    user_lang = u_db.get("language_code", "am") if u_db else "am"
    is_admin = (await db.get_admin_role(user.id)) is not None
    kb = get_referral_keyboard(tiers, available_invites, lang=user_lang, is_admin=is_admin)
    if isinstance(event, CallbackQuery):
        try:
            await message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
    else:
        await message.answer(text=text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "btn_ref_comm_rates")
async def show_referral_commission_rates(query: CallbackQuery):
    """Display comprehensive table of per-product referral commission rates and earnings."""
    await query.answer()
    user = query.from_user
    u_db = await db.get_user_by_telegram_id(user.id)
    user_lang = u_db.get("language_code", "am") if u_db else "am"

    products = await db.get_all_products(enabled_only=True)
    
    if user_lang == "am":
        header = (
            f"{emo('gift', '🎁')} <b>የእቃዎች የሪፈራል ግዢ ኮሚሽን ዝርዝር 💰⚡</b>\n\n"
            f"በእርስዎ ሊንክ የተመዘገበ ደንበኛ እቃ ሲገዛ የሚከተለውን <b>የጥሬ ገንዘብ ኮሚሽን</b> በቀጥታ ወደ ዋሌትዎ ገቢ ይደረግልዎታል፦\n\n"
        )
    else:
        header = (
            f"{emo('gift', '🎁')} <b>PRODUCT REFERRAL COMMISSION RATES 💰⚡</b>\n\n"
            f"When a friend registered with your link purchases any product, you earn the following instant cash commission directly into your wallet:\n\n"
        )

    import html
    import re
    items_text = ""
    if products:
        for p in products:
            raw_name = p.get("name", "Product")
            clean_name = html.escape(re.sub(r'<[^>]+>', '', raw_name).strip() or raw_name)
            price = float(p.get("selling_price", 0.0))
            comm_pct = float(p.get("referral_commission_percent", 5.0) or 0.0)
            earn_amt = round(price * (comm_pct / 100.0), 2)
            brand_icon = get_product_brand_icon(raw_name)
            if user_lang == "am":
                items_text += f"• {brand_icon} <b>{clean_name}</b>\n   💵 ዋጋ: <code>{price:,.0f} ብር</code> | 🎁 ኮሚሽን: <code>{comm_pct}%</code> (<b>+{earn_amt:,.2f} ብር</b> በግዢ)\n\n"
            else:
                items_text += f"• {brand_icon} <b>{clean_name}</b>\n   💵 Price: <code>{price:,.0f} Birr</code> | 🎁 Commission: <code>{comm_pct}%</code> (<b>+{earn_amt:,.2f} Birr</b> per sale)\n\n"
    else:
        items_text = "<i>ምንም እቃዎች እስካሁን አልተዘረዘሩም (No active products).</i>\n\n" if user_lang == "am" else "<i>No active products currently.</i>\n\n"

    footer = f"🔗 <i>የእርስዎን የግብዣ ሊንክ ለጓደኞችዎ በማጋራት የእድሜ ልክ ተከታታይ ገቢ ያግኙ!</i> 👑" if user_lang == "am" else \
             f"🔗 <i>Share your referral link with friends and start earning lifetime recurring commissions!</i> 👑"

    full_text = header + items_text + footer

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    back_btn_text = "🔙 ወደ ሪፈራል ማውጫ" if user_lang == "am" else "🔙 Back to Referrals"
    builder.row(InlineKeyboardButton(text=back_btn_text, callback_data="btn_referral"))
    builder.row(InlineKeyboardButton(text="❌ ሰርዝ" if user_lang == "am" else "CANCEL", callback_data="btn_cancel"))

    try:
        await query.message.edit_text(
            text=animate_text(full_text),
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logger.warning(f"Error rendering commission rates table HTML: {e}, falling back to plain text")
        plain_text = re.sub(r'<[^>]+>', '', full_text)
        await query.message.edit_text(
            text=plain_text,
            reply_markup=builder.as_markup()
        )

@router.callback_query(F.data.startswith("ref_claim:"))
async def process_referral_claim(query: CallbackQuery, bot: Bot):
    """Handle referral milestone reward claim."""
    await query.answer()
    tier_id = query.data.split(":", 1)[1]
    user = query.from_user

    u_db = await db.get_or_create_user(user.id, user.username or "", user.first_name or "")
    success, msg, claim_data = await db.claim_referral_reward(u_db["id"], tier_id, user.id)

    if not success:
        await query.answer(f"⚠️ {msg}", show_alert=True)
        return

    tier_name = claim_data.get("tier_name", "Premium Account")
    spent = claim_data.get("invites_spent", 20)
    del_code = claim_data.get("delivery_code")

    if claim_data.get("status") == "DELIVERED" and del_code:
        result_text = (
            f"🎉 <b>CONGRATULATIONS! REWARD DELIVERED!</b> {emo('sparkle', '✨')}{emo('diamond', '💎')}\n\n"
            f"🎁 <b>Claimed Reward:</b> {tier_name}\n"
            f"🎟️ <b>Points Spent:</b> <code>{spent} Invites</code>\n\n"
            f"🔑 <b>Your Account Credentials / Key:</b>\n"
            f"<code>{del_code}</code>\n\n"
            f"<i>Your available points have been reset by {spent} invites. Keep inviting friends to earn more free rewards!</i>"
        )
    else:
        result_text = (
            f"🎉 <b>REWARD CLAIM SUBMITTED!</b> {emo('sparkle', '✨')}{emo('diamond', '💎')}\n\n"
            f"🎁 <b>Claimed Reward:</b> {tier_name}\n"
            f"📋 <b>Claim ID:</b> <code>{claim_data.get('claim_id')}</code>\n"
            f"🎟️ <b>Points Spent:</b> <code>{spent} Invites</code>\n\n"
            f"<i>Our Administrator has been notified and will deliver your account credentials to you shortly! Your points have been reset so you can continue inviting.</i>"
        )

    await query.message.answer(text=result_text, parse_mode="HTML", reply_markup=get_back_keyboard())
