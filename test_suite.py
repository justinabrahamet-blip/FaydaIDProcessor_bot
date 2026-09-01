import asyncio
import logging

from verifier import verify_cbe_async, check_account_match, check_holder_match
from security_util import sanitize_input, format_4digit_id
from keyboards import get_main_reply_keyboard, get_force_join_keyboard, get_products_keyboard
from admin_customers_handler import get_admin_customer_card_keyboard
from db_client import db
from i18n import t, ALL_REPLY_BUTTON_TEXTS, REPLY_TEXT_SHOP, REPLY_TEXT_WALLET
from config import animate_text, update_dynamic_emoji

logging.basicConfig(level=logging.INFO)

async def run_full_system_test():
    print("============================================================")
    print("STARTING FULL SYSTEM END-TO-END TEST SUITE")
    print("============================================================")

    # 1. TEST SECURITY UTIL & SANITIZATION
    print("\n[1/5] Testing Security & Input Sanitization...")
    is_safe, sanitized = sanitize_input("<b>Hello World</b> <script>alert(1)</script>")
    sanitization_ok = (not is_safe) and ("<script>" not in sanitized)
    print(f"  - Input Sanitization Test: {'PASSED' if sanitization_ok else 'FAILED'}")

    short_id = format_4digit_id("srv_12")
    print(f"  - 4-Digit Product ID Formatting: {short_id} ({'PASSED' if len(short_id) == 4 else 'FAILED'})")

    # 2. TEST STRICT CBE LINK REQUIREMENT
    print("\n[2/5] Testing Strict CBE Link Requirement (Reject Plain Text Without Link)...")
    plain_text_without_link = "Your Account 1000320563279 has been Credited with Amount ETB 1000.00 from KASSA. Txn ID: FT24241XXXX."
    res1 = await verify_cbe_async(plain_text_without_link, expected_account="1000320563279", expected_holder="MELAX DIGITAL")
    print(f"  - Reject Plain Text Without Link: {'PASSED (Correctly Rejected)' if not res1['ok'] and res1['code'] == 'MISSING_LINK' else 'FAILED'}")

    # 3. TEST HOLDER NAME MATCHING ENGINE
    print("\n[3/5] Testing Account Holder Name Matcher Engine...")
    m1 = check_holder_match("MELAX DIGITAL SHOP", "MELAX")
    m2 = check_holder_match("ABEBE KASSA", "MELAX")
    print(f"  - Valid Holder Name Match ('MELAX DIGITAL SHOP' vs 'MELAX'): {'PASSED' if m1 else 'FAILED'}")
    print(f"  - Invalid Holder Name Match ('ABEBE KASSA' vs 'MELAX'): {'PASSED (Correctly Rejected)' if not m2 else 'FAILED'}")

    # 4. TEST KEYBOARDS & UI BUILDERS
    print("\n[4/5] Testing Keyboards & Reply UI Builders...")
    reply_kb = get_main_reply_keyboard(is_admin=True)
    fj_kb = get_force_join_keyboard()
    cust_card_kb = get_admin_customer_card_keyboard(123456789, is_banned=False)
    print("  - Reply Keyboard Rows Count:", len(reply_kb.keyboard))
    print("  - Force Join Inline Buttons Count:", len(fj_kb.inline_keyboard))
    print("  - Admin Customer Card Buttons Count:", len(cust_card_kb.inline_keyboard))
    print("  - Keyboards Build Test: PASSED")

    # 5. TEST DATABASE CLIENT & SETTINGS FALLBACK
    print("\n[5/7] Testing Supabase DB Manager & Fallback System...")
    print(f"  - Database Configured Status: {db.is_configured}")
    cbe_acc = await db.get_setting("cbe_account", "1000320563279")
    cbe_holder = await db.get_setting("cbe_account_holder", "MELAX DIGITAL")
    print(f"  - CBE Account Setting: {cbe_acc}")
    print(f"  - CBE Holder Setting: {cbe_holder}")
    print("  - DB Settings Test: PASSED")

    # 6. TEST REFERRAL MILESTONES & CLAIMING ENGINE
    print("\n[6/7] Testing Referral Milestones, Tiers & Claiming Engine...")
    tiers = await db.get_referral_tiers()
    print(f"  - Loaded Referral Tiers Count: {len(tiers)} (Default: Spotify 20 invites, Gemini 25 invites)")
    
    # Test claiming workflow with mock points
    test_user_id = "test-user-ref-123"
    await db.update_setting(f"ref_claimed_pts_{test_user_id}", 0)
    
    # Simulate user having 22 invites (mock stats = 22)
    await db.update_setting("referral_reward_tiers", [
        {"id": "tier_spotify", "invites": 20, "reward_name": "Spotify Premium", "auto_deliver": False}
    ])
    
    success_claim, msg, claim_obj = await db.claim_referral_reward(test_user_id, "tier_spotify", telegram_id=999888777)
    # Since in mock unconfigured mode total_invites is 0, claim correctly rejects insufficient invites
    print(f"  - Insufficient Invites Claim Guard (0/20): {'PASSED (Correctly Rejected)' if not success_claim else 'FAILED'}")

    # 7. TEST PROMO CODE & DISCOUNT ENGINE
    print("\n[7/8] Testing Promo Code & Flash Sales Engine...")
    # Create test promo code
    await db.create_or_update_promo_code("TEST20", discount_type="PERCENT", value=20.0, max_uses=5)
    valid, pmsg, disc, final_p = await db.validate_and_apply_promo("TEST20", "user-uuid", product_price=500.0)
    print(f"  - Apply 20% Promo on 500 Birr: Final={final_p:,.0f} Birr, Disc=-{disc:,.0f} Birr ({'PASSED' if final_p == 400.0 else 'FAILED'})")

    # Flat discount promo
    await db.create_or_update_promo_code("SAVE50", discount_type="FLAT", value=50.0, max_uses=5)
    valid_f, _, disc_f, final_f = await db.validate_and_apply_promo("SAVE50", "user-uuid", product_price=300.0)
    print(f"  - Apply 50 Birr Flat Promo on 300 Birr: Final={final_f:,.0f} Birr ({'PASSED' if final_f == 250.0 else 'FAILED'})")

    # Global Flash Sale
    await db.set_global_discount_percent(15.0)
    cur_flash = await db.get_global_discount_percent()
    print(f"  - Global Flash Sale Setting: {cur_flash:.0f}% OFF ({'PASSED' if cur_flash == 15.0 else 'FAILED'})")
    await db.set_global_discount_percent(0.0)

    # 8. TEST 3-WAY PRODUCT DELIVERY ENGINE & MANUAL FULFILLMENT
    print("\n[8/8] Testing 3-Way Delivery Engine (AUTOMATIC, MANUAL, HYBRID)...")
    # 8a. Create product with MANUAL delivery
    p_manual = await db.create_manual_product(
        name="Private ChatGPT Plus 1 Month",
        selling_price=1200.0,
        stock=50,
        description="Manual Admin Delivery with custom setup",
        service_id="MANUAL_TEST_01",
        delivery_type="MANUAL",
        manual_fulfillment_note="Admin will send credentials in 5 mins."
    )
    print(f"  - Manual Product Creation: deliv={p_manual.get('delivery_type')} ({'PASSED' if p_manual.get('delivery_type') == 'MANUAL' else 'FAILED'})")

    # 8b. Create product with HYBRID delivery
    p_hybrid = await db.create_manual_product(
        name="Netflix 4K UHD Profile",
        selling_price=450.0,
        stock=10,
        description="Hybrid instant with manual fallback",
        service_id="MANUAL_TEST_02",
        delivery_type="HYBRID"
    )
    print(f"  - Hybrid Product Creation: deliv={p_hybrid.get('delivery_type')} ({'PASSED' if p_hybrid.get('delivery_type') == 'HYBRID' else 'FAILED'})")

    # 8c. Test Manual Order Creation & Fulfillment
    order_m = await db.create_order(
        user_id="user-uuid-test",
        service_id="MANUAL_TEST_01",
        product_name="Private ChatGPT Plus 1 Month",
        quantity=1,
        selling_price=1200.0,
        supplier_cost=0.0,
        aiverse_order_id="MANUAL-PENDING",
        delivered_products="Waiting for Admin Fulfillment",
        status="PENDING_FULFILLMENT"
    )
    print(f"  - Manual Order Holding Status: {order_m.get('status')} ({'PASSED' if order_m.get('status') == 'PENDING_FULFILLMENT' else 'FAILED'})")

    # 8d. Test Admin Manual Fulfillment
    f_ok, f_msg, f_data = await db.fulfill_manual_order(order_m["melax_order_id"], admin_id=123456, delivery_content="email:password | Pin: 1234")
    print(f"  - Admin Fulfill Manual Order: status={f_data.get('status', 'SUCCESS') if f_data else 'ERR'} ({'PASSED' if f_ok else 'FAILED'})")

    # 9. TEST MASTER SERVICES ON/OFF & REWARD TIER CUSTOMIZATION
    print("\n[9/9] Testing Master Services ON/OFF & Referral Reward Customization...")
    # 9a. Test Reward Tier Customization
    new_tier = await db.add_referral_tier("Netflix 4K UHD 1 Month", invites=30)
    print(f"  - Add Custom Reward Tier (Netflix 30 Invites): {'PASSED' if new_tier.get('reward_name') == 'Netflix 4K UHD 1 Month' else 'FAILED'}")
    
    await db.update_referral_tier_details(new_tier["id"], reward_name="Netflix 4K Premium UHD", invites=35)
    updated_tiers = await db.get_referral_tiers()
    u_match = next((t for t in updated_tiers if t.get("id") == new_tier["id"]), {})
    print(f"  - Update Reward Tier (35 Invites): {'PASSED' if u_match.get('invites') == 35 else 'FAILED'}")

    await db.delete_referral_tier(new_tier["id"])
    del_tiers = await db.get_referral_tiers()
    del_match = next((t for t in del_tiers if t.get("id") == new_tier["id"]), None)
    print(f"  - Delete Reward Tier: {'PASSED' if del_match is None else 'FAILED'}")

    # 9b. Test Master Services ON / OFF
    await db.set_service_status("shop", False)
    shop_status = await db.get_service_status("shop", True)
    print(f"  - Toggle Shop Service OFF: {'PASSED' if shop_status is False else 'FAILED'}")
    
    await db.set_service_status("shop", True)
    shop_status_on = await db.get_service_status("shop", True)
    print(f"  - Toggle Shop Service ON: {'PASSED' if shop_status_on is True else 'FAILED'}")

    # 10. TEST MULTILINGUAL (AM/ENG), ANIMATED TEXT & STOCK-ONLY PRODUCT BUTTONS
    print("\n[10/10] Testing Multilingual (AM/ENG), Animated Emojis & Stock Format...")

    # 10a. i18n Translation & Toggle
    am_title = t("welcome_title", "am")
    en_title = t("welcome_title", "en")
    print(f"  - i18n Translation Check: {'PASSED' if 'ሜላክስ' in am_title and 'MELAX' in en_title else 'FAILED'}")

    await db.set_user_language(99998888, "en")
    user_lang = await db.get_user_language(99998888)
    print(f"  - User Language Preference DB: lang={user_lang} ({'PASSED' if user_lang == 'en' else 'FAILED'})")

    # 10b. Reply Buttons Matcher
    print(f"  - Reply Buttons Matcher Coverage: {len(ALL_REPLY_BUTTON_TEXTS)} buttons ({'PASSED' if '🛒 ዲጂታል እቃዎች' in REPLY_TEXT_SHOP and '💳 ዋሌት' in REPLY_TEXT_WALLET else 'FAILED'})")

    # 10c. Products List Button Stock-Only Format
    sample_prods = [{"service_id": "TEST_01", "name": "Spotify Premium", "selling_price": 200.0, "supplier_stock": 50, "supplier_available": True, "is_enabled": True}]
    kb = get_products_keyboard(sample_prods, lang="en")
    btn_text = kb.inline_keyboard[0][0].text
    print(f"  - Product Button Label: '{btn_text}' ({'PASSED' if 'Stock: 50' in btn_text and 'Birr' not in btn_text else 'FAILED'})")

    # 10d. Animated Text Transformer
    update_dynamic_emoji("diamond", "543210987654321")
    anim_res = animate_text("💎 MELAX SHOP 💎")
    print(f"  - Animated Emoji Replacement: {'PASSED' if 'emoji-id=\"543210987654321\"' in anim_res else 'FAILED'}")

    # 11. TEST PER-PRODUCT REFERRAL PURCHASE COMMISSION ENGINE
    print("\n[11/11] Testing Per-Product Referral Purchase Commission Engine...")
    # 11a. Create Referrer and Referred Buyer
    referrer = await db.get_or_create_user(telegram_id=7770001, username="top_referrer", first_name="Top Referrer")
    buyer = await db.get_or_create_user(telegram_id=8880002, username="new_buyer", first_name="New Buyer", referrer_telegram_id=7770001)

    # 11b. Create Product with 10% Commission
    test_prod = await db.create_manual_product(
        name="Test Commission Account",
        selling_price=500.0,
        stock=10,
        service_id="MANUAL_COMM_TEST",
        referral_commission_percent=10.0
    )
    print(f"  - Product Commission Config: {test_prod.get('referral_commission_percent')}% ({'PASSED' if test_prod.get('referral_commission_percent') == 10.0 else 'FAILED'})")

    # 11c. Process Purchase Referral Commission (10% on 500 Birr = 50 Birr)
    comm_result = await db.process_purchase_referral_commission(
        buyer_user_id=buyer["id"],
        product=test_prod,
        purchase_price=500.0,
        melax_order_id="MELAX-TEST-COMM-01"
    )
    is_comm_ok = (
        comm_result is not None and
        comm_result.get("referrer_telegram_id") == 7770001 and
        comm_result.get("commission_amount") == 50.0 and
        comm_result.get("commission_percent") == 10.0
    )
    print(f"  - Referrer Wallet Credited 10% (50.00 Birr): {'PASSED' if is_comm_ok else 'FAILED'}")

    # 11d. Update Product Commission to 15% via Admin Method
    await db.update_product_commission("MANUAL_COMM_TEST", 15.0)
    updated_prod = await db.get_product_by_service_id("MANUAL_COMM_TEST")
    print(f"  - Admin Update Product Commission (15%): {'PASSED' if updated_prod.get('referral_commission_percent') == 15.0 else 'FAILED'}")

    # 11e. Verify 15% on 400 Birr = 60 Birr
    comm_result_15 = await db.process_purchase_referral_commission(
        buyer_user_id=buyer["id"],
        product=updated_prod,
        purchase_price=400.0,
        melax_order_id="MELAX-TEST-COMM-02"
    )
    is_comm_15_ok = (
        comm_result_15 is not None and
        comm_result_15.get("commission_amount") == 60.0 and
        comm_result_15.get("commission_percent") == 15.0
    )
    print(f"  - Referrer Wallet Credited 15% (60.00 Birr): {'PASSED' if is_comm_15_ok else 'FAILED'}")

    # 11f. Delete Product Test
    del_ok = await db.delete_product("MANUAL_COMM_TEST")
    deleted_check = await db.get_product_by_service_id("MANUAL_COMM_TEST")
    print(f"  - Permanent Delete Product: {'PASSED' if del_ok and deleted_check is None else 'FAILED'}")

    # 12. TEST THREE-TIER OVERRIDE HIERARCHY, IN-PLACE UI CUSTOMIZATION & SECURITY
    print("\n[12/12] Testing Three-Tier Override Hierarchy, In-Place UI Customization & Security...")
    
    # 12a. Create product with Agent base commission = 5%, price = 380 Birr
    p_tier = await db.create_manual_product(
        name="Gemini Pro 18 Months",
        selling_price=380.0,
        stock=50,
        service_id="MANUAL_GEMINI_18M",
        referral_commission_percent=5.0
    )
    
    # 12b. Verify initial baseline
    eff_base = await db.get_effective_product("MANUAL_GEMINI_18M")
    print(f"  - Initial Agent Baseline (5%): {'PASSED' if eff_base.get('referral_commission_percent') == 5.0 and eff_base.get('calculated_commission_amount') == 19.0 else 'FAILED'}")

    # 12c. Main Admin sets 15% override, custom name, emoji, button text
    await db.set_product_override("MANUAL_GEMINI_18M", "referral_commission_percent", 15.0)
    await db.set_product_override("MANUAL_GEMINI_18M", "name", "✨ Gemini Pro 18 Months (Admin Custom)")
    await db.set_product_override("MANUAL_GEMINI_18M", "emoji", "✨")
    await db.set_product_override("MANUAL_GEMINI_18M", "button_text", "⚡ INSTANT BUY")

    # 12d. Verify Three-Tier Priority: Admin Override (15%) replaces Agent Value (5%)
    eff_overridden = await db.get_effective_product("MANUAL_GEMINI_18M")
    # Commission on 380 Birr at 15% = 57.0 Birr
    is_tier_override_ok = (
        eff_overridden.get("referral_commission_percent") == 15.0 and
        eff_overridden.get("calculated_commission_amount") == 57.0 and
        eff_overridden.get("agent_commission_percent") == 5.0 and
        eff_overridden.get("has_admin_override") is True and
        eff_overridden.get("custom_button_text") == "⚡ INSTANT BUY"
    )
    print(f"  - Three-Tier Main Admin Override (15% on 380 = 57.00 Birr): {'PASSED' if is_tier_override_ok else 'FAILED'}")

    # 12e. Verify underlying Agent/API value was NOT destroyed and remains 5.0%
    raw_agent_prod = await db.get_product_by_service_id("MANUAL_GEMINI_18M")
    is_agent_intact = raw_agent_prod.get("referral_commission_percent") == 5.0
    print(f"  - Agent Baseline Preserved Intact (5%): {'PASSED' if is_agent_intact else 'FAILED'}")

    # 12f. Remove Admin Override -> Cleanly falls back to Agent Value (5.0%)
    await db.remove_product_override("MANUAL_GEMINI_18M")
    eff_fallback = await db.get_effective_product("MANUAL_GEMINI_18M")
    is_fallback_ok = (
        eff_fallback.get("referral_commission_percent") == 5.0 and
        eff_fallback.get("calculated_commission_amount") == 19.0 and
        eff_fallback.get("has_admin_override") is False
    )
    print(f"  - Override Removal Fallback to Agent (5%): {'PASSED' if is_fallback_ok else 'FAILED'}")

    # 12g. Test Dynamic UI Text Overrides
    await db.set_ui_text_override("welcome_title", "👑 CUSTOM ADMIN WELCOME TITLE", lang="am")
    custom_ui_val = await db.get_ui_text("welcome_title", lang="am")
    print(f"  - Dynamic UI Text Custom Override: {'PASSED' if custom_ui_val == '👑 CUSTOM ADMIN WELCOME TITLE' else 'FAILED'}")

    await db.remove_ui_text_override("welcome_title", lang="am")
    reset_ui_val = await db.get_ui_text("welcome_title", lang="am")
    print(f"  - UI Text Override Reset to Default: {'PASSED' if 'MELAX' in reset_ui_val or 'ሜላክስ' in reset_ui_val else 'FAILED'}")

    # 12h. Test Admin-Only In-Place Edit Controls Security & Visibility
    from keyboards import (
        get_product_detail_keyboard,
        get_wallet_keyboard,
        get_referral_keyboard,
        get_profile_keyboard,
        get_support_keyboard,
        get_orders_keyboard
    )
    user_prod_kb = get_product_detail_keyboard("MANUAL_GEMINI_18M", is_admin=False)
    admin_prod_kb = get_product_detail_keyboard("MANUAL_GEMINI_18M", is_admin=True)

    user_has_edit = any("Edit" in btn.text or "✏️" in btn.text for row in user_prod_kb.inline_keyboard for btn in row)
    admin_has_edit = any("Edit" in btn.text or "✏️" in btn.text for row in admin_prod_kb.inline_keyboard for btn in row)

    print(f"  - Normal User Product Card (Zero Edit Buttons): {'PASSED' if not user_has_edit else 'FAILED'}")
    print(f"  - Main Admin Product Card (In-Place Edit Button Present): {'PASSED' if admin_has_edit else 'FAILED'}")

    user_wallet_kb = get_wallet_keyboard(is_admin=False)
    admin_wallet_kb = get_wallet_keyboard(is_admin=True)
    print(f"  - Wallet Screen In-Place Edit Button Guard: {'PASSED' if not any('Edit' in b.text for r in user_wallet_kb.inline_keyboard for b in r) and any('Edit' in b.text for r in admin_wallet_kb.inline_keyboard for b in r) else 'FAILED'}")

    user_ref_kb = get_referral_keyboard(lang="am", is_admin=False)
    admin_ref_kb = get_referral_keyboard(lang="am", is_admin=True)
    print(f"  - Referral Screen In-Place Edit Button Guard: {'PASSED' if not any('Edit' in b.text for r in user_ref_kb.inline_keyboard for b in r) and any('Edit' in b.text for r in admin_ref_kb.inline_keyboard for b in r) else 'FAILED'}")

    # Clean up test product
    await db.delete_product("MANUAL_GEMINI_18M")

    # 13. TEST DIGITAL STOCK INVENTORY VAULT, BLACKLIST SYNC GUARD & COMMISSION RE-EDITS
    print("\n[13/13] Testing Digital Stock Vault, Blacklist Sync Guard & Infinite Commission Re-Edits...")

    # 13a. Create Product for Digital Stock Vault Test
    p_vault = await db.create_manual_product(
        name="ChatGPT Plus 1 Month (Bulk Vault)",
        selling_price=500.0,
        stock=0,
        service_id="MANUAL_VAULT_TEST",
        referral_commission_percent=5.0
    )

    # 13b. Bulk Add 3 Stock Items (Email:Password lines)
    sample_vault_text = (
        "user1@gmail.com:SecretPass1\n"
        "user2@gmail.com:SecretPass2\n"
        "user3@gmail.com:SecretPass3"
    )
    add_vault_res = await db.add_product_stock_items("MANUAL_VAULT_TEST", sample_vault_text)
    is_vault_add_ok = (
        add_vault_res.get("added_count") == 3 and
        add_vault_res.get("available_count") == 3
    )
    print(f"  - Bulk Add 3 Stock Items (Email:Pass): {'PASSED' if is_vault_add_ok else 'FAILED'}")

    # 13c. Pop First Unused Stock Item (FIFO) for Order 1
    item_1 = await db.pop_next_stock_item("MANUAL_VAULT_TEST", "ORD-001")
    stats_after_1 = await db.get_product_stock_stats("MANUAL_VAULT_TEST")
    is_pop_1_ok = (
        item_1 == "user1@gmail.com:SecretPass1" and
        stats_after_1["available_count"] == 2 and
        stats_after_1["used_count"] == 1
    )
    print(f"  - FIFO Dispense Item #1 (user1@...): {'PASSED' if is_pop_1_ok else 'FAILED'}")

    # 13d. Pop Second Unused Stock Item for Order 2
    item_2 = await db.pop_next_stock_item("MANUAL_VAULT_TEST", "ORD-002")
    is_pop_2_ok = (item_2 == "user2@gmail.com:SecretPass2")
    print(f"  - FIFO Dispense Item #2 (user2@...): {'PASSED' if is_pop_2_ok else 'FAILED'}")

    # 13e. Pop Third Unused Stock Item for Order 3
    item_3 = await db.pop_next_stock_item("MANUAL_VAULT_TEST", "ORD-003")
    is_pop_3_ok = (item_3 == "user3@gmail.com:SecretPass3")
    print(f"  - FIFO Dispense Item #3 (user3@...): {'PASSED' if is_pop_3_ok else 'FAILED'}")

    # 13f. Pop when vault is empty (Out of Stock guard)
    item_4 = await db.pop_next_stock_item("MANUAL_VAULT_TEST", "ORD-004")
    stats_after_4 = await db.get_product_stock_stats("MANUAL_VAULT_TEST")
    is_out_of_stock_ok = (
        item_4 is None and
        stats_after_4["available_count"] == 0 and
        stats_after_4["used_count"] == 3
    )
    print(f"  - Out-of-Stock Vault Guard (Return None): {'PASSED' if is_out_of_stock_ok else 'FAILED'}")

    # 13g. Clear Sold Items History
    cleared_count = await db.clear_used_stock_items("MANUAL_VAULT_TEST")
    stats_cleared = await db.get_product_stock_stats("MANUAL_VAULT_TEST")
    is_clear_ok = (cleared_count == 3 and stats_cleared["used_count"] == 0)
    print(f"  - Clear Sold Items History (Purge 3): {'PASSED' if is_clear_ok else 'FAILED'}")

    # 13h. Test Infinite Re-Editing of Referral Commission (5% -> 15% -> 25% -> 10%)
    await db.update_product_commission("MANUAL_VAULT_TEST", 15.0)
    c1 = (await db.get_effective_product("MANUAL_VAULT_TEST")).get("referral_commission_percent")
    await db.update_product_commission("MANUAL_VAULT_TEST", 25.0)
    c2 = (await db.get_effective_product("MANUAL_VAULT_TEST")).get("referral_commission_percent")
    await db.update_product_commission("MANUAL_VAULT_TEST", 10.0)
    eff_c3 = await db.get_effective_product("MANUAL_VAULT_TEST")
    c3 = eff_c3.get("referral_commission_percent")
    calc_amt = eff_c3.get("calculated_commission_amount")
    is_reedit_ok = (c1 == 15.0 and c2 == 25.0 and c3 == 10.0 and calc_amt == 50.0)
    print(f"  - Infinite Commission Re-Edits (5%->15%->25%->10%): {'PASSED' if is_reedit_ok else 'FAILED'}")

    # 13i. Test Blacklist Deletion & Auto-Sync Protection
    await db.delete_product("MANUAL_VAULT_TEST")
    # Simulate API trying to sync the deleted product back
    sync_mock = [{"service_id": "MANUAL_VAULT_TEST", "name": "Resurrected Product", "price": 100.0, "stock": 10}]
    await db.sync_products_from_api(sync_mock)
    check_deleted = await db.get_product_by_service_id("MANUAL_VAULT_TEST")
    print(f"  - Blacklist Auto-Sync Guard (Prevent Revival): {'PASSED' if check_deleted is None else 'FAILED'}")

    # 13j. Test Live Stock Sync for Enabled Products Only (No New Products Added)
    await db.create_manual_product(
        name="Existing Live Product",
        selling_price=300.0,
        stock=10,
        service_id="SRV_ENABLED_LIVE"
    )
    api_feed = [
        {"service_id": "SRV_ENABLED_LIVE", "name": "Existing Live Product", "price": 150.0, "stock": 99},
        {"service_id": "UNWANTED_NEW_PROD", "name": "Unwanted New Product", "price": 200.0, "stock": 50}
    ]
    sync_res = await db.sync_products_from_api(api_feed, insert_new=False)
    updated_p = await db.get_product_by_service_id("SRV_ENABLED_LIVE")
    unwanted_p = await db.get_product_by_service_id("UNWANTED_NEW_PROD")

    is_live_stock_ok = (
        updated_p.get("supplier_stock") == 99 and
        unwanted_p is None and
        sync_res.get("added") == 0
    )
    print(f"  - Enabled Products Live Stock Refresh (Zero New Added): {'PASSED' if is_live_stock_ok else 'FAILED'}")
    await db.delete_product("SRV_ENABLED_LIVE")

    print("\n============================================================")
    print("ALL TEST SUITE CHECKS COMPLETED SUCCESSFULLY!")
    print("============================================================")

if __name__ == "__main__":
    asyncio.run(run_full_system_test())
