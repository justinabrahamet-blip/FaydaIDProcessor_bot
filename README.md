# MELAX DIGITAL SHOP (aiogram 3.x + Supabase PostgreSQL)

A production-ready Telegram Digital Products Reseller Platform built using **Python 3.11+**, **aiogram 3.x**, **Supabase PostgreSQL**, and **AIVerse Hub REST API**.

---

## 🌟 Key System Features

- **Framework**: `aiogram 3.x` with modular routers and FSM.
- **Database**: Supabase PostgreSQL (`schema.sql`) with atomic wallet RPCs and row-level consistency.
- **Supplier Integration**: Rate-limited (3 req/sec) AIVerse Hub API client (`https://aiversehub.store`).
- **Force Join Channel**: Mandatory membership check for official sales channel (`-1003787649556`).
- **Wallet & Deposits**: Telebirr/CBE deposit receipts upload with instant Admin approval/rejection.
- **Product Management**: Auto-sync matching `service_id`, editable descriptions, custom prices (`/setprice`), and visibility toggle.
- **Admin Dashboard**: Role-based access control (OWNER, MANAGER, FINANCE, SUPPORT, VIEWER), business revenue & profit analytics, API monitor, and broadcast engine.
- **Logs Channel Notifier**: Automatic event notifications sent to Logs Channel (`-1002786006091`).

---

## 🗄️ Supabase PostgreSQL Setup Instructions

1. Log into your [Supabase Dashboard](https://supabase.com/).
2. Create a new project (e.g. `melax-digital-shop`).
3. Open the **SQL Editor** in Supabase.
4. Copy the entire contents of [schema.sql](file:///C:/Users/Melaku%20Solutions/.gemini/antigravity/scratch/aiversexbot_clone/schema.sql) and paste it into the SQL Editor.
5. Click **RUN** to execute the schema migration and create all 13 PostgreSQL tables and atomic RPC functions.
6. Copy your `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from **Project Settings ➡️ API**.

---

## 🚀 Environment Setup & Local Execution

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Fill in your secrets in `.env`:
   ```env
   BOT_TOKEN=your_bot_token_from_botfather
   AIVERSE_API_KEY=AK_0xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   SUPABASE_URL=https://your-supabase-project.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   SALES_CHANNEL_ID=-1003787649556
   LOGS_CHANNEL_ID=-1002786006091
   SUPPORT_USERNAME=mr_melaku
   ADMIN_IDS=123456789
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Launch the Bot:
   ```bash
   python bot.py
   ```

---

## ☁️ Deployment on Render (render.com)

1. Push your repository to GitHub: `https://github.com/nisirtech1085-pixel/MELAX-DIGITAL-SHOP`
2. Create a new **Background Worker** or **Web Service** on Render.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python bot.py`
5. Configure all Environment Variables in Render Dashboard.
