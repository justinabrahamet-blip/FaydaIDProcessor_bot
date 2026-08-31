import sqlite3
import pymupdf
import os
import re
import io
import shutil
import asyncio
import threading
import requests
import random
import string
import numpy as np
from datetime import datetime, timedelta
from rembg import remove, new_session
from PIL import Image, ImageDraw, ImageFont
from ethiopian_date import EthiopianDateConverter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# ==========================================
# ⚡ INSTANT RENDER PORT BINDER (RUNS AT STARTUP IN 0.01s)
# ==========================================
def _launch_instant_render_port_listener():
    def _run_http():
        from http.server import HTTPServer, BaseHTTPRequestHandler
        class HealthCheckHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK - Fayda ID Bot Live!")
            def log_message(self, format, *args): pass
        
        port_num = int(os.environ.get("PORT", 8080))
        try:
            server = HTTPServer(("0.0.0.0", port_num), HealthCheckHandler)
            print(f"🌐 Instant Render Port Listener bound to port {port_num}!")
            server.serve_forever()
        except Exception as e:
            print(f"ℹ️ Port listener info: {e}")

    t = threading.Thread(target=_run_http, daemon=True)
    t.start()

# Fire port listener instantly at module load so Render detects port in 0.01 seconds!
_launch_instant_render_port_listener()


# Python 3.14 compatibility patch for python-telegram-bot Application slots
_APP_MARKERS = {}
Application._Application__stop_running_marker = property(
    lambda self: _APP_MARKERS.get((id(self), 'stop')),
    lambda self, v: _APP_MARKERS.__setitem__((id(self), 'stop'), v)
)

# Automatically load .env file if present
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

# ==========================================
# SECURE CONFIGURATION FROM ENVIRONMENT
# ==========================================
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CBE_EXPECTED_ACCOUNT = os.environ.get("CBE_EXPECTED_ACCOUNT", "").strip()
CBE_EXPECTED_HOLDER = os.environ.get("CBE_EXPECTED_HOLDER", "").strip()
TELEBIRR_NUMBER = os.environ.get("TELEBIRR_NUMBER", "").strip()
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "@mr_melaku").strip()
DEFAULT_PDF_PRICE_VAL = os.environ.get("DEFAULT_PDF_PRICE", "40").strip()

# SUPABASE INTEGRATION FOR CROSS-PROJECT RECEIPT DE-DUPLICATION
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "cbe_receipts").strip()

OFFICIAL_CBE_DOMAIN = "mb.cbe.com.et"
OFFICIAL_CBE_RECEIPT_HOST = "mbreciept.cbe.com.et"

MAX_BATCH_PDFS = 5

# Cache for verified receipts
VERIFICATION_CACHE = {}
CACHE_TTL_SECONDS = 600

# Concurrency Locks to prevent double PDF processing lag
ACTIVE_USER_LOCKS = set()
LOCK_SET_GUARD = threading.Lock()

# Global Rembg Session (pre-loaded for zero cold-start delay)
REMBG_SESSION = None

def warm_up_rembg_session():
    global REMBG_SESSION
    if REMBG_SESSION is None:
        print("⚡ Pre-warming lightweight u2netp Rembg model session...")
        REMBG_SESSION = new_session("u2netp")
        # Run dummy inference to warm up PyTorch/ONNX runtime
        dummy_img = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
        remove(dummy_img, session=REMBG_SESSION)
        print("✅ Rembg session pre-warmed and ready for 10x fast processing!")

def get_rembg_session():
    global REMBG_SESSION
    if REMBG_SESSION is None:
        warm_up_rembg_session()
    return REMBG_SESSION

# Thread lock for serial generator
SERIAL_LOCK = threading.Lock()

# Conversation States for 100% Inline Driven Flow
(
    MENU,
    WAIT_RECEIPT,
    SETTINGS,
    BATCH_MODE,
    WAIT_BROADCAST,
    WAIT_USER_BALANCE,
    WAIT_PRICE_SETTING,
    WAIT_DIRECT_MSG,
    WAIT_CUSTOM_PRICE,
    WAIT_BAN_UNBAN
) = range(10)


# ==========================================
# 1. DATABASE & ENHANCED USER MANAGEMENT
# ==========================================

def get_db_connection(db_file='users.db'):
    conn = sqlite3.connect(db_file, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    
    c.execute("PRAGMA table_info(users)")
    user_cols = [row['name'] for row in c.fetchall()]
    if not user_cols:
        c.execute('''CREATE TABLE users 
                     (user_id INTEGER PRIMARY KEY, 
                      balance REAL DEFAULT 0.0, 
                      total_converted INTEGER DEFAULT 0,
                      is_banned INTEGER DEFAULT 0,
                      custom_price REAL DEFAULT NULL)''')
    else:
        if 'balance' not in user_cols:
            try:
                if 'credits' in user_cols:
                    c.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0.0")
                    c.execute("UPDATE users SET balance = credits * 40.0")
                else:
                    c.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0.0")
            except sqlite3.OperationalError:
                pass
        if 'total_converted' not in user_cols:
            try:
                c.execute("ALTER TABLE users ADD COLUMN total_converted INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
        if 'is_banned' not in user_cols:
            try:
                c.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
        if 'custom_price' not in user_cols:
            try:
                c.execute("ALTER TABLE users ADD COLUMN custom_price REAL DEFAULT NULL")
            except sqlite3.OperationalError:
                pass

    c.execute('''CREATE TABLE IF NOT EXISTS receipts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  raw_text TEXT UNIQUE,
                  cbe_link TEXT UNIQUE,
                  reference TEXT UNIQUE,
                  amount REAL NOT NULL DEFAULT 0.0,
                  status TEXT NOT NULL DEFAULT 'PENDING',
                  manual_note TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY,
                  value TEXT NOT NULL)''')

    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("pdf_to_id_price", DEFAULT_PDF_PRICE_VAL))
    
    conn.commit()
    conn.close()

def get_all_user_ids(db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [r['user_id'] for r in rows]

def get_system_stats(db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as user_count, SUM(balance) as total_bal, SUM(total_converted) as total_ids FROM users")
    u_row = c.fetchone()
    c.execute("SELECT COUNT(*) as pending_cnt FROM receipts WHERE status='PENDING'")
    r_row = c.fetchone()
    c.execute("SELECT COUNT(*) as banned_cnt FROM users WHERE is_banned=1")
    b_row = c.fetchone()
    conn.close()
    return {
        "users": u_row['user_count'] or 0,
        "total_balance": u_row['total_bal'] or 0.0,
        "total_converted": u_row['total_ids'] or 0,
        "pending_receipts": r_row['pending_cnt'] or 0,
        "banned_users": b_row['banned_cnt'] or 0
    }

def get_setting(key, default=DEFAULT_PDF_PRICE_VAL, db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value, db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    c.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
              (key, str(value)))
    conn.commit()
    conn.close()

def get_pdf_price(db_file='users.db'):
    try:
        return float(get_setting("pdf_to_id_price", DEFAULT_PDF_PRICE_VAL, db_file))
    except ValueError:
        return 40.0

def get_user_effective_price(user_id, db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    c.execute("SELECT custom_price FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row and row['custom_price'] is not None:
        return float(row['custom_price'])
    return get_pdf_price(db_file)

def is_user_banned(user_id, db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    c.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row['is_banned'] == 1)

def set_user_ban(user_id, banned=True, db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, balance, total_converted) VALUES (?, 0.0, 0)", (user_id,))
    c.execute("UPDATE users SET is_banned=? WHERE user_id=?", (1 if banned else 0, user_id))
    conn.commit()
    conn.close()

def set_user_custom_price(user_id, price, db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, balance, total_converted) VALUES (?, 0.0, 0)", (user_id,))
    val = float(price) if price is not None else None
    c.execute("UPDATE users SET custom_price=? WHERE user_id=?", (val, user_id))
    conn.commit()
    conn.close()

def get_user_info(user_id, db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    c.execute("SELECT balance, total_converted, is_banned, custom_price FROM users WHERE user_id=?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id, balance, total_converted) VALUES (?, 0.0, 0)", (user_id,))
        conn.commit()
        conn.close()
        return 0.0, 0
    conn.close()
    return float(res['balance']), int(res['total_converted'])

def add_balance(user_id, amount, db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, balance, total_converted) VALUES (?, 0.0, 0)", (user_id,))
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def deduct_balance(user_id, amount, converted_count=1, db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    res = c.fetchone()
    if not res or float(res['balance']) < amount:
        conn.close()
        return False
    c.execute("UPDATE users SET balance = balance - ?, total_converted = total_converted + ? WHERE user_id = ?",
              (amount, converted_count, user_id))
    conn.commit()
    conn.close()
    return True


# ==========================================
# 1.1 SUPABASE RECEIPT DE-DUPLICATION ENGINE
# ==========================================

def is_receipt_used_supabase(raw_text, cbe_link=None, reference=None):
    """Query shared Supabase database across multiple bots to prevent receipt re-use."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        base_url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_TABLE}"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        conds = []
        if raw_text: conds.append(f"raw_text.eq.{raw_text}")
        if cbe_link: conds.append(f"cbe_link.eq.{cbe_link}")
        if reference: conds.append(f"reference.eq.{reference}")
        if not conds: return False

        or_query = ",".join(conds)
        resp = requests.get(f"{base_url}?or=({or_query})&select=id", headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return len(data) > 0
    except Exception as e:
        print(f"⚠️ Supabase query error: {e}")
    return False

def record_receipt_supabase(user_id, raw_text, cbe_link, reference, amount, status, manual_note=None):
    """Record receipt entry to shared Supabase cloud database."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        base_url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_TABLE}"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        payload = {
            "user_id": str(user_id),
            "raw_text": raw_text,
            "cbe_link": cbe_link,
            "reference": reference,
            "amount": float(amount),
            "status": status,
            "manual_note": manual_note
        }
        requests.post(base_url, json=payload, headers=headers, timeout=5)
    except Exception as e:
        print(f"⚠️ Supabase record error: {e}")

def receipt_already_used(raw_text, cbe_link=None, reference=None, db_file='users.db'):
    # 1. Check Local SQLite Database
    conn = get_db_connection(db_file)
    c = conn.cursor()
    query = """
        SELECT 1 FROM receipts
        WHERE raw_text = ?
           OR (? IS NOT NULL AND cbe_link = ?)
           OR (? IS NOT NULL AND reference = ?)
        LIMIT 1
    """
    c.execute(query, (raw_text, cbe_link, cbe_link, reference, reference))
    res = c.fetchone()
    conn.close()
    if res is not None:
        return True

    # 2. Check Shared Supabase Database across all bots/projects
    if is_receipt_used_supabase(raw_text, cbe_link, reference):
        return True

    return False

def record_receipt(user_id, raw_text, cbe_link, reference, amount, status, manual_note=None, db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO receipts (user_id, raw_text, cbe_link, reference, amount, status, manual_note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, raw_text, cbe_link, reference, amount, status, manual_note))
        rec_id = c.lastrowid
        conn.commit()
        conn.close()

        # Also sync to shared Supabase DB across projects
        record_receipt_supabase(user_id, raw_text, cbe_link, reference, amount, status, manual_note)

        return rec_id
    except sqlite3.IntegrityError:
        conn.close()
        return None

def approve_receipt(receipt_id, db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    c.execute("SELECT user_id, amount, status, raw_text, cbe_link, reference FROM receipts WHERE id=?", (receipt_id,))
    row = c.fetchone()
    if not row or row['status'] != 'PENDING':
        conn.close()
        return None
    
    user_id = row['user_id']
    amount = float(row['amount'])
    
    c.execute("UPDATE receipts SET status='VERIFIED' WHERE id=?", (receipt_id,))
    c.execute("INSERT OR IGNORE INTO users (user_id, balance, total_converted) VALUES (?, 0.0, 0)", (user_id,))
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

    # Sync approval to Supabase
    record_receipt_supabase(user_id, row['raw_text'], row['cbe_link'], row['reference'], amount, "VERIFIED")

    return user_id, amount

def reject_receipt(receipt_id, db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    c.execute("SELECT user_id, status FROM receipts WHERE id=?", (receipt_id,))
    row = c.fetchone()
    if not row or row['status'] != 'PENDING':
        conn.close()
        return None
    user_id = row['user_id']
    c.execute("UPDATE receipts SET status='REJECTED' WHERE id=?", (receipt_id,))
    conn.commit()
    conn.close()
    return user_id

def fetch_pending_receipts(db_file='users.db'):
    conn = get_db_connection(db_file)
    c = conn.cursor()
    c.execute("SELECT * FROM receipts WHERE status='PENDING' ORDER BY id ASC LIMIT 5")
    rows = c.fetchall()
    conn.close()
    return rows


# ==========================================
# 2. 100% DIRECT LOCAL CBE VERIFICATION
# ==========================================

def check_account_match(got_acc: str, expected_acc: str) -> bool:
    if not got_acc or not expected_acc:
        return True
    got_str = str(got_acc).strip().upper()
    expected_str = str(expected_acc).strip().upper()
    if got_str == expected_str:
        return True
    if "*" in expected_str:
        pattern = "^" + re.escape(expected_str).replace(r"\*", r".*") + "$"
        if re.match(pattern, got_str, re.IGNORECASE):
            return True
    got_digits = re.sub(r'[^0-9]', '', got_str)
    expected_digits = re.sub(r'[^0-9]', '', expected_str)
    if got_digits and expected_digits:
        if got_digits == expected_digits:
            return True
        if len(got_digits) >= 4 and len(expected_digits) >= 4:
            if got_digits.endswith(expected_digits[-4:]) or expected_digits.endswith(got_digits[-4:]):
                return True
    return False

def check_holder_match(got_holder: str, expected_holder: str) -> bool:
    if not got_holder or not expected_holder:
        return True
    got_clean = str(got_holder).strip().upper()
    expected_clean = str(expected_holder).strip().upper()
    return expected_clean in got_clean or got_clean in expected_clean

def is_within_24_hours(tx_date_str: str) -> bool:
    if not tx_date_str:
        return True
    now = datetime.now()
    parsed_date = None
    date_formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S",
        "%d-%b-%Y", "%b %d, %Y", "%d/%m/%y"
    ]
    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(tx_date_str.strip()[:19], fmt)
            break
        except ValueError:
            continue
    if not parsed_date:
        return True
    diff = now - parsed_date
    return diff <= timedelta(hours=24) and diff >= timedelta(days=-1)

def verify_cbe_local(input_text: str, expected_account: str = CBE_EXPECTED_ACCOUNT, expected_holder: str = CBE_EXPECTED_HOLDER) -> dict:
    link_match = re.search(r'mbreciept\.cbe\.com\.et\/([A-Za-z0-9_-]{6,})', input_text, re.IGNORECASE)
    if not link_match:
        return {
            "ok": False,
            "code": "MISSING_LINK",
            "error": "🔗 **የCBE ደረሰኝ ሊንክ አልተገኘም (MISSING LINK)**\n\nለራስ-ሰር ማረጋገጫ የ **mbreciept.cbe.com.et/...** ደረሰኝ ሊንክ የያዘውን ኤስኤምኤስ ብቻ ይላኩ!"
        }

    short_code = link_match.group(1).strip()
    cbe_link = f"https://{OFFICIAL_CBE_RECEIPT_HOST}/{short_code}"

    now_ts = datetime.now().timestamp()
    if short_code in VERIFICATION_CACHE:
        cache_time, cached_res = VERIFICATION_CACHE[short_code]
        if now_ts - cache_time < CACHE_TTL_SECONDS:
            return cached_res

    url = f"https://{OFFICIAL_CBE_DOMAIN}/api/v1/transactions/public/transaction-detail/{short_code}"
    headers = {
        'Host': OFFICIAL_CBE_DOMAIN,
        'Origin': f'https://{OFFICIAL_CBE_RECEIPT_HOST}',
        'Referer': f'https://{OFFICIAL_CBE_RECEIPT_HOST}/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 CBEBIRR/1.0',
        'x-app-id': 'd1292e42-7400-49de-a2d3-9731caa4c819',
        'x-app-version': '0a01980b-9859-1369-8198-59f403820000',
        'Accept': 'application/json, text/plain, */*'
    }

    try:
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            rec_acc = data.get("creditAccountNo", "")
            rec_holder = data.get("creditAccountHolder", "")
            
            if expected_account and not check_account_match(rec_acc, expected_account):
                return {
                    "ok": False,
                    "code": "ACCOUNT_MISMATCH",
                    "error": f"❌ **የተቀባይ አካውንት ቁጥር አይዛመድም (ACCOUNT MISMATCH)**\n\nይህ ክፍያ የተፈጸመው ወደ አካውንት `({rec_acc})` ነው። እባክዎን ክፍያዎን ወደ አካውንት **{expected_account}** ይክፈሉ።"
                }

            if expected_holder and not check_holder_match(rec_holder, expected_holder):
                return {
                    "ok": False,
                    "code": "HOLDER_MISMATCH",
                    "error": f"❌ **የተቀባይ ስም አይዛመድም (NAME MISMATCH)**\n\nይህ ክፍያ የተፈጸመው ወደ **{rec_holder}** ነው። እባክዎን ወደ **{expected_holder}** አካውንት ይክፈሉ።"
                }

            tx_date = str(data.get("processingDate") or data.get("authDate") or datetime.now().strftime("%Y-%m-%d"))
            if not is_within_24_hours(tx_date):
                return {
                    "ok": False,
                    "code": "EXPIRED_RECEIPT",
                    "error": f"🕒 **የቆየ የክፍያ ደረሰኝ (EXPIRED RECEIPT)**\n\nይህ የክፍያ ደረሰኝ የተፈጸመበት ቀን (`{tx_date[:10]}`) ከ 24 ሰዓት በፊት ስለሆነ አይቀበልም። የዛሬ ክፍያ ብቻ ያስገቡ!"
                }

            amt = float(data.get("amountCredited") or data.get("creditAmount") or 0.0)
            txn_id = str(data.get("id") or data.get("transactionId") or short_code)

            result = {
                "ok": True,
                "provider": "CBE",
                "short_code": short_code,
                "cbe_link": cbe_link,
                "transaction_id": txn_id,
                "amount": amt,
                "payer_name": data.get("debitAccountHolder", "Unknown"),
                "receiver_name": rec_holder,
                "receiver_account": rec_acc,
                "date": tx_date
            }
            VERIFICATION_CACHE[short_code] = (now_ts, result)
            return result
        else:
            return {
                "ok": False,
                "code": "NOT_FOUND",
                "error": f"⚠️ **ደረሰኙ በንግድ ባንክ ሰርቨር አልተገኘም (NOT FOUND)**\n\nየላኩት የCBE ደረሰኝ ሊንክ በንግድ ባንክ ሰርቨር ላይ አልተገኘም።"
            }
    except Exception as e:
        return {
            "ok": False,
            "code": "NETWORK_ERROR",
            "error": "⚠️ ከንግድ ባንክ ሰርቨር ጋር ማገናኘት አልተቻለም። እባክዎን ትንሽ ቆይተው እንደገና ይሞክሩ።"
        }


# ==========================================
# 3. ULTRA-FAST HIGH-PRECISION PDF & IMAGE ENGINE (NON-SEQUENTIAL NUMERIC SERIAL NUMBER)
# ==========================================

def get_next_serial_number():
    """Generates a randomized non-sequential 7-digit numeric Serial Number (SN) (e.g., 6849201, 7102948)."""
    with SERIAL_LOCK:
        first_digit = random.choice(["6", "7", "8"])
        remaining_digits = "".join(random.choices("0123456789", k=6))
        return f"{first_digit}{remaining_digits}"

def extract_data_from_pdf(pdf_path, temp_prefix):
    if not os.path.exists(pdf_path): return None
    try:
        doc = pymupdf.open(pdf_path)
        page = doc[0]

        paths = {
            'photo': f"photo_{temp_prefix}.png", 
            'qr': f"qr_{temp_prefix}.png", 
            'fin': f"fin_{temp_prefix}.png"
        }

        image_list = page.get_images(full=True)
        for i, img in enumerate(image_list):
            xref = img[0]
            pix = pymupdf.Pixmap(doc, xref)
            if pix.n - pix.alpha > 3: pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            
            if i == 0:
                img_bytes = pix.tobytes("png")
                raw_photo = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
                # Pre-downscale to target resolution (330, 370) BEFORE background removal for 10x SPEEDUP!
                raw_photo_resized = raw_photo.resize((330, 370), Image.Resampling.LANCZOS)
                output_image = remove(raw_photo_resized, session=get_rembg_session())
                output_image.save(paths['photo'])
            elif i == 1: 
                pix.save(paths['qr'])

        page.get_pixmap(clip=pymupdf.Rect(496.5, 493, 540, 501), matrix=pymupdf.Matrix(4, 4)).save(paths['fin'])
        
        text = page.get_text("text")
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        now = datetime.now()
        eth_now = EthiopianDateConverter.to_ethiopian(now.year, now.month, now.day)
        
        data = {
            'name_amh': lines[57] if len(lines) > 57 else "Unknown",
            'name_eng': lines[58] if len(lines) > 58 else "Unknown",
            'dob': f"{lines[43]} | {lines[44]}" if len(lines) > 44 else "Unknown",
            'sex': f"{lines[45]} | {lines[46]}" if len(lines) > 46 else "Unknown",
            'fan': "Unknown", 
            'sn': get_next_serial_number(),
            'phone': lines[49] if len(lines) > 49 else "",
            'address': lines[50:56] if len(lines) >= 56 else lines[40:46],
            'expiry': f"{now.day:02d}/{now.month:02d}/{now.year+10} | {eth_now.day:02d}/{eth_now.month:02d}/{eth_now.year+10}"
        }
        for line in lines:
            clean = line.replace(" ", "")
            fan_match = re.search(r'(\d{16})', clean)
            if fan_match: 
                data['fan'] = fan_match.group(1)
        doc.close()
        return data
    except Exception as e:
        print(f"Error extracting PDF {pdf_path}: {e}")
        return None

def load_bold_font(size):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    font_candidates = [
        os.path.join(base_dir, "ebrima-bold.ttf"),
        os.path.join(base_dir, "ebrima.ttf"),
        os.path.join(base_dir, "washrab.ttf"),
        os.path.join(base_dir, "arial.ttf"),
        os.path.join(base_dir, "DejaVuSans.ttf"),
    ]
    for font_path in font_candidates:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def bilateral_alpha_blur(alpha, diameter=15, sigma_color=75, sigma_space=75):
    alpha_arr = np.array(alpha, dtype=np.uint8)
    if alpha_arr.ndim != 2:
        raise ValueError("Alpha layer must be a single channel image")

    radius = diameter // 2
    padded = np.pad(alpha_arr, radius, mode='reflect')
    filtered = np.zeros_like(alpha_arr, dtype=np.float32)

    coords = np.arange(-radius, radius + 1)
    xx, yy = np.meshgrid(coords, coords)
    spatial = np.exp(-(xx**2 + yy**2) / (2.0 * (sigma_space**2)))

    for y in range(alpha_arr.shape[0]):
        for x in range(alpha_arr.shape[1]):
            region = padded[y:y + diameter, x:x + diameter]
            intensity_diff = region.astype(np.int32) - int(alpha_arr[y, x])
            range_weight = np.exp(-(intensity_diff**2) / (2.0 * (sigma_color**2)))
            weights = spatial * range_weight
            filtered[y, x] = np.sum(weights * region) / np.sum(weights)

    filtered = np.clip(filtered, 0, 255).astype(np.uint8)
    return Image.fromarray(filtered, mode='L')

def generate_fayda_v3(data, output_path, temp_prefix, mode="color", template_path=None, flipped=False):
    template_candidates = ["fayda.jpg", "Fayda.jpg", "faydatemplate1.jpg", "faydatemplate1.png", "Templet2.png", "Templet2.jpg"]
    if template_path and os.path.exists(template_path):
        chosen_template = template_path
    else:
        chosen_template = next((name for name in template_candidates if os.path.exists(name)), None)
    if not chosen_template:
        return False

    canvas = Image.open(chosen_template).convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    f_amh = load_bold_font(26)
    f_bold = load_bold_font(26)
    f_small = load_bold_font(16)

    # Dynamic Rotated Dates
    now = datetime.now()
    eth_conv = EthiopianDateConverter.to_ethiopian(now.year, now.month, now.day)
    g_date = now.strftime("%d/%m/%Y")
    e_date = f"{eth_conv.day:02d}/{eth_conv.month:02d}/{eth_conv.year}"

    def draw_rotated_text(text, position, font):
        text_img = Image.new("RGBA", (250, 60), (255, 255, 255, 0))
        d = ImageDraw.Draw(text_img)
        d.text((0, 0), text, font=font, fill="black")
        rotated = text_img.rotate(90, expand=True)
        canvas.paste(rotated, position, rotated)

    draw_rotated_text(g_date, (22, 7), f_small)
    draw_rotated_text(e_date, (22, 260), f_small)

    # Photo Logic (Pre-downscaled for fast performance)
    photo_path = f"photo_{temp_prefix}.png"
    if os.path.exists(photo_path):
        raw_photo = Image.open(photo_path).convert("RGBA")
        if mode == "bw":
            r, g, b, alpha = raw_photo.split()
            gray = raw_photo.convert("L")
            raw_photo = Image.merge("RGBA", (gray, gray, gray, alpha))

        photo_resized = raw_photo.resize((330, 370), Image.Resampling.LANCZOS)
        r, g, b, alpha = photo_resized.split()
        alpha = bilateral_alpha_blur(alpha, diameter=15, sigma_color=50, sigma_space=50)
        photo_resized = Image.merge("RGBA", (r, g, b, alpha))
        canvas.paste(photo_resized, (62, 180), photo_resized)

        ghost = raw_photo.resize((110, 130), Image.Resampling.LANCZOS)
        r_g, g_g, b_g, alpha_g = ghost.split()
        alpha_g = bilateral_alpha_blur(alpha_g, diameter=11, sigma_color=40, sigma_space=40)
        ghost = Image.merge("RGBA", (r_g, g_g, b_g, alpha_g))
        canvas.paste(ghost, (850, 480), ghost)

    # Assets (QR 4.15cm @ 1520,60 | Fingerprint @ 1170,508)
    qr_cm = 4.15
    dpi = 300
    qr_size_var = int(round((qr_cm / 2.54) * dpi))  # 490x490
    assets = [(f"qr_{temp_prefix}.png", (qr_size_var, qr_size_var), (1520, 60)), (f"fin_{temp_prefix}.png", (240, 50), (1170, 508))]
    for asset, size, pos in assets:
        if os.path.exists(asset):
            img = Image.open(asset).resize(size, Image.Resampling.LANCZOS).convert("RGBA")
            canvas.paste(img, pos, img)

    # Main Text Overlay (text_x = 402)
    text_x = 402
    draw.text((text_x, 177), data['name_amh'], font=f_amh, fill="black")
    draw.text((text_x, 219), data['name_eng'], font=f_bold, fill="black")
    draw.text((text_x, 304), data['dob'], font=f_bold, fill="black")
    draw.text((text_x, 370), data['sex'], font=f_amh, fill="black")
    draw.text((text_x, 440), data['expiry'], font=f_bold, fill="black")
    draw.text((470, 490), data['fan'], font=f_bold, fill="black")
    draw.text((canvas.width - 180, canvas.height - 56), data['sn'], font=f_bold, fill="black")

    # Back Side Text Overlay
    back_x, y_addr = (canvas.width // 2) + 26, 234
    draw.text((back_x, 71), data['phone'], font=f_bold, fill="black")
    for line in data['address']:
        draw.text((back_x, y_addr), line, font=f_amh, fill="black")
        y_addr += 40

    if flipped:
        canvas = canvas.transpose(Image.FLIP_LEFT_RIGHT)

    rgb = canvas.convert("RGB")
    rgb.save(output_path, "PNG")
    return True


# ==========================================
# 4. A4 SHEET PRINTABLE ENGINE
# ==========================================

def arrange_cards_on_a4(card_paths, output_path, num_cards=5):
    a4_width, a4_height = 2480, 3508
    a4_canvas = Image.new("RGB", (a4_width, a4_height), color="white")
    
    num_cards = max(1, min(5, num_cards))
    card_width, card_height = 1000, 640
    cutting_gap = 40
    
    total_card_height = (num_cards * card_height) + ((num_cards - 1) * cutting_gap)
    total_margin = a4_height - total_card_height
    margin_top = max(50, total_margin // 3)
    
    center_x = (a4_width - card_width) // 2
    
    current_y = margin_top
    positions = []
    for i in range(num_cards):
        positions.append((center_x, current_y))
        current_y += card_height + cutting_gap
    
    for i, card_path in enumerate(card_paths[:num_cards]):
        if i < len(positions) and os.path.exists(card_path):
            try:
                card_img = Image.open(card_path).convert("RGB")
                original_aspect = card_img.width / card_img.height
                target_aspect = card_width / card_height
                
                if original_aspect > target_aspect:
                    scale = card_height / card_img.height
                else:
                    scale = card_width / card_img.width
                
                new_width = int(card_img.width * scale)
                new_height = int(card_img.height * scale)
                card_img_resized = card_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                offset_x = (card_width - new_width) // 2
                offset_y = (card_height - new_height) // 2
                
                x, y = positions[i]
                a4_canvas.paste(card_img_resized, (x + offset_x, y + offset_y))
            except Exception as e:
                print(f"Error pasting card {i}: {e}")
    
    a4_canvas.save(output_path, "PNG", quality=95)
    return True


# ==========================================
# 5. HYBRID KEYBOARDS & LAYOUTS FOR BUTTON PERSISTENCE
# ==========================================

def main_reply_keyboard():
    """Persistent Bottom Reply Keyboard Fallback so buttons NEVER disappear!"""
    return ReplyKeyboardMarkup([
        [KeyboardButton("📋 Control Panel"), KeyboardButton("📄 Direct Print")],
        [KeyboardButton("📦 Bulk Mode"), KeyboardButton("💳 Deposit / Balance")],
        [KeyboardButton("📞 Support & Help")]
    ], resize_keyboard=True)

def main_menu_inline_keyboard(is_admin=False):
    kb = [
        [InlineKeyboardButton("📄 Direct Print (Drop 1 PDF)", callback_data='btn_single_info')],
        [InlineKeyboardButton("📦 Interactive Bulk Mode (1-5 PDFs)", callback_data='btn_start_bulk')],
        [InlineKeyboardButton("💰 My Wallet Balance", callback_data='btn_wallet'), InlineKeyboardButton("⚙️ Settings", callback_data='btn_settings')],
        [InlineKeyboardButton("💳 Deposit Funds (CBE Direct)", callback_data='btn_deposit'), InlineKeyboardButton("📞 Support", callback_data='btn_help')]
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("🛠 ADMIN CONTROL DASHBOARD", callback_data='btn_admin_dashboard')])
    return InlineKeyboardMarkup(kb)

def admin_dashboard_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Analytics", callback_data='admin_stats'), InlineKeyboardButton("🏷 Set Global Price", callback_data='admin_set_price')],
        [InlineKeyboardButton("👥 Adjust User Balance", callback_data='admin_user_adjust'), InlineKeyboardButton("🏷 Set Custom User Price", callback_data='admin_custom_price')],
        [InlineKeyboardButton("🚫 Ban / Unban User", callback_data='admin_ban_unban'), InlineKeyboardButton("💬 Send Direct Msg", callback_data='admin_direct_msg')],
        [InlineKeyboardButton("🧾 Review Receipts", callback_data='admin_review_receipts'), InlineKeyboardButton("📢 Broadcast All", callback_data='admin_broadcast')],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data='btn_main_menu')]
    ])

def bulk_interactive_keyboard(count=0):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🖨️ Convert Now ({count} PDFs Ready)", callback_data='bulk_convert_now')],
        [InlineKeyboardButton("❌ Cancel Batch", callback_data='bulk_cancel')]
    ])

def settings_keyboard(context):
    mode = context.user_data.get('output_mode', 'color')
    flip = context.user_data.get('canvas_flip', 'normal')
    
    mode_btn_text = "🟢 Mode: COLOR (Click for B/W)" if mode == 'color' else "⚪ Mode: B/W (Click for COLOR)"
    flip_btn_text = "🔄 Canvas: NORMAL (Click for FLIPPED)" if flip == 'normal' else "🪞 Canvas: FLIPPED (Click for NORMAL)"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(mode_btn_text, callback_data='toggle_mode')],
        [InlineKeyboardButton(flip_btn_text, callback_data='toggle_flip')],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data='btn_main_menu')]
    ])


# ==========================================
# 6. SMART HANDLERS & INLINE FLOWS
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if is_user_banned(user_id):
        banned_msg = f"🚫 **Your account has been restricted / banned by Admin.**\n\nFor support or unban inquiries, contact: {SUPPORT_USERNAME}"
        if update.callback_query:
            await update.callback_query.answer("🚫 Account Banned", show_alert=True)
            try:
                await update.callback_query.edit_message_text(banned_msg, parse_mode="Markdown")
            except Exception:
                await context.bot.send_message(chat_id=user_id, text=banned_msg, reply_markup=main_reply_keyboard(), parse_mode="Markdown")
        else:
            await update.message.reply_text(banned_msg, reply_markup=main_reply_keyboard(), parse_mode="Markdown")
        return MENU

    balance, total_converted = get_user_info(user_id)
    price = get_user_effective_price(user_id)
    global_price = get_pdf_price()
    is_admin = (ADMIN_ID > 0 and user_id == ADMIN_ID)

    context.user_data.setdefault('output_mode', 'color')
    context.user_data.setdefault('canvas_flip', 'normal')

    mode_str = "🟢 COLOR" if context.user_data['output_mode'] == 'color' else "⚪ B/W"
    flip_str = "🔄 NORMAL" if context.user_data['canvas_flip'] == 'normal' else "🪞 FLIPPED"
    
    price_tag = f"`{price:.2f} ETB`" if price == global_price else f"`{price:.2f} ETB` *(Custom Discount!)*"

    welcome_text = (
        "⚡ **FAYDA ID PRINTABLE CONVERTER BOT** ⚡\n"
        "እንኳን ወደ ብሔራዊ መታወቂያ ፋይዳ ካርድ መቀየሪያ በደህና መጡ!\n\n"
        f"💰 **Wallet Balance:** `{balance:.2f} ETB`\n"
        f"🏷 **Rate per ID:** {price_tag}\n"
        f"⚙️ **Active Preferences:** {mode_str} | {flip_str}\n"
        f"🪪 **Total IDs Processed:** `{total_converted}`\n\n"
        "🚀 **Fast Single PDF:** Drop 1 Fayda PDF directly in chat for instant conversion!\n"
        "📦 **Interactive Bulk Mode:** Upload 1 to 5 PDFs and tap **Convert Now** at any step!\n\n"
        "👇 **Select an option below:**"
    )
    
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(welcome_text, reply_markup=main_menu_inline_keyboard(is_admin), parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(chat_id=user_id, text=welcome_text, reply_markup=main_reply_keyboard(), parse_mode="Markdown")
    else:
        await update.message.reply_text(welcome_text, reply_markup=main_reply_keyboard(), parse_mode="Markdown")
        await update.message.reply_text("📋 **Interactive Control Panel:**", reply_markup=main_menu_inline_keyboard(is_admin), parse_mode="Markdown")
    return MENU

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if is_user_banned(user_id):
        await query.answer("🚫 Account Banned", show_alert=True)
        return MENU

    balance, _ = get_user_info(user_id)
    price = get_user_effective_price(user_id)
    is_admin = (ADMIN_ID > 0 and user_id == ADMIN_ID)

    if data == 'btn_single_info':
        await query.edit_message_text(
            f"📄 **Direct Single PDF Mode**\n\n"
            f"Simply send your **Fayda ID PDF** file directly in chat!\n"
            f"💰 Cost per ID: `{price:.2f} ETB` | Your Balance: `{balance:.2f} ETB`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data='btn_main_menu')]]),
            parse_mode="Markdown"
        )
        return MENU

    elif data == 'btn_start_bulk':
        context.user_data['batch_pdfs'] = []
        await query.edit_message_text(
            "📦 **INTERACTIVE BULK MODE (1 to 5 PDFs)**\n\n"
            "Progress: `[░░░░░] 0/5 PDFs`\n\n"
            "📥 Please send PDF 1/5 now.\n"
            "💡 Tap **🖨️ Convert Now** at any time to print collected PDFs!",
            reply_markup=bulk_interactive_keyboard(0),
            parse_mode="Markdown"
        )
        return BATCH_MODE

    elif data == 'btn_wallet':
        wallet_msg = (
            f"💳 **YOUR WALLET ACCOUNT**\n\n"
            f"👤 **User ID:** `{user_id}`\n"
            f"💰 **Available Balance:** `{balance:.2f} ETB`\n"
            f"🏷 **Your Current Rate:** `{price:.2f} ETB` / ID\n\n"
            f"🏦 Deposit automatically by pasting your CBE SMS receipt link (`mbreciept.cbe.com.et...`)\n"
            f"💳 **CBE Receiver Account:** `{CBE_EXPECTED_ACCOUNT}` ({CBE_EXPECTED_HOLDER})\n"
            f"📱 **Telebirr Transfer:** `{TELEBIRR_NUMBER}`"
        )
        btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Deposit Funds", callback_data='btn_deposit')],
            [InlineKeyboardButton("🔙 Main Menu", callback_data='btn_main_menu')]
        ])
        await query.edit_message_text(wallet_msg, reply_markup=btns, parse_mode="Markdown")
        return MENU

    elif data == 'btn_settings':
        await query.edit_message_text(
            "⚙️ **SETTINGS & PREFERENCES**\n\nConfigure your visual output preferences below:",
            reply_markup=settings_keyboard(context),
            parse_mode="Markdown"
        )
        return SETTINGS

    elif data == 'toggle_mode':
        curr = context.user_data.get('output_mode', 'color')
        context.user_data['output_mode'] = 'bw' if curr == 'color' else 'color'
        await query.edit_message_text(
            "⚙️ **SETTINGS & PREFERENCES**\n\nUpdated settings:",
            reply_markup=settings_keyboard(context),
            parse_mode="Markdown"
        )
        return SETTINGS

    elif data == 'toggle_flip':
        curr = context.user_data.get('canvas_flip', 'normal')
        context.user_data['canvas_flip'] = 'flipped' if curr == 'normal' else 'normal'
        await query.edit_message_text(
            "⚙️ **SETTINGS & PREFERENCES**\n\nUpdated settings:",
            reply_markup=settings_keyboard(context),
            parse_mode="Markdown"
        )
        return SETTINGS

    elif data == 'btn_deposit':
        dep_msg = (
            f"➕ **DEPOSIT FUNDS (100% DIRECT LOCAL CBE VERIFIER)**\n\n"
            f"🏦 **Commercial Bank of Ethiopia (CBE Direct Verification):**\n"
            f"📌 **Account:** `{CBE_EXPECTED_ACCOUNT}`\n"
            f"👤 **Holder Name:** `{CBE_EXPECTED_HOLDER}`\n"
            f"📱 **Telebirr Number:** `{TELEBIRR_NUMBER}`\n\n"
            f"Transfer money to CBE and paste your **SMS Receipt link** (e.g. `https://mbreciept.cbe.com.et/...`) directly in chat.\n\n"
            f"⚡ It will directly verify with CBE official server and credit your wallet instantly!"
        )
        btns = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data='btn_main_menu')]])
        await query.edit_message_text(dep_msg, reply_markup=btns, parse_mode="Markdown")
        return WAIT_RECEIPT

    elif data == 'btn_help':
        await query.edit_message_text(
            f"📞 **CUSTOMER SUPPORT**\n\nFor assistance or inquiries, contact: {SUPPORT_USERNAME}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data='btn_main_menu')]]),
            parse_mode="Markdown"
        )
        return MENU

    elif data == 'btn_admin_dashboard':
        if not is_admin:
            await query.edit_message_text("❌ Access denied. Admin permissions required.")
            return MENU
        stats = get_system_stats()
        adm_msg = (
            f"🛠 **ADMIN CONTROL DASHBOARD**\n\n"
            f"👥 **Total Registered Users:** `{stats['users']}`\n"
            f"💰 **Total System Balance:** `{stats['total_balance']:.2f} ETB`\n"
            f"🪪 **Total IDs Converted:** `{stats['total_converted']}`\n"
            f"⏳ **Pending Receipts:** `{stats['pending_receipts']}`\n"
            f"🚫 **Banned Users:** `{stats['banned_users']}`\n"
            f"🏷 **Global PDF Price:** `{get_pdf_price():.2f} ETB`\n\n"
            f"Choose an admin control action below:"
        )
        await query.edit_message_text(adm_msg, reply_markup=admin_dashboard_inline_keyboard(), parse_mode="Markdown")
        return MENU

    elif data == 'admin_stats':
        if not is_admin: return MENU
        stats = get_system_stats()
        msg = (
            f"📊 **SYSTEM ANALYTICS REPORT**\n\n"
            f"👥 **Active Users:** `{stats['users']}`\n"
            f"💰 **Total Wallet Balances:** `{stats['total_balance']:.2f} ETB`\n"
            f"🪪 **Total IDs Rendered:** `{stats['total_converted']}`\n"
            f"🚫 **Banned Users:** `{stats['banned_users']}`\n"
            f"📄 **Global Price / ID:** `{get_pdf_price():.2f} ETB`"
        )
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data='btn_admin_dashboard')]]), parse_mode="Markdown")
        return MENU

    elif data == 'admin_set_price':
        if not is_admin: return MENU
        await query.edit_message_text(
            "🏷 **SET GLOBAL PDF CONVERSION PRICE**\n\nPlease enter the new global price per PDF ID in ETB (e.g. `40` or `35`):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='btn_admin_dashboard')]]),
            parse_mode="Markdown"
        )
        return WAIT_PRICE_SETTING

    elif data == 'admin_user_adjust':
        if not is_admin: return MENU
        await query.edit_message_text(
            "👥 **USER BALANCE ADJUSTER**\n\nPlease enter target User ID and amount to add/deduct:\nFormat: `USER_ID AMOUNT` (e.g. `12345678 100` or `12345678 -50`)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='btn_admin_dashboard')]]),
            parse_mode="Markdown"
        )
        return WAIT_USER_BALANCE

    elif data == 'admin_custom_price':
        if not is_admin: return MENU
        await query.edit_message_text(
            "🏷 **SET CUSTOM PER-USER PRICE**\n\nPlease enter target User ID and custom price:\nFormat: `USER_ID PRICE` (e.g. `12345678 30` or `12345678 reset`)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='btn_admin_dashboard')]]),
            parse_mode="Markdown"
        )
        return WAIT_CUSTOM_PRICE

    elif data == 'admin_ban_unban':
        if not is_admin: return MENU
        await query.edit_message_text(
            "🚫 **BAN / UNBAN USER CONTROL**\n\nPlease enter target User ID and action:\nFormat: `USER_ID ban` or `USER_ID unban` (e.g. `12345678 ban` or `12345678 unban`)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='btn_admin_dashboard')]]),
            parse_mode="Markdown"
        )
        return WAIT_BAN_UNBAN

    elif data == 'admin_direct_msg':
        if not is_admin: return MENU
        await query.edit_message_text(
            "💬 **SEND DIRECT PRIVATE MESSAGE TO USER**\n\nPlease enter target User ID and message text below:\nFormat: `USER_ID MESSAGE_TEXT` (e.g. `12345678 Hello your balance has been updated!`)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='btn_admin_dashboard')]]),
            parse_mode="Markdown"
        )
        return WAIT_DIRECT_MSG

    elif data == 'admin_broadcast':
        if not is_admin: return MENU
        await query.edit_message_text(
            "📢 **BROADCAST ANNOUNCEMENT TO ALL USERS**\n\nPlease enter your announcement text below. Markdown formatting supported!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='btn_admin_dashboard')]]),
            parse_mode="Markdown"
        )
        return WAIT_BROADCAST

    elif data == 'admin_review_receipts':
        if not is_admin: return MENU
        pending = fetch_pending_receipts()
        if not pending:
            await query.edit_message_text(
                "✅ **No pending receipts to review!**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data='btn_admin_dashboard')]])
            )
            return MENU
        rec = pending[0]
        r_msg = (
            f"🧾 **PENDING RECEIPT REVIEW (1/{len(pending)})**\n\n"
            f"🆔 **Receipt ID:** `{rec['id']}` | **User:** `{rec['user_id']}`\n"
            f"💰 **Amount:** `{rec['amount']:.2f} ETB`\n"
            f"📝 **Raw Text:**\n`{rec['raw_text']}`\n"
            f"📌 **Note:** `{rec['manual_note'] or 'None'}`"
        )
        btns = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"appr_{rec['id']}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"rej_{rec['id']}")
            ],
            [InlineKeyboardButton("🔙 Admin Panel", callback_data='btn_admin_dashboard')]
        ])
        await query.edit_message_text(r_msg, reply_markup=btns, parse_mode="Markdown")
        return MENU

    elif data == 'btn_main_menu':
        return await start(update, context)

    return MENU


# ==========================================
# 7. 100% INLINE DRIVEN ADMIN ACTION HANDLERS
# ==========================================

async def handle_ban_unban_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if ADMIN_ID > 0 and user_id != ADMIN_ID: return MENU
    text = update.message.text.strip()
    parts = text.split()
    
    if len(parts) >= 1 and parts[0].isdigit():
        target_uid = int(parts[0])
        action = parts[1].lower() if len(parts) > 1 else 'ban'
        
        if action in ['unban', 'free', 'allow', 'remove']:
            set_user_ban(target_uid, banned=False)
            await update.message.reply_text(
                f"✅ **User {target_uid} restriction removed. Access restored!**",
                reply_markup=admin_dashboard_inline_keyboard(),
                parse_mode="Markdown"
            )
        else:
            set_user_ban(target_uid, banned=True)
            await update.message.reply_text(
                f"🚫 **User {target_uid} has been banned / restricted.**",
                reply_markup=admin_dashboard_inline_keyboard(),
                parse_mode="Markdown"
            )
        return MENU
        
    await update.message.reply_text("❌ Invalid input. Use format: `USER_ID ban` or `USER_ID unban` (e.g. `12345678 ban`)")
    return MENU

async def handle_direct_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if ADMIN_ID > 0 and user_id != ADMIN_ID: return MENU
    text = update.message.text.strip()
    parts = text.split(" ", 1)
    if len(parts) == 2 and parts[0].isdigit():
        target_uid = int(parts[0])
        msg_content = parts[1]
        try:
            await context.bot.send_message(
                chat_id=target_uid,
                text=f"💬 **MESSAGE FROM ADMIN**\n\n{msg_content}",
                parse_mode="Markdown"
            )
            await update.message.reply_text(f"✅ Direct message sent successfully to User `{target_uid}`!", reply_markup=admin_dashboard_inline_keyboard(), parse_mode="Markdown")
            return MENU
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to send message to User `{target_uid}`: {e}", reply_markup=admin_dashboard_inline_keyboard())
            return MENU
    await update.message.reply_text("❌ Invalid format. Use: `USER_ID MESSAGE_TEXT` (e.g. `12345678 Hello!`)")
    return MENU

async def handle_custom_price_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if ADMIN_ID > 0 and user_id != ADMIN_ID: return MENU
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) == 2 and parts[0].isdigit():
        target_uid = int(parts[0])
        if parts[1].lower() == 'reset':
            set_user_custom_price(target_uid, None)
            await update.message.reply_text(f"✅ Reset User `{target_uid}` custom price to global default ({get_pdf_price():.2f} ETB)!", reply_markup=admin_dashboard_inline_keyboard(), parse_mode="Markdown")
            return MENU
        try:
            c_price = float(parts[1])
            set_user_custom_price(target_uid, c_price)
            await update.message.reply_text(f"✅ Set User `{target_uid}` custom price to `{c_price:.2f} ETB`!", reply_markup=admin_dashboard_inline_keyboard(), parse_mode="Markdown")
            return MENU
        except ValueError:
            pass
    await update.message.reply_text("❌ Invalid format. Use: `USER_ID PRICE` (e.g. `12345678 30` or `12345678 reset`)")
    return MENU

async def handle_price_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if ADMIN_ID > 0 and user_id != ADMIN_ID: return MENU
    text = update.message.text.strip()
    try:
        new_price = float(text)
        set_setting("pdf_to_id_price", str(new_price))
        await update.message.reply_text(
            f"✅ **Global PDF Price updated successfully to {new_price:.2f} ETB!**",
            reply_markup=admin_dashboard_inline_keyboard(),
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ Invalid price format. Enter a valid number.")
    return MENU

async def handle_user_balance_adjust(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if ADMIN_ID > 0 and user_id != ADMIN_ID: return MENU
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) == 2 and parts[0].isdigit():
        target_uid = int(parts[0])
        try:
            amt = float(parts[1])
            add_balance(target_uid, amt)
            new_bal, _ = get_user_info(target_uid)
            await update.message.reply_text(
                f"✅ **Updated User {target_uid} Balance!**\n💰 Added: `{amt:.2f} ETB` | New Balance: `{new_bal:.2f} ETB`",
                reply_markup=admin_dashboard_inline_keyboard(),
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(
                    chat_id=target_uid,
                    text=f"🔔 **Admin Balance Update:** Your wallet balance has been updated by `{amt:.2f} ETB`. New balance: `{new_bal:.2f} ETB`.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            return MENU
        except ValueError:
            pass
    await update.message.reply_text("❌ Invalid input format. Use: `USER_ID AMOUNT` (e.g. `12345678 100`)")
    return MENU

async def handle_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if ADMIN_ID > 0 and user_id != ADMIN_ID: return MENU
    broadcast_text = update.message.text.strip()

    all_users = get_all_user_ids()
    status_msg = await update.message.reply_text(f"📢 **Starting broadcast to {len(all_users)} users...**")

    success_cnt = 0
    fail_cnt = 0

    for uid in all_users:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 **ANNOUNCEMENT**\n\n{broadcast_text}",
                parse_mode="Markdown"
            )
            success_cnt += 1
        except Exception:
            fail_cnt += 1
        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"📢 **BROADCAST COMPLETED!**\n\n"
        f"✅ Delivered: `{success_cnt}` users\n"
        f"❌ Blocked/Failed: `{fail_cnt}` users\n"
        f"📊 Total Target: `{len(all_users)}` users",
        reply_markup=admin_dashboard_inline_keyboard(),
        parse_mode="Markdown"
    )
    return MENU


# ==========================================
# 8. LOCAL DIRECT CBE VERIFICATION HANDLER
# ==========================================

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if is_user_banned(user_id):
        await update.message.reply_text(f"🚫 **Your account has been restricted by Admin.** Contact {SUPPORT_USERNAME} for support.", parse_mode="Markdown")
        return MENU

    text = update.message.text.strip()

    # Route Bottom Persistent Reply Keyboard clicks
    if text in ["📋 Control Panel", "📋 Main Menu", "/start", "/menu"]:
        return await start(update, context)

    elif text in ["📄 Direct Print"]:
        balance, _ = get_user_info(user_id)
        price = get_user_effective_price(user_id)
        await update.message.reply_text(
            f"📄 **Direct Single PDF Mode**\n\n"
            f"Simply send your **Fayda ID PDF** file directly in chat!\n"
            f"💰 Cost per ID: `{price:.2f} ETB` | Your Balance: `{balance:.2f} ETB`",
            reply_markup=main_reply_keyboard(),
            parse_mode="Markdown"
        )
        return MENU

    elif text in ["📦 Bulk Mode"]:
        context.user_data['batch_pdfs'] = []
        await update.message.reply_text(
            "📦 **INTERACTIVE BULK MODE (1 to 5 PDFs)**\n\n"
            "Progress: `[░░░░░] 0/5 PDFs`\n\n"
            "📥 Please send PDF 1/5 now.\n"
            "💡 Tap **🖨️ Convert Now** at any time to print collected PDFs!",
            reply_markup=bulk_interactive_keyboard(0),
            parse_mode="Markdown"
        )
        return BATCH_MODE

    elif text in ["💳 Deposit / Balance", "💳 Wallet"]:
        balance, _ = get_user_info(user_id)
        price = get_user_effective_price(user_id)
        wallet_msg = (
            f"💳 **YOUR WALLET ACCOUNT**\n\n"
            f"👤 **User ID:** `{user_id}`\n"
            f"💰 **Available Balance:** `{balance:.2f} ETB`\n"
            f"🏷 **Your Rate:** `{price:.2f} ETB` / ID\n\n"
            f"🏦 **CBE Account:** `{CBE_EXPECTED_ACCOUNT}` ({CBE_EXPECTED_HOLDER})\n"
            f"📱 **Telebirr Number:** `{TELEBIRR_NUMBER}`\n"
            f"Paste your CBE SMS receipt link (`mbreciept.cbe.com.et...`) directly in chat!"
        )
        await update.message.reply_text(wallet_msg, reply_markup=main_reply_keyboard(), parse_mode="Markdown")
        return MENU

    elif text in ["📞 Support & Help", "📞 Support"]:
        await update.message.reply_text(f"📞 **CUSTOMER SUPPORT**\n\nFor assistance or inquiries, contact: {SUPPORT_USERNAME}", reply_markup=main_reply_keyboard(), parse_mode="Markdown")
        return MENU

    # 100% Local CBE Direct Verification with Supabase Cross-Project Receipt Checking
    if "mbreciept.cbe.com.et" in text.lower():
        msg = await update.message.reply_text("🔎 **Verifying CBE Receipt directly with Official CBE Server & Shared DB...**")
        v_res = await asyncio.to_thread(verify_cbe_local, text)

        if not v_res["ok"]:
            await msg.edit_text(v_res["error"], parse_mode="Markdown")
            return MENU

        short_code = v_res["short_code"]
        cbe_link = v_res["cbe_link"]
        txn_id = v_res["transaction_id"]
        amount = v_res["amount"]

        if receipt_already_used(text, cbe_link, txn_id):
            await msg.edit_text("❌ **This CBE Receipt link or Transaction ID has already been used!**")
            return MENU

        rec_id = record_receipt(user_id, text, cbe_link, txn_id, amount, "VERIFIED")
        if rec_id:
            add_balance(user_id, amount)
            new_bal, _ = get_user_info(user_id)
            await msg.edit_text(
                f"✅ **CBE Receipt Verified Successfully!**\n\n"
                f"👤 Payer: `{v_res.get('payer_name', 'Unknown')}`\n"
                f"🏦 Account: `{v_res.get('receiver_account', '')}`\n"
                f"💰 Credited Amount: `{amount:.2f} ETB`\n"
                f"💳 New Wallet Balance: `{new_bal:.2f} ETB`",
                parse_mode="Markdown"
            )
            return MENU
        else:
            await msg.edit_text("❌ **Duplicate receipt transaction.**")
            return MENU

    is_admin = (ADMIN_ID > 0 and user_id == ADMIN_ID)
    await update.message.reply_text(
        "⚠️ **Invalid input.** Please send a valid **Fayda ID PDF file** or paste a **CBE SMS Receipt Link** (`mbreciept.cbe.com.et...`).",
        reply_markup=main_menu_inline_keyboard(is_admin)
    )
    return MENU


# ==========================================
# 9. SINGLE & BULK PDF HANDLERS WITH CONCURRENCY LOCKS & FAST REMBG
# ==========================================

async def process_single_pdf_direct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    doc = update.message.document

    if is_user_banned(user_id):
        await update.message.reply_text(f"🚫 **Your account has been restricted by Admin.** Contact {SUPPORT_USERNAME} for support.", parse_mode="Markdown")
        return MENU

    if not doc or not doc.file_name.lower().endswith('.pdf'):
        return

    # Concurrency Lock Guard
    with LOCK_SET_GUARD:
        if user_id in ACTIVE_USER_LOCKS:
            await update.message.reply_text("⏳ **Your previous file is currently being processed.** Please wait a moment...")
            return MENU
        ACTIVE_USER_LOCKS.add(user_id)

    price_per_id = get_user_effective_price(user_id)
    balance, _ = get_user_info(user_id)
    is_admin = (ADMIN_ID > 0 and user_id == ADMIN_ID)

    if balance < price_per_id:
        with LOCK_SET_GUARD: ACTIVE_USER_LOCKS.discard(user_id)
        await update.message.reply_text(
            f"❌ **Insufficient Wallet Balance!**\n\n"
            f"💰 Cost per ID: `{price_per_id:.2f} ETB` | Your Balance: `{balance:.2f} ETB`\n"
            f"Please deposit funds to continue.",
            reply_markup=main_menu_inline_keyboard(is_admin),
            parse_mode="Markdown"
        )
        return MENU

    msg = await update.message.reply_text("⏳ 📥 **Downloading Fayda PDF...**")
    temp_prefix = f"single_{user_id}_{int(datetime.now().timestamp())}"
    pdf_path = f"{temp_prefix}.pdf"

    try:
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(pdf_path)

        await msg.edit_text("⏳ 🔍 **Extracting Fayda ID Data & Photo (10x Fast Engine)...**")
        data = await asyncio.to_thread(extract_data_from_pdf, pdf_path, temp_prefix)
        
        if data:
            await msg.edit_text("⏳ 🎨 **Rendering High-Precision ID Card...**")
            user_mode = context.user_data.get('output_mode', 'color')
            is_flipped = (context.user_data.get('canvas_flip', 'normal') == 'flipped')
            
            out_path = f"Fayda_{temp_prefix}.png"
            await asyncio.to_thread(generate_fayda_v3, data, out_path, temp_prefix, user_mode, None, is_flipped)

            deduct_balance(user_id, price_per_id, converted_count=1)
            new_bal, _ = get_user_info(user_id)

            await msg.edit_text("⏳ 📤 **Delivering Printable Document...**")
            with open(out_path, 'rb') as f:
                await update.message.reply_document(
                    f,
                    filename=f"Fayda_{data.get('name_eng', 'ID').replace(' ', '_')}.png",
                    caption=(
                        f"✅ **Fayda ID Conversion Successful!**\n\n"
                        f"🎨 Mode: `{user_mode.upper()}` | 🔄 Canvas: `{'FLIPPED' if is_flipped else 'NORMAL'}`\n"
                        f"💰 Deducted: `{price_per_id:.2f} ETB` | Balance: `{new_bal:.2f} ETB`"
                    ),
                    reply_markup=main_menu_inline_keyboard(is_admin),
                    parse_mode="Markdown"
                )
            if os.path.exists(out_path): os.remove(out_path)
            # Auto-destroy progress message
            await msg.delete()
        else:
            await msg.edit_text("❌ **Extraction failed.** Invalid Fayda PDF layout or unreadable file.")
    finally:
        with LOCK_SET_GUARD: ACTIVE_USER_LOCKS.discard(user_id)
        if os.path.exists(pdf_path): os.remove(pdf_path)
        for temp_f in [f"photo_{temp_prefix}.png", f"qr_{temp_prefix}.png", f"fin_{temp_prefix}.png"]:
            if os.path.exists(temp_f): os.remove(temp_f)
    return MENU


async def handle_batch_pdf_interactive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    doc = update.message.document

    if is_user_banned(user_id):
        await update.message.reply_text(f"🚫 **Your account has been restricted by Admin.** Contact {SUPPORT_USERNAME} for support.", parse_mode="Markdown")
        return MENU

    if not doc or not doc.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("⚠️ Please send a valid **.pdf** document.", reply_markup=bulk_interactive_keyboard(len(context.user_data.get('batch_pdfs', []))))
        return BATCH_MODE

    context.user_data.setdefault('batch_pdfs', [])
    batch_list = context.user_data['batch_pdfs']

    temp_prefix = f"batch_{user_id}_{len(batch_list)+1}_{int(datetime.now().timestamp())}"
    pdf_path = f"{temp_prefix}.pdf"
    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(pdf_path)

    batch_list.append(pdf_path)
    count = len(batch_list)

    progress_bar = "█" * count + "░" * (MAX_BATCH_PDFS - count)

    if count < MAX_BATCH_PDFS:
        await update.message.reply_text(
            f"✅ **PDF {count}/{MAX_BATCH_PDFS} received!**\n\n"
            f"Progress: `[{progress_bar}] {count}/{MAX_BATCH_PDFS}`\n\n"
            f"📥 Send PDF {count+1}/{MAX_BATCH_PDFS} or tap **🖨️ Convert Now** below to print all {count} IDs on A4 sheet!",
            reply_markup=bulk_interactive_keyboard(count),
            parse_mode="Markdown"
        )
        return BATCH_MODE
    else:
        await update.message.reply_text("✅ **5/5 PDFs received!** Starting automatic conversion onto A4 printable sheet...")
        return await execute_batch_conversion(update, context)


async def handle_bulk_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    is_admin = (ADMIN_ID > 0 and user_id == ADMIN_ID)

    if data == 'bulk_convert_now':
        batch_list = context.user_data.get('batch_pdfs', [])
        if not batch_list:
            await query.message.reply_text("⚠️ No PDFs received yet. Please send at least 1 PDF.")
            return BATCH_MODE
        return await execute_batch_conversion(update, context)

    elif data == 'bulk_cancel':
        batch_list = context.user_data.get('batch_pdfs', [])
        for p in batch_list:
            if os.path.exists(p): os.remove(p)
        context.user_data['batch_pdfs'] = []
        await query.edit_message_text("❌ **Bulk conversion cancelled.**", reply_markup=main_menu_inline_keyboard(is_admin))
        return MENU


async def execute_batch_conversion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    batch_list = context.user_data.get('batch_pdfs', [])
    pdf_count = len(batch_list)
    is_admin = (ADMIN_ID > 0 and user_id == ADMIN_ID)

    if pdf_count == 0:
        return MENU

    # Lock check for batch execution
    with LOCK_SET_GUARD:
        if user_id in ACTIVE_USER_LOCKS:
            await context.bot.send_message(chat_id=user_id, text="⏳ **Your conversion task is already processing.** Please wait...")
            return MENU
        ACTIVE_USER_LOCKS.add(user_id)

    price_per_id = get_user_effective_price(user_id)
    total_cost = pdf_count * price_per_id
    balance, _ = get_user_info(user_id)

    if balance < total_cost:
        with LOCK_SET_GUARD: ACTIVE_USER_LOCKS.discard(user_id)
        msg = f"❌ **Insufficient Wallet Balance!**\n\n📦 PDFs to convert: **{pdf_count}**\n💰 Total Cost: `{total_cost:.2f} ETB` | Your Balance: `{balance:.2f} ETB`\nPlease deposit funds to continue."
        if update.callback_query:
            await update.callback_query.message.reply_text(msg, reply_markup=main_menu_inline_keyboard(is_admin), parse_mode="Markdown")
        else:
            await update.message.reply_text(msg, reply_markup=main_menu_inline_keyboard(is_admin), parse_mode="Markdown")
        return MENU

    status_msg = await context.bot.send_message(
        chat_id=user_id,
        text=f"⏳ **Processing {pdf_count} Fayda ID PDF(s) onto Printable A4 Sheet...**",
        parse_mode="Markdown"
    )

    temp_prefix = f"exec_batch_{user_id}_{int(datetime.now().timestamp())}"
    output_dir = f"output_{temp_prefix}"
    os.makedirs(output_dir, exist_ok=True)

    card_png_files = []
    success_count = 0

    user_mode = context.user_data.get('output_mode', 'color')
    is_flipped = (context.user_data.get('canvas_flip', 'normal') == 'flipped')

    try:
        for idx, p_path in enumerate(batch_list, 1):
            sub_prefix = f"{temp_prefix}_{idx}"
            data = await asyncio.to_thread(extract_data_from_pdf, p_path, sub_prefix)
            if data:
                safe_name = re.sub(r'[^\w\-_]', '_', data.get('name_eng', f"ID_{idx}"))
                c_out = os.path.join(output_dir, f"{idx:02d}_{safe_name}.png")
                await asyncio.to_thread(generate_fayda_v3, data, c_out, sub_prefix, user_mode, None, is_flipped)
                card_png_files.append(c_out)
                success_count += 1

            for temp_f in [f"photo_{sub_prefix}.png", f"qr_{sub_prefix}.png", f"fin_{sub_prefix}.png"]:
                if os.path.exists(temp_f): os.remove(temp_f)

        if success_count == 0:
            await status_msg.edit_text("❌ **Conversion failed.** Could not extract valid Fayda data from the PDF(s).")
            return MENU

        a4_output_path = f"Fayda_Printable_A4_{temp_prefix}.png"
        await asyncio.to_thread(arrange_cards_on_a4, card_png_files, a4_output_path, success_count)

        actual_cost = success_count * price_per_id
        deduct_balance(user_id, actual_cost, converted_count=success_count)
        new_bal, _ = get_user_info(user_id)

        with open(a4_output_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=user_id,
                document=f,
                filename=f"Fayda_Printable_A4_{success_count}_IDs.png",
                caption=(
                    f"🎉 **Printable A4 Sheet Ready ({success_count} Fayda ID Cards)!**\n\n"
                    f"🎨 Mode: `{user_mode.upper()}` | 🔄 Canvas: `{'FLIPPED' if is_flipped else 'NORMAL'}`\n"
                    f"💰 Total Deducted: `{actual_cost:.2f} ETB` | Balance: `{new_bal:.2f} ETB`\n\n"
                    f"🖨 **Ready to Print!** Print on A4 paper at 100% scale and cut along guidelines."
                ),
                reply_markup=main_menu_inline_keyboard(is_admin),
                parse_mode="Markdown"
            )

        if os.path.exists(a4_output_path): os.remove(a4_output_path)
        # Auto-destroy progress message
        await status_msg.delete()

    finally:
        with LOCK_SET_GUARD: ACTIVE_USER_LOCKS.discard(user_id)
        for p in batch_list:
            if os.path.exists(p): os.remove(p)
        if os.path.exists(output_dir): shutil.rmtree(output_dir, ignore_errors=True)
        context.user_data['batch_pdfs'] = []

    return MENU


# ==========================================
# 10. MAIN ENTRY POINT
# ==========================================

def main():
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    init_db()
    warm_up_rembg_session()

    if not BOT_TOKEN:
        print("⚠️ WARNING: BOT_TOKEN is empty! Please set BOT_TOKEN in your .env file.")

    if SUPABASE_URL and SUPABASE_KEY:
        print(f"☁️ Supabase Cross-Project Receipt Sync active on table: '{SUPABASE_TABLE}'")
    else:
        print("ℹ️ Supabase not configured in .env (Using Local SQLite Database for receipt tracking).")

    print("🚀 Initializing Fayda ID Bot (Instant Port Binding & Fast Rembg)...")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('admin', start),
            CommandHandler('menu', start),
            CallbackQueryHandler(handle_callback_query),
            MessageHandler(filters.Document.PDF, process_single_pdf_direct),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
        ],
        states={
            MENU: [
                CallbackQueryHandler(handle_callback_query),
                MessageHandler(filters.Document.PDF, process_single_pdf_direct),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
            ],
            WAIT_RECEIPT: [
                CallbackQueryHandler(handle_callback_query),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
            ],
            SETTINGS: [
                CallbackQueryHandler(handle_callback_query)
            ],
            BATCH_MODE: [
                MessageHandler(filters.Document.PDF, handle_batch_pdf_interactive),
                CallbackQueryHandler(handle_bulk_callback)
            ],
            WAIT_BROADCAST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast_text),
                CallbackQueryHandler(handle_callback_query)
            ],
            WAIT_USER_BALANCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_balance_adjust),
                CallbackQueryHandler(handle_callback_query)
            ],
            WAIT_PRICE_SETTING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price_setting),
                CallbackQueryHandler(handle_callback_query)
            ],
            WAIT_DIRECT_MSG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_direct_msg),
                CallbackQueryHandler(handle_callback_query)
            ],
            WAIT_CUSTOM_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_price_setting),
                CallbackQueryHandler(handle_callback_query)
            ],
            WAIT_BAN_UNBAN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ban_unban_input),
                CallbackQueryHandler(handle_callback_query)
            ]
        },
        fallbacks=[CommandHandler('start', start)],
        per_message=False
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(approve_receipt, pattern="^(appr|rej)_"))

    print("✅ Bot started successfully in 100% Polling mode! Listening for updates...")
    app.run_polling()

if __name__ == "__main__":
    main()
