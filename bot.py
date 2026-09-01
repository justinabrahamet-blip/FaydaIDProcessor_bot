import logging
import asyncio
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_TOKEN, WEBHOOK_URL, PORT, ADMIN_IDS
from db_client import db
from api_client import api_client

from force_join_middleware import ForceJoinMiddleware
from anti_flood_middleware import AntiFloodMiddleware
from maintenance_middleware import MaintenanceMiddleware

# Flat Routers from root directory
from start_handler import router as start_router
from shop_handler import router as shop_router
from wallet_handler import router as wallet_router
from orders_handler import router as orders_router
from referral_handler import router as referral_router
from support_handler import router as support_router

# Flat Admin Routers from root directory
from admin_main_handler import router as admin_main_router
from admin_products_handler import router as admin_products_router
from admin_ui_editor_handler import router as admin_ui_editor_router
from admin_customers_handler import router as admin_customers_router
from admin_payments_handler import router as admin_payments_router
from admin_analytics_handler import router as admin_analytics_router
from admin_broadcast_handler import router as admin_broadcast_router
from admin_api_monitor_handler import router as admin_api_monitor_router

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Ultra-lightweight HTTP 200 OK handler for Render Web Service, UptimeRobot and Cron-Job keep-alive pings."""
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", "2")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", "2")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            self.wfile.write(b"OK")
        except Exception:
            pass

    def log_message(self, format, *args):
        pass

def start_health_check_server(port: int):
    """Start lightweight health check server in background thread for Render Web Services."""
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Health check server listening on port {port} for Render Web Service & Cron-Jobs.")
    except Exception as e:
        logger.warning(f"Could not start health check server on port {port}: {e}")

async def set_bot_commands(bot: Bot):
    """Register official Bot Commands with Telegram API for persistent menu button."""
    commands = [
        BotCommand(command="start", description="🏠 Main Menu"),
        BotCommand(command="products", description="🛒 Digital Products Catalog"),
        BotCommand(command="wallet", description="💳 Wallet & Add Balance"),
        BotCommand(command="orders", description="📦 My Orders History"),
        BotCommand(command="profile", description="👤 My Profile"),
        BotCommand(command="referral", description="🎁 Refer & Earn Program"),
        BotCommand(command="support", description="❓ Support & User Guide"),
        BotCommand(command="admin", description="⚙️ Admin Dashboard (Admins Only)")
    ]
    try:
        await bot.set_my_commands(commands)
        logger.info("Bot commands successfully registered with Telegram API.")
    except Exception as e:
        logger.warning(f"Could not set bot commands: {e}")

async def on_startup(bot: Bot):
    """Perform initial startup sync, drop old webhooks, and pre-load persistent cache."""
    logger.info("Starting MELAX DIGITAL SHOP (aiogram 3.x + Supabase)...")

    # 1. PURGE OLD WEBHOOKS TO PREVENT CONFLICTS
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Old Telegram Webhooks & pending updates purged successfully.")
    except Exception as e:
        logger.warning(f"Webhook purge warning: {e}")

    # 2. Register Bot Commands
    await set_bot_commands(bot)

    # 3. Pre-load all persistent Admin Overrides & UI texts into cache
    try:
        await db.load_all_overrides_to_cache()
    except Exception as e:
        logger.warning(f"Overrides cache pre-load warning: {e}")

    # 4. Sync Catalog Products (Only if Admin has enabled auto-sync)
    try:
        auto_sync = await db.get_setting("api_auto_sync", False)
        if auto_sync:
            api_prods = await api_client.get_products()
            if api_prods:
                res = await db.sync_products_from_api(api_prods)
                logger.info(f"Startup product sync: {res}")
        else:
            logger.info("API Auto-Sync is OFF by default. Catalog managed directly by Admin.")
    except Exception as e:
        logger.warning(f"Startup product sync error: {e}")

    # 5. Load Custom Animated Emojis from Database Settings
    try:
        from config import DYNAMIC_EMOJIS, update_dynamic_emoji
        for key in DYNAMIC_EMOJIS.keys():
            db_val = await db.get_setting(f"custom_emoji_{key}")
            if db_val:
                update_dynamic_emoji(key, str(db_val))
        logger.info("Custom Animated Emojis loaded successfully into cache.")
    except Exception as e:
        logger.warning(f"Custom emoji startup load warning: {e}")

    # 6. Launch Continuous Live Stock Refresh Background Worker
    asyncio.create_task(periodic_live_stock_sync_task())

    logger.info("Bot initialization complete.")

async def periodic_live_stock_sync_task():
    """Background loop that continuously refreshes stock of enabled API products every 20 seconds."""
    logger.info("Live stock auto-refresh worker started.")
    while True:
        try:
            await asyncio.sleep(20)
            await db.refresh_live_stock_for_enabled_products()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Periodic stock sync loop warning: {e}")
            await asyncio.sleep(30)

async def main():
    if not BOT_TOKEN or BOT_TOKEN == "7744383120:AAH_your_real_bot_token_here":
        logger.error("BOT_TOKEN is missing or not set in .env file!")
        print("\n❌ ERROR: BOT_TOKEN missing in .env file!\n")
        return

    start_health_check_server(PORT)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Register Middlewares on MESSAGE and CALLBACK_QUERY level (NOT dp.update!)
    # This ensures isinstance(event, Message) and isinstance(event, CallbackQuery) work correctly.
    dp.message.outer_middleware(AntiFloodMiddleware())
    dp.message.outer_middleware(MaintenanceMiddleware())
    dp.message.outer_middleware(ForceJoinMiddleware())
    dp.callback_query.outer_middleware(AntiFloodMiddleware())
    dp.callback_query.outer_middleware(MaintenanceMiddleware())
    dp.callback_query.outer_middleware(ForceJoinMiddleware())

    # PRIORITY ROUTERS: Admin FSM Routers FIRST
    dp.include_router(admin_ui_editor_router)
    dp.include_router(admin_products_router)
    dp.include_router(admin_payments_router)
    dp.include_router(admin_main_router)
    dp.include_router(admin_customers_router)
    dp.include_router(admin_analytics_router)
    dp.include_router(admin_broadcast_router)
    dp.include_router(admin_api_monitor_router)

    # Standard User Routers
    dp.include_router(start_router)
    dp.include_router(shop_router)
    dp.include_router(orders_router)
    dp.include_router(referral_router)
    dp.include_router(support_router)

    # Wallet Router (Contains F.text catch-all for receipts)
    dp.include_router(wallet_router)

    dp.startup.register(on_startup)

    # Ensure webhook is cleared before starting polling
    await bot.delete_webhook(drop_pending_updates=True)

    print("🚀 Starting MELAX DIGITAL SHOP Telegram Bot (aiogram 3.x)...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
