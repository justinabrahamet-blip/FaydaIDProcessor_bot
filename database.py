import aiosqlite
import logging
from pathlib import Path
from config import DB_PATH, MARKUP_PERCENT, REFERRAL_PERCENT

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)

    async def init_db(self):
        """Initialize SQLite database schema."""
        async with aiosqlite.connect(self.db_path) as db:
            # Users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    wallet_balance REAL DEFAULT 0.0,
                    referred_by INTEGER,
                    total_spent REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Deposits table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS deposits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount REAL,
                    payment_method TEXT,
                    txid TEXT,
                    screenshot_file_id TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Orders table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    service_id TEXT,
                    service_name TEXT,
                    quantity INTEGER,
                    price_paid REAL,
                    api_order_id TEXT,
                    delivered_code TEXT,
                    status TEXT DEFAULT 'success',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Custom local product prices decided by admin
            await db.execute("""
                CREATE TABLE IF NOT EXISTS product_prices (
                    service_id TEXT PRIMARY KEY,
                    custom_price REAL
                )
            """)

            await db.commit()

    async def get_user(self, user_id: int):
        """Fetch user record."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                return await cursor.fetchone()

    async def register_user(self, user_id: int, username: str, first_name: str, referrer_id: int = None) -> tuple[bool, str]:
        """Register a new user or update details."""
        async with aiosqlite.connect(self.db_path) as db:
            existing = await self.get_user(user_id)
            if existing:
                await db.execute(
                    "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
                    (username, first_name, user_id)
                )
                await db.commit()
                return False, ""

            valid_referrer = None
            referrer_name = ""
            if referrer_id and referrer_id != user_id:
                async with db.execute("SELECT user_id, first_name FROM users WHERE user_id = ?", (referrer_id,)) as cursor:
                    r = await cursor.fetchone()
                    if r:
                        valid_referrer = referrer_id
                        referrer_name = r[1]

            await db.execute("""
                INSERT INTO users (user_id, username, first_name, wallet_balance, referred_by)
                VALUES (?, ?, ?, 0.0, ?)
            """, (user_id, username, first_name, valid_referrer))
            await db.commit()
            return True, referrer_name

    async def get_user_balance(self, user_id: int) -> float:
        """Get user wallet balance."""
        user = await self.get_user(user_id)
        return float(user["wallet_balance"]) if user else 0.0

    async def add_deposit_request(self, user_id: int, amount: float, method: str, txid: str, photo_file_id: str) -> int:
        """Create a pending deposit request."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO deposits (user_id, amount, payment_method, txid, screenshot_file_id, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            """, (user_id, amount, method, txid, photo_file_id))
            await db.commit()
            return cursor.lastrowid

    async def approve_deposit(self, deposit_id: int) -> tuple[bool, str, int, float]:
        """Approve deposit, credit user wallet, and reward referrer."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM deposits WHERE id = ?", (deposit_id,)) as cursor:
                dep = await cursor.fetchone()
                if not dep:
                    return False, "Deposit not found", 0, 0.0
                if dep["status"] != "pending":
                    return False, f"Deposit already {dep['status']}", 0, 0.0

            user_id = dep["user_id"]
            amount = float(dep["amount"])

            # Credit user
            await db.execute("UPDATE users SET wallet_balance = wallet_balance + ? WHERE user_id = ?", (amount, user_id))
            await db.execute("UPDATE deposits SET status = 'approved' WHERE id = ?", (deposit_id,))

            # Check referrer commission
            user = await self.get_user(user_id)
            if user and user["referred_by"]:
                referrer_id = user["referred_by"]
                commission = amount * (REFERRAL_PERCENT / 100.0)
                if commission > 0:
                    await db.execute("UPDATE users SET wallet_balance = wallet_balance + ? WHERE user_id = ?", (commission, referrer_id))

            await db.commit()
            return True, "Deposit approved", user_id, amount

    async def reject_deposit(self, deposit_id: int) -> tuple[bool, str, int]:
        """Reject a pending deposit."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM deposits WHERE id = ?", (deposit_id,)) as cursor:
                dep = await cursor.fetchone()
                if not dep or dep["status"] != "pending":
                    return False, "Deposit not pending or not found", 0

            await db.execute("UPDATE deposits SET status = 'rejected' WHERE id = ?", (deposit_id,))
            await db.commit()
            return True, "Deposit rejected", dep["user_id"]

    async def record_successful_order(
        self, user_id: int, service_id: str, service_name: str, quantity: int, price_paid: float, api_order_id: str, delivered_code: str
    ):
        """Deduct user balance, record order in DB, and update total spent."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users 
                SET wallet_balance = wallet_balance - ?, total_spent = total_spent + ? 
                WHERE user_id = ?
            """, (price_paid, price_paid, user_id))

            await db.execute("""
                INSERT INTO orders (user_id, service_id, service_name, quantity, price_paid, api_order_id, delivered_code, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'success')
            """, (user_id, service_id, service_name, quantity, price_paid, api_order_id, delivered_code))

            await db.commit()

    async def get_user_orders(self, user_id: int) -> list:
        """Fetch all orders for specific user."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC", (user_id,)) as cursor:
                return await cursor.fetchall()

    async def set_product_price(self, service_id: str, price: float):
        """Set custom local selling price for a product."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO product_prices (service_id, custom_price)
                VALUES (?, ?)
                ON CONFLICT(service_id) DO UPDATE SET custom_price = excluded.custom_price
            """, (service_id, price))
            await db.commit()

    async def get_product_price(self, service_id: str) -> float | None:
        """Get custom local selling price for a product if set by admin."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT custom_price FROM product_prices WHERE service_id = ?", (service_id,)) as cursor:
                row = await cursor.fetchone()
                return float(row[0]) if row else None

    async def get_all_product_prices(self) -> dict:
        """Get mapping of all custom prices."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT service_id, custom_price FROM product_prices") as cursor:
                rows = await cursor.fetchall()
                return {r[0]: float(r[1]) for r in rows}

    async def get_referral_info(self, user_id: int) -> dict:
        """Fetch referral stats."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,)) as cursor:
                total_refs = (await cursor.fetchone())[0]
            
            user = await self.get_user(user_id)
            balance = user["wallet_balance"] if user else 0.0

            return {
                "total_referrals": total_refs,
                "balance": balance
            }

    async def get_all_user_ids(self) -> list[int]:
        """Fetch all user Telegram IDs."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id FROM users") as cursor:
                rows = await cursor.fetchall()
                return [r[0] for r in rows]

    async def get_admin_shop_stats(self) -> dict:
        """Fetch store metrics."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as c1:
                total_users = (await c1.fetchone())[0]
            
            async with db.execute("SELECT COUNT(*), SUM(price_paid) FROM orders") as c2:
                row2 = await c2.fetchone()
                total_orders = row2[0] or 0
                total_revenue = row2[1] or 0.0

            async with db.execute("SELECT COUNT(*) FROM deposits WHERE status = 'pending'") as c3:
                pending_deposits = (await c3.fetchone())[0]

            return {
                "total_users": total_users,
                "total_orders": total_orders,
                "total_revenue": total_revenue,
                "pending_deposits": pending_deposits
            }

db = DatabaseManager()
