import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import sqlite3
import os

API_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

conn = sqlite3.connect("bot.db")
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    invited_by INTEGER,
    channel TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS referrals (
    referrer INTEGER,
    referred INTEGER
)""")
conn.commit()

def get_ref_link(user_id):
    return f"https://t.me/{{os.getenv('BOT_USERNAME')}}?start={{user_id}}"

@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    args = message.get_args()
    user_id = message.from_user.id

    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not cur.fetchone():
        invited_by = int(args) if args.isdigit() else None
        cur.execute("INSERT INTO users (user_id, invited_by) VALUES (?, ?)", (user_id, invited_by))
        if invited_by:
            cur.execute("INSERT INTO referrals (referrer, referred) VALUES (?, ?)", (invited_by, user_id))
        conn.commit()

    cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer=?", (user_id,))
    ref_count = cur.fetchone()[0]

    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Привязать канал", callback_data="bind_channel"))
    await message.answer(
        f"Твоя реферальная ссылка:\n{{get_ref_link(user_id)}}\n\n"
        f"Ты пригласил: {{ref_count}} человек(а)",
        reply_markup=kb
    )

@dp.message_handler(lambda msg: msg.text and msg.text.startswith("/start ") and msg.chat.type == "private")
async def anonymous_message(message: types.Message):
    sender_id = message.from_user.id
    receiver_id = int(message.text.split(" ")[1])
    if sender_id == receiver_id:
        return await message.reply("Ты не можешь отправить сообщение себе.")
    await message.reply("Напиши сообщение, и я передам его анонимно. Просто ответь на это сообщение.")

@dp.message_handler(lambda msg: msg.reply_to_message and "анонимно" in msg.reply_to_message.text)
async def handle_reply(message: types.Message):
    original_text = message.reply_to_message.text
    receiver_id = int(original_text.split(" ")[-1])
    text = message.text

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("Удалить", callback_data="delete"),
        InlineKeyboardButton("Отправить в канал", callback_data=f"publish_{receiver_id}")
    )
    await bot.send_message(receiver_id, f"Тебе пришло анонимное сообщение:\n\n{text}", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "delete")
async def delete_message(callback_query: types.CallbackQuery):
    await callback_query.message.delete()

@dp.callback_query_handler(lambda c: c.data.startswith("publish_"))
async def publish_to_channel(callback_query: types.CallbackQuery):
    user_id = int(callback_query.data.split("_")[1])
    cur.execute("SELECT channel FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if row and row[0]:
        await bot.send_message(row[0], callback_query.message.text)
        await callback_query.answer("Отправлено в канал.")
    else:
        await callback_query.answer("Канал не привязан.")

@dp.callback_query_handler(lambda c: c.data == "bind_channel")
async def ask_for_channel(callback_query: types.CallbackQuery):
    await callback_query.message.answer("Перешли мне @юзернейм канала, куда хочешь публиковать сообщения.")

@dp.message_handler(lambda msg: msg.text.startswith("@"))
async def bind_channel(message: types.Message):
    user_id = message.from_user.id
    cur.execute("UPDATE users SET channel=? WHERE user_id=?", (message.text.strip(), user_id))
    conn.commit()
    await message.reply("Канал привязан. Убедись, что бот — админ в канале.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
