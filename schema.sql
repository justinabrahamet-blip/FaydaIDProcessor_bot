-- =============================================================================
-- MELAX DIGITAL SHOP - Complete Production Supabase PostgreSQL Schema
-- Includes Automatic Table Reset (DROP) and Complete Table/RPC Creations
-- =============================================================================

-- 1. DROP EXISTING TABLES TO PREVENT COLUMN MISMATCH CONFLICTS
DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS wallet_transactions CASCADE;
DROP TABLE IF EXISTS wallets CASCADE;
DROP TABLE IF EXISTS customer_prices CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS promo_usage CASCADE;
DROP TABLE IF EXISTS promo_codes CASCADE;
DROP TABLE IF EXISTS referrals CASCADE;
DROP TABLE IF EXISTS admin_actions CASCADE;
DROP TABLE IF EXISTS admins CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS settings CASCADE;

-- 2. ENABLE UUID EXTENSION
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 3. USERS TABLE
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    is_banned BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    is_vip BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_users_username ON users(username);

-- 4. WALLETS TABLE
CREATE TABLE wallets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    balance NUMERIC(12, 2) NOT NULL DEFAULT 0.00 CHECK (balance >= 0.00),
    currency TEXT DEFAULT 'Birr',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_wallets_user_id ON wallets(user_id);

-- 5. WALLET TRANSACTIONS LEDGER TABLE
CREATE TABLE wallet_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('DEPOSIT', 'PURCHASE', 'REFUND', 'ADMIN_CREDIT', 'ADMIN_DEBIT', 'REFERRAL_REWARD', 'PROMO', 'ADJUSTMENT')),
    amount NUMERIC(12, 2) NOT NULL,
    balance_before NUMERIC(12, 2) NOT NULL,
    balance_after NUMERIC(12, 2) NOT NULL,
    reference TEXT,
    description TEXT,
    created_by TEXT DEFAULT 'SYSTEM',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_wallet_tx_user_id ON wallet_transactions(user_id);
CREATE INDEX idx_wallet_tx_created_at ON wallet_transactions(created_at DESC);

-- 6. PRODUCTS TABLE (Synchronized with AIVerse Hub API)
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    supplier_cost NUMERIC(12, 2) DEFAULT 0.00,
    supplier_stock INT DEFAULT 0,
    selling_price NUMERIC(12, 2) DEFAULT 0.00,
    description TEXT DEFAULT 'No description provided.',
    currency TEXT DEFAULT 'Birr',
    is_enabled BOOLEAN DEFAULT FALSE,
    supplier_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_synced_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_products_service_id ON products(service_id);
CREATE INDEX idx_products_is_enabled ON products(is_enabled);

-- 7. CUSTOMER SPECIFIC PRICING TABLE
CREATE TABLE customer_prices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    custom_price NUMERIC(12, 2) NOT NULL CHECK (custom_price >= 0.00),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, product_id)
);

-- 8. PAYMENTS TABLE (Customer Wallet Deposits & Anti-Reuse Transaction ID)
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    payment_id TEXT UNIQUE NOT NULL,
    transaction_id TEXT UNIQUE, -- Enforces Anti-Reuse of FT... / 3GA... Txn IDs
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0.00),
    currency TEXT DEFAULT 'Birr',
    method TEXT DEFAULT 'Telebirr/CBE',
    reference TEXT,
    deposit_note TEXT,
    status TEXT DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'REFUNDED')),
    screenshot_file_id TEXT,
    approved_by BIGINT,
    approved_at TIMESTAMP WITH TIME ZONE,
    rejection_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_payments_user_id ON payments(user_id);
CREATE INDEX idx_payments_status ON payments(status);
CREATE INDEX idx_payments_transaction_id ON payments(transaction_id);

-- 9. ORDERS TABLE
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    melax_order_id TEXT UNIQUE NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    service_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    quantity INT DEFAULT 1 CHECK (quantity > 0),
    selling_price NUMERIC(12, 2) NOT NULL,
    supplier_cost NUMERIC(12, 2) DEFAULT 0.00,
    total_amount NUMERIC(12, 2) NOT NULL,
    profit NUMERIC(12, 2) DEFAULT 0.00,
    aiverse_order_id TEXT,
    status TEXT DEFAULT 'SUCCESS' CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED', 'REFUNDED')),
    delivered_products TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);

-- 10. REFERRALS TABLE
CREATE TABLE referrals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    referrer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    referred_user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reward_earned NUMERIC(12, 2) DEFAULT 0.00,
    status TEXT DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 11. PROMO CODES TABLE
CREATE TABLE promo_codes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code TEXT UNIQUE NOT NULL,
    discount_type TEXT NOT NULL CHECK (discount_type IN ('PERCENTAGE', 'FIXED')),
    discount_amount NUMERIC(12, 2) NOT NULL CHECK (discount_amount > 0.00),
    max_uses INT DEFAULT 100,
    current_uses INT DEFAULT 0,
    per_user_limit INT DEFAULT 1,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 12. PROMO USAGE TABLE
CREATE TABLE promo_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    promo_id UUID NOT NULL REFERENCES promo_codes(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    used_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(promo_id, user_id)
);

-- 13. ADMINS TABLE
CREATE TABLE admins (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    telegram_id BIGINT UNIQUE NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('OWNER', 'MANAGER', 'FINANCE', 'SUPPORT', 'VIEWER')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 14. ADMIN ACTIONS AUDIT LOG
CREATE TABLE admin_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    admin_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    old_value TEXT,
    new_value TEXT,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 15. SETTINGS TABLE
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

-- Insert Default System Settings
INSERT INTO settings (key, value) VALUES 
('maintenance_mode', 'false'::jsonb),
('force_join_enabled', 'true'::jsonb),
('default_markup_percent', '10.0'::jsonb),
('referral_commission_percent', '5.0'::jsonb),
('low_supplier_balance_threshold', '20.0'::jsonb)
ON CONFLICT (key) DO NOTHING;

-- Function for Atomic Wallet Balance Deduction
CREATE OR REPLACE FUNCTION atomic_deduct_wallet(
    p_user_id UUID,
    p_amount NUMERIC,
    p_ref TEXT,
    p_desc TEXT
) RETURNS JSONB AS $$
DECLARE
    v_balance NUMERIC;
    v_new_balance NUMERIC;
BEGIN
    SELECT balance INTO v_balance FROM wallets WHERE user_id = p_user_id FOR UPDATE;
    
    IF v_balance IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'Wallet not found');
    END IF;
    
    IF v_balance < p_amount THEN
        RETURN jsonb_build_object('success', false, 'error', 'Insufficient balance');
    END IF;

    v_new_balance := v_balance - p_amount;
    
    UPDATE wallets SET balance = v_new_balance, updated_at = CURRENT_TIMESTAMP WHERE user_id = p_user_id;

    INSERT INTO wallet_transactions (user_id, type, amount, balance_before, balance_after, reference, description)
    VALUES (p_user_id, 'PURCHASE', -p_amount, v_balance, v_new_balance, p_ref, p_desc);

    RETURN jsonb_build_object(
        'success', true, 
        'balance_before', v_balance, 
        'balance_after', v_new_balance
    );
END;
$$ LANGUAGE plpgsql;

-- Function for Atomic Wallet Balance Credit
CREATE OR REPLACE FUNCTION atomic_credit_wallet(
    p_user_id UUID,
    p_amount NUMERIC,
    p_type TEXT,
    p_ref TEXT,
    p_desc TEXT,
    p_created_by TEXT DEFAULT 'SYSTEM'
) RETURNS JSONB AS $$
DECLARE
    v_balance NUMERIC;
    v_new_balance NUMERIC;
BEGIN
    SELECT balance INTO v_balance FROM wallets WHERE user_id = p_user_id FOR UPDATE;
    
    IF v_balance IS NULL THEN
        INSERT INTO wallets (user_id, balance) VALUES (p_user_id, 0.00) RETURNING balance INTO v_balance;
    END IF;

    v_new_balance := v_balance + p_amount;
    
    UPDATE wallets SET balance = v_new_balance, updated_at = CURRENT_TIMESTAMP WHERE user_id = p_user_id;

    INSERT INTO wallet_transactions (user_id, type, amount, balance_before, balance_after, reference, description, created_by)
    VALUES (p_user_id, p_type, p_amount, v_balance, v_new_balance, p_ref, p_desc, p_created_by);

    RETURN jsonb_build_object(
        'success', true, 
        'balance_before', v_balance, 
        'balance_after', v_new_balance
    );
END;
$$ LANGUAGE plpgsql;
