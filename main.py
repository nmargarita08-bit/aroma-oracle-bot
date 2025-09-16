import os, threading
from flask import Flask

app = Flask(__name__)

@app.get("/")
def health():
    return "Bot is running!"

def run_http():
    port = int(os.environ.get("PORT", 10000))
    # важное: слушаем 0.0.0.0 и порт из ENV
    app.run(host="0.0.0.0", port=port)

# поднимаем http-сервер в отдельном потоке,
# а основной поток остаётся для бота (polling)
threading.Thread(target=run_http, daemon=True).start()

print("HTTP health server started")
import os
import csv
import random
import sqlite3
from datetime import date
from contextlib import closing
from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = os.getenv("ADMIN_ID", "")  # optional: your Telegram user id for /broadcast
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "false").lower() == "true"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # e.g. https://yourapp.onrender.com/webhook
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("DB_PATH", "oracle.db")
CSV_PATH = os.getenv("CSV_PATH", "aroma_oracle_pack.csv")

# --- storage ---
def _init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            last_draw TEXT
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS saved (
            user_id TEXT,
            oil_id INTEGER,
            ts TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
    return True

# --- content ---
@dataclass
class Oil:
    id: int
    name: str
    emoji: str
    physical: str
    emotional: str
    mantra: str
    bg_hex: str
    audio_cue: str

OILS = []

def load_oils():
    global OILS
    OILS = []
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f)):
            OILS.append(Oil(
                id=i,
                name=row.get("oil","").strip(),
                emoji=row.get("emoji","").strip(),
                physical=row.get("physical","").strip(),
                emotional=row.get("emotional","").strip(),
                mantra=row.get("mantra","").strip(),
                bg_hex=row.get("bg_hex","#000000").strip(),
                audio_cue=row.get("audio_cue","").strip(),
            ))

def get_user_last_draw(user_id:str):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT last_draw FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None

def set_user_last_draw(user_id:str, d: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO users(user_id,last_draw) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET last_draw=excluded.last_draw", (user_id, d))

def save_user_oil(user_id:str, oil_id:int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO saved(user_id, oil_id) VALUES (?,?)", (user_id, oil_id))

def list_user_saved(user_id:str, limit:int=10):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("""
            SELECT oil_id, ts FROM saved WHERE user_id=? ORDER BY ts DESC LIMIT ?
        """, (user_id, limit))
        rows = cur.fetchall()
    items = []
    for oil_id, ts in rows:
        o = next((x for x in OILS if x.id == oil_id), None)
        if o:
            items.append((o, ts))
    return items

def pick_oil() -> Oil:
    return random.choice(OILS)

def format_oil_message(o:Oil) -> str:
    lines = [
        f"🔮 <b>Арома‑Оракул: {o.name} {o.emoji}</b>",
        "",
        f"• <b>Физика:</b> {o.physical}",
        f"• <b>Эмоции:</b> {o.emotional}",
        f"<i>{o.mantra}</i>"
    ]
    return "\n".join(lines)

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ Масло дня", callback_data="draw")],
        [InlineKeyboardButton("📦 Мой набор", callback_data="saved"),
         InlineKeyboardButton("💬 Консультация", url=os.getenv("CONSULT_URL","https://wa.me/77000000000"))],
    ])

def draw_keyboard(oil_id:int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 Сохранить", callback_data=f"save:{oil_id}"),
         InlineKeyboardButton("🔁 Ещё раз", callback_data="draw_again")],
        [InlineKeyboardButton("📣 Поделиться", url=os.getenv("SHARE_URL","https://t.me/share/url"))]
    ])

# --- handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "Привет! Я <b>Арома‑Оракул</b>. Раз в день подберу твоё <b>масло дня</b>. Нажми кнопку ниже ✨",
        reply_markup=main_keyboard()
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команды: /start — начать, /help — помощь. Нажми «Масло дня» на клавиатуре.")

async def draw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    today = date.today().isoformat()

    last = get_user_last_draw(user_id)
    if last == today:
        await query.edit_message_text(
            "Сегодня ты уже вытянула своё масло 🙂 Возвращайся завтра!",
            reply_markup=main_keyboard()
        )
        return

    o = pick_oil()
    set_user_last_draw(user_id, today)
    context.user_data["last_oil_id"] = o.id

    await query.edit_message_html(
        format_oil_message(o),
        reply_markup=draw_keyboard(o.id)
    )

async def draw_again(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    today = date.today().isoformat()
    last = get_user_last_draw(user_id)
    if last == today:
        # запрещаем переигровку
        await query.edit_message_text(
            "Сегодня уже был твой Оракул 😉 Жду тебя завтра.",
            reply_markup=main_keyboard()
        )
        return
    # fallback
    await draw_callback(update, context)

async def saved_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    items = list_user_saved(str(query.from_user.id), limit=10)
    if not items:
        await query.edit_message_text("Пока пусто. Нажми «Масло дня» и сохраняй понравившиеся.", reply_markup=main_keyboard())
        return
    lines = ["Твои последние масла:\n"]
    for (o, ts) in items:
        lines.append(f"• {o.name} {o.emoji} — {ts.split('.')[0]}")
    await query.edit_message_text("\n".join(lines), reply_markup=main_keyboard())

async def save_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Сохранила в твой набор 💾")
    payload = query.data.split(":",1)
    oil_id = int(payload[1])
    save_user_oil(str(query.from_user.id), oil_id)
    await query.edit_message_reply_markup(reply_markup=draw_keyboard(oil_id))

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == "draw":
        return await draw_callback(update, context)
    if data == "saved":
        return await saved_callback(update, context)
    if data == "draw_again":
        return await draw_again(update, context)
    if data.startswith("save:"):
        return await save_callback(update, context)
    await update.callback_query.answer()

def build_app():
    _init_db()
    load_oils()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(callback_router))
    return app

if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("Please set BOT_TOKEN env var (from @BotFather).")
    app = build_app()
    if USE_WEBHOOK and WEBHOOK_URL:
        # webhook mode (for Render/Railway/Heroku). PTB hosts aiohttp server.
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
            secret_token=None
        )
    else:
        # local quick start (long polling)
        app.run_polling(drop_pending_updates=True)
