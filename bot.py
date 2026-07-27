# ==================================================
# ربات هوشمند ویدیو کلوپ (نسخه نهایی - همه قابلیت‌ها)
# ==================================================

import sqlite3
import logging
import requests
import re
import os
import time
from datetime import datetime
import jdatetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler

# ===================== تنظیمات اولیه (فقط همینجا را ویرایش کنید!) =====================
TOKEN = "8756645103:AAFILFDh1msJoOSEc3svbOaCWm1WU4_ADQw"           # توکن ربات از @BotFather
ADMIN_ID = 119892235                                            # آیدی عددی شما از @userinfobot
TMDB_API_KEY = "aaf08d01d1cf90e9381ffd82d5e535da"              # کلید TMDB

# ثابت‌های فنی (نیازی به تغییر ندارند)
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
TMDB_DETAIL_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE = "https://image.tmdb.org/t/p/w500"
BULK_LIMIT = 150  # حداکثر فیلم در هر بار افزودن انبوه

# ===================== راه‌اندازی دیتابیس =====================
def init_db():
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY, name TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS items (
        custom_id INTEGER PRIMARY KEY, 
        tmdb_id INTEGER, 
        media_type TEXT, 
        category_id INTEGER, 
        title TEXT, 
        title_en TEXT,
        overview TEXT, 
        poster_file_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS episodes (
        custom_id INTEGER, 
        season_num INTEGER, 
        episode_num INTEGER, 
        name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS season_posters (
        custom_id INTEGER, 
        season_num INTEGER, 
        poster_file_id TEXT, 
        PRIMARY KEY(custom_id, season_num))''')
    c.execute('''CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY, 
        value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS category_visibility (
        category_id INTEGER PRIMARY KEY,
        visible BOOLEAN DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_bulk (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        custom_id INTEGER,
        title TEXT,
        status TEXT)''')  # برای ذخیره موقت خطاهای افزودن انبوه
    
    # دسته‌بندی‌های پیش‌فرض
    c.execute('INSERT OR IGNORE INTO categories (id, name) VALUES (1, "همه")')
    c.execute('INSERT OR IGNORE INTO categories (id, name) VALUES (2, "انیمیشن")')
    c.execute('INSERT OR IGNORE INTO categories (id, name) VALUES (3, "هندی")')
    c.execute('INSERT OR IGNORE INTO categories (id, name) VALUES (4, "سریال ایرانی")')
    c.execute('''INSERT OR IGNORE INTO category_visibility (category_id, visible)
                 SELECT id, 1 FROM categories''')
    conn.commit()
    conn.close()
init_db()

# ===================== توابع کمکی دیتابیس =====================
def get_categories(only_visible=True):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    if only_visible:
        c.execute('''SELECT c.id, c.name FROM categories c
                     JOIN category_visibility v ON c.id = v.category_id
                     WHERE v.visible = 1 AND c.id != 1 ORDER BY c.name''')
    else:
        c.execute("SELECT id, name FROM categories WHERE id != 1 ORDER BY name")
    data = c.fetchall()
    conn.close()
    return data

def get_category_name(cat_id):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("SELECT name FROM categories WHERE id=?", (cat_id,))
    data = c.fetchone()
    conn.close()
    return data[0] if data else "بدون دسته"

def add_category(name):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("INSERT INTO categories (name) VALUES (?)", (name,))
    c.execute("INSERT INTO category_visibility (category_id, visible) VALUES (last_insert_rowid(), 1)")
    conn.commit()
    conn.close()

def toggle_category_visibility(cat_id):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("UPDATE category_visibility SET visible = NOT visible WHERE category_id=?", (cat_id,))
    conn.commit()
    conn.close()

def add_item(custom_id, tmdb_id, media_type, category_id, title, title_en, overview, poster_file_id):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO items (custom_id, tmdb_id, media_type, category_id, title, title_en, overview, poster_file_id) VALUES (?,?,?,?,?,?,?,?)", 
              (custom_id, tmdb_id, media_type, category_id, title, title_en, overview, poster_file_id))
    conn.commit()
    conn.close()

def update_item(custom_id, field, value):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute(f"UPDATE items SET {field}=? WHERE custom_id=?", (value, custom_id))
    conn.commit()
    conn.close()

def get_item(custom_id):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("SELECT * FROM items WHERE custom_id=?", (custom_id,))
    data = c.fetchone()
    conn.close()
    return data

def get_items_by_category(cat_id):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    if cat_id == 1:
        c.execute("SELECT custom_id, title, created_at FROM items ORDER BY created_at DESC, custom_id")
    else:
        c.execute("SELECT custom_id, title, created_at FROM items WHERE category_id=? ORDER BY created_at DESC, custom_id", (cat_id,))
    data = c.fetchall()
    conn.close()
    return data

def get_latest_items(limit=20):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("SELECT custom_id, title, created_at FROM items ORDER BY created_at DESC LIMIT ?", (limit,))
    data = c.fetchall()
    conn.close()
    return data

def add_episode(custom_id, season, episode, name):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO episodes VALUES (?,?,?,?)", (custom_id, season, episode, name))
    conn.commit()
    conn.close()

def get_episodes(custom_id):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("SELECT season_num, episode_num, name FROM episodes WHERE custom_id=? ORDER BY season_num, episode_num", (custom_id,))
    data = c.fetchall()
    conn.close()
    return data

def save_season_poster(custom_id, season_num, file_id):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO season_posters VALUES (?,?,?)", (custom_id, season_num, file_id))
    conn.commit()
    conn.close()

def get_season_poster(custom_id, season_num):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("SELECT poster_file_id FROM season_posters WHERE custom_id=? AND season_num=?", (custom_id, season_num))
    data = c.fetchone()
    conn.close()
    return data[0] if data else None

def get_channel_id():
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key='channel_id'")
    data = c.fetchone()
    conn.close()
    return data[0] if data else None

def set_channel_id(channel_id):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('channel_id', ?)", (str(channel_id),))
    conn.commit()
    conn.close()

def clear_pending_bulk():
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("DELETE FROM pending_bulk")
    conn.commit()
    conn.close()

def add_pending_bulk(custom_id, title, status):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("INSERT INTO pending_bulk (custom_id, title, status) VALUES (?,?,?)", (custom_id, title, status))
    conn.commit()
    conn.close()

def get_pending_bulk():
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("SELECT custom_id, title, status FROM pending_bulk")
    data = c.fetchall()
    conn.close()
    return data

# ===================== توابع جستجوی TMDB =====================
def search_tmdb(query, media_type=None, language="fa-IR"):
    params = {"api_key": TMDB_API_KEY, "query": query.strip(), "language": language}
    if media_type:
        params["media_type"] = media_type
    try:
        resp = requests.get(TMDB_SEARCH_URL, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("results", [])
    except:
        pass
    return []

def get_tmdb_detail(tmdb_id, media_type, language="fa-IR"):
    url = f"{TMDB_DETAIL_URL}/{media_type}/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "language": language}
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return None

def fetch_poster(tmdb_id, media_type):
    for lang in ["fa-IR", "en-US"]:
        detail = get_tmdb_detail(tmdb_id, media_type, lang)
        if detail and detail.get('poster_path'):
            return TMDB_IMAGE + detail['poster_path']
    return None

def fetch_overview(tmdb_id, media_type):
    for lang in ["fa-IR", "en-US"]:
        detail = get_tmdb_detail(tmdb_id, media_type, lang)
        if detail and detail.get('overview'):
            return detail['overview']
    return "توضیحاتی برای این اثر موجود نیست."

def fetch_title_en(tmdb_id, media_type):
    detail = get_tmdb_detail(tmdb_id, media_type, "en-US")
    if detail:
        return detail.get('title') or detail.get('name', '')
    return ""

def fetch_episodes_from_tmdb(tmdb_id):
    episodes = []
    detail = get_tmdb_detail(tmdb_id, 'tv', "fa-IR")
    if not detail:
        detail = get_tmdb_detail(tmdb_id, 'tv', "en-US")
    if not detail or 'seasons' not in detail:
        return []
    for season in detail['seasons']:
        snum = season.get('season_number', 0)
        if snum == 0: continue
        ep_url = f"{TMDB_DETAIL_URL}/tv/{tmdb_id}/season/{snum}"
        params = {"api_key": TMDB_API_KEY, "language": "fa-IR"}
        try:
            resp = requests.get(ep_url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for ep in data.get('episodes', []):
                    episodes.append({
                        'season': snum,
                        'episode': ep.get('episode_number', 0),
                        'name': ep.get('name', f"قسمت {ep.get('episode_number', 0)}")
                    })
        except:
            pass
    return episodes

# ===================== تابع ارسال خطا به ادمین =====================
async def send_error_to_admin(context, error_text):
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ *خطای ربات:*\n{error_text}", parse_mode="Markdown")
    except:
        pass

# ===================== STATE ها =====================
ADD_STATE, ADD_NUMBER, ADD_SEARCH, ADD_CATEGORY, ADD_WAIT_PHOTO, ADD_WAIT_SEASON_PHOTO = range(6)
EDIT_STATE = 10
SET_CHANNEL_STATE = 11
NAME_STATE = 12
BULK_STATE, BULK_CATEGORY, BULK_CONFIRM = 13, 14, 15

# ===================== مدیریت خطاهای سراسری =====================
async def error_handler(update, context):
    err = str(context.error)
    await send_error_to_admin(context, f"خطا در آپدیت:\n{err}")
    logging.error(f"Update {update} caused error {context.error}")

# ===================== ADMIN: مدیریت دسته‌بندی‌ها =====================
async def manage_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("شما اجازه ندارید.")
        return
    cats = get_categories(only_visible=False)
    keyboard = []
    for cid, name in cats:
        conn = sqlite3.connect("shop.db")
        c = conn.cursor()
        c.execute("SELECT visible FROM category_visibility WHERE category_id=?", (cid,))
        vis = c.fetchone()
        conn.close()
        status = "✅" if (vis and vis[0] == 1) else "❌"
        keyboard.append([InlineKeyboardButton(f"{status} {name}", callback_data=f"toggle_cat_{cid}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_menu")])
    await update.message.reply_text("مدیریت دسته‌بندی‌ها:\n✅ = قابل مشاهده\n❌ = مخفی", reply_markup=InlineKeyboardMarkup(keyboard))

async def toggle_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("شما اجازه ندارید.")
        return
    cat_id = int(query.data.split("_")[2])
    toggle_category_visibility(cat_id)
    await manage_categories(update, context)

# ===================== ADMIN: ویرایش فیلم =====================
async def edit_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("شما اجازه ندارید.")
        return
    await update.message.reply_text("🔧 شماره فیلم/سریالی را که می‌خواهید ویرایش کنید وارد کنید:")
    return EDIT_STATE

async def edit_get_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        custom_id = int(update.message.text.strip())
        item = get_item(custom_id)
        if not item:
            await update.message.reply_text("❌ فیلمی با این شماره یافت نشد.")
            return EDIT_STATE
        context.user_data['edit_custom_id'] = custom_id
        keyboard = [
            [InlineKeyboardButton("📝 نام فارسی", callback_data="edit_title")],
            [InlineKeyboardButton("📝 نام انگلیسی", callback_data="edit_title_en")],
            [InlineKeyboardButton("📝 توضیحات", callback_data="edit_overview")],
            [InlineKeyboardButton("🖼 تغییر پوستر", callback_data="edit_poster")],
            [InlineKeyboardButton("🔙 انصراف", callback_data="edit_cancel")]
        ]
        await update.message.reply_text(f"چه فیلدی را برای شماره {custom_id} ویرایش می‌کنید؟", reply_markup=InlineKeyboardMarkup(keyboard))
        return EDIT_STATE
    except:
        await update.message.reply_text("لطفاً یک عدد معتبر وارد کنید.")
        return EDIT_STATE

async def edit_choose_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field = query.data.split("_")[1]
    context.user_data['edit_field'] = field
    if field == "poster":
        await query.edit_message_text("📤 لطفاً عکس جدید را ارسال کنید.")
        return EDIT_STATE
    else:
        names = {"title": "نام فارسی", "title_en": "نام انگلیسی", "overview": "توضیحات"}
        await query.edit_message_text(f"مقدار جدید برای **{names.get(field, field)}** را وارد کنید:")
        return EDIT_STATE

async def edit_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    custom_id = context.user_data['edit_custom_id']
    field = context.user_data['edit_field']
    value = update.message.text.strip()
    update_item(custom_id, field, value)
    await update.message.reply_text(f"✅ {field} با موفقیت ویرایش شد.")
    context.user_data.clear()
    return ConversationHandler.END

async def edit_receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    if not update.message.photo:
        await update.message.reply_text("لطفاً یک عکس معتبر ارسال کنید.")
        return EDIT_STATE
    file_id = update.message.photo[-1].file_id
    custom_id = context.user_data['edit_custom_id']
    update_item(custom_id, "poster_file_id", file_id)
    await update.message.reply_text("✅ پوستر با موفقیت به‌روزرسانی شد.")
    context.user_data.clear()
    return ConversationHandler.END

async def edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("ویرایش لغو شد.")
    context.user_data.clear()
    return ConversationHandler.END

# ===================== ADMIN: افزودن تک فیلم =====================
async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("شما اجازه ندارید.")
        return ConversationHandler.END
    await update.message.reply_text("🔢 شماره دلخواه را وارد کنید (مثلاً 155):")
    return ADD_NUMBER

async def add_get_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        custom_id = int(update.message.text.strip())
        if get_item(custom_id):
            await update.message.reply_text("⚠️ این شماره قبلاً ثبت شده! شماره دیگری وارد کنید.")
            return ADD_NUMBER
        context.user_data['add_custom_id'] = custom_id
        await update.message.reply_text("✅ حالا **نام فیلم/سریال** را وارد کنید:")
        return ADD_SEARCH
    except:
        await update.message.reply_text("لطفاً یک عدد معتبر وارد کنید.")
        return ADD_NUMBER

async def add_search_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    results = search_tmdb(query)
    if not results:
        await update.message.reply_text("❌ پیدا نشد. دوباره بفرستید یا /cancel.")
        return ADD_SEARCH
    context.user_data['search_results'] = results
    keyboard = []
    for idx, item in enumerate(results[:8]):
        media = "🎬 فیلم" if item.get("media_type") == "movie" else "📺 سریال"
        title = item.get("title") or item.get("name", "نامشخص")
        year = (item.get("release_date") or item.get("first_air_date") or "????")[:4]
        keyboard.append([InlineKeyboardButton(f"{media} - {title} ({year})", callback_data=f"admin_sel_{idx}")])
    keyboard.append([InlineKeyboardButton("❌ انصراف", callback_data="admin_cancel")])
    await update.message.reply_text("یکی را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADD_SEARCH

async def admin_select_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("_")[2])
    results = context.user_data.get('search_results', [])
    if idx >= len(results):
        await query.edit_message_text("خطا!")
        return ConversationHandler.END
    selected = results[idx]
    tmdb_id = selected['id']
    media_type = selected.get('media_type', 'movie')
    title = selected.get('title') or selected.get('name', 'بدون نام')
    title_en = fetch_title_en(tmdb_id, media_type)
    context.user_data.update({
        'add_tmdb_id': tmdb_id,
        'add_media_type': media_type,
        'add_title': title,
        'add_title_en': title_en,
        'add_overview': fetch_overview(tmdb_id, media_type),
        'add_poster_url': fetch_poster(tmdb_id, media_type)
    })
    cats = get_categories(only_visible=False)
    keyboard = [[InlineKeyboardButton(cname, callback_data=f"admin_cat_{cid}")] for cid, cname in cats if cid != 1]
    keyboard.append([InlineKeyboardButton("➕ دسته جدید", callback_data="admin_new_cat")])
    await query.edit_message_text(f"📌 *{title}*\nدسته را انتخاب کنید:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADD_CATEGORY

async def admin_choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_id = int(query.data.split("_")[2])
    context.user_data['add_category_id'] = cat_id
    poster_url = context.user_data.get('add_poster_url')
    if poster_url:
        keyboard = [
            [InlineKeyboardButton("✅ پوستر TMDB", callback_data="admin_use_tmdb")],
            [InlineKeyboardButton("📤 آپلود خودم", callback_data="admin_upload")]
        ]
        await query.edit_message_text("پوستر پیدا شد. انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ADD_WAIT_PHOTO
    else:
        await query.edit_message_text("❌ پوستری در TMDB نیست. عکس را بفرستید:")
        return ADD_WAIT_PHOTO

async def admin_use_tmdb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['add_poster_file_id'] = context.user_data.get('add_poster_url')
    await query.edit_message_text("✅ ذخیره می‌شود...")
    await save_item_and_finish(update, context)

async def admin_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📤 عکس را بفرستید:")
    return ADD_WAIT_PHOTO

async def admin_receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    if not update.message.photo:
        await update.message.reply_text("عکس بفرستید.")
        return ADD_WAIT_PHOTO
    context.user_data['add_poster_file_id'] = update.message.photo[-1].file_id
    media_type = context.user_data.get('add_media_type')
    if media_type == 'tv':
        keyboard = [
            [InlineKeyboardButton("✅ بله، هر فصل جداگانه", callback_data="admin_season_yes")],
            [InlineKeyboardButton("❌ نه، یکی برای همه", callback_data="admin_season_no")]
        ]
        await update.message.reply_text("برای هر فصل پوستر جداگانه می‌خواهید؟", reply_markup=InlineKeyboardMarkup(keyboard))
        return ADD_WAIT_SEASON_PHOTO
    else:
        await save_item_and_finish(update, context)
        return ConversationHandler.END

async def admin_season_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "admin_season_yes":
        tmdb_id = context.user_data['add_tmdb_id']
        eps = fetch_episodes_from_tmdb(tmdb_id)
        seasons = sorted(set(e['season'] for e in eps))
        if not seasons:
            await query.edit_message_text("فصلی یافت نشد. از همان پوستر استفاده می‌شود.")
            await save_item_and_finish(update, context)
            return ConversationHandler.END
        context.user_data['seasons_list'] = seasons
        context.user_data['season_index'] = 0
        await query.edit_message_text(f"📸 پوستر **فصل {seasons[0]}** را بفرستید:")
        return ADD_WAIT_SEASON_PHOTO
    else:
        await save_item_and_finish(update, context)
        return ConversationHandler.END

async def admin_receive_season_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not update.message.photo:
        return ADD_WAIT_SEASON_PHOTO
    file_id = update.message.photo[-1].file_id
    custom_id = context.user_data['add_custom_id']
    seasons = context.user_data.get('seasons_list', [])
    idx = context.user_data.get('season_index', 0)
    if idx < len(seasons):
        save_season_poster(custom_id, seasons[idx], file_id)
        idx += 1
        context.user_data['season_index'] = idx
        if idx < len(seasons):
            await update.message.reply_text(f"✅ شد. پوستر **فصل {seasons[idx]}** را بفرستید:")
            return ADD_WAIT_SEASON_PHOTO
        else:
            await update.message.reply_text("✅ همه پوسترهای فصل ذخیره شد.")
            await save_item_and_finish(update, context)
            return ConversationHandler.END
    await save_item_and_finish(update, context)
    return ConversationHandler.END

async def save_item_and_finish(update, context):
    custom_id = context.user_data['add_custom_id']
    tmdb_id = context.user_data['add_tmdb_id']
    media_type = context.user_data['add_media_type']
    cat_id = context.user_data['add_category_id']
    title = context.user_data['add_title']
    title_en = context.user_data.get('add_title_en', '')
    overview = context.user_data['add_overview']
    poster = context.user_data.get('add_poster_file_id', '')
    add_item(custom_id, tmdb_id, media_type, cat_id, title, title_en, overview, poster)
    if media_type == 'tv':
        for ep in fetch_episodes_from_tmdb(tmdb_id):
            add_episode(custom_id, ep['season'], ep['episode'], ep['name'])
    msg = f"✅ {title} با شماره {custom_id} اضافه شد."
    if media_type == 'tv':
        msg += f"\n📺 {len(get_episodes(custom_id))} قسمت ذخیره شد."
    # ارسال به کانال (اگر تنظیم شده باشد، به صورت خودکار)
    channel_id = get_channel_id()
    if channel_id:
        try:
            await send_to_channel(context, custom_id, title, overview, poster, media_type)
            msg += "\n📢 در کانال پست شد."
        except Exception as e:
            msg += f"\n⚠️ خطا در ارسال به کانال: {e}"
    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")
    context.user_data.clear()

async def admin_new_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("نام دسته جدید را بنویسید:")
    context.user_data['waiting_for_new_cat'] = True
    return ADD_CATEGORY

async def add_new_category_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    name = update.message.text.strip()
    if name:
        add_category(name)
        await update.message.reply_text(f"✅ دسته '{name}' اضافه شد. دوباره /add بزنید.")
    context.user_data['waiting_for_new_cat'] = False
    return ConversationHandler.END

async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("لغو شد.")
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لغو شد.")
    context.user_data.clear()
    return ConversationHandler.END

# ===================== ارسال به کانال =====================
async def send_to_channel(context, custom_id, title, overview, poster, media_type):
    channel_id = get_channel_id()
    if not channel_id:
        return
    text = f"🎞 *شماره:* {custom_id}\n*نام:* {title}\n*نوع:* {'سریال' if media_type == 'tv' else 'فیلم'}\n\n📝 *توضیحات:*\n{overview[:500]}..."
    keyboard = [[InlineKeyboardButton("🎬 مشاهده در ربات", url=f"https://t.me/Dizbad_VideoClubBot?start=detail_{custom_id}")]]
    if poster and (poster.startswith('http') or len(poster) > 10):
        await context.bot.send_photo(chat_id=channel_id, photo=poster, caption=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await context.bot.send_message(chat_id=channel_id, text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ===================== ADMIN: Set Channel =====================
async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("شما اجازه ندارید.")
        return ConversationHandler.END
    await update.message.reply_text("📢 یوزرنیم کانال را بفرستید (مثلاً @MyChannel):")
    return SET_CHANNEL_STATE

async def receive_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    text = update.message.text.strip()
    try:
        if text.startswith('@'):
            chat = await context.bot.get_chat(text[1:])
        else:
            chat = await context.bot.get_chat(int(text))
        set_channel_id(chat.id)
        await update.message.reply_text(f"✅ کانال {text} ثبت شد!")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: ربات ادمین کانال است؟\n{e}")
    context.user_data.clear()
    return ConversationHandler.END

# ===================== ADMIN: Bulk Add (افزودن انبوه) =====================
async def bulk_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("شما اجازه ندارید.")
        return
    await update.message.reply_text("📤 فایل متنی (TXT) حاوی لیست فیلم‌ها را ارسال کنید.\nفرمت هر سطر:\n`شماره - نام فیلم`\nمثال:\n`101 - گل سنگ`\n`102 - پدرخوانده`", parse_mode="Markdown")
    return BULK_STATE

async def bulk_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    if not update.message.document:
        await update.message.reply_text("لطفاً یک فایل متنی (TXT) ارسال کنید.")
        return BULK_STATE
    doc = update.message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("فقط فایل TXT پشتیبانی می‌شود.")
        return BULK_STATE
    try:
        file = await context.bot.get_file(doc.file_id)
        content = await file.download_as_bytearray()
        lines = content.decode('utf-8').splitlines()
        if len(lines) > BULK_LIMIT:
            await update.message.reply_text(f"⚠️ حداکثر {BULK_LIMIT} فیلم در هر بار مجاز است.")
            return BULK_STATE
        # پردازش خطوط
        items = []
        errors = []
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            if ' - ' not in line and '-' not in line:
                errors.append(f"سطر {i}: فرمت اشتباه (مثال: 101 - نام فیلم)")
                continue
            # استخراج شماره و نام
            if ' - ' in line:
                parts = line.split(' - ', 1)
            else:
                parts = line.split('-', 1)
            if len(parts) != 2:
                errors.append(f"سطر {i}: فرمت اشتباه")
                continue
            try:
                custom_id = int(parts[0].strip())
                title = parts[1].strip()
                if not title:
                    errors.append(f"سطر {i}: نام فیلم خالی است")
                    continue
                if get_item(custom_id):
                    errors.append(f"سطر {i}: شماره {custom_id} تکراری است")
                    continue
                items.append((custom_id, title))
            except ValueError:
                errors.append(f"سطر {i}: شماره نامعتبر")
        if not items:
            await update.message.reply_text("❌ هیچ آیتم معتبری در فایل یافت نشد.\n" + "\n".join(errors[:5]))
            return ConversationHandler.END
        context.user_data['bulk_items'] = items
        context.user_data['bulk_errors'] = errors
        # انتخاب دسته
        cats = get_categories(only_visible=False)
        keyboard = [[InlineKeyboardButton(cname, callback_data=f"bulk_cat_{cid}")] for cid, cname in cats if cid != 1]
        keyboard.append([InlineKeyboardButton("➕ دسته جدید", callback_data="bulk_new_cat")])
        await update.message.reply_text(f"✅ {len(items)} فیلم معتبر خوانده شد.\nحالا دسته را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
        return BULK_CATEGORY
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در خواندن فایل: {e}")
        return ConversationHandler.END

async def bulk_category_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("bulk_cat_"):
        cat_id = int(query.data.split("_")[2])
        context.user_data['bulk_category_id'] = cat_id
        await query.edit_message_text(f"⏳ در حال پردازش {len(context.user_data['bulk_items'])} فیلم... ممکن است چند دقیقه طول بکشد.")
        # پردازش
        items = context.user_data['bulk_items']
        found = []
        not_found = []
        total = len(items)
        for idx, (cid, title) in enumerate(items, 1):
            # جستجو در TMDB
            results = search_tmdb(title)
            if results:
                res = results[0]
                tmdb_id = res['id']
                media_type = res.get('media_type', 'movie')
                title_en = fetch_title_en(tmdb_id, media_type)
                overview = fetch_overview(tmdb_id, media_type)
                poster = fetch_poster(tmdb_id, media_type)
                add_item(cid, tmdb_id, media_type, cat_id, res.get('title') or res.get('name', title), title_en, overview, poster or '')
                if media_type == 'tv':
                    for ep in fetch_episodes_from_tmdb(tmdb_id):
                        add_episode(cid, ep['season'], ep['episode'], ep['name'])
                found.append(f"{cid} - {title}")
            else:
                not_found.append(f"{cid} - {title}")
                add_pending_bulk(cid, title, "not_found")
            # تاخیر برای جلوگیری از محدودیت
            time.sleep(0.4)
            # ارسال گزارش وضعیت هر ۱۰ مورد
            if idx % 10 == 0 or idx == total:
                await query.edit_message_text(f"⏳ پردازش {idx} از {total}...")
        # گزارش نهایی
        msg = f"📊 *گزارش پردازش:*\n✅ پیدا شد: {len(found)}\n❌ پیدا نشد: {len(not_found)}"
        if context.user_data.get('bulk_errors'):
            msg += f"\n⚠️ خطاهای فایل: {len(context.user_data['bulk_errors'])}"
        if not_found:
            msg += f"\n\n🔍 *لیست پیدا نشده:*\n" + "\n".join(not_found[:10])
            if len(not_found) > 10:
                msg += f"\n... و {len(not_found)-10} مورد دیگر"
        keyboard = [[InlineKeyboardButton("✅ ذخیره موارد پیدا شده و ارسال به کانال", callback_data="bulk_save_channel")],
                    [InlineKeyboardButton("✅ فقط ذخیره کن (بدون کانال)", callback_data="bulk_save_only")],
                    [InlineKeyboardButton("❌ لغو همه", callback_data="bulk_cancel")]]
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data['bulk_found_count'] = len(found)
        context.user_data['bulk_not_found'] = not_found
        return BULK_CONFIRM
    else:
        await query.edit_message_text("نام دسته جدید را بنویسید:")
        context.user_data['waiting_bulk_new_cat'] = True
        return BULK_CATEGORY

async def bulk_new_cat_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    name = update.message.text.strip()
    if name:
        add_category(name)
        conn = sqlite3.connect("shop.db")
        c = conn.cursor()
        c.execute("SELECT id FROM categories WHERE name=?", (name,))
        cat_id = c.fetchone()[0]
        conn.close()
        context.user_data['bulk_category_id'] = cat_id
        await update.message.reply_text(f"✅ دسته '{name}' اضافه شد. در حال پردازش...")
        # ادامه پردازش (تکرار کد مشابه)
        items = context.user_data['bulk_items']
        found = []
        not_found = []
        for idx, (cid, title) in enumerate(items, 1):
            results = search_tmdb(title)
            if results:
                res = results[0]
                tmdb_id = res['id']
                media_type = res.get('media_type', 'movie')
                title_en = fetch_title_en(tmdb_id, media_type)
                overview = fetch_overview(tmdb_id, media_type)
                poster = fetch_poster(tmdb_id, media_type)
                add_item(cid, tmdb_id, media_type, cat_id, res.get('title') or res.get('name', title), title_en, overview, poster or '')
                if media_type == 'tv':
                    for ep in fetch_episodes_from_tmdb(tmdb_id):
                        add_episode(cid, ep['season'], ep['episode'], ep['name'])
                found.append(f"{cid} - {title}")
            else:
                not_found.append(f"{cid} - {title}")
                add_pending_bulk(cid, title, "not_found")
            time.sleep(0.4)
        msg = f"📊 *گزارش:*\n✅ پیدا شد: {len(found)}\n❌ پیدا نشد: {len(not_found)}"
        keyboard = [[InlineKeyboardButton("✅ ذخیره و ارسال به کانال", callback_data="bulk_save_channel")],
                    [InlineKeyboardButton("✅ فقط ذخیره کن", callback_data="bulk_save_only")],
                    [InlineKeyboardButton("❌ لغو", callback_data="bulk_cancel")]]
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data['bulk_found_count'] = len(found)
        context.user_data['bulk_not_found'] = not_found
        return BULK_CONFIRM
    return ConversationHandler.END

async def bulk_final_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "bulk_save_channel":
        channel_id = get_channel_id()
        if channel_id:
            # ارسال خلاصه به کانال
            try:
                await context.bot.send_message(chat_id=channel_id, text=f"📢 {context.user_data.get('bulk_found_count', 0)} فیلم جدید به دسته {get_category_name(context.user_data.get('bulk_category_id', 0))} اضافه شد.")
            except:
                await query.edit_message_text("⚠️ کانال تنظیم نشده یا ربات ادمین نیست.")
        else:
            await query.edit_message_text("⚠️ کانال تنظیم نشده است.")
        clear_pending_bulk()
        await query.edit_message_text(f"✅ {context.user_data.get('bulk_found_count', 0)} فیلم ذخیره و به کانال ارسال شد.")
    elif query.data == "bulk_save_only":
        clear_pending_bulk()
        await query.edit_message_text(f"✅ {context.user_data.get('bulk_found_count', 0)} فیلم ذخیره شد (کانال ارسال نشد).")
    else:
        clear_pending_bulk()
        await query.edit_message_text("❌ عملیات لغو شد.")
    context.user_data.clear()
    return ConversationHandler.END

# ===================== USER PANEL =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].startswith('detail_'):
        custom_id = int(context.args[0].split('_')[1])
        await show_detail_direct(update, context, custom_id)
        return
    keyboard = [[InlineKeyboardButton("🆕 جدیدترین", callback_data="latest")]]
    for cid, name in get_categories(only_visible=True):
        keyboard.append([InlineKeyboardButton(f"📂 {name}", callback_data=f"browse_{cid}")])
    keyboard.append([InlineKeyboardButton("🔍 جستجو", callback_data="search_mode")])
    keyboard.append([InlineKeyboardButton("🛒 سبد خرید", callback_data="show_cart")])
    keyboard.append([InlineKeyboardButton("📤 نهایی کردن سفارش", callback_data="finalize_order")])
    await update.message.reply_text("🎬 به فروشگاه خوش آمدید!", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_detail_direct(update, context, custom_id):
    item = get_item(custom_id)
    if not item:
        await update.message.reply_text("یافت نشد.")
        return
    await send_item_detail(update, context, custom_id, update.message)

async def send_item_detail(update, context, custom_id, message_obj=None):
    item = get_item(custom_id)
    if not item:
        return
    custom_id, tmdb_id, media_type, cat_id, title, title_en, overview, poster, _ = item
    text = f"🎞 *شماره:* {custom_id}\n*نام:* {title}"
    if title_en:
        text += f"\n*نام انگلیسی:* {title_en}"
    text += f"\n📝 *توضیحات:*\n{overview}"
    keyboard = []
    if media_type == 'movie':
        keyboard.append([InlineKeyboardButton("➕ افزودن به سبد", callback_data=f"add_movie_{custom_id}")])
    else:
        episodes = get_episodes(custom_id)
        if episodes:
            keyboard.append([InlineKeyboardButton("📦 کل سریال", callback_data=f"add_series_all_{custom_id}")])
            keyboard.append([InlineKeyboardButton("🎬 انتخاب فصل/قسمت", callback_data=f"select_season_{custom_id}")])
        else:
            keyboard.append([InlineKeyboardButton("➕ افزودن به سبد", callback_data=f"add_movie_{custom_id}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_menu")])
    if message_obj:
        if poster and poster.startswith('http'):
            await message_obj.reply_photo(photo=poster, caption=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        elif poster:
            await message_obj.reply_photo(photo=poster, caption=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        query = update.callback_query
        if poster and poster.startswith('http'):
            await query.message.reply_photo(photo=poster, caption=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            await query.delete_message()
        elif poster:
            await query.message.reply_photo(photo=poster, caption=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            await query.delete_message()
        else:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def browse_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_id = int(query.data.split("_")[1])
    items = get_items_by_category(cat_id)
    if not items:
        await query.edit_message_text("خالی است.")
        return
    text = "📋 لیست (جدیدترین):\n"
    keyboard = [[InlineKeyboardButton(f"{cid} - {title}", callback_data=f"detail_{cid}")] for cid, title, _ in items[:30]]
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    items = get_latest_items(20)
    if not items:
        await query.edit_message_text("خالی است.")
        return
    text = "🆕 جدیدترین:\n"
    keyboard = [[InlineKeyboardButton(f"{cid} - {title}", callback_data=f"detail_{cid}")] for cid, title, _ in items]
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_menu")])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    custom_id = int(query.data.split("_")[1])
    await send_item_detail(update, context, custom_id)

async def select_season(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    custom_id = int(query.data.split("_")[2])
    episodes = get_episodes(custom_id)
    if not episodes:
        await query.edit_message_text("قسمتی ثبت نشده!")
        return
    seasons = sorted(set(e[0] for e in episodes))
    keyboard = [[InlineKeyboardButton(f"فصل {s}", callback_data=f"select_ep_{custom_id}_{s}")] for s in seasons]
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"detail_{custom_id}")])
    await query.edit_message_text("فصل را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

async def select_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    custom_id = int(parts[2])
    season_num = int(parts[3])
    eps = [e for e in get_episodes(custom_id) if e[0] == season_num]
    season_poster = get_season_poster(custom_id, season_num)
    item = get_item(custom_id)
    title = item[4] if item else "سریال"
    text = f"📺 *{title} - فصل {season_num}*"
    keyboard = [[InlineKeyboardButton(f"➕ کل فصل {season_num}", callback_data=f"add_season_{custom_id}_{season_num}")]]
    for _, ep_num, ep_name in eps:
        keyboard.append([InlineKeyboardButton(f"قسمت {ep_num}: {ep_name}", callback_data=f"add_ep_{custom_id}_{season_num}_{ep_num}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"select_season_{custom_id}")])
    if season_poster:
        await query.message.reply_photo(photo=season_poster, caption=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        await query.delete_message()
    else:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ===================== CART =====================
async def add_to_cart(update, context, display_text, custom_id, category_id):
    if "cart" not in context.user_data:
        context.user_data["cart"] = []
    context.user_data["cart"].append({"text": display_text, "custom_id": custom_id, "category_id": category_id})
    await update.callback_query.answer("✅ اضافه شد!")

async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    custom_id = int(query.data.split("_")[2])
    item = get_item(custom_id)
    if not item:
        return
    await add_to_cart(update, context, f"🎬 {item[4]} (شماره {custom_id})", custom_id, item[3])
    await query.edit_message_text(f"✅ {item[4]} به سبد اضافه شد.")

async def add_series_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    custom_id = int(query.data.split("_")[3])
    item = get_item(custom_id)
    if not item:
        return
    await add_to_cart(update, context, f"📺 {item[4]} (کل سریال - شماره {custom_id})", custom_id, item[3])
    await query.edit_message_text(f"✅ کل سریال به سبد اضافه شد.")

async def add_season(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split("_")
    custom_id = int(parts[2])
    season_num = int(parts[3])
    item = get_item(custom_id)
    if not item:
        return
    await add_to_cart(update, context, f"📺 {item[4]} - فصل {season_num} (شماره {custom_id})", custom_id, item[3])
    await query.edit_message_text(f"✅ فصل {season_num} اضافه شد.")

async def add_episode_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split("_")
    custom_id = int(parts[2])
    season_num = int(parts[3])
    episode_num = int(parts[4])
    item = get_item(custom_id)
    if not item:
        return
    eps = get_episodes(custom_id)
    ep_name = next((n for s, e, n in eps if s == season_num and e == episode_num), f"قسمت {episode_num}")
    await add_to_cart(update, context, f"📺 {item[4]} - فصل {season_num} - قسمت {episode_num} ({ep_name}) - شماره {custom_id}", custom_id, item[3])
    await query.edit_message_text(f"✅ قسمت {episode_num} اضافه شد.")

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cart = context.user_data.get("cart", [])
    if not cart:
        await query.edit_message_text("🛒 خالی است.")
        return
    grouped = {}
    for item in cart:
        cat_name = get_category_name(item["category_id"])
        grouped.setdefault(cat_name, []).append(item)
    text = "🛒 *سبد خرید:*\n\n"
    keyboard = []
    for cat_name, items in grouped.items():
        text += f"📂 **{cat_name}**\n"
        for idx, item in enumerate(items):
            text += f"  {idx+1}. {item['text']}\n"
        for idx, item in enumerate(items):
            pos = context.user_data["cart"].index(item)
            keyboard.append([InlineKeyboardButton(f"❌ حذف {item['text'][:20]}...", callback_data=f"remove_{pos}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_menu")])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def remove_from_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pos = int(query.data.split("_")[1])
    cart = context.user_data.get("cart", [])
    if 0 <= pos < len(cart):
        cart.pop(pos)
        await query.edit_message_text("✅ حذف شد.")
        await show_cart(update, context)
    else:
        await query.edit_message_text("خطا!")

# ===================== FINALIZE ORDER =====================
async def finalize_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not context.user_data.get("cart"):
        await query.edit_message_text("سبد خالی است!")
        return
    await query.edit_message_text("👤 لطفاً **نام خود** را وارد کنید:")
    return NAME_STATE

async def receive_customer_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("نام را وارد کنید.")
        return NAME_STATE
    cart = context.user_data.get("cart", [])
    if not cart:
        await update.message.reply_text("سبد خالی!")
        return ConversationHandler.END
    grouped = {}
    for item in cart:
        cat_name = get_category_name(item["category_id"])
        grouped.setdefault(cat_name, []).append(item)
    now = jdatetime.datetime.now()
    persian_date = now.strftime("%Y/%m/%d")
    persian_time = now.strftime("%H:%M")
    text = f"🛒 *سفارش جدید*\n👤 {name}\n📅 {persian_date} ساعت {persian_time}\n\n"
    for cat_name, items in grouped.items():
        text += f"📂 **{cat_name}**\n"
        for item in items:
            text += f"  ✅ {item['text']}\n"
    await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")
    context.user_data["cart"] = []
    await update.message.reply_text("✅ سفارش ارسال شد! متشکریم. /start")
    return ConversationHandler.END

# ===================== SEARCH =====================
async def search_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔍 نام فیلم را بنویسید:")

async def handle_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.message.text.strip()
    results = search_tmdb(q)
    if not results:
        await update.message.reply_text("❌ پیدا نشد.")
        return
    keyboard = []
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    for res in results[:5]:
        title = res.get('title') or res.get('name', '')
        c.execute("SELECT custom_id, title FROM items WHERE title LIKE ? OR title_en LIKE ?", (f"%{title}%", f"%{title}%"))
        db_items = c.fetchall()
        if db_items:
            for cid, db_title in db_items:
                keyboard.append([InlineKeyboardButton(f"{cid} - {db_title}", callback_data=f"detail_{cid}")])
        else:
            keyboard.append([InlineKeyboardButton(f"🔍 {title} (موجود نیست)", callback_data="none")])
    conn.close()
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_menu")])
    await update.message.reply_text("نتایج:", reply_markup=InlineKeyboardMarkup(keyboard))

async def none_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("موجود نیست.", show_alert=True)

async def back_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🆕 جدیدترین", callback_data="latest")]]
    for cid, name in get_categories(only_visible=True):
        keyboard.append([InlineKeyboardButton(f"📂 {name}", callback_data=f"browse_{cid}")])
    keyboard.append([InlineKeyboardButton("🔍 جستجو", callback_data="search_mode")])
    keyboard.append([InlineKeyboardButton("🛒 سبد خرید", callback_data="show_cart")])
    keyboard.append([InlineKeyboardButton("📤 نهایی کردن", callback_data="finalize_order")])
    await query.edit_message_text("🎬 منو:", reply_markup=InlineKeyboardMarkup(keyboard))

# ===================== MAIN CALLBACK HANDLER =====================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == "back_menu":
        await back_menu(update, context)
    elif data == "search_mode":
        await search_mode(update, context)
    elif data == "show_cart":
        await show_cart(update, context)
    elif data == "finalize_order":
        await finalize_order(update, context)
    elif data == "latest":
        await show_latest(update, context)
    elif data.startswith("browse_"):
        await browse_category(update, context)
    elif data.startswith("detail_"):
        await show_detail(update, context)
    elif data.startswith("add_movie_"):
        await add_movie(update, context)
    elif data.startswith("add_series_all_"):
        await add_series_all(update, context)
    elif data.startswith("select_season_"):
        await select_season(update, context)
    elif data.startswith("select_ep_"):
        await select_episode(update, context)
    elif data.startswith("add_season_"):
        await add_season(update, context)
    elif data.startswith("add_ep_"):
        await add_episode_to_cart(update, context)
    elif data.startswith("remove_"):
        await remove_from_cart(update, context)
    elif data.startswith("toggle_cat_"):
        await toggle_category(update, context)
    elif data.startswith("edit_"):
        await edit_choose_field(update, context)
    elif data == "edit_cancel":
        await edit_cancel(update, context)
    elif data == "none":
        await none_callback(update, context)
    elif data == "admin_use_tmdb":
        await admin_use_tmdb(update, context)
    elif data == "admin_upload":
        await admin_upload(update, context)
    elif data == "admin_season_yes" or data == "admin_season_no":
        await admin_season_choice(update, context)
    elif data == "admin_new_cat":
        await admin_new_category(update, context)
    elif data == "admin_cancel":
        await admin_cancel(update, context)
    elif data.startswith("bulk_cat_"):
        await bulk_category_choice(update, context)
    elif data == "bulk_new_cat":
        await update.callback_query.edit_message_text("نام دسته جدید را بنویسید:")
        context.user_data['waiting_bulk_new_cat'] = True
    elif data in ["bulk_save_channel", "bulk_save_only", "bulk_cancel"]:
        await bulk_final_decision(update, context)

# ===================== RUN =====================
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Add Error Handler
    app.add_error_handler(error_handler)
    
    # Add Conversation Handlers
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('add', admin_add)],
        states={
            ADD_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_get_number)],
            ADD_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_search_name)],
            ADD_WAIT_PHOTO: [MessageHandler(filters.PHOTO, admin_receive_photo)],
            ADD_WAIT_SEASON_PHOTO: [MessageHandler(filters.PHOTO, admin_receive_season_photo)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('edit', edit_item_start)],
        states={EDIT_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_receive_text), MessageHandler(filters.PHOTO, edit_receive_photo)]},
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('setchannel', set_channel)],
        states={SET_CHANNEL_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_channel)]},
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('bulkadd', bulk_add_start)],
        states={
            BULK_STATE: [MessageHandler(filters.Document.ALL, bulk_receive_file)],
            BULK_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_new_cat_text)],
            BULK_CONFIRM: [CallbackQueryHandler(bulk_final_decision)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(finalize_order, pattern="finalize_order")],
        states={NAME_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_customer_name)]},
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    
    # Admin commands
    app.add_handler(CommandHandler("managecats", manage_categories))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID), add_new_category_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_text))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("🤖 ربات با موفقیت روشن شد!")
    app.run_polling()

if __name__ == "__main__":
    main()