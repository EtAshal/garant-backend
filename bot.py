import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.types import Message, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SECRET"))

@dp.message(CommandStart())
async def start(message: Message):
    # Сохраняем пользователя в базу
    user = message.from_user
    try:
        supabase.table("users").upsert({
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name
        }).execute()
    except Exception as e:
        print(f"Ошибка сохранения пользователя: {e}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔒 Открыть Гарант",
            web_app=WebAppInfo(url=os.getenv("WEBAPP_URL"))
        )]
    ])
    await message.answer(
        "Добро пожаловать в Гарант!\n\nБезопасные сделки между людьми.",
        reply_markup=keyboard
    )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())