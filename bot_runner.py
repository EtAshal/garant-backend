import asyncio
import os
import sys
import math
sys.stdout.reconfigure(encoding='utf-8')

from aiogram import Bot, Dispatcher
from aiogram.types import Message, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ChatPermissions
from aiogram.filters import CommandStart, Command
from aiogram import F
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SECRET"))

WEBAPP_URL = os.getenv("WEBAPP_URL")

# Постоянная клавиатура внизу чата
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="📋 Мои сделки"),
            KeyboardButton(text="👤 Профиль"),
            KeyboardButton(text="❓ Помощь"),
        ]
    ],
    resize_keyboard=True,
    persistent=True
)

# ── ХЕЛПЕРЫ ───────────────────────────────────────────────────────────────────

def get_status(pts):
    if pts >= 1500: return "⭐ Гарант"
    if pts >= 500:  return "🛡️ Надёжный"
    if pts >= 100:  return "📜 Проверенный"
    return "🆕 Новичок"

def get_commission(amount):
    if amount <= 25000:  return 0.03
    if amount <= 100000: return 0.04
    return 0.05

def calc_points(deals, user_id):
    completed = [d for d in deals if d["status"] == "completed"]
    seller_pts = sum(math.floor(float(d["amount"]) / 100) for d in completed if d["seller_id"] == user_id)
    buyer_pts  = sum(math.floor(float(d["amount"]) / 100) for d in completed if d["buyer_id"]  == user_id)
    return seller_pts + buyer_pts


# ── /start ────────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def start(message: Message):
    user = message.from_user
    args = message.text.split(maxsplit=1)
    deep_link = args[1] if len(args) > 1 else ""

    # Сохраняем пользователя
    try:
        supabase.table("users").upsert({
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name
        }).execute()
    except Exception as e:
        print(f"Ошибка: {e}")

    # Реферальная ссылка
    if deep_link.startswith("ref_"):
        referrer_id = int(deep_link.replace("ref_", ""))

        # Проверяем что это не сам себя приглашает
        if referrer_id != user.id:
            try:
                # Проверяем что пользователь новый (не был раньше)
                existing = supabase.table("users").select("referred_by").eq("id", user.id).execute()

                if existing.data and existing.data[0].get("referred_by") is None:
                    # Проверяем лимит приглашений у реферера (макс 5)
                    referrer = supabase.table("users").select("referral_count").eq("id", referrer_id).execute()

                    if referrer.data and referrer.data[0].get("referral_count", 0) < 5:
                        # Записываем кто пригласил
                        supabase.table("users").update({
                            "referred_by": referrer_id
                        }).eq("id", user.id).execute()

                        # Начисляем +20 очков рефереру
                        new_count  = referrer.data[0].get("referral_count", 0) + 1
                        new_points = referrer.data[0].get("referral_points", 0) + 20 if hasattr(referrer.data[0], 'get') else 20
                        supabase.table("users").update({
                            "referral_count":  new_count,
                            "referral_points": supabase.table("users").select("referral_points").eq("id", referrer_id).execute().data[0].get("referral_points", 0) + 20
                        }).eq("id", referrer_id).execute()

                        # Уведомляем реферера
                        try:
                            await bot.send_message(
                                referrer_id,
                                f"🎉 По вашей ссылке зарегистрировался новый пользователь!\n\n"
                                f"+20 очков репутации\n"
                                f"Приглашено: {new_count}/5"
                            )
                        except:
                            pass
            except Exception as e:
                print(f"Реферал ошибка: {e}")

    # Глубокая ссылка на сделку
    if deep_link.startswith("deal_"):
        deal_id = deep_link.replace("deal_", "")
        deal_url = f"{WEBAPP_URL.rstrip('/')}/deal.html?id={deal_id}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔒 Открыть сделку",
                web_app=WebAppInfo(url=deal_url)
            )]
        ])
        await message.answer(
            "📜 Вам прислали ссылку на сделку.\n\nНажмите кнопку чтобы открыть её:",
            reply_markup=keyboard
        )
        return

    # Глубокая ссылка на профиль
    if deep_link.startswith("profile_"):
        user_id = deep_link.replace("profile_", "")
        profile_url = f"{WEBAPP_URL.rstrip('/')}/public_profile.html?id={user_id}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👤 Посмотреть профиль", web_app=WebAppInfo(url=profile_url))],
            [InlineKeyboardButton(text="🔒 Открыть Гарант",     web_app=WebAppInfo(url=WEBAPP_URL))]
        ])
        await message.answer(
            "📜 Вам прислали карточку репутации.\n\nНажмите кнопку чтобы посмотреть профиль пользователя.",
            reply_markup=keyboard
        )
        return

    # Обычный старт
    await message.answer(
        "⚖️ Добро пожаловать в Гарантъ!\n\n"
        "Безопасные сделки между людьми — деньги хранятся у нас до подтверждения обеих сторон.",
        reply_markup=MAIN_KEYBOARD
    )
    await message.answer(
        "Нажмите кнопку чтобы открыть платформу:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Открыть Гарант", web_app=WebAppInfo(url=WEBAPP_URL))]
        ])
    )


ADMIN_ID = 1291887879

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return  # Молча игнорируем
    admin_url = f"{WEBAPP_URL.rstrip('/')}/admin.html"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⚖️ Открыть панель арбитража",
            web_app=WebAppInfo(url=admin_url)
        )]
    ])
    await message.answer(
        "🔐 <b>Панель арбитража</b>\n\nДобро пожаловать, арбитр.",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.message(Command("deals"))
async def cmd_deals(message: Message):
    user_id = message.from_user.id
    try:
        result = supabase.table("deals").select("*").or_(
            f"seller_id.eq.{user_id},buyer_id.eq.{user_id}"
        ).in_("status", ["pending", "active", "dispute"]).execute()

        deals = result.data
        if not deals:
            await message.answer("📭 У вас нет активных сделок.\n\nОткройте Гарант чтобы создать новую.")
            return

        status_map = {
            "pending": "🕯 Ожидает покупателя",
            "active":  "📜 Активна",
            "dispute": "⚔️ Спор"
        }

        text = "📋 <b>Ваши активные сделки:</b>\n\n"
        buttons = []

        for deal in deals:
            role = "Продавец" if deal["seller_id"] == user_id else "Покупатель"
            amount = int(float(deal["amount"]))
            status = status_map.get(deal["status"], deal["status"])
            text += f"• <b>{deal['description']}</b>\n"
            text += f"  {amount:,} ₽ · {role} · {status}\n\n"

            deal_url = f"{WEBAPP_URL.rstrip('/')}/deal.html?id={deal['id']}"
            buttons.append([InlineKeyboardButton(
                text=f"📜 {deal['description'][:25]}",
                web_app=WebAppInfo(url=deal_url)
            )])

        buttons.append([InlineKeyboardButton(
            text="🔒 Открыть Гарант",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )])

        await message.answer(text, parse_mode="HTML",
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    except Exception as e:
        await message.answer(f"Ошибка: {e}")


# ── /profile ──────────────────────────────────────────────────────────────────

@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    user_id = message.from_user.id
    user = message.from_user
    try:
        result = supabase.table("deals").select("*").or_(
            f"seller_id.eq.{user_id},buyer_id.eq.{user_id}"
        ).execute()

        deals = result.data
        completed = [d for d in deals if d["status"] == "completed"]
        disputes  = [d for d in deals if d["status"] == "dispute"]
        as_seller = [d for d in completed if d["seller_id"] == user_id]
        as_buyer  = [d for d in completed if d["buyer_id"]  == user_id]

        total_pts = calc_points(deals, user_id)
        status    = get_status(total_pts)
        volume    = sum(float(d["amount"]) for d in completed)

        # Прогресс до следующего уровня
        levels = [0, 100, 500, 1500]
        next_label = ""
        for i in range(len(levels) - 1):
            if total_pts < levels[i+1]:
                need = levels[i+1] - total_pts
                next_label = f"До следующего звания: {need:,} очков"
                break

        name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Пользователь"
        vol_str = f"{volume/1000:.1f}к ₽" if volume >= 1000 else f"{int(volume):,} ₽"

        text = (
            f"👤 <b>{name}</b>\n"
            f"{status}\n\n"
            f"⭐ Очки доверия: <b>{total_pts:,}</b>\n"
            f"{next_label}\n\n"
            f"📊 Статистика:\n"
            f"✅ Завершено: <b>{len(completed)}</b>\n"
            f"📦 Как продавец: <b>{len(as_seller)}</b> сделок\n"
            f"🛒 Как покупатель: <b>{len(as_buyer)}</b> сделок\n"
            f"⚔️ Споров: <b>{len(disputes)}</b>\n"
            f"🪙 Оборот: <b>{vol_str}</b>"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👤 Открыть профиль", web_app=WebAppInfo(url=f"{WEBAPP_URL.rstrip('/')}/profile.html"))]
        ])

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    except Exception as e:
        await message.answer(f"Ошибка: {e}")


# ── /help ─────────────────────────────────────────────────────────────────────

@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "⚖️ <b>Как работает Гарантъ</b>\n\n"
        "1️⃣ <b>Продавец</b> создаёт сделку и отправляет ссылку покупателю\n\n"
        "2️⃣ <b>Покупатель</b> переходит по ссылке и вносит деньги — они хранятся у Гаранта, не у продавца\n\n"
        "3️⃣ <b>Продавец</b> передаёт товар или услугу\n\n"
        "4️⃣ <b>Оба подтверждают</b> — деньги уходят продавцу\n\n"
        "❌ Если один отказывается — открывается спор и арбитр разбирается\n\n"
        "⏳ Если никто не нажал кнопку 7 дней — деньги автоматически уходят продавцу"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔒 Открыть Гарант", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ── ОБЫЧНЫЕ СООБЩЕНИЯ ─────────────────────────────────────────────────────────

@dp.message()
async def handle_message(message: Message):
    text = message.text or ""

    # Кнопки клавиатуры
    if text == "📋 Мои сделки":
        await cmd_deals(message)
        return
    if text == "👤 Профиль":
        await cmd_profile(message)
        return
    if text == "❓ Помощь":
        await cmd_help(message)
        return

    # Ссылка на сделку
    if "deal.html?id=" in text:
        deal_id = text.split("id=")[-1].strip()
        deal_url = f"{WEBAPP_URL.rstrip('/')}/deal.html?id={deal_id}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Открыть сделку", web_app=WebAppInfo(url=deal_url))]
        ])
        await message.answer(
            "Нажми кнопку чтобы открыть сделку:",
            reply_markup=keyboard
        )


# ── УВЕДОМЛЕНИЕ О НОВОМ СТАТУСЕ ───────────────────────────────────────────────
# Вызывается из main.py после завершения сделки

async def notify_status_upgrade(bot_instance, user_id: int, old_pts: int, new_pts: int):
    """Отправляет поздравление если пользователь получил новый статус."""
    levels = {100: "📜 Проверенный", 500: "🛡️ Надёжный", 1500: "⭐ Гарант"}
    for threshold, status_name in levels.items():
        if old_pts < threshold <= new_pts:
            try:
                await bot_instance.send_message(
                    user_id,
                    f"🎉 Поздравляем! Вы получили новый статус:\n\n"
                    f"<b>{status_name}</b>\n\n"
                    f"Ваши очки доверия: {new_pts:,}\n"
                    f"Продолжайте в том же духе!",
                    parse_mode="HTML"
                )
            except:
                pass
            break


# ── АРБИТРАЖНАЯ ГРУППА ────────────────────────────────────────────

async def create_dispute_group(deal_id: str, seller_id: int, buyer_id: int, description: str, amount: float):
    """Уведомляет стороны о споре и предлагает написать арбитру напрямую."""
    try:
        ADMIN_USERNAME = "abdaletashal"  # твой username без @

        msg = (
            "<b>По вашей сделке открыт спор</b>\n\n"
            f"Товар: {description}\n"
            f"Сумма: {int(amount):,} ₽\n\n"
            "Арбитр рассмотрит ситуацию. Напишите ему напрямую и изложите свою позицию."
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✉️ Написать арбитру", url=f"https://t.me/{ADMIN_USERNAME}")]
        ])

        try:
            await bot.send_message(seller_id, msg, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            print(f"[Арбитраж] Не смог написать продавцу: {e}")

        try:
            await bot.send_message(buyer_id, msg, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            print(f"[Арбитраж] Не смог написать покупателю: {e}")

        return {"success": True}

    except Exception as e:
        print(f"[Арбитраж] Ошибка: {e}")
        return {"success": False, "error": str(e)}


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())