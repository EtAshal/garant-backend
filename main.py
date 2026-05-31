from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client
from dotenv import load_dotenv
import os
import uuid

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