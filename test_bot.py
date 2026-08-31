import os
import sys
import sqlite3
import numpy as np
from PIL import Image
from main_bot import (
    init_db,
    get_user_info,
    add_balance,
    deduct_balance,
    receipt_already_used,
    record_receipt,
    approve_receipt,
    reject_receipt,
    get_pdf_price,
    set_setting,
    get_system_stats,
    get_all_user_ids,
    is_user_banned,
    set_user_ban,
    set_user_custom_price,
    get_user_effective_price,
    arrange_cards_on_a4,
    bilateral_alpha_blur,
    generate_fayda_v3,
    main_menu_inline_keyboard,
    admin_dashboard_inline_keyboard,
    settings_keyboard,
    bulk_interactive_keyboard,
    verify_cbe_local,
    check_account_match,
    check_holder_match,
    is_within_24_hours,
    SUPPORT_USERNAME,
    MAX_BATCH_PDFS
)

TEST_DB = "test_users.db"

def run_comprehensive_full_test_suite():
    print("=" * 60)
    print("[TEST] RUNNING COMPREHENSIVE FULL TEST SUITE ON ISOLATED TEST DB...")
    print("=" * 60); sys.stdout.flush()

    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    # 1. Test Support Contact Username
    assert SUPPORT_USERNAME == "@mr_melaku", f"Expected @mr_melaku, got {SUPPORT_USERNAME}"
    print("[PASS] 1. Support Contact Username (@mr_melaku) check passed."); sys.stdout.flush()

    # 2. Test Database Initialization & Migrations on Isolated DB
    init_db(TEST_DB)
    conn = sqlite3.connect(TEST_DB)
    c = conn.cursor()
    c.execute("PRAGMA table_info(users)")
    user_cols = [row[1] for row in c.fetchall()]
    assert 'balance' in user_cols, "Database schema missing 'balance' column"
    assert 'total_converted' in user_cols, "Database schema missing 'total_converted' column"
    assert 'is_banned' in user_cols, "Database schema missing 'is_banned' column"
    assert 'custom_price' in user_cols, "Database schema missing 'custom_price' column"
    conn.close()
    print("[PASS] 2. Isolated DB Schema & Ban/CustomPrice Columns check passed."); sys.stdout.flush()

    # 3. Test User Ban & Custom Pricing Controls
    test_user_id = 999888777
    assert is_user_banned(test_user_id, TEST_DB) is False, "Default user ban check failed"
    set_user_ban(test_user_id, banned=True, db_file=TEST_DB)
    assert is_user_banned(test_user_id, TEST_DB) is True, "User ban failed"
    set_user_ban(test_user_id, banned=False, db_file=TEST_DB)
    assert is_user_banned(test_user_id, TEST_DB) is False, "User unban failed"

    # Test Custom Per-User Pricing
    global_p = get_pdf_price(TEST_DB)
    assert get_user_effective_price(test_user_id, TEST_DB) == global_p, "Default price lookup failed"
    set_user_custom_price(test_user_id, 30.0, db_file=TEST_DB)
    assert get_user_effective_price(test_user_id, TEST_DB) == 30.0, "Custom price lookup failed"
    set_user_custom_price(test_user_id, None, db_file=TEST_DB)
    assert get_user_effective_price(test_user_id, TEST_DB) == global_p, "Custom price reset failed"
    print("[PASS] 3. User Ban / Restrict & Custom Per-User Pricing passed."); sys.stdout.flush()

    # 4. Test Admin Analytics & User List
    stats = get_system_stats(TEST_DB)
    assert 'users' in stats and 'total_balance' in stats, "System stats failed"
    all_users = get_all_user_ids(TEST_DB)
    assert isinstance(all_users, list), "User ID retrieval failed"
    print("[PASS] 4. Admin System Analytics & User List check passed."); sys.stdout.flush()

    # 5. Test Wallet Balance & Deductions
    add_balance(test_user_id, 100.0, db_file=TEST_DB)
    bal, total_conv = get_user_info(test_user_id, TEST_DB)
    assert bal >= 100.0, f"Expected balance >= 100.0, got {bal}"
    
    deducted = deduct_balance(test_user_id, 40.0, converted_count=1, db_file=TEST_DB)
    assert deducted is True, "Balance deduction failed"
    new_bal, new_total = get_user_info(test_user_id, TEST_DB)
    assert new_bal == bal - 40.0, f"Expected {bal - 40.0}, got {new_bal}"
    assert new_total == total_conv + 1, f"Expected total converted increment, got {new_total}"
    print("[PASS] 5. Wallet Balance & Transaction engine passed."); sys.stdout.flush()

    # 6. Test Local CBE Match Helpers & Account Validation
    assert check_account_match("1000320563279", "1000320563279") is True
    assert check_account_match("1000320563279", "1****3279") is True
    assert check_holder_match("MELAX DIGITAL SHOP", "MELAX") is True
    assert is_within_24_hours("2026-08-31 10:00:00") is True
    print("[PASS] 6. Local CBE Direct Verifier helpers & 24h checks passed."); sys.stdout.flush()

    # 7. Test Bilateral Alpha Blur (Photo Edge Smoothing)
    dummy_alpha = Image.new("L", (120, 120), color=150)
    blurred = bilateral_alpha_blur(dummy_alpha, diameter=15, sigma_color=50, sigma_space=50)
    assert blurred is not None, "Bilateral alpha blur returned None"
    assert blurred.size == (120, 120), f"Expected (120, 120), got {blurred.size}"
    print("[PASS] 7. Bilateral Alpha Blur (Photo Edge Filter) passed."); sys.stdout.flush()

    # 8. Test Card Generation (Flipped, Normal, Color, B/W)
    mock_data = {
        'name_amh': "አበበ በቀለ ደስታ",
        'name_eng': "Abebe Bekele Desta",
        'dob': "12/05/1990 | 04/09/1982",
        'sex': "ወንድ | Male",
        'fan': "1234567890123456",
        'sn': "6000001",
        'phone': "0911223344",
        'address': ["አዲስ አበባ", "ልደታ", "ወረዳ 01", "ቤት ቁጥር 123"],
        'expiry': "12/05/2034 | 04/09/2026"
    }

    # Dummy photo files
    p_path = "photo_test_gen.png"
    q_path = "qr_test_gen.png"
    f_path = "fin_test_gen.png"

    Image.new("RGBA", (330, 370), color=(100, 150, 200, 255)).save(p_path)
    Image.new("RGBA", (260, 260), color=(0, 0, 0, 255)).save(q_path)
    Image.new("RGBA", (240, 50), color=(50, 50, 50, 255)).save(f_path)

    out_normal = "test_card_normal.png"
    out_flipped = "test_card_flipped.png"

    res1 = generate_fayda_v3(mock_data, out_normal, "test_gen", mode="color", flipped=False)
    res2 = generate_fayda_v3(mock_data, out_flipped, "test_gen", mode="bw", flipped=True)

    assert res1 is True, "Normal color card rendering failed"
    assert res2 is True, "Flipped B/W card rendering failed"
    assert os.path.exists(out_normal), "Normal card output file missing"
    assert os.path.exists(out_flipped), "Flipped card output file missing"
    print("[PASS] 8. 10x Fast Card Rendering Engine (Normal, Flipped, Color, B/W) passed."); sys.stdout.flush()

    # 9. Test A4 Grid Printable Engine (Tiling 5 cards)
    dummy_cards = [out_normal, out_flipped, out_normal, out_flipped, out_normal]
    a4_output = "test_full_a4_output.png"
    a4_success = arrange_cards_on_a4(dummy_cards, a4_output, num_cards=5)
    assert a4_success is True, "A4 grid layout creation failed"
    assert os.path.exists(a4_output), "A4 sheet file missing"

    with Image.open(a4_output) as a4_img:
        assert a4_img.size == (2480, 3508), f"Expected A4 size (2480, 3508), got {a4_img.size}"
    print("[PASS] 9. A4 Printable Sheet Engine (2480x3508 @ 300DPI) passed."); sys.stdout.flush()

    # Cleanup card artifacts
    for f in [p_path, q_path, f_path, out_normal, out_flipped, a4_output]:
        if os.path.exists(f): os.remove(f)

    # 10. Test 100% Inline UI Keyboards & Admin User Control Layouts
    inline_kb = main_menu_inline_keyboard(is_admin=True)
    admin_kb = admin_dashboard_inline_keyboard()
    bulk_kb = bulk_interactive_keyboard(count=3)
    
    assert inline_kb is not None, "Inline keyboard failed"
    assert admin_kb is not None, "Admin dashboard keyboard failed"
    assert bulk_kb is not None, "Bulk keyboard failed"
    print("[PASS] 10. 100% Inline UI Keyboards & Admin Control Layouts passed."); sys.stdout.flush()

    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    print("=" * 60)
    print("[OK] ALL COMPREHENSIVE FULL TEST SUITE TESTS PASSED 100% SUCCESSFULLY!")
    print("=" * 60); sys.stdout.flush()

if __name__ == "__main__":
    run_comprehensive_full_test_suite()
