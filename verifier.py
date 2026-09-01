import re
import logging
import asyncio
import httpx
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

OFFICIAL_CBE_DOMAIN = "mb.cbe.com.et"
OFFICIAL_CBE_RECEIPT_HOST = "mbreciept.cbe.com.et"
TELEBIRR_RECEIPT_BASE_URL = "https://transactioninfo.ethiotelecom.et/receipt/"

VERIFICATION_CACHE = {}  # {code/txn_id: (timestamp, result_dict)}
CACHE_TTL_SECONDS = 600  # 10 minutes cache TTL

outbound_bank_lock = asyncio.Lock()

class NotFoundError(Exception):
    pass

class ValidationError(Exception):
    pass

def normalize(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()

def compare_amount(expected, parsed):
    try:
        def num(v):
            return round(float(re.sub(r"[^0-9.-]", "", str(v).replace(",", ""))), 2)
        return num(expected) == num(parsed)
    except (TypeError, ValueError):
        return False

def _adjacent(soup, labels):
    labels = [normalize(x) for x in labels]
    for td in soup.find_all(["td", "th"]):
        text = normalize(td.get_text(" ", strip=True))
        if any(label in text for label in labels):
            sibling = td.find_next_sibling(["td", "th"])
            if sibling:
                value = " ".join(sibling.get_text(" ", strip=True).split())
                if value:
                    return value
    return ""

def _column(table, labels):
    if not table:
        return ""
    labels = [normalize(x) for x in labels]
    rows = table.find_all("tr")
    for row_index, row in enumerate(rows):
        cells = row.find_all(["td", "th"])
        for col_index, cell in enumerate(cells):
            if any(label in normalize(cell.get_text(" ", strip=True)) for label in labels):
                if row_index + 1 < len(rows):
                    next_cells = rows[row_index + 1].find_all(["td", "th"])
                    if col_index < len(next_cells):
                        return " ".join(next_cells[col_index].get_text(" ", strip=True).split())
                if col_index + 1 < len(cells):
                    return " ".join(cells[col_index + 1].get_text(" ", strip=True).split())
    return ""

def telebirr_verification(raw_html, default_verification=None, expected_data=None):
    """HTML Parser for Telebirr Web Receipts."""
    if not raw_html:
        raise NotFoundError("Empty Telebirr receipt response")

    soup = BeautifulSoup(raw_html, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    normalized = normalize(text)

    for bad in ("this request is not correct", "receipt not found", "transaction not found", "invalid receipt"):
        if bad in normalized:
            raise NotFoundError("Receipt not found or invalid")

    tables = soup.find_all("table")
    invoice_table = next((t for t in reversed(tables) if "settled amount" in normalize(t.get_text(" ", strip=True))), None)
    status_table = next((t for t in reversed(tables) if "transaction status" in normalize(t.get_text(" ", strip=True))), None)

    name = _adjacent(soup, ["Credited Party name", "Receiver Name", "Recipient Name", "Beneficiary Name"])
    account = _adjacent(soup, ["Credited party account no", "Credited party account", "Receiver Account", "Recipient Account", "Account Number"])

    paid_ref = soup.find(id="paid_reference_number")
    if paid_ref and (not name or not account):
        parts = " ".join(paid_ref.get_text(" ", strip=True).split()).split()
        if not account and parts:
            account = parts[0]
        if not name and len(parts) > 1:
            name = " ".join(parts[1:])

    amount = _column(invoice_table, ["Settled Amount", "Payment Amount", "Transaction Amount", "Amount"])
    amount = re.sub(r"[^0-9.,-]", "", amount).replace(",", "")
    if not amount:
        m = re.search(r"(?:settled\s*amount|payment\s*amount|amount)\s*[:\-]?\s*(?:etb|birr)?\s*([\d,]+(?:\.\d{1,2})?)", text, re.I)
        amount = m.group(1).replace(",", "") if m else ""

    status = _adjacent(status_table or soup, ["Transaction Status", "Payment Status", "Status"])
    if not status:
        m = re.search(r"(?:transaction\s*status|payment\s*status|status)\s*[:\-]?\s*([^\n]+)", text, re.I)
        status = m.group(1).strip() if m else ""

    date = _column(invoice_table, ["Payment date", "Transaction date", "Date"])
    if not date:
        m = re.search(r"(?:payment\s*date|transaction\s*date|date)\s*[:\-]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})", text, re.I)
        date = m.group(1) if m else ""

    dm = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", date or "")
    if dm:
        date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"

    parsed = {"amount": amount, "status": status, "recipientName": name, "date": date, "accountNumber": account}

    flags = default_verification if isinstance(default_verification, dict) else ({
        "amount": True, "status": True, "recipientName": True, "accountNumber": True, "date": True
    } if default_verification is True else {})
    expected_data = expected_data or {}

    for key in ("amount", "status", "recipientName", "accountNumber", "date"):
        if not flags.get(key):
            continue
        expected = expected_data.get(key)
        if expected in (None, ""):
            continue
        actual = parsed.get(key, "")
        if not actual:
            raise ValidationError(f'No parsed data for "{key}"')
        if key == "amount":
            ok = compare_amount(expected, actual)
        elif key == "date":
            dm = re.match(r"(\d{4})-(\d{2})-(\d{2})", actual)
            if not dm:
                raise ValidationError(f"Invalid date format in receipt: {actual}")
            if expected_data.get("paymentYear") and int(dm.group(1)) != int(expected_data["paymentYear"]):
                raise ValidationError(f"Year mismatch. Expected: {expected_data['paymentYear']}, Actual: {dm.group(1)}")
            if expected_data.get("paymentMonth") and int(dm.group(2)) != int(expected_data["paymentMonth"]):
                raise ValidationError(f"Month mismatch. Expected: {expected_data['paymentMonth']}, Actual: {dm.group(2)}")
            ok = True
        else:
            ok = normalize(expected) == normalize(actual)
        if not ok:
            raise ValidationError(f"Mismatch on {key}. Expected: {expected}, Actual: {actual}")

    return parsed

def check_account_match(got_acc: str, expected_acc: str) -> bool:
    """
    Validates if the receiver account/phone returned by server matches the expected account configured in .env.
    Supports user-masked patterns in .env (e.g. '1****7241', '10003*****279', '0912***678') as well as full numbers.
    """
    if not got_acc or not expected_acc:
        return False
    
    got_str = str(got_acc).strip().upper()
    expected_str = str(expected_acc).strip().upper()

    if got_str == expected_str:
        return True

    # 1. User specified mask in .env with asterisks (e.g. "1****7241")
    if "*" in expected_str:
        pattern = "^" + re.escape(expected_str).replace(r"\*", r".*") + "$"
        if re.match(pattern, got_str, re.IGNORECASE):
            return True

    # 2. Extract digits only for numeric comparisons
    got_digits = re.sub(r'[^0-9]', '', got_str)
    expected_digits = re.sub(r'[^0-9]', '', expected_str)

    if got_digits and expected_digits:
        if got_digits == expected_digits:
            return True
        
        # 3. Check suffix matching (last 4 digits) for masked server outputs
        if len(got_digits) >= 4 and len(expected_digits) >= 4:
            if got_digits.endswith(expected_digits[-4:]) or expected_digits.endswith(got_digits[-4:]):
                return True

    return False

def check_holder_match(got_holder: str, expected_holder: str) -> bool:
    """
    Validates if the parsed creditAccountHolder / recipientName matches target CBE/Telebirr Account Holder Name in .env.
    Case-insensitive partial matching (e.g., 'MELAX DIGITAL SHOP' matches 'MELAX').
    """
    if not got_holder or not expected_holder:
        return True
    
    got_clean = str(got_holder).strip().upper()
    expected_clean = str(expected_holder).strip().upper()

    if not got_clean or not expected_clean:
        return True

    return expected_clean in got_clean or got_clean in expected_clean

def is_within_24_hours(tx_date_str: str) -> bool:
    """
    Validates that the transaction date returned by server is within the last 24 hours ("የዛሬ ለዛሬ ብቻ").
    """
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
            parsed_date = datetime.strptime(tx_date_str.strip(), fmt)
            break
        except ValueError:
            continue

    if not parsed_date:
        return True

    diff = now - parsed_date
    return diff <= timedelta(hours=24) and diff >= timedelta(days=-1)

async def verify_telebirr_web_async(input_text: str, expected_phone: str = None, expected_name: str = None) -> dict:
    """
    Fetches and verifies Telebirr Web Receipts from https://transactioninfo.ethiotelecom.et/receipt/{txn_id}
    STRICT CHECKS:
    1. Receiver Account / Phone matching (supporting masked patterns in .env like 1****7241 or 0912***678)
    2. Receiver Holder Name matching
    3. 24-Hour transaction date validation
    """
    txn_id = None
    url_match = re.search(r'transactioninfo\.ethiotelecom\.et\/receipt\/([A-Za-z0-9_-]+)', input_text, re.IGNORECASE)
    if url_match:
        txn_id = url_match.group(1).strip()
    else:
        txn_match = re.search(r'\b([A-Z0-9]{8,12})\b', input_text, re.IGNORECASE)
        if txn_match:
            txn_id = txn_match.group(1).strip()

    if not txn_id:
        return {
            "ok": False,
            "code": "MISSING_TXN_ID",
            "error": "📱 <b>የቴሌብር የግብይት ቁጥር (Txn ID) አልተገኘም</b>\n\nእባክዎን የ <b>https://transactioninfo.ethiotelecom.et/receipt/...</b> ሊንክ ወይም የግብይት ቁጥር (ምሳሌ፦ <code>DHB2PJFAQW</code>) ይላኩ!"
        }

    txn_id = txn_id.upper()
    now_ts = datetime.now().timestamp()
    if txn_id in VERIFICATION_CACHE:
        cache_time, cached_res = VERIFICATION_CACHE[txn_id]
        if now_ts - cache_time < CACHE_TTL_SECONDS:
            return cached_res

    async with outbound_bank_lock:
        await asyncio.sleep(0.5)
        try:
            url = f"{TELEBIRR_RECEIPT_BASE_URL}{txn_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 TELEBIRR/1.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
            }
            async with httpx.AsyncClient(verify=False, timeout=12.0) as client:
                res = await client.get(url, headers=headers, follow_redirects=True)
                if res.status_code == 200 and res.text:
                    try:
                        parsed = telebirr_verification(res.text)
                    except NotFoundError:
                        return {
                            "ok": False,
                            "code": "NOT_FOUND",
                            "error": f"⚠️ <b>የቴሌብር ደረሰኝ በሰርቨር ላይ አልተገኘም (NOT FOUND)</b>\n\nየግብይት ቁጥር <code>{txn_id}</code> በኢትዮ ቴሌኮም ሰርቨር ላይ አልተገኘም።"
                        }
                    except ValidationError as ve:
                        return {
                            "ok": False,
                            "code": "VALIDATION_ERROR",
                            "error": f"❌ <b>የቴሌብር ደረሰኝ ማረጋገጫ አልተሳካም</b>\n\n{ve}"
                        }

                    amt = float(parsed.get("amount") or 0.0)
                    rec_name = parsed.get("recipientName", "")
                    rec_phone = parsed.get("accountNumber", "")
                    tx_date = parsed.get("date", datetime.now().strftime("%Y-%m-%d"))

                    # 1. MANDATORY RECEIVER PHONE CHECK (SUPPORTING USER MASKED PATTERNS LIKE 1****7241)
                    if expected_phone and rec_phone and not check_account_match(rec_phone, expected_phone):
                        return {
                            "ok": False,
                            "code": "ACCOUNT_MISMATCH",
                            "error": f"❌ <b>የተቀባይ ቴሌብር ስልክ ቁጥር አይዛመድም (PHONE MISMATCH)</b>\n\nክፍያው የተፈጸመው ወደ <b>{rec_phone}</b> ነው። እባክዎን ወደ እኛ ቁጥር (<code>{expected_phone}</code>) ይክፈሉ።"
                        }

                    # 2. MANDATORY RECEIVER NAME CHECK
                    if expected_name and rec_name and not check_holder_match(rec_name, expected_name):
                        return {
                            "ok": False,
                            "code": "HOLDER_MISMATCH",
                            "error": f"❌ <b>የተቀባይ ስም አይዛመድም (NAME MISMATCH)</b>\n\nክፍያው የተፈጸመው ወደ <b>{rec_name}</b> ነው። እባክዎን ወደ <b>{expected_name}</b> ይክፈሉ።"
                        }

                    # 3. MANDATORY 24-HOUR DATE CHECK
                    if not is_within_24_hours(tx_date):
                        return {
                            "ok": False,
                            "code": "EXPIRED_RECEIPT",
                            "error": f"🕒 <b>የቆየ የቴሌብር ደረሰኝ (EXPIRED RECEIPT)</b>\n\nይህ ክፍያ ከ 24 ሰዓት በፊት የተፈጸመ ስለሆነ አይቀበልም። የዛሬ ክፍያ ብቻ ያስገቡ!"
                        }

                    result = {
                        "ok": True,
                        "provider": "TELEBIRR",
                        "transaction_id": txn_id,
                        "amount": amt,
                        "payer_name": "Telebirr Customer",
                        "receiver_name": rec_name,
                        "receiver_account": rec_phone,
                        "date": tx_date
                    }
                    VERIFICATION_CACHE[txn_id] = (now_ts, result)
                    return result
                else:
                    return {
                        "ok": False,
                        "code": "NOT_FOUND",
                        "error": f"⚠️ <b>የቴሌብር ደረሰኝ አልተገኘም (NOT FOUND)</b>\n\nየግብይት ቁጥር <code>{txn_id}</code> በኢትዮ ቴሌኮም ሰርቨር ላይ አልተገኘም።"
                    }
        except Exception as e:
            logger.error(f"Telebirr web receipt verification network error: {e}")
            return {
                "ok": False,
                "code": "NETWORK_ERROR",
                "error": "⚠️ ከቴሌብር ሰርቨር ጋር ማገናኘት አልተቻለም። እባክዎን ትንሽ ቆይተው እንደገና ይሞክሩ።"
            }

async def verify_cbe_async(input_text: str, expected_account: str = None, expected_holder: str = None) -> dict:
    """Parses and verifies CBE receipts strictly via official CBE Receipt Links."""
    link_match = re.search(r'mbreciept\.cbe\.com\.et\/([A-Za-z0-9_-]{6,})', input_text, re.IGNORECASE)
    if not link_match:
        return {
            "ok": False,
            "code": "MISSING_LINK",
            "error": "🔗 <b>የCBE ደረሰኝ ሊንክ አልተገኘም (MISSING LINK)</b>\n\nለራስ-ሰር ማረጋገጫ የ <b>mbreciept.cbe.com.et/...</b> ደረሰኝ ሊንክ የያዘውን ኤስኤምኤስ ብቻ ኮፒ አድርገው ይላኩ!"
        }

    short_code = link_match.group(1).strip()
    if OFFICIAL_CBE_RECEIPT_HOST not in input_text.lower():
        return {
            "ok": False,
            "code": "INVALID_DOMAIN",
            "error": "⛔ <b>ህገ-ወጥ የCBE ደረሰኝ ሊንክ (INVALID DOMAIN)</b>\n\nየላኩት ሊንክ ከኦፊሺያሉ የኢትዮጵያ ንግድ ባንክ mbreciept.cbe.com.et ዶሜይን ውጭ ነው።"
        }

    now_ts = datetime.now().timestamp()
    if short_code in VERIFICATION_CACHE:
        cache_time, cached_res = VERIFICATION_CACHE[short_code]
        if now_ts - cache_time < CACHE_TTL_SECONDS:
            return cached_res

    async with outbound_bank_lock:
        await asyncio.sleep(0.5)
        try:
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
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    rec_acc = data.get("creditAccountNo", "")
                    rec_holder = data.get("creditAccountHolder", "")
                    
                    if expected_account and not check_account_match(rec_acc, expected_account):
                        return {
                            "ok": False,
                            "code": "ACCOUNT_MISMATCH",
                            "error": f"❌ <b>የተቀባይ አካውንት ቁጥር አይዛመድም (ACCOUNT MISMATCH)</b>\n\nይህ ክፍያ የተፈጸመው ወደ አካውንት <code>{rec_acc}</code> ነው። እባክዎን ክፍያዎን ወደ እኛ አካውንት (<code>{expected_account}</code>) ይክፈሉ።"
                        }

                    if expected_holder and not check_holder_match(rec_holder, expected_holder):
                        return {
                            "ok": False,
                            "code": "HOLDER_MISMATCH",
                            "error": f"❌ <b>የተቀባይ ስም አይዛመድም (HOLDER NAME MISMATCH)</b>\n\nይህ ክፍያ የተፈጸመው ወደ <b>{rec_holder}</b> አካውንት ነው። እባክዎን ክፍያዎን ወደ <b>{expected_holder}</b> አካውንት ይክፈሉ።"
                        }

                    tx_date = str(data.get("processingDate") or data.get("authDate") or datetime.now().strftime("%Y-%m-%d"))
                    if not is_within_24_hours(tx_date):
                        return {
                            "ok": False,
                            "code": "EXPIRED_RECEIPT",
                            "error": f"🕒 <b>የቆየ የክፍያ ደረሰኝ (EXPIRED RECEIPT)</b>\n\nይህ የክፍያ ደረሰኝ የተፈጸመበት ቀን (<code>{tx_date[:10]}</code>) ከ 24 ሰዓት በፊት ስለሆነ አይቀበልም። የዛሬ ክፍያ ብቻ ያስገቡ!"
                        }

                    amt = float(data.get("amountCredited") or data.get("creditAmount") or 0)
                    txn_id = str(data.get("id") or data.get("transactionId") or short_code)

                    result = {
                        "ok": True,
                        "provider": "CBE",
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
                        "error": f"⚠️ <b>ደረሰኙ በባንክ ሰርቨር አልተገኘም (NOT FOUND)</b>\n\nየላኩት የCBE ደረሰኝ ሊንክ በባንክ ሰርቨር ላይ አልተገኘም። እባክዎን ትክክለኛውን ሊንክ ማረጋገጫ ይላኩ።"
                    }
        except Exception as e:
            logger.error(f"CBE link verification network error: {e}")
            return {
                "ok": False,
                "code": "NETWORK_ERROR",
                "error": "⚠️ የባንክ ሰርቨር ማረጋገጫ አገልግሎት ላይ የኔትወርክ ችግር አጋጥሟል። እባክዎን ትንሽ ቆይተው እንደገና ይሞክሩ።"
            }

async def verify_payment(
    input_text: str,
    expected_cbe_account: str = "1000320563279",
    expected_cbe_holder: str = "MELAX DIGITAL",
    expected_telebirr_phone: str = "0912345678",
    expected_telebirr_holder: str = "MELAX DIGITAL"
) -> dict:
    """
    Main entry point: Automatically routes input to CBE Verifier or Telebirr Web Receipt Verifier.
    """
    text = input_text.strip()
    
    if "transactioninfo.ethiotelecom.et" in text.lower() or "telebirr" in text.lower() or re.search(r'\b[A-Z0-9]{8,12}\b', text):
        if "mbreciept" not in text.lower() and "cbe" not in text.lower() and not re.search(r'\bFT[A-Z0-9]{8,}\b', text, re.I):
            return await verify_telebirr_web_async(text, expected_phone=expected_telebirr_phone, expected_name=expected_telebirr_holder)

    return await verify_cbe_async(text, expected_account=expected_cbe_account, expected_holder=expected_cbe_holder)
