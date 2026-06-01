import asyncio
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

from aiogram import Bot, Dispatcher
from aiogram.types import Message, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SECRET"))

WEBAPP_URL = os.getenv("WEBAPP_URL")

@dp.message(CommandStart())
async def start(message: Message):
    user = message.from_user
    try:
        supabase.table("users").upsert({
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name
        }).execute()
    except Exception as e:
        print(f"Ошибка: {e}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔒 Открыть Гарант",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ])
    await message.answer(
        "Добро пожаловать в Гарант!\n\nБезопасные сделки между людьми.",
        reply_markup=keyboard
    )

@dp.message()
async def handle_message(message: Message):
    text = message.text or ""
    if "deal.html?id=" in text:
        deal_id = text.split("id=")[-1].strip()
        deal_url = f"{WEBAPP_URL.rstrip('/')}/deal.html?id={deal_id}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔒 Открыть сделку",
                web_app=WebAppInfo(url=deal_url)
            )]
        ])
        await message.answer(
            "Нажми кнопку чтобы открыть сделку:",
            reply_markup=keyboard
        )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())