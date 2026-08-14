import sqlite3
import fitz
import os
from flask import Flask, request  # Add this
import re
import io
import asyncio
from datetime import datetime
from rembg import remove, new_session
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from ethiopian_date import EthiopianDateConverter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# CONFIGURATION 
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1032772516"))
TELEBIRR_NUMBER = os.environ.get("TELEBIRR_NUMBER", "0946140878")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")
# ADD THIS LINE:
REMBG_SESSION = new_session()

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
MENU, BUY_PACK, WAIT_RECEIPT, SETTINGS, BATCH_MODE = range(5)


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
    filename = "serial_counter.txt"
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            f.write("0000000")
            return "6000000"
    with open(filename, "r") as f:
        content = f.read().strip()
        current_sn = int(content) if content else 7000000
    next_sn = current_sn + 1
    with open(filename, "w") as f:
        f.write(str(next_sn))
    return str(next_sn)

def extract_data_from_pdf(pdf_path, user_id):
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
            output_image = remove(Image.open(io.BytesIO(img_data)), session=REMBG_SESSION)
            output_image.save(paths['photo'])
        elif i == 1: pix.save(paths['qr'])

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


def generate_fayda_v3(data, output_path, user_id, mode="color", template_path=None, qr_size=None):
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

    # Flip the final composed output for all generated images
    canvas = canvas.transpose(Image.FLIP_LEFT_RIGHT)

    # Save as PDF if filename extension requests it, otherwise default to PNG
    # Save output as PNG
    rgb = canvas.convert("RGB")
    rgb.save(output_path, "PNG")
    return True

def arrange_cards_on_a4(card_paths, output_path, num_cards=5):
    """
    Arrange ID cards (2-5) on one A4 page with proper cutting gaps.
    
    Layout:
    - A4: 2480 × 3508 px (210mm × 297mm at 300 DPI)
    - Cards: 1000 × 640 px each (aspect ratio 1.57:1 preserved)
    - Cutting gaps: 40 px between each card (white space for cutting)
    - Cards are vertically arranged, one per row, centered horizontally
    - Supports 2, 3, 4, or 5 cards per page
    """
    # A4 dimensions at 300 DPI: 2480 x 3508 pixels
    a4_width, a4_height = 2480, 3508
    a4_canvas = Image.new("RGB", (a4_width, a4_height), color="white")
    
    # Validate num_cards
    num_cards = max(2, min(5, num_cards))  # Ensure between 2-5
    
    # Card dimensions with aspect ratio 1.57:1
    card_width, card_height = 1000, 640
    
    # Cutting gap between cards (white space for easy cutting)
    cutting_gap = 40  # pixels
    
    # Calculate optimal margins based on number of cards
    # Total height needed: margin_top + (num_cards * card_height) + ((num_cards-1) * cutting_gap) + margin_bottom
    total_card_height = (num_cards * card_height) + ((num_cards - 1) * cutting_gap)
    total_margin = a4_height - total_card_height
    margin_top = max(50, total_margin // 3)  # Top third of remaining space
    margin_bottom = a4_height - margin_top - total_card_height
    
    # Calculate horizontal center position
    center_x = (a4_width - card_width) // 2
    
    # Calculate vertical positions
    current_y = margin_top
    positions = []
    for i in range(num_cards):
        positions.append((center_x, current_y))
        current_y += card_height + cutting_gap
    
    # Paste cards onto A4 canvas
    for i, card_path in enumerate(card_paths[:num_cards]):
        if i < len(positions) and os.path.exists(card_path):
            try:
                card_img = Image.open(card_path).convert("RGB")
                
                # Resize card proportionally to fit target dimensions while preserving aspect ratio
                original_aspect = card_img.width / card_img.height
                target_aspect = card_width / card_height
                
                if original_aspect > target_aspect:
                    # Image is wider - scale by height
                    scale = card_height / card_img.height
                else:
                    # Image is taller - scale by width
                    scale = card_width / card_img.width
                
                new_width = int(card_img.width * scale)
                new_height = int(card_img.height * scale)
                card_img_resized = card_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Center the resized card on the target area
                offset_x = (card_width - new_width) // 2
                offset_y = (card_height - new_height) // 2
                
                x, y = positions[i]
                a4_canvas.paste(card_img_resized, (x + offset_x, y + offset_y))
            except Exception as e:
                print(f"Error pasting card {i}: {e}")
    
    # Save as high-quality PNG
    a4_canvas.save(output_path, "PNG", quality=95)
    return True

def arrange_5_cards_on_a4(card_paths, output_path):
    """Backward compatibility wrapper for 5 cards"""
    return arrange_cards_on_a4(card_paths, output_path, num_cards=5)

# ==========================================
# 3. UI HELPERS - INLINE & REPLY KEYBOARDS
# ==========================================

# INLINE KEYBOARDS (Edit-able buttons)
def main_menu_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🖨 Print ID", callback_data='print_id')],
                                 [InlineKeyboardButton("💳 Buy Package", callback_data='buy_package')],
                                 [InlineKeyboardButton("📞 Contact Help", callback_data='contact_help')]])

def package_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("40 birr = 1 package", callback_data='pkg_1')],
                                 [InlineKeyboardButton("500 birr = 25 packages", callback_data='pkg_20')],
                                 [InlineKeyboardButton("1500 birr = 100 packages", callback_data='pkg_100')],
                                 [InlineKeyboardButton("2000 birr = 155 packages", callback_data='pkg_150')]])

# REPLY KEYBOARDS (persistent buttons for quick access)
def main_menu_reply_keyboard():
    """Quick access reply buttons for main menu"""
    return ReplyKeyboardMarkup([
        [KeyboardButton("🖨 Print ID"), KeyboardButton("� Batch (5x A4)")],
        [KeyboardButton("⚙️ Settings"), KeyboardButton("📞 Help")],
        [KeyboardButton("💰 Balance")]
    ], resize_keyboard=True, one_time_keyboard=False)
def print_now_keyboard():
    """Inline keyboard with Print Now button"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🖨️ Print Now", callback_data="print_now")]
    ])

def batch_card_count_keyboard():
    """Keyboard to select number of cards per A4 page"""
    return ReplyKeyboardMarkup([
        [KeyboardButton("2️⃣ 2 Cards per A4"), KeyboardButton("3️⃣ 3 Cards per A4")],
        [KeyboardButton("4️⃣ 4 Cards per A4"), KeyboardButton("5️⃣ 5 Cards per A4")],
        [KeyboardButton("❌ Cancel")]
    ], resize_keyboard=True, one_time_keyboard=True)
def cancel_keyboard():
    """Quick cancel button"""
    return ReplyKeyboardMarkup([
        [KeyboardButton("❌ Cancel")]
    ], resize_keyboard=True, one_time_keyboard=True)

def confirm_keyboard():
    """Confirm/Cancel buttons"""
    return ReplyKeyboardMarkup([
        [KeyboardButton("✅ Confirm"), KeyboardButton("❌ Cancel")]
    ], resize_keyboard=True, one_time_keyboard=True)

def remove_keyboard():
    """Remove all reply keyboards"""
    return ReplyKeyboardRemove()


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display settings menu from /settings command"""
    user_id = update.message.from_user.id
    current_tpl = context.user_data.get('template_choice', 'default')
    current_mode = context.user_data.get('output_mode', 'color')
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Template Choice", callback_data='set_template')],
        [InlineKeyboardButton("Output Mode", callback_data='set_mode')],
        [InlineKeyboardButton("Back", callback_data='back_main')]
    ])
    settings_text = (
        f"⚙️ **Settings**\n\n"
        f"📋 Template: `{current_tpl}`\n"
        f"🎨 Output Mode: `{current_mode}`\n\n"
        f"Choose an option below:"
    )
    await update.message.reply_text(settings_text, reply_markup=kb, parse_mode="Markdown")
    return SETTINGS

async def show_settings_menu(query, context: ContextTypes.DEFAULT_TYPE):
    """Display settings menu from callback query"""
    current_tpl = context.user_data.get('template_choice', 'default')
    current_mode = context.user_data.get('output_mode', 'color')
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Template Choice", callback_data='set_template')],
        [InlineKeyboardButton("Output Mode", callback_data='set_mode')],
        [InlineKeyboardButton("Back", callback_data='back_main')]
    ])
    settings_text = (
        f"⚙️ **Settings**\n\n"
        f"📋 Template: `{current_tpl}`\n"
        f"🎨 Output Mode: `{current_mode}`\n\n"
        f"Choose an option below:"
    )
    await query.edit_message_text(settings_text, reply_markup=kb, parse_mode="Markdown")


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    # Show template options
    if data == 'set_template':
        candidates = ["fayda.jpg", "Fayda.jpg", "faydatemplate1.jpg", "faydatemplate1.png", "Templet2.png", "Templet2.jpg"]
        buttons = [[InlineKeyboardButton(os.path.basename(c), callback_data=f"tpl:{os.path.basename(c)}")] for c in candidates if os.path.exists(c)]
        buttons.append([InlineKeyboardButton("Back", callback_data='back_settings')])
        if not buttons:
            await query.edit_message_text("No templates found in the working directory.")
            return
        await query.edit_message_text("📋 Choose a template:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        return
    if data.startswith('tpl:'):
        chosen = data.split(':', 1)[1]
        context.user_data['template_choice'] = chosen
        await query.edit_message_text(f"✅ Template set to `{chosen}`", parse_mode="Markdown")
        await asyncio.sleep(1)
        await show_settings_menu(query, context)
        return
    # Output mode options
    if data == 'set_mode':
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Color", callback_data='mode:color')],
            [InlineKeyboardButton("B/W", callback_data='mode:bw')],
            [InlineKeyboardButton("Back", callback_data='back_settings')]
        ])
        await query.edit_message_text("🎨 Choose output mode:", reply_markup=kb, parse_mode="Markdown")
        return
    if data.startswith('mode:'):
        val = data.split(':', 1)[1]
        if val in ['color', 'bw']:
            context.user_data['output_mode'] = val
            await query.edit_message_text(f"✅ Output mode set to `{val}`", parse_mode="Markdown")
            await asyncio.sleep(1)
            await show_settings_menu(query, context)
        else:
            await query.edit_message_text("Invalid mode")
        return
    if data == 'back_settings':
        await show_settings_menu(query, context)
        return
    if data == 'back_main':
        await query.edit_message_text("Back to main menu.", reply_markup=main_menu_keyboard())
        return MENU


# 4. BOT HANDLERS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    credits = get_credits(user_id)
    welcome = (
        "Welcome to the National ID Fayda Printable Converter Service! 🎉\n\n"
        "📑 **To get your printable ID card:**\n"
        "1. Download the FAYDA ID pdf from FAYDA app  OR Telebirr \n"
        "2. Send the downloaded PDF file here to this bot.\n\n"
        "እንኳን ወደ ብሔራዊ መታወቂያ ፋይዳ ካርድ ሊታተም የሚችል መቀየሪያ አገልግሎት በደህና መጡ! 🎉\n"
        "🪪 ሊታተም የሚችል መታወቂያ ካርድዎን ለማግኘት፡-\n"
       "1. የFAYDA መታወቂያ ፒዲኤፍ ከFAYDA መተግበሪያ ወይም ከTelebirr ያውርዱ \n"
       "2. የወረደውን የፒዲኤፍ ፋይል ወደዚህ ቦት ይላኩ።\n\n"
       "Baga Gara Tajaajila Jijjiirraa Maxxanfamuu Danda'u FAYDA Eenyummaa Biyyaalessaatti dhuftan! 🎉\n\n" 
"📑 NATIONAL ID  maxxanfamuu danda'u argachuuf:**\n" 
"1. ID FAYDA pdf appii FAYDA YKN Telebirr irraa buufadhaa \n" 
"2. Faayila PDF buufame as gara bot kanaatti ergi.\n\n"
        f"💰 **Your Balance:** {credits} packages"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown", reply_markup=main_menu_reply_keyboard())
    return MENU

async def button_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == 'buy_package':
        if user_id == ADMIN_ID:
            await query.edit_message_text(
                "✅ **Admin - Free Access**\n\n"
                "You have unlimited free access to print ID cards.\n\n"
                "🎉 No packages needed!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data='back_main')]])
            )
        else:
            await query.edit_message_text(
                "💳 **Payment Coming Soon**\n\n"
                "Telebirr and Bank payment integration is coming very soon!\n\n"
                "Thank you for your patience.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data='back_main')]])
            )
        return MENU
    elif query.data == 'print_id':
        await query.message.reply_text("📄 Please send your Fayda PDF file now.", reply_markup=cancel_keyboard())
        return MENU
    elif query.data == 'contact_help':
        await query.edit_message_text("📞 **Support Information**\n\nFor assistance, contact: @altleg\n\nResponse time: Usually within 24 hours", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data='back_main')]]))
        return MENU

async def handle_reply_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reply keyboard button presses"""
    text = update.message.text
    user_id = update.message.from_user.id
    
    if text == "🖨 Print ID":
        await update.message.reply_text("📄 Please send your Fayda PDF file now.", reply_markup=cancel_keyboard())
        return MENU
    elif text == "� Batch (5x A4)":
        if user_id != ADMIN_ID:
            await update.message.reply_text(
                "🔒 **Service Coming Soon**\n\n"
                "Batch processing available only in beta.",
                parse_mode="Markdown",
                reply_markup=main_menu_reply_keyboard()
            )
            return MENU
        
        await update.message.reply_text(
            "📋 **How many ID cards per A4 page?**\n\n"
            "Select 2, 3, 4, or 5 cards to print on a single A4 page.",
            parse_mode="Markdown",
            reply_markup=batch_card_count_keyboard()
        )
        return BATCH_MODE
    elif text == "⚙️ Settings":
        await settings_cmd(update, context)
        return SETTINGS
    elif text == "📞 Help":
        await update.message.reply_text("📞 **Support Information**\n\nFor assistance, contact: @altleg\n\nResponse time: Usually within 24 hours", parse_mode="Markdown")
        return MENU
    elif text == "💰 Balance":
        if user_id == ADMIN_ID:
            balance_msg = "✅ **Admin Account**\n\n💰 Unlimited Free Access\n\n🎉 No packages needed!"
        else:
            credits = get_credits(user_id)
            balance_msg = f"💰 **Your Balance:** {credits} packages\n\n💳 Payment coming soon!"
        
        await update.message.reply_text(balance_msg, reply_markup=main_menu_reply_keyboard(), parse_mode="Markdown")
        return MENU
    elif text == "❌ Cancel":
        await update.message.reply_text("Cancelled. Back to main menu.", reply_markup=main_menu_reply_keyboard())
        return MENU
    
    return MENU

async def select_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pkg_map = {'pkg_1': '1', 'pkg_20': '20', 'pkg_100': '100', 'pkg_150': '150'}
    context.user_data['pending_pkg'] = pkg_map[query.data]
    pkg_amount = query.data.replace('pkg_', '')
    
    payment_msg = (
        f"💳 **Payment Details**\n\n"
        f"📱 Send **{pkg_map[query.data]} birr** to: `{TELEBIRR_NUMBER}`\n\n"
        f"After sending, reply with the SMS receipt/transaction ID"
    )
    await query.edit_message_text(payment_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='back_main')]]))
    return WAIT_RECEIPT

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    
    # Get the username or fallback to First Name if they don't have one
    user_name = f"@{user.username}" if user.username else user.first_name
    
    # Add Username to the admin message
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
    
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=btns, parse_mode="Markdown")
    await update.message.reply_text("Receipt sent for approval. / ደረሰኝዎ ለቁጥጥር ተልኳል።")
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

async def handle_print_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Print Now button with multi-stage progress workflow"""
    query = update.callback_query
    await query.answer()  # Answer callback query to stop loading spinner
    
    user_id = query.from_user.id
    
    # Prevent duplicate processing
    if context.user_data.get('print_now_processing'):
        await query.answer("⏳ Already processing. Please wait...", show_alert=True)
        return
    
    # Mark as processing
    context.user_data['print_now_processing'] = True
    
    # Check if we have a source PDF
    source_pdf = context.user_data.get('last_pdf_path')
    
    if not source_pdf or not os.path.exists(source_pdf):
        context.user_data['print_now_processing'] = False
        await query.answer("❌ Source PDF not found. Please upload a PDF again.", show_alert=True)
        return
    
    try:
        # Stage 1: Processing PDF
        progress_msg = await query.message.reply_text(
            "🖨️ **Print Now**\n\n"
            "1️⃣ Processing PDF...",
            parse_mode="Markdown"
        )
        
        # Extract data from PDF
        data = await asyncio.to_thread(extract_data_from_pdf, source_pdf, f"{user_id}_print")
        
        if not data:
            context.user_data['print_now_processing'] = False
            await progress_msg.edit_text(
                "❌ **Error**\n\nFailed to extract PDF data. Please try again.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Try Again", callback_data='print_now')]])
            )
            return
        
        # Stage 2: Preparing ID cards
        await progress_msg.edit_text(
            "🖨️ **Print Now**\n\n"
            "1️⃣ Processing PDF... ✅\n"
            "2️⃣ Preparing ID cards...",
            parse_mode="Markdown"
        )
        
        # Generate printable ID
        user_mode = context.user_data.get('output_mode', 'color')
        template = context.user_data.get('template_choice')
        printable_path = f"printable_{user_id}.png"
        
        await asyncio.to_thread(
            generate_fayda_v3, 
            data, 
            printable_path, 
            f"{user_id}_print", 
            user_mode, 
            template_path=template
        )
        
        # Stage 3: Creating A4 printable layout
        await progress_msg.edit_text(
            "🖨️ **Print Now**\n\n"
            "1️⃣ Processing PDF... ✅\n"
            "2️⃣ Preparing ID cards... ✅\n"
            "3️⃣ Creating A4 printable layout...",
            parse_mode="Markdown"
        )
        
        # For single PDF, create a simple printable (or could arrange on A4 if multiple)
        if os.path.exists(printable_path):
            # Stage 4: Finalizing
            await progress_msg.edit_text(
                "🖨️ **Print Now**\n\n"
                "1️⃣ Processing PDF... ✅\n"
                "2️⃣ Preparing ID cards... ✅\n"
                "3️⃣ Creating A4 printable layout... ✅\n"
                "4️⃣ Finalizing...",
                parse_mode="Markdown"
            )
            
            # Send the printable file
            with open(printable_path, 'rb') as f:
                filename = f"Fayda_Printable_{user_id}.png"
                await query.message.reply_document(
                    f,
                    filename=filename,
                    caption="✅ **Your Printable ID is Ready!**\n\n🖨️ Ready to print!\n\n💡 Use high-quality print settings (photo quality) for best results."
                )
            
            # Auto-completion message
            await progress_msg.edit_text(
                "🖨️ **Print Now**\n\n"
                "1️⃣ Processing PDF... ✅\n"
                "2️⃣ Preparing ID cards... ✅\n"
                "3️⃣ Creating A4 printable layout... ✅\n"
                "4️⃣ Finalizing... ✅\n\n"
                "✅ **Printable file sent successfully!**",
                parse_mode="Markdown",
                reply_markup=print_now_keyboard()
            )
        else:
            context.user_data['print_now_processing'] = False
            await progress_msg.edit_text(
                "❌ **Error**\n\nFailed to generate printable file.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Try Again", callback_data='print_now')]])
            )
            return
    
    except Exception as e:
        context.user_data['print_now_processing'] = False
        await progress_msg.edit_text(
            f"❌ **Error**\n\n{str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Try Again", callback_data='print_now')]])
        )
        return
    
    finally:
        # Cleanup
        for f in [f"printable_{user_id}.png", f"photo_{user_id}_print.png", 
                 f"qr_{user_id}_print.png", f"fin_{user_id}_print.png"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except:
                    pass
        
        context.user_data['print_now_processing'] = False


# 5. INTEGRATED PDF HANDLER WITH UPDATABLE STATUS

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    # Free access for admin
    if user_id != ADMIN_ID:
        await update.message.reply_text(
            "🔒 **Service Coming Soon**\n\n"
            "This service is currently in beta and available only to admin users.\n\n"
            "📱 Telebirr and Bank integration coming soon! Stay tuned.",
            parse_mode="Markdown",
            reply_markup=main_menu_reply_keyboard()
        )
        return MENU
    
    credits = get_credits(user_id)

    # Create updatable status message
    status_msg = await update.message.reply_text("⏳ **Processing...**\n\n📥 Downloading PDF...", parse_mode="Markdown")
    
    pdf_path = f"input_{user_id}.pdf"
    file = await context.bot.get_file(update.message.document.file_id)
    await file.download_to_drive(pdf_path)
    
    # Store PDF path for Print Now functionality
    context.user_data['last_pdf_path'] = pdf_path
    context.user_data['print_now_processing'] = False

    try:
        # Update: Extracting data
        await status_msg.edit_text("⏳ **Processing...**\n\n🔍 Extracting data...", parse_mode="Markdown")
        data = await asyncio.to_thread(extract_data_from_pdf, pdf_path, user_id)
        
        if data:
            # Update: Generating card
            await status_msg.edit_text("⏳ **Processing...**\n\n🎨 Generating ID card...", parse_mode="Markdown")
            
            user_template = context.user_data.get('template_choice')
            user_mode = context.user_data.get('output_mode', 'color')
            out_path = f"{user_mode}_{user_id}.png"

            await asyncio.to_thread(generate_fayda_v3, data, out_path, user_id, user_mode, template_path=user_template)
            
            # Store file path for Print Now button
            context.user_data['last_printable'] = out_path
            
            # Update: Uploading result
            await status_msg.edit_text("⏳ **Processing...**\n\n📤 Uploading result...", parse_mode="Markdown")
            
            with open(out_path, 'rb') as f:
                filename = "Fayda_Color.png" if user_mode == 'color' else "Fayda_BW.png"
                await update.message.reply_document(f, filename=filename, caption="✅ Your ID Card is ready!")
            
            # Final success message with Print Now button
            if user_id == ADMIN_ID:
                final_text = (
                    "✅ **Success! (Admin - Free Access)**\n\n"
                    "📄 ID card generated successfully\n"
                    "🎉 Unlimited free printing"
                )
            else:
                add_credits(user_id, -1)
                new_balance = get_credits(user_id)
                final_text = (
                    f"✅ **Success!**\n\n"
                    f"💼 1 package used\n"
                    f"💰 Remaining balance: **{new_balance}** packages"
                )
            
            await status_msg.edit_text(
                final_text,
                parse_mode="Markdown",
                reply_markup=print_now_keyboard()
            )
        else:
            await status_msg.edit_text(
                "❌ **Extraction Failed**\n\n"
                "The PDF format is not recognized. Please ensure you're using an official FAYDA PDF.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Try Again", callback_data='print_id')]])
            )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ **Error occurred**\n\nError: {str(e)[:100]}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Try Again", callback_data='print_id')]])
        )
    finally:
        for f in [pdf_path, f"{context.user_data.get('output_mode', 'color')}_{user_id}.png", f"photo_{user_id}.png", f"qr_{user_id}.png", f"fin_{user_id}.png"]:
            if os.path.exists(f): os.remove(f)

async def handle_batch_count_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user selection of how many cards per A4 page"""
    user_id = update.message.from_user.id
    
    # Only admin can use batch mode
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Batch mode is admin-only.", reply_markup=main_menu_reply_keyboard())
        return MENU
    
    text = update.message.text
    card_count_map = {
        "2️⃣ 2 Cards per A4": 2,
        "3️⃣ 3 Cards per A4": 3,
        "4️⃣ 4 Cards per A4": 4,
        "5️⃣ 5 Cards per A4": 5,
    }
    
    if text not in card_count_map:
        await update.message.reply_text("❌ Invalid selection. Please choose a valid option.", reply_markup=batch_card_count_keyboard())
        return BATCH_MODE
    
    num_cards = card_count_map[text]
    
    # Initialize batch list
    context.user_data['batch_pdfs'] = []
    context.user_data['batch_count'] = 0
    context.user_data['batch_target'] = num_cards
    
    await update.message.reply_text(
        f"📋 **Batch Mode: {num_cards} Cards per A4**\n\n📤 Send PDF {1}/{num_cards} now",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    return BATCH_MODE

async def handle_batch_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle multiple PDFs for batch processing"""
    user_id = update.message.from_user.id
    
    # Only admin can use batch mode
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Batch mode is admin-only.", reply_markup=main_menu_reply_keyboard())
        return MENU
    
    # Initialize if first PDF
    target_count = context.user_data.get('batch_target', 5)
    
    if 'batch_pdfs' not in context.user_data:
        context.user_data['batch_pdfs'] = []
        context.user_data['batch_count'] = 0
        context.user_data['batch_target'] = target_count
    
    # Download PDF
    pdf_path = f"batch_{user_id}_{context.user_data['batch_count']}.pdf"
    file = await context.bot.get_file(update.message.document.file_id)
    await file.download_to_drive(pdf_path)
    
    context.user_data['batch_count'] += 1
    context.user_data['batch_pdfs'].append(pdf_path)
    
    # Show progress
    progress = context.user_data['batch_count']
    target_count = context.user_data.get('batch_target', 5)
    
    if progress < target_count:
        await update.message.reply_text(
            f"✅ PDF {progress}/{target_count} received!\n\n⏳ Waiting for PDF {progress + 1}/{target_count}...",
            reply_markup=cancel_keyboard()
        )
        return BATCH_MODE
    else:
        # All PDFs received, process them
        target_count = context.user_data.get('batch_target', 5)
        status_msg = await update.message.reply_text(
            f"✅ All {target_count} PDFs received!\n\n⏳ **Processing...**\n\n🔍 Extracting data from PDFs...",
            parse_mode="Markdown"
        )
        
        try:
            card_paths = []
            
            # Process each PDF
            for i, pdf_path in enumerate(context.user_data['batch_pdfs']):
                await status_msg.edit_text(
                    f"⏳ **Processing...**\n\n🔍 Extracting data from PDF {i+1}/{target_count}...",
                    parse_mode="Markdown"
                )
                
                data = await asyncio.to_thread(extract_data_from_pdf, pdf_path, f"{user_id}_batch_{i}")
                
                if data:
                    await status_msg.edit_text(
                        f"⏳ **Processing...**\n\n🎨 Generating card {i+1}/{target_count}...",
                        parse_mode="Markdown"
                    )
                    
                    card_path = f"batch_card_{user_id}_{i}.png"
                    user_mode = context.user_data.get('output_mode', 'color')
                    await asyncio.to_thread(generate_fayda_v3, data, card_path, f"{user_id}_batch_{i}", user_mode)
                    card_paths.append(card_path)
            
            if len(card_paths) == target_count:
                await status_msg.edit_text(
                    "⏳ **Processing...**\n\n📋 Arranging cards on A4 page...",
                    parse_mode="Markdown"
                )
                
                a4_output = f"batch_a4_{user_id}.png"
                await asyncio.to_thread(arrange_cards_on_a4, card_paths, a4_output, target_count)
                
                await status_msg.edit_text(
                    "⏳ **Processing...**\n\n📤 Uploading A4 page...",
                    parse_mode="Markdown"
                )
                
                # Send final A4 image
                with open(a4_output, 'rb') as f:
                    filename = f"Fayda_{target_count}Cards_A4.png"
                    caption = f"✅ **{target_count} ID Cards on A4 Page Ready!**\n\n📋 Ready to print!\n\n🖨️ Use high-quality print settings for best results."
                    await update.message.reply_document(f, filename=filename, caption=caption)
                
                # Store file path for Print Now button
                context.user_data['last_printable'] = a4_output
                
                await status_msg.edit_text(
                    f"✅ **Success!**\n\n"
                    f"📋 {target_count} ID cards arranged on one A4 page\n"
                    f"🖨️ Ready to print!\n\n"
                    f"💡 Use high-quality print settings (photo quality) for best results.",
                    parse_mode="Markdown",
                    reply_markup=print_now_keyboard()
                )
            else:
                await status_msg.edit_text(
                    f"❌ **Error**\n\nOnly {len(card_paths)}/{target_count} cards were generated successfully.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Try Again", callback_data='print_id')]])
                )
        
        except Exception as e:
            await status_msg.edit_text(
                f"❌ **Error occurred**\n\nError: {str(e)[:100]}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Try Again", callback_data='print_id')]])
            )
        
        finally:
            # Cleanup
            for pdf_path in context.user_data.get('batch_pdfs', []):
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
            
            for i in range(5):
                for pattern in [f"batch_card_{user_id}_{i}.png", f"photo_{user_id}_batch_{i}.png", 
                               f"qr_{user_id}_batch_{i}.png", f"fin_{user_id}_batch_{i}.png"]:
                    if os.path.exists(pattern):
                        os.remove(pattern)
            
            a4_file = f"batch_a4_{user_id}.png"
            if os.path.exists(a4_file):
                os.remove(a4_file)
            
            context.user_data['batch_pdfs'] = []
            context.user_data['batch_count'] = 0
        
        return MENU




# ADD THIS NEW BLOCK
# 1. Initialize Database and Bot (OUTSIDE the main block)
init_db()

# Initialize the Telegram App globally so Flask can see it
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Define Handlers
conv = ConversationHandler(
    entry_points=[CommandHandler('start', start), MessageHandler(filters.Document.PDF, handle_pdf)],
    states={
        MENU: [
            MessageHandler(filters.Document.PDF, handle_pdf),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply_buttons),
            CallbackQueryHandler(button_tap, pattern="^(print_id|buy_package|contact_help|back_main)$")
        ],
        BUY_PACK: [
            CallbackQueryHandler(select_package, pattern="^(pkg_1|pkg_20|pkg_100|pkg_150)$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply_buttons)
        ],
        WAIT_RECEIPT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_receipt)
        ],
        SETTINGS: [
            CallbackQueryHandler(settings_callback, pattern="^(set_template|set_mode|back_main|tpl:.*|mode:.*)$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply_buttons)
        ],
        BATCH_MODE: [
            MessageHandler(filters.Document.PDF, handle_batch_pdf),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply_buttons)
        ]
    },
    fallbacks=[CommandHandler('start', start)]
)

app.add_handler(conv)
app.add_handler(CallbackQueryHandler(admin_approval, pattern="^(appr|rej)_"))
app.add_handler(CallbackQueryHandler(handle_print_now, pattern="^print_now$"))
app.add_handler(CommandHandler('settings', settings_cmd))
app.add_handler(CallbackQueryHandler(settings_callback, pattern="^(set_template|set_mode|back_main|back_settings|tpl:.*|mode:.*)$"))

# 2. Add a helper to start the bot's background processes
async def setup_webhook():
    URL = os.environ.get("RENDER_EXTERNAL_URL")
    if URL:
        await app.bot.set_webhook(url=f"{URL}/webhook")
        print(f"🚀 Webhook set to {URL}/webhook")

# This logic runs when Gunicorn starts
import threading
if os.environ.get("RENDER_EXTERNAL_URL"):
    # Run the webhook setup in the background
    import asyncio
    loop = asyncio.new_event_loop()
    threading.Thread(target=lambda: loop.run_until_complete(app.initialize())).start()

# 3. Keep the main block ONLY for local testing (VS Code)
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))
    URL = os.environ.get("RENDER_EXTERNAL_URL") 

    if not URL:
        print("🚀 Local Mode: Polling")
        app.run_polling()
