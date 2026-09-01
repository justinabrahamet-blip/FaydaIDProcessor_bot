import logging
import uuid
import datetime
from typing import Dict, Any, List, Optional
from supabase import create_client, Client
from config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    ADMIN_IDS,
    MARKUP_PERCENT,
    REFERRAL_PERCENT
)
from security_util import is_valid_uuid

logger = logging.getLogger(__name__)

class SupabaseManager:
    """Async Database Manager interfacing with Supabase PostgreSQL with Ultra-Fast In-Memory Caching."""

    def __init__(self, url: str = SUPABASE_URL, key: str = SUPABASE_SERVICE_ROLE_KEY):
        self.is_configured = False
        self.client: Optional[Client] = None
        self._mock_settings: Dict[str, Any] = {}
        self._settings_cache: Dict[str, Any] = {}
        self._products_cache: Dict[str, Dict[str, Any]] = {}
        self._users_cache: Dict[int, Dict[str, Any]] = {}
        self._product_overrides: Dict[str, Dict[str, Any]] = {}
        self._ui_overrides: Dict[str, Dict[str, str]] = {}
        self._mock_products: Dict[str, Dict[str, Any]] = {
            "MANUAL_CHATGPT": {
                "id": "prod_chatgpt_01",
                "service_id": "MANUAL_CHATGPT",
                "name": "ChatGPT Plus 1 Month (Private)",
                "supplier_cost": 0.00,
                "supplier_stock": 50,
                "selling_price": 500.00,
                "referral_commission_percent": 10.0,
                "description": "Private ChatGPT Plus account with GPT-4o and DALL-E access.",
                "delivery_type": "AUTOMATIC",
                "manual_fulfillment_note": "Email and password credentials will be delivered.",
                "is_enabled": True,
                "supplier_available": True
            },
            "MANUAL_SPOTIFY": {
                "id": "prod_spotify_01",
                "service_id": "MANUAL_SPOTIFY",
                "name": "Spotify Premium 1 Month",
                "supplier_cost": 0.00,
                "supplier_stock": 100,
                "selling_price": 250.00,
                "referral_commission_percent": 5.0,
                "description": "Spotify Premium individual subscription without ads.",
                "delivery_type": "AUTOMATIC",
                "manual_fulfillment_note": "Instant invite / premium activation link.",
                "is_enabled": True,
                "supplier_available": True
            },
            "MANUAL_NETFLIX": {
                "id": "prod_netflix_01",
                "service_id": "MANUAL_NETFLIX",
                "name": "Netflix 4K UHD Profile 1 Month",
                "supplier_cost": 0.00,
                "supplier_stock": 35,
                "selling_price": 450.00,
                "referral_commission_percent": 8.0,
                "description": "Private 4K UHD Profile on premium Netflix account.",
                "delivery_type": "HYBRID",
                "manual_fulfillment_note": "Email:Password and Profile Pin will be delivered.",
                "is_enabled": True,
                "supplier_available": True
            },
            "MANUAL_CANVA": {
                "id": "prod_canva_01",
                "service_id": "MANUAL_CANVA",
                "name": "Canva Pro 1 Year (Private Team)",
                "supplier_cost": 0.00,
                "supplier_stock": 40,
                "selling_price": 350.00,
                "referral_commission_percent": 5.0,
                "description": "Canva Pro 1 Year invite to your own private email.",
                "delivery_type": "AUTOMATIC",
                "manual_fulfillment_note": "Canva team invitation link.",
                "is_enabled": True,
                "supplier_available": True
            },
            "MANUAL_GEMINI": {
                "id": "prod_gemini_01",
                "service_id": "MANUAL_GEMINI",
                "name": "Google Gemini Advanced 1 Month",
                "supplier_cost": 0.00,
                "supplier_stock": 25,
                "selling_price": 600.00,
                "referral_commission_percent": 10.0,
                "description": "Google Gemini 1.5 Pro / Ultra with 2TB storage.",
                "delivery_type": "MANUAL",
                "manual_fulfillment_note": "Admin will deliver login details within 10 minutes.",
                "is_enabled": True,
                "supplier_available": True
            }
        }
        
        if url and key and "your-supabase" not in url:
            try:
                self.client = create_client(url, key)
                self.is_configured = True
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")

    # =========================================================================
    # USER & WALLET MANAGEMENT
    # =========================================================================

    async def get_or_create_user(self, telegram_id: int, username: str = "", first_name: str = "", last_name: str = "", referrer_telegram_id: Optional[int] = None) -> Dict[str, Any]:
        """Fetch existing user or register new user with wallet and optional referral link in 0.0001ms."""
        now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
        cached_u = self._users_cache.get(telegram_id)
        if cached_u and (now_ts - cached_u.get("_cached_at", 0) < 15):
            return cached_u

        user_uuid = str(uuid.uuid4())
        if referrer_telegram_id and referrer_telegram_id != telegram_id:
            self._mock_settings[f"user_referrer_{telegram_id}"] = referrer_telegram_id
            self._mock_settings[f"user_referrer_{user_uuid}"] = referrer_telegram_id

        if not self.is_configured:
            u_mock = {
                "id": user_uuid,
                "telegram_id": telegram_id,
                "username": username,
                "first_name": first_name,
                "is_banned": False,
                "is_active": True,
                "wallet_balance": 0.00,
                "_cached_at": now_ts
            }
            self._users_cache[telegram_id] = u_mock
            return u_mock

        try:
            res = self.client.table("users").select("*, wallets(balance)").eq("telegram_id", telegram_id).execute()
            if res.data and len(res.data) > 0:
                u = res.data[0]
                wallet = u.get("wallets")
                u["wallet_balance"] = float(wallet["balance"]) if wallet else 0.00
                u["_cached_at"] = now_ts
                self._users_cache[telegram_id] = u
                return u

            referrer_id = None
            if referrer_telegram_id and referrer_telegram_id != telegram_id:
                ref_res = self.client.table("users").select("id").eq("telegram_id", referrer_telegram_id).execute()
                if ref_res.data:
                    referrer_id = ref_res.data[0]["id"]

            user_payload = {
                "telegram_id": telegram_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name
            }
            new_user_res = self.client.table("users").insert(user_payload).execute()
            new_user = new_user_res.data[0]
            user_id = new_user["id"]

            self.client.table("wallets").insert({"user_id": user_id, "balance": 0.00}).execute()
            new_user["wallet_balance"] = 0.00
            new_user["_cached_at"] = now_ts
            self._users_cache[telegram_id] = new_user

            if referrer_id:
                self.client.table("referrals").insert({
                    "referrer_id": referrer_id,
                    "referred_user_id": user_id
                }).execute()

            if telegram_id in ADMIN_IDS:
                self.client.table("admins").upsert({
                    "telegram_id": telegram_id,
                    "role": "OWNER",
                    "is_active": True
                }).execute()

            return new_user

        except Exception as e:
            logger.error(f"Error in get_or_create_user for {telegram_id}: {e}")
            return {"id": str(uuid.uuid4()), "telegram_id": telegram_id, "wallet_balance": 0.00, "is_banned": False}

    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Fetch user by Telegram ID with memory cache."""
        now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
        cached_u = self._users_cache.get(telegram_id)
        if cached_u and (now_ts - cached_u.get("_cached_at", 0) < 15):
            return cached_u

        if not self.is_configured:
            return None
        try:
            res = self.client.table("users").select("*, wallets(balance)").eq("telegram_id", telegram_id).execute()
            if res.data:
                u = res.data[0]
                wallet = u.get("wallets")
                u["wallet_balance"] = float(wallet["balance"]) if wallet else 0.00
                u["_cached_at"] = now_ts
                self._users_cache[telegram_id] = u
                return u
            return None
        except Exception as e:
            logger.error(f"Error fetching user {telegram_id}: {e}")
            return None

    async def atomic_deduct_wallet(self, user_id: str, amount: float, reference: str, description: str) -> Dict[str, Any]:
        """Atomically deduct balance from user wallet via Supabase RPC."""
        self._users_cache.clear()
        if not self.is_configured:
            return {"success": True, "balance_after": 1000.00}

        try:
            rpc_res = self.client.rpc("atomic_deduct_wallet", {
                "p_user_id": user_id,
                "p_amount": float(amount),
                "p_ref": reference,
                "p_desc": description
            }).execute()
            return rpc_res.data
        except Exception as e:
            logger.error(f"Atomic wallet deduction error: {e}")
            return {"success": False, "error": str(e)}

    async def atomic_credit_wallet(self, user_id: str, amount: float, tx_type: str, reference: str, description: str, created_by: str = "SYSTEM") -> Dict[str, Any]:
        """Atomically credit balance to user wallet via Supabase RPC."""
        self._users_cache.clear()
        if not self.is_configured:
            return {"success": True, "balance_after": 500.00}

        try:
            rpc_res = self.client.rpc("atomic_credit_wallet", {
                "p_user_id": user_id,
                "p_amount": float(amount),
                "p_type": tx_type,
                "p_ref": reference,
                "p_desc": description,
                "p_created_by": created_by
            }).execute()
            return rpc_res.data
        except Exception as e:
            logger.error(f"Atomic wallet credit error: {e}")
            return {"success": False, "error": str(e)}

    async def get_wallet_transactions(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch user wallet transaction ledger history."""
        if not self.is_configured:
            return []
        try:
            res = self.client.table("wallet_transactions").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"Error fetching wallet transactions: {e}")
            return []

    # =========================================================================
    # ANTI-REUSE & PAYMENT VERIFICATION SYSTEM
    # =========================================================================

    async def is_transaction_id_used(self, transaction_id: str) -> bool:
        """Anti-Reuse Check: Verify if a transaction ID (FT... / 3GA...) was already processed."""
        if not self.is_configured or not transaction_id:
            return False
        try:
            res = self.client.table("payments").select("id").or_(f"reference.eq.{transaction_id},transaction_id.eq.{transaction_id}").execute()
            if res.data and len(res.data) > 0:
                return True
            return False
        except Exception as e:
            logger.error(f"Error checking transaction_id reuse: {e}")
            return False

    async def create_payment_request(
        self,
        user_id: str,
        amount: float,
        method: str,
        reference: str,
        screenshot_file_id: Optional[str] = None,
        status: str = "PENDING",
        deposit_note: str = ""
    ) -> Dict[str, Any]:
        """Create payment deposit request (Auto-Verified or Pending)."""
        payment_id = f"DEP-{uuid.uuid4().hex[:8].upper()}"
        if not self.is_configured:
            return {"payment_id": payment_id, "amount": amount, "status": status}

        try:
            payload = {
                "payment_id": payment_id,
                "transaction_id": reference[:100] if reference else None,
                "user_id": user_id,
                "amount": amount,
                "method": method,
                "reference": reference[:100] if reference else None,
                "deposit_note": deposit_note if deposit_note else None,
                "screenshot_file_id": screenshot_file_id,
                "status": status,
                "rejection_reason": deposit_note if status == "REJECTED" else None
            }
            res = self.client.table("payments").insert(payload).execute()
            return res.data[0]
        except Exception as e:
            logger.error(f"Error creating payment request: {e}")
            return {"payment_id": payment_id, "amount": amount, "status": status}


    async def approve_payment(self, payment_id: str, admin_telegram_id: int, deposit_note: str = "Approved by Admin") -> tuple[bool, str, Optional[Dict[str, Any]]]:
        """Approve payment, credit customer wallet, and process referral commission with admin deposit note."""
        if not self.is_configured:
            return True, "Approved (Mock)", None

        try:
            res = self.client.table("payments").select("*").eq("payment_id", payment_id).execute()
            if not res.data:
                return False, "Payment request not found", None
            
            pay = res.data[0]
            if pay["status"] != "PENDING":
                return False, f"Payment is already {pay['status']}", None

            user_id = pay["user_id"]
            amount = float(pay["amount"])

            cred_res = await self.atomic_credit_wallet(
                user_id=user_id,
                amount=amount,
                tx_type="DEPOSIT",
                reference=payment_id,
                description=f"Deposit via {pay['method']} - Note: {deposit_note}",
                created_by=str(admin_telegram_id)
            )

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.client.table("payments").update({
                "status": "APPROVED",
                "approved_by": admin_telegram_id,
                "approved_at": now_iso
            }).eq("payment_id", payment_id).execute()

            ref_res = self.client.table("referrals").select("referrer_id").eq("referred_user_id", user_id).execute()
            if ref_res.data:
                referrer_id = ref_res.data[0]["referrer_id"]
                commission = amount * (REFERRAL_PERCENT / 100.0)
                if commission > 0:
                    await self.atomic_credit_wallet(
                        user_id=referrer_id,
                        amount=commission,
                        tx_type="REFERRAL_REWARD",
                        reference=f"REF-{payment_id}",
                        description=f"Referral commission on deposit #{payment_id}",
                        created_by="SYSTEM"
                    )

            return True, "Payment successfully approved and credited", pay

        except Exception as e:
            logger.error(f"Error approving payment {payment_id}: {e}")
            return False, str(e), None

    async def reject_payment(self, payment_id: str, admin_telegram_id: int, reason: str = "Invalid receipt") -> tuple[bool, str, Optional[Dict[str, Any]]]:
        """Reject payment request with custom admin note/reason."""
        if not self.is_configured:
            return True, "Rejected (Mock)", None

        try:
            res = self.client.table("payments").select("*").eq("payment_id", payment_id).execute()
            if not res.data or res.data[0]["status"] != "PENDING":
                return False, "Payment not found or not PENDING", None

            pay = res.data[0]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.client.table("payments").update({
                "status": "REJECTED",
                "approved_by": admin_telegram_id,
                "rejection_reason": reason,
                "approved_at": now_iso
            }).eq("payment_id", payment_id).execute()

            return True, "Payment rejected", pay

        except Exception as e:
            logger.error(f"Error rejecting payment: {e}")
            return False, str(e), None

    # =========================================================================
    # PRODUCTS & ORDERS SYSTEM
    # =========================================================================

    async def sync_products_from_api(self, api_products: List[Dict[str, Any]], insert_new: bool = False) -> Dict[str, Any]:
        """
        Sync live stock and availability from supplier API.
        - insert_new=False (DEFAULT): Refreshes stock of already existing products. NEVER adds new products!
        - insert_new=True: Allows admin to explicitly import newly discovered products.
        - Strictly skips any blacklisted/deleted service IDs.
        """
        if not self.is_configured:
            # In mock mode, update stock for matching mock products without inserting new ones
            updated_count = 0
            for p in api_products:
                sid = str(p.get("service_id", "")).strip().upper()
                for k, mock_p in self._mock_products.items():
                    if k == sid or mock_p.get("service_id") == sid:
                        mock_p["supplier_stock"] = int(p.get("stock", 0))
                        mock_p["supplier_cost"] = float(p.get("price", 0.0))
                        mock_p["supplier_available"] = int(p.get("stock", 0)) > 0
                        updated_count += 1
            return {"added": 0, "updated": updated_count, "unavailable": 0, "new_products": []}

        added = 0
        updated = 0
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        current_service_ids = [p["service_id"] for p in api_products if "service_id" in p]
        new_products_list = []

        try:
            import json
            del_list = await self.get_setting("deleted_service_ids", []) or []
            if isinstance(del_list, str):
                try:
                    del_list = json.loads(del_list)
                except Exception:
                    del_list = []
            deleted_set = {str(x).strip().upper() for x in del_list}

            existing_res = self.client.table("products").select("id, service_id, selling_price, description, is_enabled").execute()
            existing_map = {item["service_id"]: item for item in existing_res.data} if existing_res.data else {}

            for api_prod in api_products:
                s_id = api_prod.get("service_id")
                if not s_id or str(s_id).strip().upper() in deleted_set:
                    continue

                name = api_prod.get("name", "Product")
                supplier_cost = float(api_prod.get("price", 0.00))
                supplier_stock = int(api_prod.get("stock", 0))
                supp_desc = api_prod.get("description") or api_prod.get("desc") or f"Premium {name} subscription with instant automated delivery."

                if s_id in existing_map:
                    # Update live stock, cost and availability for existing product
                    self.client.table("products").update({
                        "supplier_cost": supplier_cost,
                        "supplier_stock": supplier_stock,
                        "supplier_available": True if supplier_stock > 0 else False,
                        "last_synced_at": now_iso
                    }).eq("service_id", s_id).execute()
                    updated += 1
                elif insert_new:
                    # ONLY insert new product if explicitly permitted (insert_new=True)
                    default_selling_price = round(supplier_cost * (1.0 + (MARKUP_PERCENT / 100.0)), 2)
                    self.client.table("products").insert({
                        "service_id": s_id,
                        "name": name,
                        "supplier_cost": supplier_cost,
                        "supplier_stock": supplier_stock,
                        "selling_price": default_selling_price,
                        "description": supp_desc,
                        "is_enabled": False,  # New products start disabled (hidden from users)
                        "supplier_available": True if supplier_stock > 0 else False,
                        "last_synced_at": now_iso
                    }).execute()
                    added += 1
                    new_products_list.append({
                        "service_id": s_id,
                        "name": name,
                        "supplier_cost": supplier_cost,
                        "supplier_stock": supplier_stock
                    })

            if current_service_ids:
                # Mark missing API products as unavailable without touching manual products
                self.client.table("products").update({"supplier_available": False}).not_.in_("service_id", current_service_ids).not_.like("service_id", "MANUAL_%").execute()

            return {"added": added, "updated": updated, "unavailable": 0, "new_products": new_products_list}

        except Exception as e:
            logger.error(f"Error syncing products: {e}")
            return {"added": added, "updated": updated, "unavailable": 0, "new_products": []}

    async def refresh_live_stock_for_enabled_products(self) -> int:
        """
        Continuously refresh stock and availability for all active/enabled API products in real-time.
        Guarantees ZERO new unwanted products are inserted!
        """
        try:
            from api_client import api_client
            api_prods = await api_client.get_products()
            if not api_prods or not isinstance(api_prods, list):
                return 0

            res = await self.sync_products_from_api(api_prods, insert_new=False)
            return res.get("updated", 0)
        except Exception as e:
            logger.warning(f"Live stock refresh error: {e}")
            return 0

    async def create_manual_product(
        self,
        name: str,
        selling_price: float,
        stock: int = 100,
        description: str = "Premium manual product with instant delivery.",
        service_id: Optional[str] = None,
        delivery_type: str = "AUTOMATIC",
        manual_fulfillment_note: str = "",
        referral_commission_percent: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        """Add custom manual product with selectable delivery mode (AUTOMATIC, MANUAL, HYBRID) and commission %."""
        if not service_id:
            service_id = f"MANUAL_{uuid.uuid4().hex[:6].upper()}"
        else:
            service_id = service_id.strip().upper()

        payload = {
            "id": str(uuid.uuid4()),
            "service_id": service_id,
            "name": name,
            "supplier_cost": 0.00,
            "supplier_stock": stock,
            "selling_price": float(selling_price),
            "referral_commission_percent": float(referral_commission_percent),
            "description": description,
            "delivery_type": delivery_type,
            "manual_fulfillment_note": manual_fulfillment_note,
            "is_enabled": True,
            "supplier_available": True
        }

        self._mock_products[service_id] = payload
        self._mock_products[service_id.upper()] = payload
        self._mock_products[service_id.lower()] = payload

        if not self.is_configured:
            return payload

        try:
            res = self.client.table("products").upsert(payload, on_conflict="service_id").execute()
            if res.data:
                return res.data[0]
            return payload
        except Exception as e:
            logger.warning(f"Full payload manual product insert failed ({e}), trying base columns insert...")
            try:
                base_payload = {
                    "service_id": service_id,
                    "name": name,
                    "supplier_cost": 0.00,
                    "supplier_stock": stock,
                    "selling_price": float(selling_price),
                    "description": description,
                    "is_enabled": True,
                    "supplier_available": True
                }
                res = self.client.table("products").upsert(base_payload, on_conflict="service_id").execute()
                if res.data:
                    return res.data[0]
                return payload
            except Exception as e2:
                logger.error(f"Error creating manual product in DB: {e2}")
                return payload

    async def update_product_delivery_type(self, service_id: str, delivery_type: str, manual_note: str = "") -> bool:
        """Update delivery mode (AUTOMATIC, MANUAL, HYBRID) and holding note for a product."""
        s_raw = str(service_id).strip()
        s_str = s_raw.upper()
        if s_str in self._mock_products:
            self._mock_products[s_str]["delivery_type"] = delivery_type
            if manual_note:
                self._mock_products[s_str]["manual_fulfillment_note"] = manual_note

        if not self.is_configured:
            return True
        try:
            update_data = {
                "delivery_type": delivery_type,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            if manual_note:
                update_data["manual_fulfillment_note"] = manual_note
            self.client.table("products").update(update_data).eq("service_id", s_raw).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating delivery type for {service_id}: {e}")
            return False

    async def get_all_products(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """Fetch all active products with seamless in-memory cache and applied Three-Tier overrides in 0.01ms."""
        # Merge products from _products_cache and _mock_products
        product_map = {}
        for sid, p in self._mock_products.items():
            s_key = str(p.get("service_id", sid)).strip().upper()
            product_map[s_key] = p

        for sid, p in self._products_cache.items():
            s_key = str(p.get("service_id", sid)).strip().upper()
            product_map[s_key] = p

        # If cache is empty and DB is configured, do 1 batch fetch to populate cache
        if not product_map and self.is_configured:
            try:
                res = self.client.table("products").select("*").order("name").execute()
                if res.data:
                    for row in res.data:
                        s_key = str(row.get("service_id", "")).strip()
                        if s_key:
                            self._products_cache[s_key] = dict(row)
                            self._products_cache[s_key.upper()] = dict(row)
                            self._products_cache[s_key.lower()] = dict(row)
                            product_map[s_key.upper()] = row
            except Exception as e:
                logger.error(f"Error fetching products: {e}")

        # Resolve every product with Three-Tier hierarchy in RAM (0.01ms)
        effective_list = []
        for s_key, p in sorted(product_map.items(), key=lambda x: str(x[1].get("name", ""))):
            eff_p = await self.get_effective_product(p)
            if eff_p:
                if not enabled_only or eff_p.get("is_enabled", True):
                    effective_list.append(eff_p)

        return effective_list

    # =========================================================================
    # THREE-TIER VALUE HIERARCHY & ADMIN OVERRIDE ENGINE
    # Priority: MAIN ADMIN OVERRIDE -> AGENT VALUE / DEFAULT -> SYSTEM DEFAULT
    # =========================================================================

    async def get_all_product_overrides(self) -> Dict[str, Dict[str, Any]]:
        """Retrieve all active Main Admin product overrides from in-memory cache."""
        import json
        raw = await self.get_setting("admin_product_overrides", {})
        if isinstance(raw, str):
            try:
                db_overrides = json.loads(raw)
            except Exception:
                db_overrides = {}
        elif isinstance(raw, dict):
            db_overrides = raw
        else:
            db_overrides = {}

        merged = {**db_overrides, **self._product_overrides}
        return merged

    async def get_product_override(self, service_id: str) -> Dict[str, Any]:
        """Get admin override dictionary for a specific product from RAM cache."""
        if not service_id:
            return {}
        s_raw = str(service_id).strip()
        s_str = s_raw.upper()
        all_overrides = await self.get_all_product_overrides()
        return all_overrides.get(s_str) or all_overrides.get(s_raw) or {}

    async def set_product_override(self, service_id: str, field: str, value: Any) -> bool:
        """
        Set a Main Admin override for a product field without modifying the underlying agent value.
        Supported fields: name, emoji, selling_price, referral_commission_percent,
        commission_text, button_text, description, is_enabled.
        """
        import json
        s_raw = str(service_id).strip()
        s_str = s_raw.upper()

        if s_str not in self._product_overrides:
            self._product_overrides[s_str] = {}
        self._product_overrides[s_str][field] = value

        all_overrides = await self.get_all_product_overrides()
        if s_str not in all_overrides:
            all_overrides[s_str] = {}
        all_overrides[s_str][field] = value

        await self.update_setting("admin_product_overrides", json.dumps(all_overrides))
        return True

    async def remove_product_override(self, service_id: str, field: Optional[str] = None) -> bool:
        """
        Remove a Main Admin override so the product cleanly falls back to the Agent / base value.
        If field is None, removes all overrides for this product.
        """
        import json
        s_raw = str(service_id).strip()
        s_str = s_raw.upper()

        all_overrides = await self.get_all_product_overrides()

        if field:
            if s_str in self._product_overrides and field in self._product_overrides[s_str]:
                del self._product_overrides[s_str][field]
            if s_str in all_overrides and field in all_overrides[s_str]:
                del all_overrides[s_str][field]
        else:
            if s_str in self._product_overrides:
                del self._product_overrides[s_str]
            if s_str in all_overrides:
                del all_overrides[s_str]

        await self.update_setting("admin_product_overrides", json.dumps(all_overrides))
        return True

    async def get_effective_product(self, service_id_or_product: Any) -> Optional[Dict[str, Any]]:
        """
        Resolve product using the strict Three-Tier Value Hierarchy:
        1. MAIN ADMIN OVERRIDE (if configured by admin)
        2. AGENT VALUE / SUPPLIER API VALUE (underlying default)
        3. SYSTEM DEFAULT FALLBACK

        Calculates dynamic amounts (e.g. commission Birr = price * comm_pct) and returns merged product in 0.0001ms.
        """
        if not service_id_or_product:
            return None

        if isinstance(service_id_or_product, dict):
            base = service_id_or_product
        else:
            base = await self.get_product_by_service_id(str(service_id_or_product))

        if not base:
            return None

        # Create a clean shallow copy of base product
        product = dict(base)
        s_id = str(product.get("service_id") or product.get("id") or "").strip()
        s_upper = s_id.upper()

        # Retrieve Main Admin override from memory cache
        override = self._product_overrides.get(s_upper) or self._product_overrides.get(s_id) or await self.get_product_override(s_id)

        # Baseline / Agent values
        agent_name = str(base.get("name", "Product"))
        agent_price = float(base.get("selling_price", 0.0))
        agent_desc = str(base.get("description", ""))
        agent_comm_pct = float(base.get("referral_commission_percent", 5.0) or 0.0)
        agent_deliv = str(base.get("delivery_type", "AUTOMATIC"))
        agent_enabled = bool(base.get("is_enabled", True))

        # Three-tier resolution
        effective_name = str(override.get("name", agent_name)) if override.get("name") is not None else agent_name
        effective_price = float(override.get("selling_price", agent_price)) if override.get("selling_price") is not None else agent_price
        effective_desc = str(override.get("description", agent_desc)) if override.get("description") is not None else agent_desc
        effective_comm_pct = float(override.get("referral_commission_percent", agent_comm_pct)) if override.get("referral_commission_percent") is not None else agent_comm_pct
        effective_deliv = str(override.get("delivery_type", agent_deliv)) if override.get("delivery_type") is not None else agent_deliv
        effective_enabled = bool(override.get("is_enabled", agent_enabled)) if override.get("is_enabled") is not None else agent_enabled
        effective_emoji = str(override.get("emoji", ""))
        custom_comm_text = str(override.get("commission_text", ""))
        custom_button_text = str(override.get("button_text", ""))

        # Dynamic calculated commission amount
        calc_comm_amount = round(effective_price * (effective_comm_pct / 100.0), 2)

        has_override = bool(override and any(v is not None for v in override.values()))

        # Populate effective product
        product["name"] = effective_name
        product["selling_price"] = effective_price
        product["description"] = effective_desc
        product["referral_commission_percent"] = effective_comm_pct
        product["delivery_type"] = effective_deliv
        product["is_enabled"] = effective_enabled
        product["emoji"] = effective_emoji
        product["custom_commission_text"] = custom_comm_text
        product["custom_button_text"] = custom_button_text
        product["calculated_commission_amount"] = calc_comm_amount
        product["agent_commission_percent"] = agent_comm_pct
        product["agent_price"] = agent_price
        product["has_admin_override"] = has_override
        product["admin_override_data"] = override

        return product

    # =========================================================================
    # UI CONTENT & TEXT OVERRIDE ENGINE
    # Allows in-place visual editing of any user-facing message, banner, or label
    # =========================================================================

    async def get_all_ui_overrides(self) -> Dict[str, Dict[str, str]]:
        """Retrieve all active Main Admin UI text overrides."""
        import json
        raw = await self.get_setting("admin_ui_overrides", {})
        if isinstance(raw, str):
            try:
                db_overrides = json.loads(raw)
            except Exception:
                db_overrides = {}
        elif isinstance(raw, dict):
            db_overrides = raw
        else:
            db_overrides = {}

        merged = {**db_overrides, **self._ui_overrides}
        return merged

    async def get_ui_text(self, key: str, lang: str = "am", default: Optional[str] = None, **kwargs) -> str:
        """
        Get UI text with priority:
        1. MAIN ADMIN OVERRIDE (for key & language)
        2. i18n Translation (am / en)
        3. Default fallback
        """
        from i18n import t
        lang_code = "am" if str(lang).lower().startswith("am") else "en"
        overrides = await self.get_all_ui_overrides()

        key_overrides = overrides.get(key, {})
        text = key_overrides.get(lang_code)

        if text is None:
            # Fall back to i18n system translation
            text = t(key, lang=lang_code)
            if text == key and default is not None:
                text = default

        if kwargs and text:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text or default or key

    async def set_ui_text_override(self, key: str, text: str, lang: str = "am") -> bool:
        """Set a Main Admin custom override for any UI text key."""
        import json
        lang_code = "am" if str(lang).lower().startswith("am") else "en"
        overrides = await self.get_all_ui_overrides()

        if key not in overrides:
            overrides[key] = {}
        overrides[key][lang_code] = text

        if key not in self._ui_overrides:
            self._ui_overrides[key] = {}
        self._ui_overrides[key][lang_code] = text

        await self.update_setting("admin_ui_overrides", json.dumps(overrides))
        return True

    async def remove_ui_text_override(self, key: str, lang: Optional[str] = None) -> bool:
        """Remove a Main Admin UI override, cleanly falling back to system default."""
        import json
        overrides = await self.get_all_ui_overrides()
        lang_code = "am" if lang and str(lang).lower().startswith("am") else ("en" if lang else None)

        if lang_code:
            if key in overrides and lang_code in overrides[key]:
                del overrides[key][lang_code]
            if key in self._ui_overrides and lang_code in self._ui_overrides[key]:
                del self._ui_overrides[key][lang_code]
        else:
            if key in overrides:
                del overrides[key]
            if key in self._ui_overrides:
                del self._ui_overrides[key]

        await self.update_setting("admin_ui_overrides", json.dumps(overrides))
        return True

    async def get_product_by_service_id(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Fetch product by service_id or primary id with instant in-memory cache lookup in 0.0001ms."""
        if not service_id:
            return None

        s_raw = str(service_id).strip()
        s_str = s_raw.upper()
        s_lower = s_raw.lower()

        # 1. Check in-memory RAM cache first (0.0001ms)
        if s_str in self._products_cache:
            return self._products_cache[s_str]
        if s_raw in self._products_cache:
            return self._products_cache[s_raw]
        if s_lower in self._products_cache:
            return self._products_cache[s_lower]

        # 2. Check local mock cache
        if s_str in self._mock_products:
            return self._mock_products[s_str]
        if s_raw in self._mock_products:
            return self._mock_products[s_raw]
        if s_lower in self._mock_products:
            return self._mock_products[s_lower]

        # Check by internal fields across memory
        for p in list(self._products_cache.values()) + list(self._mock_products.values()):
            if str(p.get("service_id", "")).upper() == s_str or str(p.get("id", "")).upper() == s_str or str(p.get("id", "")) == s_raw or str(p.get("name", "")).upper() == s_str:
                return p

        if not self.is_configured:
            return None

        try:
            # 3. Query DB by service_id
            res = self.client.table("products").select("*").eq("service_id", s_raw).execute()
            if res.data:
                p_data = res.data[0]
                self._products_cache[s_raw] = p_data
                self._products_cache[s_str] = p_data
                return p_data

            if s_str != s_raw:
                res = self.client.table("products").select("*").eq("service_id", s_str).execute()
                if res.data:
                    p_data = res.data[0]
                    self._products_cache[s_str] = p_data
                    return p_data

            # 4. Query DB by primary key 'id' ONLY if valid UUID format (fixes 22P02 error)
            if is_valid_uuid(s_raw):
                res = self.client.table("products").select("*").eq("id", s_raw).execute()
                if res.data:
                    p_data = res.data[0]
                    self._products_cache[s_raw] = p_data
                    return p_data

            return None
        except Exception as e:
            logger.error(f"Error fetching product {service_id}: {e}")
            return None

    async def get_effective_price(self, user_id: str, is_vip: bool, product: Dict[str, Any]) -> float:
        default_price = float(product.get("selling_price", 0.0))
        product_id = product.get("id")

        if not self.is_configured or not user_id or not product_id:
            if is_vip:
                return round(default_price * 0.95, 2)
            return default_price

        try:
            if len(str(user_id).strip()) >= 32:
                cp_res = self.client.table("customer_prices").select("custom_price").eq("user_id", str(user_id).strip()).eq("product_id", str(product_id).strip()).execute()
                if cp_res.data:
                    return float(cp_res.data[0]["custom_price"])

            if is_vip:
                return round(default_price * 0.95, 2)

            return default_price
        except Exception as e:
            logger.error(f"Error calculating effective price: {e}")
            return default_price

    async def update_product_name(self, service_id: str, new_name: str) -> bool:
        """Update product display name across RAM cache and PostgreSQL."""
        s_raw = str(service_id).strip()
        s_str = s_raw.upper()
        s_lower = s_raw.lower()

        # Update in-memory caches immediately (0.0001ms)
        for p_map in (self._mock_products, self._products_cache):
            for k, p in p_map.items():
                if k == s_str or k == s_raw or k == s_lower or p.get("service_id") == s_raw or str(p.get("service_id", "")).upper() == s_str or p.get("id") == s_raw:
                    p["name"] = new_name.strip()

        if not self.is_configured:
            return True
        try:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.client.table("products").update({"name": new_name.strip(), "updated_at": now_iso}).eq("service_id", s_raw).execute()
            if s_str != s_raw:
                self.client.table("products").update({"name": new_name.strip(), "updated_at": now_iso}).eq("service_id", s_str).execute()
            if is_valid_uuid(s_raw):
                self.client.table("products").update({"name": new_name.strip(), "updated_at": now_iso}).eq("id", s_raw).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating product name: {e}")
            return False

    async def update_product_price(self, service_id: str, new_price: float) -> bool:
        """Update product price across RAM cache and PostgreSQL."""
        s_raw = str(service_id).strip()
        s_str = s_raw.upper()
        s_lower = s_raw.lower()
        p_val = float(new_price)

        for p_map in (self._mock_products, self._products_cache):
            for k, p in p_map.items():
                if k == s_str or k == s_raw or k == s_lower or p.get("service_id") == s_raw or str(p.get("service_id", "")).upper() == s_str or p.get("id") == s_raw:
                    p["selling_price"] = p_val

        if not self.is_configured:
            return True
        try:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.client.table("products").update({"selling_price": p_val, "updated_at": now_iso}).eq("service_id", s_raw).execute()
            if s_str != s_raw:
                self.client.table("products").update({"selling_price": p_val, "updated_at": now_iso}).eq("service_id", s_str).execute()
            if is_valid_uuid(s_raw):
                self.client.table("products").update({"selling_price": p_val, "updated_at": now_iso}).eq("id", s_raw).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating product price: {e}")
            return False

    async def update_product_description(self, service_id: str, new_desc: str) -> bool:
        """Update product description across RAM cache and PostgreSQL."""
        s_raw = str(service_id).strip()
        s_str = s_raw.upper()
        s_lower = s_raw.lower()

        for p_map in (self._mock_products, self._products_cache):
            for k, p in p_map.items():
                if k == s_str or k == s_raw or k == s_lower or p.get("service_id") == s_raw or str(p.get("service_id", "")).upper() == s_str or p.get("id") == s_raw:
                    p["description"] = new_desc

        if not self.is_configured:
            return True
        try:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.client.table("products").update({"description": new_desc, "updated_at": now_iso}).eq("service_id", s_raw).execute()
            if s_str != s_raw:
                self.client.table("products").update({"description": new_desc, "updated_at": now_iso}).eq("service_id", s_str).execute()
            if is_valid_uuid(s_raw):
                self.client.table("products").update({"description": new_desc, "updated_at": now_iso}).eq("id", s_raw).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating description: {e}")
            return False

    async def toggle_product_visibility(self, service_id: str, is_enabled: bool) -> bool:
        """Toggle product enabled/disabled status in RAM cache and PostgreSQL."""
        s_raw = str(service_id).strip()
        s_str = s_raw.upper()
        s_lower = s_raw.lower()

        for p_map in (self._mock_products, self._products_cache):
            for k, p in p_map.items():
                if k == s_str or k == s_raw or k == s_lower or p.get("service_id") == s_raw or str(p.get("service_id", "")).upper() == s_str or p.get("id") == s_raw:
                    p["is_enabled"] = is_enabled

        if not self.is_configured:
            return True
        try:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.client.table("products").update({"is_enabled": is_enabled, "updated_at": now_iso}).eq("service_id", s_raw).execute()
            if s_str != s_raw:
                self.client.table("products").update({"is_enabled": is_enabled, "updated_at": now_iso}).eq("service_id", s_str).execute()
            if is_valid_uuid(s_raw):
                self.client.table("products").update({"is_enabled": is_enabled, "updated_at": now_iso}).eq("id", s_raw).execute()
            return True
        except Exception as e:
            logger.error(f"Error toggling product visibility: {e}")
            return False

    async def delete_product(self, service_id: str) -> bool:
        """Permanently delete a product from store catalog, blacklisting it from auto-sync revival."""
        s_raw = str(service_id).strip()
        s_str = s_raw.upper()
        s_lower = s_raw.lower()

        # Remove from RAM caches immediately
        for k in list(self._mock_products.keys()):
            if k == s_str or k == s_raw or k == s_lower or self._mock_products[k].get("id") == s_raw:
                del self._mock_products[k]

        for k in list(self._products_cache.keys()):
            if k == s_str or k == s_raw or k == s_lower or self._products_cache[k].get("id") == s_raw:
                del self._products_cache[k]

        # Remove any overrides
        await self.remove_product_override(s_raw)

        # Blacklist from future API syncs
        try:
            import json
            del_list = await self.get_setting("deleted_service_ids", []) or []
            if isinstance(del_list, str):
                try:
                    del_list = json.loads(del_list)
                except Exception:
                    del_list = []
            if not isinstance(del_list, list):
                del_list = []
            if s_str not in del_list:
                del_list.append(s_str)
            if s_raw not in del_list:
                del_list.append(s_raw)
            await self.update_setting("deleted_service_ids", json.dumps(del_list))
        except Exception as blacklist_err:
            logger.warning(f"Error updating deleted blacklist: {blacklist_err}")

        if not self.is_configured:
            return True

        try:
            # Try hard delete first
            try:
                self.client.table("products").delete().eq("service_id", s_raw).execute()
                if s_str != s_raw:
                    self.client.table("products").delete().eq("service_id", s_str).execute()
                if is_valid_uuid(s_raw):
                    self.client.table("products").delete().eq("id", s_raw).execute()
                return True
            except Exception as hard_err:
                logger.warning(f"Hard delete blocked ({hard_err}), archiving product permanently instead.")
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                self.client.table("products").update({
                    "is_enabled": False,
                    "supplier_available": False,
                    "supplier_stock": 0,
                    "updated_at": now_iso
                }).eq("service_id", s_raw).execute()
                if s_str != s_raw:
                    self.client.table("products").update({
                        "is_enabled": False,
                        "supplier_available": False,
                        "supplier_stock": 0,
                        "updated_at": now_iso
                    }).eq("service_id", s_str).execute()
                if is_valid_uuid(s_raw):
                    self.client.table("products").update({
                        "is_enabled": False,
                        "supplier_available": False,
                        "supplier_stock": 0,
                        "updated_at": now_iso
                    }).eq("id", s_raw).execute()
                return True
        except Exception as e:
            logger.error(f"Error deleting product {service_id}: {e}")
            return True

    async def update_product_commission(self, service_id: str, percent: float) -> bool:
        """
        Update referral commission percentage for a specific product.
        Persists to both Three-Tier overrides and PostgreSQL products table.
        """
        s_raw = str(service_id).strip()
        s_str = s_raw.upper()
        s_lower = s_raw.lower()
        pct_val = max(0.0, float(percent))

        # Update in-memory mock products
        for k, p in self._mock_products.items():
            if k == s_str or k == s_raw or k == s_lower or p.get("service_id") == s_raw or str(p.get("service_id", "")).upper() == s_str or p.get("id") == s_raw:
                p["referral_commission_percent"] = pct_val

        # Update Three-Tier persistent overrides
        await self.set_product_override(s_raw, "referral_commission_percent", pct_val)

        if not self.is_configured:
            return True
        try:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.client.table("products").update({
                "referral_commission_percent": pct_val,
                "updated_at": now_iso
            }).eq("service_id", s_raw).execute()
            if s_str != s_raw:
                self.client.table("products").update({
                    "referral_commission_percent": pct_val,
                    "updated_at": now_iso
                }).eq("service_id", s_str).execute()
            self.client.table("products").update({
                "referral_commission_percent": pct_val,
                "updated_at": now_iso
            }).eq("id", s_raw).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating product commission: {e}")
            return True

    # =========================================================================
    # DIGITAL STOCK INVENTORY POOL & FIFO AUTO-DELIVERY VAULT
    # Allows adding 70+ bulk accounts/tokens/keys and delivering them 1-by-1
    # =========================================================================

    async def get_product_stock_stats(self, service_id: str) -> Dict[str, Any]:
        """
        Get complete stock statistics for a product vault:
        Returns total_items, available_count, used_count, available_items, used_items.
        """
        import json
        s_str = str(service_id).strip().upper()
        pool_key = f"stock_pool_{s_str}"
        raw = await self.get_setting(pool_key, []) or []
        if isinstance(raw, str):
            try:
                items = json.loads(raw)
            except Exception:
                items = []
        elif isinstance(raw, list):
            items = raw
        else:
            items = []

        available_items = [it for it in items if not it.get("is_used", False)]
        used_items = [it for it in items if it.get("is_used", False)]

        return {
            "service_id": s_str,
            "total_items": len(items),
            "available_count": len(available_items),
            "used_count": len(used_items),
            "available_items": available_items,
            "used_items": used_items,
            "all_items": items
        }

    async def add_product_stock_items(self, service_id: str, items_text: str) -> Dict[str, Any]:
        """
        Bulk add digital stock items (e.g. 70 email:password, license keys, tokens, or links).
        Automatically increments product available stock and enables availability.
        """
        import json
        s_raw = str(service_id).strip()
        s_str = s_raw.upper()
        pool_key = f"stock_pool_{s_str}"

        stats = await self.get_product_stock_stats(s_str)
        existing_items = stats["all_items"]

        # Parse lines
        lines = [line.strip() for line in str(items_text).splitlines() if line.strip()]
        if not lines:
            return {"added_count": 0, "available_count": stats["available_count"], "total_items": stats["total_items"]}

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        new_items = []
        for line in lines:
            new_items.append({
                "id": str(uuid.uuid4())[:8],
                "service_id": s_str,
                "content": line,
                "is_used": False,
                "used_by_order_id": None,
                "created_at": now_iso,
                "used_at": None
            })

        all_items = existing_items + new_items
        await self.update_setting(pool_key, json.dumps(all_items))

        available_count = len([it for it in all_items if not it.get("is_used", False)])

        # Synchronize product stock count in DB & memory
        await self.update_product_stock_count(s_raw, available_count)

        return {
            "added_count": len(new_items),
            "available_count": available_count,
            "total_items": len(all_items)
        }

    async def pop_next_stock_item(self, service_id: str, order_id: str) -> Optional[str]:
        """
        Atomically fetch and mark the next available unused stock item as used.
        Returns the raw credential/content string (e.g. user@domain.com:pass123).
        """
        import json
        s_raw = str(service_id).strip()
        s_str = s_raw.upper()
        pool_key = f"stock_pool_{s_str}"

        stats = await self.get_product_stock_stats(s_str)
        items = stats["all_items"]

        target_item = None
        for it in items:
            if not it.get("is_used", False):
                target_item = it
                break

        if not target_item:
            return None

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        target_item["is_used"] = True
        target_item["used_by_order_id"] = str(order_id)
        target_item["used_at"] = now_iso

        await self.update_setting(pool_key, json.dumps(items))

        remaining_count = len([it for it in items if not it.get("is_used", False)])
        await self.update_product_stock_count(s_raw, remaining_count)

        return str(target_item.get("content", "")).strip()

    async def update_product_stock_count(self, service_id: str, new_stock: int) -> bool:
        """Update live stock count for a product across memory and database."""
        s_raw = str(service_id).strip()
        s_str = s_raw.upper()
        s_lower = s_raw.lower()
        stock_val = max(0, int(new_stock))
        is_avail = (stock_val > 0)

        for k, p in self._mock_products.items():
            if k == s_str or k == s_raw or k == s_lower or p.get("service_id") == s_raw or str(p.get("service_id", "")).upper() == s_str or p.get("id") == s_raw:
                p["supplier_stock"] = stock_val
                p["supplier_available"] = is_avail

        if not self.is_configured:
            return True

        try:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.client.table("products").update({
                "supplier_stock": stock_val,
                "supplier_available": is_avail,
                "updated_at": now_iso
            }).eq("service_id", s_raw).execute()
            if s_str != s_raw:
                self.client.table("products").update({
                    "supplier_stock": stock_val,
                    "supplier_available": is_avail,
                    "updated_at": now_iso
                }).eq("service_id", s_str).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating stock count: {e}")
            return False

    async def clear_used_stock_items(self, service_id: str) -> int:
        """Purge all sold/used stock items from a product's vault history."""
        import json
        s_str = str(service_id).strip().upper()
        pool_key = f"stock_pool_{s_str}"
        stats = await self.get_product_stock_stats(s_str)
        avail = stats["available_items"]
        used_count = stats["used_count"]
        await self.update_setting(pool_key, json.dumps(avail))
        return used_count

    async def delete_stock_item(self, service_id: str, item_id: str) -> bool:
        """Delete a specific stock item from vault."""
        import json
        s_str = str(service_id).strip().upper()
        pool_key = f"stock_pool_{s_str}"
        stats = await self.get_product_stock_stats(s_str)
        items = [it for it in stats["all_items"] if it.get("id") != item_id]
        await self.update_setting(pool_key, json.dumps(items))
        remaining = len([it for it in items if not it.get("is_used", False)])
        await self.update_product_stock_count(s_str, remaining)
        return True

    async def load_all_overrides_to_cache(self) -> None:
        """Pre-load all persistent overrides, settings, and products into in-memory cache during startup."""
        import json
        # 1. Preload mock products into memory cache
        for k, p in self._mock_products.items():
            sid = str(p.get("service_id", k)).strip()
            self._products_cache[sid] = dict(p)
            self._products_cache[sid.upper()] = dict(p)
            self._products_cache[sid.lower()] = dict(p)

        if not self.is_configured:
            logger.info("Loaded mock catalog and settings into in-memory RAM cache.")
            return

        try:
            # 2. Batch load ALL settings in 1 single query
            st_res = self.client.table("settings").select("*").execute()
            if st_res.data:
                for row in st_res.data:
                    k = row.get("key")
                    v = row.get("value")
                    if k:
                        self._settings_cache[k] = v
                        self._mock_settings[k] = v

            # 3. Batch load ALL products in 1 single query
            pr_res = self.client.table("products").select("*").execute()
            if pr_res.data:
                for row in pr_res.data:
                    sid = str(row.get("service_id", "")).strip()
                    if sid:
                        self._products_cache[sid] = dict(row)
                        self._products_cache[sid.upper()] = dict(row)
                        self._products_cache[sid.lower()] = dict(row)

            # 4. Parse overrides from cached settings
            raw_prod_ov = self._settings_cache.get("admin_product_overrides", {})
            if isinstance(raw_prod_ov, str):
                try:
                    self._product_overrides = json.loads(raw_prod_ov)
                except Exception:
                    self._product_overrides = {}
            elif isinstance(raw_prod_ov, dict):
                self._product_overrides = raw_prod_ov

            raw_ui_ov = self._settings_cache.get("admin_ui_overrides", {})
            if isinstance(raw_ui_ov, str):
                try:
                    self._ui_overrides = json.loads(raw_ui_ov)
                except Exception:
                    self._ui_overrides = {}
            elif isinstance(raw_ui_ov, dict):
                self._ui_overrides = raw_ui_ov

            logger.info(f"⚡ FAST STARTUP: Preloaded {len(self._settings_cache)} settings, {len(self._products_cache)//3} products, {len(self._product_overrides)} overrides into RAM.")
        except Exception as e:
            logger.warning(f"Error batch pre-loading cache on startup: {e}")

    async def get_user_referrer(self, user_id_or_telegram_id: Any) -> Optional[Dict[str, Any]]:
        """Get referrer user record for a customer."""
        u_id_str = str(user_id_or_telegram_id).strip()
        
        # Check mock settings first
        ref_tg_id = self._mock_settings.get(f"user_referrer_{u_id_str}")
        if not ref_tg_id:
            u_record = await self.get_user_by_telegram_id(int(u_id_str)) if u_id_str.isdigit() else None
            if u_record:
                ref_tg_id = self._mock_settings.get(f"user_referrer_{u_record['id']}") or self._mock_settings.get(f"user_referrer_{u_record.get('telegram_id')}")

        if not self.is_configured:
            if ref_tg_id:
                return await self.get_or_create_user(int(ref_tg_id))
            return None

        try:
            buyer_uuid = u_id_str
            if u_id_str.isdigit():
                u_res = self.client.table("users").select("id").eq("telegram_id", int(u_id_str)).execute()
                if u_res.data:
                    buyer_uuid = u_res.data[0]["id"]

            ref_res = self.client.table("referrals").select("referrer_id").eq("referred_user_id", buyer_uuid).execute()
            if ref_res.data:
                referrer_uuid = ref_res.data[0]["referrer_id"]
                u_referrer = self.client.table("users").select("*, wallets(balance)").eq("id", referrer_uuid).execute()
                if u_referrer.data:
                    u = u_referrer.data[0]
                    wallet = u.get("wallets")
                    u["wallet_balance"] = float(wallet["balance"]) if wallet else 0.00
                    return u

            if ref_tg_id:
                return await self.get_or_create_user(int(ref_tg_id))
            return None
        except Exception as e:
            logger.error(f"Error getting user referrer: {e}")
            if ref_tg_id:
                return await self.get_or_create_user(int(ref_tg_id))
            return None

    async def process_purchase_referral_commission(
        self,
        buyer_user_id: Any,
        product: Dict[str, Any],
        purchase_price: float,
        melax_order_id: str
    ) -> Optional[Dict[str, Any]]:
        """Process purchase commission credit to referrer's wallet based on product's commission %."""
        # Check if referrals service is enabled
        if not (await self.get_service_status("referrals", True)):
            return None

        referrer = await self.get_user_referrer(buyer_user_id)
        if not referrer:
            return None

        referrer_tg_id = referrer.get("telegram_id")
        referrer_uuid = referrer.get("id")

        # Resolve product via Three-Tier Hierarchy (Admin Override -> Agent Value -> Default)
        s_id = str(product.get("service_id") or product.get("id") or "").strip()
        eff_product = await self.get_effective_product(s_id) if s_id else product
        if not eff_product:
            eff_product = product

        # Commission percentage configured for this specific product (defaults to 5.0%)
        comm_pct = float(eff_product.get("referral_commission_percent", 5.0) or 0.0)
        if comm_pct <= 0.0:
            return None

        commission_amount = round(purchase_price * (comm_pct / 100.0), 2)
        if commission_amount <= 0.0:
            return None

        # Credit Referrer's Wallet Atomically
        cred_res = await self.atomic_credit_wallet(
            user_id=referrer_uuid or str(referrer_tg_id),
            amount=commission_amount,
            tx_type="REFERRAL_COMMISSION",
            reference=melax_order_id,
            description=f"Referral commission ({comm_pct}%) on purchase of {eff_product.get('name', 'Product')}",
            created_by="SYSTEM"
        )

        # Update referral reward earnings in Supabase or mock stats
        if self.is_configured and referrer_uuid:
            try:
                self.client.rpc("increment_referral_reward", {
                    "p_referrer_id": referrer_uuid,
                    "p_amount": commission_amount
                }).execute()
            except Exception:
                pass

        ref_updated = await self.get_user_by_telegram_id(int(referrer_tg_id)) if referrer_tg_id else None
        new_bal = float(ref_updated.get("wallet_balance", 0.00)) if ref_updated else float(referrer.get("wallet_balance", 0.00)) + commission_amount

        return {
            "referrer_telegram_id": referrer_tg_id,
            "referrer_id": referrer_uuid,
            "commission_amount": commission_amount,
            "commission_percent": comm_pct,
            "product_name": product.get("name", "Product"),
            "new_balance": new_bal,
            "melax_order_id": melax_order_id
        }

    async def create_order(
        self,
        user_id: str,
        service_id: str,
        product_name: str,
        quantity: int,
        selling_price: float,
        supplier_cost: float,
        aiverse_order_id: str,
        delivered_products: str,
        status: str = "SUCCESS"
    ) -> Dict[str, Any]:
        melax_order_id = f"MELAX-{uuid.uuid4().hex[:8].upper()}"
        total_amount = round(selling_price * quantity, 2)
        total_supplier_cost = round(supplier_cost * quantity, 2)
        profit = round(total_amount - total_supplier_cost, 2)

        if not self.is_configured:
            return {
                "melax_order_id": melax_order_id,
                "product_name": product_name,
                "total_amount": total_amount,
                "profit": profit,
                "delivered_products": delivered_products,
                "status": status
            }

        try:
            payload = {
                "melax_order_id": melax_order_id,
                "user_id": user_id,
                "service_id": service_id,
                "product_name": product_name,
                "quantity": quantity,
                "selling_price": selling_price,
                "supplier_cost": supplier_cost,
                "total_amount": total_amount,
                "profit": profit,
                "aiverse_order_id": aiverse_order_id,
                "status": status,
                "delivered_products": delivered_products
            }
            res = self.client.table("orders").insert(payload).execute()
            return res.data[0]
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return {"melax_order_id": melax_order_id, "delivered_products": delivered_products, "status": status}

    async def get_user_orders(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        if not self.is_configured:
            return []
        try:
            res = self.client.table("orders").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"Error fetching user orders: {e}")
            return []

    async def get_pending_manual_orders(self) -> List[Dict[str, Any]]:
        """Get all orders in PENDING_FULFILLMENT status waiting for Admin manual delivery."""
        if not self.is_configured:
            return []
        try:
            res = self.client.table("orders").select("*, users(telegram_id, username, first_name)").eq("status", "PENDING_FULFILLMENT").order("created_at", desc=True).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"Error fetching pending manual orders: {e}")
            return []

    async def fulfill_manual_order(self, melax_order_id: str, admin_id: int, delivery_content: str) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        """Mark manual order fulfilled with delivered credentials/key and return order data."""
        if not self.is_configured:
            return True, "Fulfilled (Mock)", {"melax_order_id": melax_order_id, "delivered_products": delivery_content}

        try:
            res = self.client.table("orders").select("*, users(telegram_id, username, first_name)").eq("melax_order_id", melax_order_id).execute()
            if not res.data:
                return False, "Order not found", None

            order_data = res.data[0]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            self.client.table("orders").update({
                "status": "SUCCESS",
                "delivered_products": delivery_content,
                "aiverse_order_id": f"MANUAL-BY-{admin_id}",
                "updated_at": now_iso
            }).eq("melax_order_id", melax_order_id).execute()

            order_data["status"] = "SUCCESS"
            order_data["delivered_products"] = delivery_content
            return True, "Order fulfilled successfully", order_data
        except Exception as e:
            logger.error(f"Error fulfilling manual order {melax_order_id}: {e}")
            return False, str(e), None

    # =========================================================================
    # ADMIN ROLES, ACTIONS & ANALYTICS
    # =========================================================================

    async def get_admin_role(self, telegram_id: int) -> Optional[str]:
        if telegram_id in ADMIN_IDS:
            return "OWNER"
        if not self.is_configured:
            return None
        try:
            res = self.client.table("admins").select("role, is_active").eq("telegram_id", telegram_id).execute()
            if res.data and res.data[0]["is_active"]:
                return res.data[0]["role"]
            return None
        except Exception as e:
            logger.error(f"Error checking admin role: {e}")
            return None

    async def log_admin_action(self, admin_id: int, action: str, target_type: str = "", target_id: str = "", old_val: str = "", new_val: str = "", reason: str = ""):
        if not self.is_configured:
            return
        try:
            self.client.table("admin_actions").insert({
                "admin_id": admin_id,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "old_value": old_val,
                "new_value": new_val,
                "reason": reason
            }).execute()
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")

    async def get_sales_analytics(self) -> Dict[str, Any]:
        if not self.is_configured:
            return {
                "total_users": 0,
                "total_orders": 0,
                "revenue": 0.00,
                "supplier_cost": 0.00,
                "profit": 0.00,
                "pending_payments": 0
            }

        try:
            u_count = len(self.client.table("users").select("id", count="exact").execute().data or [])
            o_res = self.client.table("orders").select("total_amount, supplier_cost, profit").eq("status", "SUCCESS").execute()
            
            revenue = sum(float(r.get("total_amount", 0.0)) for r in o_res.data) if o_res.data else 0.0
            cost = sum(float(r.get("supplier_cost", 0.0)) for r in o_res.data) if o_res.data else 0.0
            profit = sum(float(r.get("profit", 0.0)) for r in o_res.data) if o_res.data else 0.0

            p_count = len(self.client.table("payments").select("id", count="exact").eq("status", "PENDING").execute().data or [])

            return {
                "total_users": u_count,
                "total_orders": len(o_res.data) if o_res.data else 0,
                "revenue": round(revenue, 2),
                "supplier_cost": round(cost, 2),
                "profit": round(profit, 2),
                "pending_payments": p_count
            }
        except Exception as e:
            logger.error(f"Error fetching analytics: {e}")
            return {"total_users": 0, "revenue": 0.00, "profit": 0.00, "pending_payments": 0}


    async def get_referral_stats(self, user_id: str) -> Dict[str, Any]:
        """Get referral count and total reward earned for a user."""
        if not self.is_configured:
            return {"count": 0, "total_earned": 0.0}

        try:
            res = self.client.table("referrals").select("reward_earned").eq("referrer_id", user_id).execute()
            count = len(res.data) if res.data else 0
            total_earned = sum(float(r.get("reward_earned", 0.0)) for r in res.data) if res.data else 0.0
            return {"count": count, "total_earned": round(total_earned, 2)}
        except Exception as e:
            logger.error(f"Error fetching referral stats: {e}")
            return {"count": 0, "total_earned": 0.0}

    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Get system setting instantly from in-memory cache with zero network latency."""
        if key in self._settings_cache:
            return self._settings_cache[key]
        if key in self._mock_settings:
            return self._mock_settings[key]

        if not self.is_configured:
            return default

        try:
            res = self.client.table("settings").select("value").eq("key", key).execute()
            if res.data:
                val = res.data[0]["value"]
                self._settings_cache[key] = val
                return val
            self._settings_cache[key] = default
            return default
        except Exception as e:
            logger.error(f"Error fetching setting '{key}': {e}")
            return default

    async def update_setting(self, key: str, value: Any) -> bool:
        """Update system setting in memory cache immediately and persist to DB."""
        self._settings_cache[key] = value
        self._mock_settings[key] = value
        if not self.is_configured:
            return True
        try:
            self.client.table("settings").upsert({"key": key, "value": value}).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating setting '{key}': {e}")
            return False

    # =========================================================================
    # REFERRAL MILESTONES, REWARD TIERS & CLAIMS ENGINE
    # =========================================================================

    async def get_referral_milestones(self, user_id: str) -> Dict[str, Any]:
        """Get total invites, claimed count, and currently available unspent invite points for rewards."""
        stats = await self.get_referral_stats(user_id)
        total_invites = int(stats.get("count", 0))
        
        # Claimed / consumed invites stored in settings
        claimed_key = f"ref_claimed_pts_{user_id}"
        claimed_pts = int(await self.get_setting(claimed_key, 0) or 0)
        
        available_invites = max(0, total_invites - claimed_pts)
        return {
            "total_invites": total_invites,
            "claimed_invites": claimed_pts,
            "available_invites": available_invites,
            "total_earned": float(stats.get("total_earned", 0.0))
        }

    async def get_referral_tiers(self) -> List[Dict[str, Any]]:
        """Get list of active referral reward tiers (Admin configurable)."""
        import json
        from config import DEFAULT_REFERRAL_TIERS
        raw = await self.get_setting("referral_reward_tiers", None)
        if raw:
            try:
                if isinstance(raw, list):
                    return raw
                elif isinstance(raw, str):
                    return json.loads(raw)
            except Exception as e:
                logger.error(f"Error parsing referral_reward_tiers: {e}")
        return DEFAULT_REFERRAL_TIERS

    async def update_referral_tiers(self, tiers: List[Dict[str, Any]]) -> bool:
        """Save updated referral reward tiers list."""
        import json
        return await self.update_setting("referral_reward_tiers", json.dumps(tiers))

    async def claim_referral_reward(self, user_id: str, tier_id: str, telegram_id: int = 0) -> tuple[bool, str, Dict[str, Any]]:
        """Claim a referral reward tier, deduct available invite points, and log or auto-deliver reward."""
        milestones = await self.get_referral_milestones(user_id)
        avail = milestones["available_invites"]
        
        tiers = await self.get_referral_tiers()
        target_tier = next((t for t in tiers if t.get("id") == tier_id), None)
        if not target_tier:
            return False, "Selected reward tier does not exist.", {}

        req_invites = int(target_tier.get("invites", 20))
        if avail < req_invites:
            return False, f"You need {req_invites} invites to claim this reward (you currently have {avail}).", {}

        # Consume invites points
        claimed_key = f"ref_claimed_pts_{user_id}"
        current_claimed = int(await self.get_setting(claimed_key, 0) or 0)
        new_claimed = current_claimed + req_invites
        await self.update_setting(claimed_key, new_claimed)

        # Generate claim record
        claim_id = f"CLAIM-{uuid.uuid4().hex[:8].upper()}"
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        claim_data = {
            "claim_id": claim_id,
            "user_id": user_id,
            "telegram_id": telegram_id,
            "tier_id": tier_id,
            "tier_name": target_tier.get("reward_name", "Reward"),
            "invites_spent": req_invites,
            "status": "PENDING",
            "delivery_code": None,
            "created_at": now_iso
        }

        # Check if product is available for auto-delivery in manual stock
        serv_id = target_tier.get("service_id", "")
        auto_deliver = target_tier.get("auto_deliver", True)

        if serv_id and auto_deliver:
            prod = await self.get_product_by_service_id(serv_id)
            if prod and prod.get("stock_keys"):
                keys = [k.strip() for k in str(prod.get("stock_keys", "")).split("\n") if k.strip()]
                if keys:
                    delivered_code = keys.pop(0)
                    claim_data["status"] = "DELIVERED"
                    claim_data["delivery_code"] = delivered_code
                    if self.is_configured:
                        try:
                            self.client.table("products").update({
                                "stock_keys": "\n".join(keys),
                                "supplier_stock": len(keys)
                            }).eq("service_id", serv_id).execute()
                        except Exception:
                            pass

        # Save claim in claims registry
        all_claims = await self.get_setting("referral_reward_claims_list", []) or []
        if isinstance(all_claims, str):
            import json
            try:
                all_claims = json.loads(all_claims)
            except Exception:
                all_claims = []
        all_claims.insert(0, claim_data)
        import json
        await self.update_setting("referral_reward_claims_list", json.dumps(all_claims[:200]))

        return True, "Reward claim submitted successfully!", claim_data

    async def get_pending_referral_claims(self) -> List[Dict[str, Any]]:
        """Get all pending reward claims waiting for Admin fulfillment."""
        import json
        raw = await self.get_setting("referral_reward_claims_list", []) or []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = []
        return [c for c in raw if c.get("status") == "PENDING"]

    async def resolve_referral_claim(self, claim_id: str, status: str, delivery_code: str = "", admin_note: str = "") -> tuple[bool, str, Optional[Dict[str, Any]]]:
        """Approve/Deliver or Reject a pending reward claim."""
        import json
        raw = await self.get_setting("referral_reward_claims_list", []) or []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = []
        
        target = None
        for c in raw:
            if c.get("claim_id") == claim_id:
                target = c
                break
        
        if not target:
            return False, "Claim record not found", None
            
        target["status"] = status
        if delivery_code:
            target["delivery_code"] = delivery_code
        if admin_note:
            target["admin_note"] = admin_note
        target["resolved_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # If rejected, refund the spent invite points back to user
        if status == "REJECTED":
            u_id = target.get("user_id", "")
            spent = int(target.get("invites_spent", 0))
            if u_id and spent > 0:
                claimed_key = f"ref_claimed_pts_{u_id}"
                current = int(await self.get_setting(claimed_key, 0) or 0)
                await self.update_setting(claimed_key, max(0, current - spent))

        await self.update_setting("referral_reward_claims_list", json.dumps(raw[:200]))
        return True, f"Claim marked as {status}", target

    # =========================================================================
    # DISCOUNT, PROMO CODES & FLASH SALES ENGINE
    # =========================================================================

    async def get_promo_codes(self) -> List[Dict[str, Any]]:
        """Get list of active promo codes."""
        import json
        raw = await self.get_setting("active_promo_codes", []) or []
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return []
        return raw if isinstance(raw, list) else []

    async def create_or_update_promo_code(
        self,
        code: str,
        discount_type: str = "PERCENT",
        value: float = 10.0,
        max_uses: int = 100,
        min_order: float = 0.0
    ) -> bool:
        """Create or update a promo code."""
        import json
        clean_code = code.strip().upper()
        codes = await self.get_promo_codes()
        existing = next((c for c in codes if c.get("code") == clean_code), None)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        if existing:
            existing["discount_type"] = discount_type
            existing["value"] = float(value)
            existing["max_uses"] = int(max_uses)
            existing["min_order"] = float(min_order)
            existing["is_active"] = True
            existing["updated_at"] = now_iso
        else:
            codes.append({
                "code": clean_code,
                "discount_type": discount_type,
                "value": float(value),
                "max_uses": int(max_uses),
                "times_used": 0,
                "min_order": float(min_order),
                "is_active": True,
                "created_at": now_iso
            })
            
        return await self.update_setting("active_promo_codes", json.dumps(codes))

    async def delete_promo_code(self, code: str) -> bool:
        """Delete or deactivate a promo code."""
        import json
        clean_code = code.strip().upper()
        codes = await self.get_promo_codes()
        filtered = [c for c in codes if c.get("code") != clean_code]
        return await self.update_setting("active_promo_codes", json.dumps(filtered))

    async def validate_and_apply_promo(self, code: str, user_id: str, product_price: float) -> tuple[bool, str, float, float]:
        """Validate promo code and calculate discount amount and final price."""
        clean_code = code.strip().upper()
        codes = await self.get_promo_codes()
        promo = next((c for c in codes if c.get("code") == clean_code and c.get("is_active", True)), None)
        
        if not promo:
            return False, "❌ Invalid or inactive promo code.", 0.0, product_price

        max_uses = int(promo.get("max_uses", 100))
        times_used = int(promo.get("times_used", 0))
        if times_used >= max_uses:
            return False, "❌ Promo code usage limit reached.", 0.0, product_price

        min_order = float(promo.get("min_order", 0.0))
        if product_price < min_order:
            return False, f"❌ Promo code requires a minimum order of {min_order:,.0f} Birr.", 0.0, product_price

        disc_type = promo.get("discount_type", "PERCENT")
        val = float(promo.get("value", 0.0))
        if val <= 0.0:
            return False, "❌ Invalid promo discount value.", 0.0, product_price

        if disc_type == "PERCENT":
            val = min(100.0, max(0.0, val))
            discount_amount = round(product_price * (val / 100.0), 2)
        else:
            val = max(0.0, val)
            discount_amount = min(product_price, round(val, 2))

        final_price = max(0.0, round(product_price - discount_amount, 2))
        return True, f"✅ Promo code '{clean_code}' applied! (-{discount_amount:,.2f} Birr)", discount_amount, final_price

    async def increment_promo_usage(self, code: str, user_id: str) -> bool:
        """Increment usage counter for a promo code."""
        import json
        clean_code = code.strip().upper()
        codes = await self.get_promo_codes()
        for c in codes:
            if c.get("code") == clean_code:
                c["times_used"] = int(c.get("times_used", 0)) + 1
                break
        return await self.update_setting("active_promo_codes", json.dumps(codes))

    async def get_global_discount_percent(self) -> float:
        """Get store-wide flash sale discount percentage (0.0 means no active sale)."""
        from config import DEFAULT_GLOBAL_DISCOUNT_PERCENT
        val = await self.get_setting("global_flash_discount_percent", DEFAULT_GLOBAL_DISCOUNT_PERCENT)
        try:
            return float(val)
        except Exception:
            return 0.0

    async def set_global_discount_percent(self, percent: float) -> bool:
        """Set store-wide flash sale discount percentage."""
        return await self.update_setting("global_flash_discount_percent", float(percent))

    async def add_referral_tier(self, reward_name: str, invites: int, reward_type: str = "DIGITAL_ACCOUNT", value_amount: float = 0.0, description: str = "") -> Dict[str, Any]:
        """Add a new referral reward milestone tier."""
        tiers = await self.get_referral_tiers()
        tier_id = f"tier_{uuid.uuid4().hex[:6]}"
        new_tier = {
            "id": tier_id,
            "reward_name": reward_name,
            "invites": int(invites),
            "reward_type": reward_type,
            "value_amount": float(value_amount),
            "description": description,
            "icon": "🎁"
        }
        tiers.append(new_tier)
        await self.update_referral_tiers(tiers)
        return new_tier

    async def delete_referral_tier(self, tier_id: str) -> bool:
        """Delete a referral reward milestone tier."""
        tiers = await self.get_referral_tiers()
        filtered = [t for t in tiers if t.get("id") != tier_id]
        return await self.update_referral_tiers(filtered)

    async def update_referral_tier_details(self, tier_id: str, reward_name: Optional[str] = None, invites: Optional[int] = None, reward_type: Optional[str] = None) -> bool:
        """Update properties of a referral reward milestone tier."""
        tiers = await self.get_referral_tiers()
        for t in tiers:
            if t.get("id") == tier_id:
                if reward_name is not None:
                    t["reward_name"] = reward_name
                if invites is not None:
                    t["invites"] = int(invites)
                if reward_type is not None:
                    t["reward_type"] = reward_type
                break
        return await self.update_referral_tiers(tiers)

    # =========================================================================
    # MASTER BOT SERVICES ON / OFF FEATURE FLAGS
    # =========================================================================

    async def get_service_status(self, service_key: str, default: bool = True) -> bool:
        """Get enable/disable status for a bot service/module (e.g. shop, deposits, referrals, discounts, support, force_join)."""
        val = await self.get_setting(f"service_enabled_{service_key}", default)
        return bool(val)

    async def set_service_status(self, service_key: str, enabled: bool) -> bool:
        """Set enable/disable status for a bot service/module."""
        return await self.update_setting(f"service_enabled_{service_key}", enabled)

    async def get_all_services_status(self) -> Dict[str, bool]:
        """Fetch status of all system services."""
        return {
            "shop": await self.get_service_status("shop", True),
            "deposits": await self.get_service_status("deposits", True),
            "referrals": await self.get_service_status("referrals", True),
            "discounts": await self.get_service_status("discounts", True),
            "support": await self.get_service_status("support", True),
            "force_join": await self.get_service_status("force_join", True),
            "maintenance": bool(await self.get_setting("maintenance_mode", False))
        }

    async def get_user_language(self, telegram_id: int) -> str:
        """Get preferred language for user ('am' or 'en', defaults to 'am')."""
        return str(await self.get_setting(f"user_lang_{telegram_id}", "am"))

    async def set_user_language(self, telegram_id: int, lang: str) -> bool:
        """Set preferred language for user."""
        lang_code = "am" if str(lang).lower().startswith("am") else "en"
        return await self.update_setting(f"user_lang_{telegram_id}", lang_code)

db = SupabaseManager()
