import sqlite3
import fitz
import os
from flask import Flask, request  # Add this
import re
import io
import asyncio
import random
import requests
from datetime import datetime
from rembg import remove, new_session
from PIL import Image, ImageDraw, ImageFont, ImageChops
import numpy as np
from ethiopian_date import EthiopianDateConverter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# CONFIGURATION 
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
TELEBIRR_NUMBER = os.environ.get("TELEBIRR_NUMBER", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7662166641:AAHn8IZ3nHFPhU2YtJZlMMIJVW8vUaGu7E8")
FAYDA_API_BASE = os.environ.get("FAYDA_API_BASE", "https://fayda-railway-full-production.up.railway.app")
FAYDA_API_KEY = os.environ.get("FAYDA_API_KEY", "rk_85c7922a2271c518c2302350fb2a2777898c6c82ec6a0786")
REMBG_SESSION = new_session(model_name='u2net')

# flask
# --- ADD THIS BLOCK ---
flask_app = Flask(__name__)

# 2. Define a placeholder for the bot app
app = None

@flask_app.route('/')
def health_check():
    return "Bot is alive!", 200

@flask_app.route('/webhook', methods=['POST'])
async def webhook():
    global app
    if app:
        # Initialize and Start if not already running
        if not app.updater: 
            await app.initialize()
            await app.start()
            
            # AUTO-SET WEBHOOK: This ensures Telegram knows where to send updates
            URL = os.environ.get("RENDER_EXTERNAL_URL")
            if URL:
                await app.bot.set_webhook(url=f"{URL}/webhook")
            
        data = request.get_json(force=True)
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
        
    return "ok", 200

# Conversation States
MENU, BUY_PACK, WAIT_RECEIPT, SETTINGS = range(4)


# 1. DATABASE LOGIC

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def get_credits(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE user_id=?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else 0

def add_credits(user_id, amount):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, credits) VALUES (?, 0)", (user_id,))
    c.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()


# 2. PDF & ID LOGIC (Preserving your exact extraction)

def get_next_serial_number():
    return f"{random.randint(10_000_00, 99_999_99)}"

def extract_data_from_pdf(pdf_path, user_id, keep_background=False):
    if not os.path.exists(pdf_path): return None
    doc = fitz.open(pdf_path)
    page = doc[0]

    paths = {'photo': f"photo_{user_id}.png", 'qr': f"qr_{user_id}.png", 
             'fin': f"fin_{user_id}.png"}

    image_list = page.get_images(full=True)
    for i, img in enumerate(image_list):
        xref = img[0]
        pix = fitz.Pixmap(doc, xref)
        if pix.n - pix.alpha > 3: pix = fitz.Pixmap(fitz.csRGB, pix)
        
        if i == 0:
            img_data = pix.tobytes("png")
            raw_image = Image.open(io.BytesIO(img_data)).convert("RGBA")
            if keep_background:
                raw_image = feather_upper_half(raw_image)
                raw_image.save(paths['photo'])
            else:
                output_image = remove(
                    raw_image,
                    session=REMBG_SESSION,
                    alpha_matting=False,
                    post_process_mask=True,
                )
                output_image.save(paths['photo'])
        elif i == 1:
            pix.save(paths['qr'])

    page.get_pixmap(clip=fitz.Rect(496.5, 493, 540, 501), matrix=fitz.Matrix(4, 4)).save(paths['fin'])
    
    text = page.get_text("text")
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    now = datetime.now()
    eth_now = EthiopianDateConverter.to_ethiopian(now.year, now.month, now.day)
    
    data = {
        'name_amh': lines[57] if len(lines) > 57 else "Unknown",
        'name_eng': lines[58] if len(lines) > 58 else "Unknown",
        'dob': f"{lines[43]} | {lines[44]}" if len(lines) > 44 else "Unknown",
        'sex': f"{lines[45]} | {lines[46]}" if len(lines) > 46 else "Unknown",
        'fan': "Unknown", 'sn': get_next_serial_number(),
        'phone': lines[49] if len(lines) > 49 else "",
        'address': lines[50:56],
        'expiry': f"{now.day:02d}/{now.month:02d}/{now.year+10} | {eth_now.day:02d}/{eth_now.month:02d}/{eth_now.year+10}"
    }
    for line in lines:
        clean = line.replace(" ", "")
        fan_match = re.search(r'(\d{16})', clean)
        if fan_match: data['fan'] = fan_match.group(1)
    doc.close()
    return data

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


def feather_upper_half(image, feather_strength=150):
    image = image.convert("RGBA")
    width, height = image.size
    _, _, _, alpha = image.split()
    gradient = Image.new("L", (1, height), color=255)
    for y in range(height):
        if y < height // 2:
            fade = 1.0 - ((height // 2 - y) / float(height // 2))
            alpha_value = int(255 - (feather_strength * (1.0 - fade)))
            gradient.putpixel((0, y), max(0, min(255, alpha_value)))
        else:
            gradient.putpixel((0, y), 255)
    gradient = gradient.resize((width, height))
    alpha = ImageChops.multiply(alpha, gradient)
    image.putalpha(alpha)
    return image


def generate_fayda_v3(data, output_path, user_id, mode="color", template_path=None, qr_size=None, flip=True):
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

    # Photo Logic
    photo_path = f"photo_{user_id}.png"
    if os.path.exists(photo_path):
        raw_photo = Image.open(photo_path).convert("RGBA")
        if mode == "bw":
            r, g, b, alpha = raw_photo.split()
            gray = raw_photo.convert("L")
            raw_photo = Image.merge("RGBA", (gray, gray, gray, alpha))

        # Apply bilateral smoothing to the alpha mask to preserve sharpness while smoothing edges.
        photo_resized = raw_photo.resize((330, 370))
        r, g, b, alpha = photo_resized.split()
        alpha = bilateral_alpha_blur(alpha, diameter=15, sigma_color=50, sigma_space=50)
        photo_resized = Image.merge("RGBA", (r, g, b, alpha))
        canvas.paste(photo_resized, (62, 180), photo_resized)

        ghost = raw_photo.resize((110, 130))
        r_g, g_g, b_g, alpha_g = ghost.split()
        alpha_g = bilateral_alpha_blur(alpha_g, diameter=11, sigma_color=40, sigma_space=40)
        ghost = Image.merge("RGBA", (r_g, g_g, b_g, alpha_g))
        canvas.paste(ghost, (850, 480), ghost)

    # Assets (QR, Fingerprint)
    # Set QR size to 4.15 cm square (convert to pixels at 300 DPI)
    qr_cm = 4.15
    dpi = 300
    qr_size_var = int(round((qr_cm / 2.54) * dpi))
    assets = [(f"qr_{user_id}.png", (qr_size_var, qr_size_var), (1520, 60)), (f"fin_{user_id}.png", (240, 50), (1170, 508))]
    for asset, size, pos in assets:
        if os.path.exists(asset):
            img = Image.open(asset).resize(size).convert("RGBA")
            canvas.paste(img, pos, img)

    # Main Text Overlay
    text_x = 402
    draw.text((text_x, 177), data['name_amh'], font=f_amh, fill="black")
    draw.text((text_x, 219), data['name_eng'], font=f_bold, fill="black")
    draw.text((text_x, 304), data['dob'], font=f_bold, fill="black")
    draw.text((text_x, 370), data['sex'], font=f_amh, fill="black")
    draw.text((text_x, 440), data['expiry'], font=f_bold, fill="black")
    draw.text((470, 490), data['fan'], font=f_bold, fill="black")
    draw.text((canvas.width - 180, canvas.height - 56), data['sn'], font=f_bold, fill="black")

    back_x, y_addr = (canvas.width // 2) + 26, 234
    draw.text((back_x, 71), data['phone'], font=f_bold, fill="black")
    for line in data['address']:
        draw.text((back_x, y_addr), line, font=f_amh, fill="black")
        y_addr += 40

    # Flip the final composed output when requested
    if flip:
        canvas = canvas.transpose(Image.FLIP_LEFT_RIGHT)

    # Save as PNG
    rgb = canvas.convert("RGB")
    rgb.save(output_path, "PNG")
    return True

# ==========================================
# 3. UI HELPERS
# ==========================================
def main_menu_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🖨️ Print ID")],
        [KeyboardButton("💳 Buy Pack")],
        [KeyboardButton("🔑 FAN/FIN")],
        [KeyboardButton("📞 Help")],
        [KeyboardButton("🏠 Start")]
    ], resize_keyboard=True, one_time_keyboard=False, selective=False)

def package_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("40 birr = 1", callback_data='pkg_1')],
        [InlineKeyboardButton("500 birr = 25", callback_data='pkg_20')],
        [InlineKeyboardButton("1500 birr = 100", callback_data='pkg_100')],
        [InlineKeyboardButton("2000 birr = 155", callback_data='pkg_150')],
        [InlineKeyboardButton("Cancel", callback_data='cancel')]
    ])

def navigation_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Back", callback_data='back_main'), InlineKeyboardButton("Cancel", callback_data='cancel')]
    ])

def get_available_templates():
    candidates = [
        "fayda.jpg", "Fayda.jpg", "faydatemplate1.jpg", "faydatemplate1.png",
        "Templet2.png", "Templet2.jpg"
    ]
    return [path for path in candidates if os.path.exists(path)]


def template_label(template_choice):
    if not template_choice:
        return "Default"
    templates = get_available_templates()
    if template_choice in templates:
        return f"Template {templates.index(template_choice) + 1}"
    return os.path.basename(template_choice)


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    current_tpl = template_label(context.user_data.get('template_choice'))
    current_mode = context.user_data.get('output_mode', 'color')
    current_orientation = context.user_data.get('orientation', 'flip')
    current_bg = context.user_data.get('background_mode', 'remove')
    current_auto = context.user_data.get('auto_destroy', 'on')
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Template", callback_data='set_template'), InlineKeyboardButton("BG", callback_data='set_bg')],
        [InlineKeyboardButton("Orientation", callback_data='set_orientation'), InlineKeyboardButton("Auto Destroy", callback_data='set_auto_destroy')],
        [InlineKeyboardButton("Mode", callback_data='set_mode'), InlineKeyboardButton("Back", callback_data='back_main')]
    ])
    await update.message.reply_text(
        f"Settings\nTemplate: {current_tpl}\nOrientation: {current_orientation}\nBG: {current_bg}\nAuto Destroy: {current_auto}\nMode: {current_mode}",
        reply_markup=kb
    )
    return SETTINGS


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'set_template':
        templates = get_available_templates()
        buttons = [[InlineKeyboardButton(f"Template {i + 1}", callback_data=f"tpl:{tmpl}")] for i, tmpl in enumerate(templates)]
        if not buttons:
            await query.edit_message_text("No templates found in the working directory.")
            return
        buttons.append([InlineKeyboardButton("Back", callback_data='back_main'), InlineKeyboardButton("Cancel", callback_data='cancel')])
        await query.edit_message_text("Choose a template:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith('tpl:'):
        chosen = data.split(':', 1)[1]
        context.user_data['template_choice'] = chosen
        await query.edit_message_text(f"Template set to {template_label(chosen)}", reply_markup=navigation_keyboard())
        return

    if data == 'set_orientation':
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Normal", callback_data='orient:normal')],
            [InlineKeyboardButton("Flipped", callback_data='orient:flip')],
            [InlineKeyboardButton("Back", callback_data='back_main'), InlineKeyboardButton("Cancel", callback_data='cancel')]
        ])
        await query.edit_message_text("Choose orientation:", reply_markup=kb)
        return

    if data.startswith('orient:'):
        val = data.split(':', 1)[1]
        if val in ['normal', 'flip']:
            context.user_data['orientation'] = val
            await query.edit_message_text(f"Orientation set to {val}", reply_markup=navigation_keyboard())
        else:
            await query.edit_message_text("Invalid orientation", reply_markup=navigation_keyboard())
        return

    if data == 'set_bg':
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Keep", callback_data='bg:keep')],
            [InlineKeyboardButton("Remove", callback_data='bg:remove')],
            [InlineKeyboardButton("Back", callback_data='back_main'), InlineKeyboardButton("Cancel", callback_data='cancel')]
        ])
        await query.edit_message_text("Photo background:", reply_markup=kb)
        return

    if data.startswith('bg:'):
        val = data.split(':', 1)[1]
        if val in ['keep', 'remove']:
            context.user_data['background_mode'] = val
            await query.edit_message_text(f"Background mode set to {val}", reply_markup=navigation_keyboard())
        else:
            await query.edit_message_text("Invalid background mode", reply_markup=navigation_keyboard())
        return

    if data == 'set_auto_destroy':
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("On", callback_data='auto_destroy:on')],
            [InlineKeyboardButton("Off", callback_data='auto_destroy:off')],
            [InlineKeyboardButton("Back", callback_data='back_main'), InlineKeyboardButton("Cancel", callback_data='cancel')]
        ])
        await query.edit_message_text("Auto destroy:", reply_markup=kb)
        return

    if data.startswith('auto_destroy:'):
        val = data.split(':', 1)[1]
        if val in ['on', 'off']:
            context.user_data['auto_destroy'] = val
            await query.edit_message_text(f"Auto destroy set to {val}", reply_markup=navigation_keyboard())
        else:
            await query.edit_message_text("Invalid auto destroy value", reply_markup=navigation_keyboard())
        return

    if data == 'set_mode':
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Color", callback_data='mode:color')],
            [InlineKeyboardButton("B/W", callback_data='mode:bw')],
            [InlineKeyboardButton("Back", callback_data='back_main'), InlineKeyboardButton("Cancel", callback_data='cancel')]
        ])
        await query.edit_message_text("Choose output mode:", reply_markup=kb)
        return

    if data.startswith('mode:'):
        val = data.split(':', 1)[1]
        if val in ['color', 'bw']:
            context.user_data['output_mode'] = val
            await query.edit_message_text(f"Output mode set to {val}", reply_markup=navigation_keyboard())
        else:
            await query.edit_message_text("Invalid mode", reply_markup=navigation_keyboard())
        return

    if data == 'back_main':
        await query.edit_message_text("Back to main menu.", reply_markup=main_menu_keyboard())
        return

    if data == 'cancel':
        context.user_data.pop('fan_flow', None)
        context.user_data.pop('otp_flow', None)
        context.user_data.pop('pending_receipt', None)
        await query.edit_message_text("Cancelled. Back to menu.", reply_markup=main_menu_keyboard())
        return


# 4. BOT HANDLERS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    credits = get_credits(user_id)
    welcome = (
        "Welcome to Fayda ID Converter! 🎉\n"
        "Send your FAYDA PDF or use 🔑 FAN/FIN.\n"
        "Tap a button below to begin.\n\n"
        f"💰 Balance: {credits} packages"
    )
    await update.message.reply_text(welcome, reply_markup=main_menu_keyboard())
    return MENU

async def button_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'buy_package':
        context.user_data.pop('fan_flow', None)
        context.user_data['pending_receipt'] = True
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Select a package below 👇", reply_markup=package_keyboard())
        return BUY_PACK
    elif query.data == 'print_id':
        context.user_data.pop('fan_flow', None)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Send your FAYDA PDF.", reply_markup=main_menu_keyboard())
        return MENU
    elif query.data == 'fan_flow':
        context.user_data['fan_flow'] = True
        context.user_data.pop('pending_receipt', None)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Send FAN or FIN (12-16 digits).", reply_markup=main_menu_keyboard())
        return MENU
    elif query.data == 'settings':
        current_tpl = template_label(context.user_data.get('template_choice'))
        current_mode = context.user_data.get('output_mode', 'color')
        current_orientation = context.user_data.get('orientation', 'flip')
        current_bg = context.user_data.get('background_mode', 'remove')
        current_auto = context.user_data.get('auto_destroy', 'on')
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Template", callback_data='set_template'), InlineKeyboardButton("BG", callback_data='set_bg')],
            [InlineKeyboardButton("Orientation", callback_data='set_orientation'), InlineKeyboardButton("Auto Destroy", callback_data='set_auto_destroy')],
            [InlineKeyboardButton("Mode", callback_data='set_mode'), InlineKeyboardButton("Back", callback_data='back_main')]
        ])
        await query.edit_message_text(
            f"Settings\nTemplate: {current_tpl}\nOrientation: {current_orientation}\nBG: {current_bg}\nAuto Destroy: {current_auto}\nMode: {current_mode}",
            reply_markup=kb
        )
        return SETTINGS
    elif query.data == 'contact_help':
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Get support on @globalformfiller", reply_markup=main_menu_keyboard())
        return MENU
    elif query.data == 'cancel':
        context.user_data.pop('fan_flow', None)
        context.user_data.pop('otp_flow', None)
        context.user_data.pop('pending_receipt', None)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Cancelled. Back to menu.", reply_markup=main_menu_keyboard())
        return MENU
    elif query.data == 'delete_output':
        await query.answer("Output buttons cleared")
        await query.edit_message_reply_markup(reply_markup=None)
        return MENU

async def select_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pkg_map = {'pkg_1': '1', 'pkg_20': '20', 'pkg_100': '100', 'pkg_150': '150'}
    context.user_data['pending_pkg'] = pkg_map[query.data]
    context.user_data['pending_receipt'] = True
    await query.edit_message_text(f"Pay to **{TELEBIRR_NUMBER}** and send the receipt.")
    return WAIT_RECEIPT

async def handle_main_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🖨️ Print ID":
        context.user_data.pop('fan_flow', None)
        await update.message.reply_text("Send your FAYDA PDF.", reply_markup=main_menu_keyboard())
        return MENU
    elif text == "💳 Buy Pack":
        context.user_data.pop('fan_flow', None)
        context.user_data['pending_receipt'] = True
        await update.message.reply_text("Select a package below 👇", reply_markup=package_keyboard())
        return BUY_PACK
    elif text == "🔑 FAN/FIN":
        context.user_data['fan_flow'] = True
        context.user_data.pop('pending_receipt', None)
        await update.message.reply_text("Send FAN or FIN (12-16 digits).", reply_markup=main_menu_keyboard())
        return MENU
    elif text == "📞 Help":
        await update.message.reply_text("Get support on @globalformfiller", reply_markup=main_menu_keyboard())
        return MENU
    elif text == "🏠 Start":
        return await start(update, context)
    return

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('pending_receipt'):
        await update.message.reply_text("Select a package first, then send the receipt.")
        return MENU

    user = update.message.from_user
    
    user_name = f"@{user.username}" if user.username else user.first_name
    admin_msg = (
        f"🔔 New Payment\n"
        f"👤 User: {user_name}\n"
        f"🆔 ID: {user.id}\n"
        f"📦 Pkg: {context.user_data.get('pending_pkg')}\n\n"
        f"📝 SMS Receipt:\n{update.message.text}"
    )
    
    btns = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"appr_{user.id}_{context.user_data.get('pending_pkg')}"), 
        InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user.id}")
    ]])
    
    context.user_data.pop('pending_receipt', None)
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=btns)
    await update.message.reply_text("Receipt sent for approval.")
    return MENU

async def admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    if data[0] == "appr":
        add_credits(int(data[1]), int(data[2]))
        await context.bot.send_message(chat_id=int(data[1]), text="✅ Payment Approved!")
        await query.edit_message_text("✅ Approved")
    elif data[0] == "rej":
        await context.bot.send_message(chat_id=int(data[1]), text="❌ Payment Rejected")
        await query.edit_message_text("❌ Rejected")
    else:
        await query.edit_message_text("Done.")

def create_fayda_session(fan: str):
    headers = {"x-api-key": FAYDA_API_KEY}
    payload = {"individualId": fan}
    return requests.post(
        f"{FAYDA_API_BASE}/api/session",
        json=payload,
        headers=headers,
        timeout=20,
    )

def verify_fayda_session(session_id: str, otp: str):
    headers = {"x-api-key": FAYDA_API_KEY}
    payload = {"otp": otp, "format": "pdf"}
    return requests.post(
        f"{FAYDA_API_BASE}/api/session/{session_id}/verify",
        json=payload,
        headers=headers,
        timeout=20,
    )

async def handle_fan_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('fan_flow'):
        return

    fan = update.message.text.strip()
    if not re.fullmatch(r"\d{12,16}", fan):
        await update.message.reply_text("Send a valid FAN or FIN number (12-16 digits).")
        return

    await update.message.reply_text("⏳ Requesting OTP for your FAN/FIN...")
    try:
        response = await asyncio.to_thread(create_fayda_session, fan)
    except requests.exceptions.RequestException as exc:
        await update.message.reply_text("⚠️ Could not contact Fayda API. Please try again later.")
        print(f"Fayda session request failed: {exc}")
        return

    if response.status_code != 200:
        error_text = response.text or response.reason
        await update.message.reply_text(f"⚠️ Failed to start session: {error_text}")
        return

    try:
        data = response.json()
    except ValueError:
        await update.message.reply_text("⚠️ Invalid response from Fayda API. Please try again.")
        print(f"Invalid JSON from Fayda session response: {response.text}")
        return

    session_id = data.get("sessionId") or data.get("session_id") or data.get("id")
    masked = data.get("maskedMobile") or data.get("masked_mobile") or data.get("maskedPhone")
    if not session_id:
        await update.message.reply_text("⚠️ Could not start session. Please try again.")
        print(f"Missing sessionId in Fayda response: {data}")
        return

    context.user_data['fan_flow'] = False
    context.user_data['otp_flow'] = True
    context.user_data['fayda_session_id'] = session_id
    await update.message.reply_text(f"✅ OTP sent to {masked or 'your registered phone'}. Please send the OTP code now.")

async def handle_otp_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('otp_flow'):
        return

    otp = update.message.text.strip()
    if not re.fullmatch(r"\d{4,6}", otp):
        await update.message.reply_text("Send the OTP (4-6 digits).")
        return

    session_id = context.user_data.get('fayda_session_id')
    if not session_id:
        await update.message.reply_text("Session expired. Start again with FAN/FIN.")
        context.user_data.pop('otp_flow', None)
        return

    await update.message.reply_text("⏳ Verifying OTP and downloading PDF...")
    try:
        response = await asyncio.to_thread(verify_fayda_session, session_id, otp)
    except requests.exceptions.RequestException as exc:
        await update.message.reply_text("⚠️ Could not contact Fayda API. Please try again later.")
        print(f"Fayda verify request failed: {exc}")
        return

    if response.status_code != 200:
        error_text = response.text or response.reason
        await update.message.reply_text(f"⚠️ Verification failed: {error_text}")
        return

    pdf_path = f"fayda_{update.message.from_user.id}.pdf"
    with open(pdf_path, "wb") as f:
        f.write(response.content)

    out_path = None
    try:
        keep_bg = context.user_data.get('background_mode', 'remove') == 'keep'
        data = await asyncio.to_thread(extract_data_from_pdf, pdf_path, update.message.from_user.id, keep_background=keep_bg)
        if data:
            user_template = context.user_data.get('template_choice')
            user_mode = context.user_data.get('output_mode', 'color')
            out_path = f"{user_mode}_{update.message.from_user.id}.png"
            user_flip = context.user_data.get('orientation', 'flip') == 'flip'
            await asyncio.to_thread(generate_fayda_v3, data, out_path, update.message.from_user.id, user_mode, template_path=user_template, flip=user_flip)
            await update.message.reply_text("✅ Success! Your ID is ready.", reply_markup=main_menu_keyboard())
            with open(out_path, 'rb') as f:
                filename = "Fayda_Color.png" if user_mode == 'color' else "Fayda_BW.png"
                doc_message = await update.message.reply_document(f, filename=filename, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Clear Buttons", callback_data='delete_output')]]))
            if context.user_data.get('auto_destroy', 'on') == 'on':
                asyncio.create_task(auto_delete_message(context.bot, update.message.chat_id, doc_message.message_id, delay=60))
        else:
            await update.message.reply_text("❌ Extraction failed.")
    finally:
        for fpath in [pdf_path, out_path or "", f"photo_{update.message.from_user.id}.png", f"qr_{update.message.from_user.id}.png", f"fin_{update.message.from_user.id}.png"]:
            if fpath and os.path.exists(fpath):
                os.remove(fpath)
        context.user_data.pop('otp_flow', None)
        context.user_data.pop('fayda_session_id', None)


# 5. INTEGRATED PDF HANDLER

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    msg = await update.message.reply_text("⏳ Processing...")
    pdf_path = f"input_{user_id}.pdf"
    file = await context.bot.get_file(update.message.document.file_id)
    await file.download_to_drive(pdf_path)

    try:
        keep_bg = context.user_data.get('background_mode', 'remove') == 'keep'
        data = await asyncio.to_thread(extract_data_from_pdf, pdf_path, user_id, keep_background=keep_bg)
        
        if data:
            user_template = context.user_data.get('template_choice')
            user_mode = context.user_data.get('output_mode', 'color')
            out_path = f"{user_mode}_{user_id}.png"

            user_flip = context.user_data.get('orientation', 'flip') == 'flip'
            await asyncio.to_thread(generate_fayda_v3, data, out_path, user_id, user_mode, template_path=user_template, flip=user_flip)
            await msg.edit_text("✅ Success! Your ID is ready.")
            with open(out_path, 'rb') as f:
                filename = "Fayda_Color.png" if user_mode == 'color' else "Fayda_BW.png"
                doc_message = await update.message.reply_document(f, filename=filename, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Clear Buttons", callback_data='delete_output')]]))
            if context.user_data.get('auto_destroy', 'on') == 'on':
                asyncio.create_task(auto_delete_message(context.bot, update.message.chat_id, doc_message.message_id, delay=60))
        else:
            await msg.edit_text("❌ Extraction failed.")
    finally:
        for f in [pdf_path, f"{context.user_data.get('output_mode', 'color')}_{user_id}.png", f"photo_{user_id}.png", f"qr_{user_id}.png", f"fin_{user_id}.png"]:
            if os.path.exists(f): os.remove(f)




# ADD THIS NEW BLOCK
# 1. Initialize Database and Bot (OUTSIDE the main block)
init_db()

# Initialize the Telegram App globally so Flask can see it
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Define Handlers
app.add_handler(CommandHandler('start', start))
app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
app.add_handler(CallbackQueryHandler(button_tap, pattern='^(buy_package|print_id|contact_help|fan_flow|settings|cancel|delete_output)$'))
app.add_handler(CallbackQueryHandler(select_package, pattern="^(pkg_1|pkg_20|pkg_100|pkg_150)$"))
app.add_handler(CallbackQueryHandler(admin_approval, pattern="^(appr|rej)_"))
app.add_handler(CommandHandler('settings', settings_cmd))
app.add_handler(CallbackQueryHandler(settings_callback, pattern="^(set_template|set_orientation|set_bg|set_auto_destroy|set_mode|back_main|cancel|tpl:.*|orient:.*|bg:.*|auto_destroy:.*|mode:.*)$"))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^(🖨️ Print ID|💳 Buy Pack|🔑 FAN/FIN|📞 Help|🏠 Start)$'), handle_main_keyboard))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^[0-9]{12,16}$'), handle_fan_input))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^[0-9]{4,6}$'), handle_otp_input))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_receipt))

# 2. Add a helper to start the bot's background processes
async def initialize_bot():
    await app.initialize()
    await app.start()

async def auto_delete_message(bot, chat_id, message_id, delay=60):
    await asyncio.sleep(delay)
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
    except Exception:
        pass

async def setup_webhook():
    URL = os.environ.get("RENDER_EXTERNAL_URL")
    if URL:
        await initialize_bot()
        await app.bot.set_webhook(url=f"{URL}/webhook")
        print(f"🚀 Webhook set to {URL}/webhook")

# This logic runs when Gunicorn starts
import asyncio

if os.environ.get("RENDER_EXTERNAL_URL"):
    def _webhook_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(setup_webhook())
    import threading
    threading.Thread(target=_webhook_thread, daemon=True).start()

# 3. Keep the main block ONLY for local testing (VS Code)
if __name__ == "__main__":
    URL = os.environ.get("RENDER_EXTERNAL_URL")
    if not URL:
        print("🚀 Local Mode: Polling")
        app.run_polling()
