from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client
import sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
import os
import uuid

from aiogram import Bot
bot_instance = Bot(token=os.getenv("BOT_TOKEN"))

load_dotenv()

app = FastAPI()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SECRET"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class DealCreate(BaseModel):
    seller_id: int
    amount: float
    description: str

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
            return {"success": True, "deal": result.data[0]}
        return {"success": False, "error": "Сделка не найдена"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/")
async def root():
    return {"status": "ok"}

@app.post("/deals/{deal_id}/accept")
async def accept_deal(deal_id: str, data: dict):
    try:
        buyer_id = data.get("buyer_id")
        result = supabase.table("deals").update({
            "buyer_id": buyer_id,
            "status": "active"
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

@app.post("/deals/{deal_id}/action")
async def deal_action(deal_id: str, data: dict):
    try:
        user_id = data.get("user_id")
        action = data.get("action")

        deal = supabase.table("deals").select("*").eq("id", deal_id).execute().data[0]
        
        is_seller = user_id == deal["seller_id"]
        is_buyer = user_id == deal["buyer_id"]

        if is_seller:
            supabase.table("deals").update({"seller_action": action}).eq("id", deal_id).execute()
        elif is_buyer:
            supabase.table("deals").update({"buyer_action": action}).eq("id", deal_id).execute()
        else:
            return {"success": False, "error": "Вы не участник сделки"}

        deal = supabase.table("deals").select("*").eq("id", deal_id).execute().data[0]
        seller_action = deal["seller_action"]
        buyer_action = deal["buyer_action"]

        if seller_action == "confirm" and buyer_action == "confirm":
            supabase.table("deals").update({"status": "completed"}).eq("id", deal_id).execute()
            return {"success": True, "message": "✅ Сделка завершена! Деньги переведены продавцу."}
        elif seller_action == "cancel" and buyer_action == "cancel":
            supabase.table("deals").update({"status": "cancelled"}).eq("id", deal_id).execute()
            return {"success": True, "message": "❌ Сделка отменена. Деньги возвращены покупателю."}
        elif seller_action and buyer_action and seller_action != buyer_action:
            supabase.table("deals").update({"status": "dispute"}).eq("id", deal_id).execute()
            return {"success": True, "message": "⚠️ Открыт спор. Арбитр рассмотрит ситуацию."}
        else:
            return {"success": True, "message": "Действие записано. Ожидаем второй стороны."}

    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)