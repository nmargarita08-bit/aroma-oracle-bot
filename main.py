import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, executor, types

# === Flask "healthcheck" сервер для Render ===
app = Flask(__name__)

@app.get("/")
def health():
    return "Bot is running!"

def run_http():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Запускаем Flask в отдельном потоке
threading.Thread(target=run_http, daemon=True).start()
print("HTTP health server started")

# === Telegram бот ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Обработчик команды /start
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Привет 🌿! Я твой Aroma-бот, напиши /help")

# Обработчик команды /help
@dp.message_handler(commands=["help"])
async def help_cmd(message: types.Message):
    await message.answer("Доступные команды:\n/start - приветствие\n/help - помощь")

# === Запуск бота ===
if __name__ == "__main__":
    print("Telegram bot starting...")
    executor.start_polling(dp, skip_updates=True)
