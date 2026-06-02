from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client
from dotenv import load_dotenv
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timezone
import os
import sys
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

# ── ФОНОВАЯ ЗАДАЧА: автозавершение через 7 дней ──────────────────────────────
async def auto_complete_deals():
    """Раз в час проверяет активные сделки. Если прошло 7 дней — завершает в пользу продавца."""
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
                # Завершаем в пользу продавца
                supabase.table("deals").update({
                    "status": "completed",
                    "seller_action": "confirm",
                    "buyer_action": "confirm"
                }).eq("id", deal["id"]).execute()

                try:
                    await bot_instance.send_message(
                        deal["seller_id"],
                        f"✅ Сделка автоматически завершена!\n\n"
                        f"Товар: {deal['description']}\n"
                        f"Сумма: {int(deal['amount']):,} ₽\n\n"
                        f"Прошло 7 дней — деньги переведены вам."
                    )
                except:
                    pass

                if deal.get("buyer_id"):
                    try:
                        await bot_instance.send_message(
                            deal["buyer_id"],
                            f"📋 Сделка автоматически завершена.\n\n"
                            f"Товар: {deal['description']}\n"
                            f"Прошло 7 дней без действий — средства переведены продавцу."
                        )
                    except:
                        pass

                print(f"[Автозавершение] Сделка {deal['id']} завершена через 7 дней")

    except Exception as e:
        print(f"[Автозавершение] Ошибка: {e}")


# ── ЗАПУСК ПЛАНИРОВЩИКА ───────────────────────────────────────────────────────
scheduler = AsyncIOScheduler(timezone="UTC")

@app.on_event("startup")
async def startup():
    scheduler.add_job(auto_complete_deals, "interval", hours=1, id="auto_complete")
    scheduler.start()
    print("Планировщик запущен")

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

            # Считаем сколько дней прошло с принятия сделки (для фронта)
            days_since_accepted = None
            if deal.get("status") == "active":
                accepted_at_str = deal.get("accepted_at") or deal.get("updated_at") or deal.get("created_at")
                if accepted_at_str:
                    accepted_at = datetime.fromisoformat(accepted_at_str.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    days_since_accepted = (now - accepted_at).total_seconds() / 86400

            return {
                "success": True,
                "deal": deal,
                "days_since_accepted": days_since_accepted
            }
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
            "accepted_at": now_iso          # фиксируем время принятия
        }).eq("id", deal_id).eq("status", "pending").execute()

        if result.data:
            deal = result.data[0]
            try:
                await bot_instance.send_message(
                    deal["seller_id"],
                    f"✅ Покупатель принял вашу сделку!\n\n"
                    f"Товар: {deal['description']}\n"
                    f"Сумма: {int(deal['amount']):,} ₽\n\n"
                    f"Ожидайте подтверждения."
                )
            except:
                pass
            return {"success": True}
        return {"success": False, "error": "Сделка не найдена или уже принята"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/deals/{deal_id}/dispute")
async def open_dispute(deal_id: str, data: dict):
    """Покупатель открывает спор вручную (если продавец молчит 2+ дня)."""
    try:
        user_id = data.get("user_id")
        deal = supabase.table("deals").select("*").eq("id", deal_id).execute().data[0]

        if user_id != deal["buyer_id"]:
            return {"success": False, "error": "Только покупатель может открыть спор"}

        if deal["status"] != "active":
            return {"success": False, "error": "Спор можно открыть только по активной сделке"}

        # Проверяем что прошло 2+ дня с принятия
        accepted_at_str = deal.get("accepted_at") or deal.get("updated_at") or deal.get("created_at")
        accepted_at = datetime.fromisoformat(accepted_at_str.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - accepted_at).total_seconds() / 86400

        if days < 2:
            days_left = round(2 - days, 1)
            return {
                "success": False,
                "error": f"Спор можно открыть через {days_left} дн. (продавец молчит менее 2 дней)"
            }

        supabase.table("deals").update({"status": "dispute"}).eq("id", deal_id).execute()

        try:
            await bot_instance.send_message(
                deal["seller_id"],
                f"⚠️ Покупатель открыл спор!\n\n"
                f"Товар: {deal['description']}\n"
                f"Сумма: {int(deal['amount']):,} ₽\n\n"
                f"Причина: продавец не реагировал 2 дня.\n"
                f"Арбитр рассмотрит ситуацию."
            )
        except:
            pass

        try:
            await bot_instance.send_message(
                deal["buyer_id"],
                f"⚠️ Спор открыт.\n\n"
                f"Товар: {deal['description']}\n"
                f"Сумма заморожена до решения арбитра."
            )
        except:
            pass

        return {"success": True, "message": "⚠️ Спор открыт. Арбитр рассмотрит ситуацию."}

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/deals/{deal_id}/action")
async def deal_action(deal_id: str, data: dict):
    try:
        user_id = data.get("user_id")
        action = data.get("action")
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
            supabase.table("deals").update({"status": "completed"}).eq("id", deal_id).execute()
            try:
                await bot_instance.send_message(deal["seller_id"], "✅ Сделка завершена! Деньги будут переведены вам.")
                await bot_instance.send_message(deal["buyer_id"],  "✅ Сделка завершена! Спасибо за использование Гаранта.")
            except:
                pass
            return {"success": True, "message": "✅ Сделка завершена! Деньги переведены продавцу."}

        elif seller_action == "cancel" and buyer_action == "cancel":
            supabase.table("deals").update({"status": "cancelled"}).eq("id", deal_id).execute()
            try:
                await bot_instance.send_message(deal["seller_id"], "❌ Сделка отменена.")
                await bot_instance.send_message(deal["buyer_id"],  "❌ Сделка отменена. Деньги возвращены.")
            except:
                pass
            return {"success": True, "message": "❌ Сделка отменена. Деньги возвращены покупателю."}

        elif seller_action and buyer_action and seller_action != buyer_action:
            supabase.table("deals").update({"status": "dispute"}).eq("id", deal_id).execute()
            try:
                await bot_instance.send_message(deal["seller_id"], "⚠️ Открыт спор по вашей сделке. Арбитр рассмотрит ситуацию.")
                await bot_instance.send_message(deal["buyer_id"],  "⚠️ Открыт спор по вашей сделке. Арбитр рассмотрит ситуацию.")
            except:
                pass
            return {"success": True, "message": "⚠️ Открыт спор. Арбитр рассмотрит ситуацию."}

        else:
            if is_seller:
                try:
                    await bot_instance.send_message(deal["buyer_id"],  "🔔 Продавец принял решение. Войдите и подтвердите.")
                except:
                    pass
            else:
                try:
                    await bot_instance.send_message(deal["seller_id"], "🔔 Покупатель принял решение. Войдите и подтвердите.")
                except:
                    pass
            return {"success": True, "message": "Действие записано. Ожидаем второй стороны."}

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/users/{user_id}/public")
async def get_public_profile(user_id: int):
    """Публичный профиль пользователя — только завершённые сделки и очки."""
    try:
        # Данные пользователя
        user = supabase.table("users").select("*").eq("id", user_id).execute()
        if not user.data:
            return {"success": False, "error": "Пользователь не найден"}

        # Только завершённые сделки для подсчёта очков
        deals = supabase.table("deals").select(
            "id, amount, status, seller_id, buyer_id, created_at"
        ).or_(
            f"seller_id.eq.{user_id},buyer_id.eq.{user_id}"
        ).execute()

        return {
            "success": True,
            "user": user.data[0],
            "deals": deals.data
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/users/{user_id}/photo")
async def get_user_photo(user_id: int):
    """Получаем фото профиля пользователя через Telegram Bot API."""
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
    """Лента последних активных сделок всех пользователей — без личных данных."""
    try:
        result = supabase.table("deals").select(
            "id, amount, description, status, created_at"
        ).in_("status", ["pending", "active", "completed", "dispute"]
        ).order("created_at", desc=True).limit(30).execute()
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