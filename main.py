from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client
from dotenv import load_dotenv
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timezone, timedelta, time as dtime
import os
import sys
import math
import asyncio
import threading
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

bot_instance = Bot(token=os.getenv("BOT_TOKEN"))

app = FastAPI()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SECRET"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = AsyncIOScheduler(timezone="UTC")

# ── КОМИССИЯ ─────────────────────────────────────────────────────────────────
def get_commission(amount, is_premium=False):
    if is_premium:
        if amount <= 10000:  return 0.01
        if amount <= 25000:  return 0.02
        if amount <= 50000:  return 0.03
        if amount <= 100000: return 0.04
        return 0.05
    if amount <= 25000:  return 0.03
    if amount <= 100000: return 0.04
    return 0.05

# ── АВТОЗАВЕРШЕНИЕ ────────────────────────────────────────────────────────────
async def auto_complete_deals():
    try:
        result = supabase.table("deals").select("*").eq("status", "active").execute()
        now = datetime.now(timezone.utc)
        for deal in result.data:
            accepted_at_str = deal.get("accepted_at") or deal.get("updated_at") or deal.get("created_at")
            if not accepted_at_str:
                continue
            accepted_at = datetime.fromisoformat(accepted_at_str.replace("Z", "+00:00"))
            days_passed = (now - accepted_at).total_seconds() / 86400
            if days_passed >= 7:
                now_iso = now.isoformat()
                supabase.table("deals").update({
                    "status": "completed",
                    "seller_action": "confirm",
                    "buyer_action": "confirm",
                    "completed_at": now_iso
                }).eq("id", deal["id"]).execute()
                try:
                    await bot_instance.send_message(deal["seller_id"],
                        f"✅ Сделка автоматически завершена!\n\nТовар: {deal['description']}\nСумма: {int(deal['amount']):,} ₽\n\nПрошло 7 дней — деньги переведены вам.")
                except: pass
                if deal.get("buyer_id"):
                    try:
                        await bot_instance.send_message(deal["buyer_id"],
                            f"📋 Сделка автоматически завершена.\n\nТовар: {deal['description']}\nПрошло 7 дней — средства переведены продавцу.")
                    except: pass
                print(f"[Автозавершение] Сделка {deal['id']} завершена через 7 дней")
    except Exception as e:
        print(f"[Автозавершение] Ошибка: {e}")

# ── НАПОМИНАНИЯ ───────────────────────────────────────────────────────────────
async def send_reminders():
    try:
        result = supabase.table("deals").select("*").eq("status", "active").execute()
        now = datetime.now(timezone.utc)
        for deal in result.data:
            updated_str = deal.get("accepted_at") or deal.get("updated_at") or deal.get("created_at")
            if not updated_str:
                continue
            updated_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            hours_passed = (now - updated_at).total_seconds() / 3600
            if 24 <= hours_passed < 25:
                seller_action = deal.get("seller_action")
                buyer_action  = deal.get("buyer_action")
                if not seller_action and deal.get("seller_id"):
                    try:
                        await bot_instance.send_message(deal["seller_id"],
                            f"🔔 Напоминание о сделке\n\nТовар: {deal['description']}\nСумма: {int(deal['amount']):,} ₽\n\nПокупатель ждёт подтверждения.")
                    except: pass
                if not buyer_action and deal.get("buyer_id"):
                    try:
                        await bot_instance.send_message(deal["buyer_id"],
                            f"🔔 Напоминание о сделке\n\nТовар: {deal['description']}\nСумма: {int(deal['amount']):,} ₽\n\nПродавец ждёт вашего решения.")
                    except: pass
    except Exception as e:
        print(f"[Напоминание] Ошибка: {e}")

# ── ВЫПЛАТЫ ───────────────────────────────────────────────────────────────────
async def process_payouts():
    try:
        result = supabase.table("deals").select("*").eq("status", "completed").execute()
        now = datetime.now(timezone.utc)
        for deal in result.data:
            if deal.get("payout_sent"):
                continue
            completed_str = deal.get("completed_at") or deal.get("updated_at")
            if not completed_str:
                continue
            completed_at = datetime.fromisoformat(completed_str.replace("Z", "+00:00"))
            hours_passed = (now - completed_at).total_seconds() / 3600
            seller_deals = supabase.table("deals").select("amount").eq("status", "completed").eq("seller_id", deal["seller_id"]).execute()
            seller_pts = sum(math.floor(float(d["amount"]) / 100) for d in seller_deals.data)
            if seller_pts >= 1500:
                delay_hours = 2
            elif seller_pts >= 500:
                delay_hours = 6
            else:
                delay_hours = 12
            if hours_passed >= delay_hours:
                supabase.table("deals").update({"payout_sent": True}).eq("id", deal["id"]).execute()
                amount = int(float(deal["amount"]))
                seller_info = supabase.table("users").select("premium_until").eq("id", deal["seller_id"]).execute()
                seller_premium = False
                if seller_info.data and seller_info.data[0].get("premium_until"):
                    premium_dt = datetime.fromisoformat(seller_info.data[0]["premium_until"].replace("Z", "+00:00"))
                    seller_premium = premium_dt > datetime.now(timezone.utc)
                commission  = round(amount * get_commission(amount, is_premium=seller_premium))
                seller_gets = amount - commission
                try:
                    await bot_instance.send_message(deal["seller_id"],
                        f"💰 Деньги переведены!\n\nТовар: {deal['description']}\nСумма: {amount:,} ₽\nКомиссия: {commission:,} ₽\nВы получили: {seller_gets:,} ₽")
                except: pass
                print(f"[Выплата] Сделка {deal['id']} — выплачено {deal['seller_id']}")
    except Exception as e:
        print(f"[Выплата] Ошибка: {e}")

# ── ЗАТУХАНИЕ ОЧКОВ ───────────────────────────────────────────────────────────
async def apply_season_decay():
    try:
        now = datetime.now(timezone.utc)
        seasons = [
            datetime(now.year, 1,  1, tzinfo=timezone.utc),
            datetime(now.year, 4,  1, tzinfo=timezone.utc),
            datetime(now.year, 7,  1, tzinfo=timezone.utc),
            datetime(now.year, 10, 1, tzinfo=timezone.utc),
        ]
        season_names = {1: "Зима ❄️", 4: "Весна 🌸", 7: "Лето ☀️", 10: "Осень 🍂"}
        today_season = next((s for s in seasons if s.date() == now.date()), None)
        if not today_season:
            return
        season_name = season_names.get(today_season.month, "Сезон")
        users = supabase.table("users").select("id, referral_points, decay_history").execute()
        for user in users.data:
            try:
                current_pts = user.get("referral_points", 0) or 0
                if current_pts == 0:
                    continue
                new_pts = round(current_pts * 0.7)
                decay_history = user.get("decay_history") or []
                decay_history.append({
                    "season": season_name,
                    "date": now.strftime("%d.%m.%Y"),
                    "before": current_pts,
                    "after": new_pts
                })
                decay_history = decay_history[-10:]
                supabase.table("users").update({
                    "referral_points": new_pts,
                    "decay_history": decay_history
                }).eq("id", user["id"]).execute()
            except: pass
        print(f"[Затухание] Применено — {season_name}")
    except Exception as e:
        print(f"[Затухание] Ошибка: {e}")

# ── УВЕДОМЛЕНИЕ О ЗАТУХАНИИ ───────────────────────────────────────────────────
async def notify_season_decay():
    try:
        now = datetime.now(timezone.utc)
        seasons = [
            datetime(now.year, 1,  1, tzinfo=timezone.utc),
            datetime(now.year, 4,  1, tzinfo=timezone.utc),
            datetime(now.year, 7,  1, tzinfo=timezone.utc),
            datetime(now.year, 10, 1, tzinfo=timezone.utc),
        ]
        next_season = min((s for s in seasons if s > now), default=None)
        if not next_season:
            next_season = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        days_left = (next_season - now).days
        if days_left != 7:
            return
        users = supabase.table("users").select("id").execute()
        season_names = {1: "Зима ❄️", 4: "Весна 🌸", 7: "Лето ☀️", 10: "Осень 🍂"}
        name = season_names.get(next_season.month, "Новый сезон")
        date_str = next_season.strftime("%d.%m.%Y")
        for user in users.data:
            try:
                await bot_instance.send_message(user["id"],
                    f"⏳ <b>Через 7 дней наступает новый сезон!</b>\n\n{name} — {date_str}\n\nВсе очки уменьшатся на <b>30%</b>.\nУспейте провести сделки!",
                    parse_mode="HTML")
            except: pass
        print(f"[Затухание] Уведомления отправлены")
    except Exception as e:
        print(f"[Затухание] Ошибка: {e}")

# ── ЗАПУСК БОТА В ОТДЕЛЬНОМ ТРЕДЕ ────────────────────────────────────────────
def run_bot():
    """Запускает бота в отдельном event loop."""
    import bot_runner
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot_runner.main())

# ── ПЛАНИРОВЩИК ───────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    scheduler.add_job(auto_complete_deals, "interval", hours=1,    id="auto_complete")
    scheduler.add_job(send_reminders,      "interval", hours=1,    id="reminders")
    scheduler.add_job(process_payouts,     "interval", minutes=30, id="payouts")
    scheduler.add_job(notify_season_decay, "interval", hours=24,   id="season_notify")
    scheduler.add_job(apply_season_decay,  "interval", hours=24,   id="season_decay")
    scheduler.start()
    print("Планировщик запущен")

    # Запускаем бота в отдельном треде
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    print("Бот запущен")

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()

# ── МОДЕЛИ ────────────────────────────────────────────────────────────────────
class DealCreate(BaseModel):
    seller_id: int
    amount: float
    description: str

# ── ЭНДПОИНТЫ ─────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "ok"}

@app.post("/deals/create")
async def create_deal(deal: DealCreate):
    try:
        if deal.amount > 500000:
            return {"success": False, "error": "Максимальная сумма сделки — 500 000 ₽"}

        seller_deals = supabase.table("deals").select("amount, seller_id, buyer_id, status").or_(
            f"seller_id.eq.{deal.seller_id},buyer_id.eq.{deal.seller_id}"
        ).eq("status", "completed").execute()

        seller_pts = sum(math.floor(float(d["amount"]) / 100) for d in seller_deals.data)

        seller_user = supabase.table("users").select("premium_until, referral_points").eq("id", deal.seller_id).execute()
        is_premium = False
        if seller_user.data and seller_user.data[0].get("premium_until"):
            premium_until = datetime.fromisoformat(seller_user.data[0]["premium_until"].replace("Z", "+00:00"))
            is_premium = premium_until > datetime.now(timezone.utc)

        ref_pts = seller_user.data[0].get("referral_points", 0) if seller_user.data else 0
        seller_pts += ref_pts

        if is_premium:
            limit = 500000
        elif seller_pts >= 1500:
            limit = 250000
        elif seller_pts >= 500:
            limit = 150000
        elif seller_pts >= 100:
            limit = 50000
        else:
            limit = 10000

        if deal.amount > limit:
            status_name = "💎 Премиум" if is_premium else (
                "⭐ Гарант" if seller_pts >= 1500 else
                "🛡️ Надёжный" if seller_pts >= 500 else
                "📜 Проверенный" if seller_pts >= 100 else "🆕 Новичок"
            )
            return {"success": False, "error": f"Лимит для статуса «{status_name}» — {limit:,} ₽", "limit": limit}

        result = supabase.table("deals").insert({
            "seller_id": deal.seller_id,
            "amount": deal.amount,
            "description": deal.description,
            "status": "pending"
        }).execute()
        deal_id = result.data[0]["id"]
        return {"success": True, "deal_id": deal_id}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/deals/{deal_id}")
async def get_deal(deal_id: str):
    try:
        result = supabase.table("deals").select("*").eq("id", deal_id).execute()
        if result.data:
            deal = result.data[0]
            days_since_accepted = None
            if deal.get("status") == "active":
                accepted_at_str = deal.get("accepted_at") or deal.get("updated_at") or deal.get("created_at")
                if accepted_at_str:
                    accepted_at = datetime.fromisoformat(accepted_at_str.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    days_since_accepted = (now - accepted_at).total_seconds() / 86400
            return {"success": True, "deal": deal, "days_since_accepted": days_since_accepted}
        return {"success": False, "error": "Сделка не найдена"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/deals/{deal_id}/accept")
async def accept_deal(deal_id: str, data: dict):
    try:
        buyer_id = data.get("buyer_id")
        now_iso = datetime.now(timezone.utc).isoformat()
        result = supabase.table("deals").update({
            "buyer_id": buyer_id,
            "status": "active",
            "accepted_at": now_iso
        }).eq("id", deal_id).eq("status", "pending").execute()
        if result.data:
            deal = result.data[0]
            try:
                await bot_instance.send_message(deal["seller_id"],
                    f"✅ Покупатель принял вашу сделку!\n\nТовар: {deal['description']}\nСумма: {int(deal['amount']):,} ₽\n\nОжидайте подтверждения.")
            except: pass
            return {"success": True}
        return {"success": False, "error": "Сделка не найдена или уже принята"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/deals/{deal_id}/dispute")
async def open_dispute(deal_id: str, data: dict):
    try:
        user_id = data.get("user_id")
        deal = supabase.table("deals").select("*").eq("id", deal_id).execute().data[0]
        if user_id != deal["buyer_id"]:
            return {"success": False, "error": "Только покупатель может открыть спор"}
        if deal["status"] != "active":
            return {"success": False, "error": "Спор можно открыть только по активной сделке"}
        accepted_at_str = deal.get("accepted_at") or deal.get("updated_at") or deal.get("created_at")
        accepted_at = datetime.fromisoformat(accepted_at_str.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - accepted_at).total_seconds() / 86400
        if days < 2:
            days_left = round(2 - days, 1)
            return {"success": False, "error": f"Спор можно открыть через {days_left} дн."}
        supabase.table("deals").update({"status": "dispute"}).eq("id", deal_id).execute()
        try:
            await bot_instance.send_message(deal["seller_id"],
                f"⚠️ Покупатель открыл спор!\n\nТовар: {deal['description']}\nАрбитр рассмотрит ситуацию.")
        except: pass
        try:
            await bot_instance.send_message(deal["buyer_id"],
                f"⚠️ Спор открыт.\n\nСумма заморожена до решения арбитра.")
        except: pass
        return {"success": True, "message": "⚠️ Спор открыт. Арбитр рассмотрит ситуацию."}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/deals/{deal_id}/action")
async def deal_action(deal_id: str, data: dict):
    try:
        user_id = data.get("user_id")
        action  = data.get("action")
        deal = supabase.table("deals").select("*").eq("id", deal_id).execute().data[0]
        is_seller = user_id == deal["seller_id"]
        is_buyer  = user_id == deal["buyer_id"]

        if is_seller:
            supabase.table("deals").update({"seller_action": action}).eq("id", deal_id).execute()
        elif is_buyer:
            supabase.table("deals").update({"buyer_action": action}).eq("id", deal_id).execute()
        else:
            return {"success": False, "error": "Вы не участник сделки"}

        deal = supabase.table("deals").select("*").eq("id", deal_id).execute().data[0]
        seller_action = deal["seller_action"]
        buyer_action  = deal["buyer_action"]

        if seller_action == "confirm" and buyer_action == "confirm":
            now_iso = datetime.now(timezone.utc).isoformat()
            supabase.table("deals").update({"status": "completed", "completed_at": now_iso}).eq("id", deal_id).execute()
            try:
                await bot_instance.send_message(deal["seller_id"], "✅ Сделка завершена! Деньги будут переведены вам.")
                await bot_instance.send_message(deal["buyer_id"],  "✅ Сделка завершена! Спасибо за использование Гаранта.")
            except: pass
            try:
                from bot_runner import notify_status_upgrade
                for uid in [deal["seller_id"], deal["buyer_id"]]:
                    if not uid: continue
                    all_deals = supabase.table("deals").select("*").or_(f"seller_id.eq.{uid},buyer_id.eq.{uid}").execute().data
                    old_deals = [d for d in all_deals if d["id"] != deal_id]
                    old_pts = sum(math.floor(float(d["amount"]) / 100) for d in old_deals if d["status"] == "completed")
                    new_pts = old_pts + math.floor(float(deal["amount"]) / 100)
                    await notify_status_upgrade(bot_instance, uid, old_pts, new_pts)
            except: pass
            return {"success": True, "message": "✅ Сделка завершена!"}

        elif seller_action == "cancel" and buyer_action == "cancel":
            supabase.table("deals").update({"status": "cancelled"}).eq("id", deal_id).execute()
            try:
                await bot_instance.send_message(deal["seller_id"], "❌ Сделка отменена.")
                await bot_instance.send_message(deal["buyer_id"],  "❌ Сделка отменена. Деньги возвращены.")
            except: pass
            return {"success": True, "message": "❌ Сделка отменена."}

        elif seller_action and buyer_action and seller_action != buyer_action:
            supabase.table("deals").update({"status": "dispute"}).eq("id", deal_id).execute()
            try:
                await bot_instance.send_message(deal["seller_id"], "⚠️ Открыт спор. Арбитр рассмотрит ситуацию.")
                await bot_instance.send_message(deal["buyer_id"],  "⚠️ Открыт спор. Арбитр рассмотрит ситуацию.")
            except: pass
            return {"success": True, "message": "⚠️ Открыт спор."}

        else:
            if is_seller:
                try: await bot_instance.send_message(deal["buyer_id"],  "🔔 Продавец принял решение. Войдите и подтвердите.")
                except: pass
            else:
                try: await bot_instance.send_message(deal["seller_id"], "🔔 Покупатель принял решение. Войдите и подтвердите.")
                except: pass
            return {"success": True, "message": "Действие записано. Ожидаем второй стороны."}

    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/users/{user_id}/daily")
async def daily_bonus(user_id: int):
    try:
        user = supabase.table("users").select("last_daily_bonus, referral_points, daily_streak, daily_history").eq("id", user_id).execute()
        if not user.data:
            return {"success": False, "error": "Пользователь не найден"}
        now     = datetime.now(timezone.utc)
        data    = user.data[0]
        last    = data.get("last_daily_bonus")
        streak  = data.get("daily_streak") or 0
        history = data.get("daily_history") or []
        today_str = now.date().isoformat()
        if last:
            last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if last_dt.date() >= now.date():
                midnight   = datetime.combine(now.date() + timedelta(days=1), dtime.min, tzinfo=timezone.utc)
                hours_left = max(0, int((midnight - now).total_seconds() / 3600))
                return {"success": False, "already_claimed": True, "hours_left": hours_left, "streak": streak, "history": history}
            yesterday = (now.date() - timedelta(days=1)).isoformat()
            streak = streak + 1 if last_dt.date().isoformat() == yesterday else 1
        else:
            streak = 1
        if today_str not in history:
            history.append(today_str)
        history = sorted(history)[-30:]
        current_pts = data.get("referral_points", 0) or 0
        supabase.table("users").update({
            "referral_points": current_pts + 2,
            "last_daily_bonus": now.isoformat(),
            "daily_streak": streak,
            "daily_history": history
        }).eq("id", user_id).execute()
        return {"success": True, "bonus": 2, "streak": streak, "history": history}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/users/{user_id}/ban")
async def ban_user(user_id: int, body: dict):
    try:
        if body.get("admin_id") != 1291887879:
            return {"success": False, "error": "Доступ запрещён"}
        supabase.table("users").update({"is_banned": True, "is_frozen": True}).eq("id", user_id).execute()
        try: await bot_instance.send_message(user_id, "🚫 Ваш аккаунт заблокирован навсегда.")
        except: pass
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/users/{user_id}/freeze")
async def freeze_user(user_id: int, body: dict):
    try:
        if body.get("admin_id") != 1291887879:
            return {"success": False, "error": "Доступ запрещён"}
        frozen_until = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        supabase.table("users").update({"is_frozen": True, "frozen_until": frozen_until}).eq("id", user_id).execute()
        try: await bot_instance.send_message(user_id, "❄️ Ваш аккаунт заморожен на 7 дней.")
        except: pass
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/users/{user_id}/penalty")
async def penalty_user(user_id: int, body: dict):
    try:
        if body.get("admin_id") != 1291887879:
            return {"success": False, "error": "Доступ запрещён"}
        points = int(body.get("points", 300))
        user = supabase.table("users").select("referral_points").eq("id", user_id).execute()
        if user.data:
            current = user.data[0].get("referral_points", 0) or 0
            supabase.table("users").update({"referral_points": current - points}).eq("id", user_id).execute()
        try: await bot_instance.send_message(user_id, f"⚠️ Штраф: −{points} очков репутации.")
        except: pass
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/deals/{deal_id}/resolve")
async def resolve_dispute(deal_id: str, body: dict):
    try:
        admin_id = body.get("admin_id")
        winner   = body.get("winner")
        if admin_id != 1291887879:
            return {"success": False, "error": "Доступ запрещён"}
        if winner not in ["seller", "buyer"]:
            return {"success": False, "error": "Неверный winner"}
        deal = supabase.table("deals").select("*").eq("id", deal_id).execute()
        if not deal.data:
            return {"success": False, "error": "Сделка не найдена"}
        deal = deal.data[0]
        if winner == "seller":
            now_iso = datetime.now(timezone.utc).isoformat()
            supabase.table("deals").update({"status": "completed", "completed_at": now_iso}).eq("id", deal_id).execute()
            try:
                await bot_instance.send_message(deal["seller_id"], "⚖️ Спор решён в вашу пользу. Деньги будут переведены вам.")
                if deal.get("buyer_id"):
                    await bot_instance.send_message(deal["buyer_id"], "⚖️ Спор решён в пользу продавца.")
            except: pass
        else:
            supabase.table("deals").update({"status": "cancelled"}).eq("id", deal_id).execute()
            try:
                if deal.get("buyer_id"):
                    await bot_instance.send_message(deal["buyer_id"], "⚖️ Спор решён в вашу пользу. Деньги возвращены.")
                await bot_instance.send_message(deal["seller_id"], "⚖️ Спор решён в пользу покупателя.")
            except: pass
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/disputes/{deal_id}/create-chat")
async def create_dispute_chat(deal_id: str, body: dict):
    try:
        if body.get("admin_id") != 1291887879:
            return {"success": False, "error": "Доступ запрещён"}

        seller_id   = body.get("seller_id")
        buyer_id    = body.get("buyer_id")
        description = body.get("description", "Сделка")
        amount      = float(body.get("amount", 0))

        if not seller_id or not buyer_id:
            return {"success": False, "error": "Не указаны стороны сделки"}

        # Вызываем функцию из bot_runner
        import bot_runner
        result = await bot_runner.create_dispute_group(
            deal_id=deal_id,
            seller_id=seller_id,
            buyer_id=buyer_id,
            description=description,
            amount=amount
        )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/leaderboard")
async def get_leaderboard():
    try:
        result = supabase.table("deals").select("id, amount, description, seller_id, buyer_id, completed_at, created_at").eq("status", "completed").order("amount", desc=True).limit(25).execute()
        return {"success": True, "deals": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/users/{user_id}/public")
async def get_public_profile(user_id: int):
    try:
        user = supabase.table("users").select("*").eq("id", user_id).execute()
        if not user.data:
            return {"success": False, "error": "Пользователь не найден"}
        deals = supabase.table("deals").select("id, amount, status, seller_id, buyer_id, created_at").or_(
            f"seller_id.eq.{user_id},buyer_id.eq.{user_id}"
        ).execute()
        return {"success": True, "user": user.data[0], "deals": deals.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/users/{user_id}/photo")
async def get_user_photo(user_id: int):
    try:
        photos = await bot_instance.get_user_profile_photos(user_id, limit=1)
        if photos.total_count == 0:
            return {"photo_url": None}
        file = await bot_instance.get_file(photos.photos[0][0].file_id)
        url = f"https://api.telegram.org/file/bot{os.getenv('BOT_TOKEN')}/{file.file_path}"
        return {"photo_url": url}
    except Exception as e:
        return {"photo_url": None}

@app.get("/feed")
async def get_feed():
    try:
        result = supabase.table("deals").select("id, amount, description, status, created_at, seller_id, buyer_id, seller_action, buyer_action").in_("status", ["pending", "active", "completed", "dispute", "cancelled"]).order("created_at", desc=True).limit(50).execute()
        return {"success": True, "deals": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/users/{user_id}/deals")
async def get_user_deals(user_id: int):
    try:
        result = supabase.table("deals").select("*").or_(
            f"seller_id.eq.{user_id},buyer_id.eq.{user_id}"
        ).order("created_at", desc=True).execute()
        return {"success": True, "deals": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)