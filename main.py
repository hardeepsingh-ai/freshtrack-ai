from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv
import os
import httpx
from datetime import datetime, timedelta
from typing import Optional
from supabase import create_client, Client

load_dotenv()

app = FastAPI(title="FreshTrack AI")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------- Pages ----------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/scan", response_class=HTMLResponse)
async def scan_page(request: Request):
    return templates.TemplateResponse("scan.html", {"request": request})


@app.get("/stock", response_class=HTMLResponse)
async def stock_page(request: Request):
    return templates.TemplateResponse("stock.html", {"request": request})


@app.get("/waste", response_class=HTMLResponse)
async def waste_page(request: Request):
    return templates.TemplateResponse("waste.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


# ---------- API: Product Lookup ----------

@app.get("/api/product/{barcode}")
async def lookup_product(barcode: str):
    """Look up product info from multiple databases: Open Food Facts, Open Beauty Facts, UPCitemdb."""
    async with httpx.AsyncClient() as client:
        # 1. Try Open Food Facts (food & drink)
        try:
            resp = await client.get(
                f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json",
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == 1:
                    product = data["product"]
                    name = product.get("product_name", "").strip()
                    if name:
                        return JSONResponse({
                            "found": True, "barcode": barcode,
                            "name": name,
                            "brand": product.get("brands", ""),
                            "category": (product.get("categories_tags", ["other"])[0]
                                         if product.get("categories_tags") else "other"),
                            "image": product.get("image_front_small_url", ""),
                        })
        except Exception:
            pass

        # 2. Try Open Beauty Facts (cosmetics, hair, skincare)
        try:
            resp = await client.get(
                f"https://world.openbeautyfacts.org/api/v2/product/{barcode}.json",
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == 1:
                    product = data["product"]
                    name = product.get("product_name", "").strip()
                    if name:
                        return JSONResponse({
                            "found": True, "barcode": barcode,
                            "name": name,
                            "brand": product.get("brands", ""),
                            "category": "beauty",
                            "image": product.get("image_front_small_url", ""),
                        })
        except Exception:
            pass

        # 3. Try Open Pet Food Facts (pet products)
        try:
            resp = await client.get(
                f"https://world.openpetfoodfacts.org/api/v2/product/{barcode}.json",
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == 1:
                    product = data["product"]
                    name = product.get("product_name", "").strip()
                    if name:
                        return JSONResponse({
                            "found": True, "barcode": barcode,
                            "name": name,
                            "brand": product.get("brands", ""),
                            "category": "pet",
                            "image": product.get("image_front_small_url", ""),
                        })
        except Exception:
            pass

        # 4. Try UPCitemdb (general products — electronics, household, etc.)
        try:
            resp = await client.get(
                f"https://api.upcitemdb.com/prod/trial/lookup?upc={barcode}",
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if items:
                    item = items[0]
                    name = item.get("title", "").strip()
                    if name:
                        images = item.get("images", [])
                        return JSONResponse({
                            "found": True, "barcode": barcode,
                            "name": name,
                            "brand": item.get("brand", ""),
                            "category": item.get("category", "other"),
                            "image": images[0] if images else "",
                        })
        except Exception:
            pass

    return JSONResponse({"found": False, "barcode": barcode})


# ---------- API: Stock ----------

@app.post("/api/stock/add")
async def add_stock(
    barcode: str = Form(...),
    name: str = Form(...),
    quantity: int = Form(...),
    expiry_date: str = Form(...),
    cost_price: float = Form(0.0),
    sell_price: float = Form(0.0),
):
    """Add stock items with expiry dates."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    result = supabase.table("stock").insert({
        "barcode": barcode,
        "name": name,
        "quantity": quantity,
        "expiry_date": expiry_date,
        "cost_price": cost_price,
        "sell_price": sell_price,
        "added_at": datetime.utcnow().isoformat(),
    }).execute()

    return JSONResponse({"success": True, "data": result.data})


@app.get("/api/stock/current")
async def get_current_stock():
    """Get all current stock with expiry info."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    result = supabase.table("stock").select("*").gt("quantity", 0).order("expiry_date").execute()
    return JSONResponse({"stock": result.data})


@app.get("/api/stock/expiring")
async def get_expiring_stock():
    """Get items expiring within 3 days."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    cutoff = (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%d")
    result = (
        supabase.table("stock")
        .select("*")
        .gt("quantity", 0)
        .lte("expiry_date", cutoff)
        .order("expiry_date")
        .execute()
    )
    return JSONResponse({"expiring": result.data})


# ---------- API: Sales / Shelf Count ----------

@app.post("/api/stock/sold")
async def record_sale(
    barcode: str = Form(...),
    quantity: int = Form(1),
):
    """Record items sold — reduces stock, oldest expiry first."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    rows = (
        supabase.table("stock")
        .select("*")
        .eq("barcode", barcode)
        .gt("quantity", 0)
        .order("expiry_date")
        .execute()
    ).data

    remaining = quantity
    for row in rows:
        if remaining <= 0:
            break
        take = min(remaining, row["quantity"])
        supabase.table("stock").update({"quantity": row["quantity"] - take}).eq("id", row["id"]).execute()
        remaining -= take

    supabase.table("sales").insert({
        "barcode": barcode,
        "quantity": quantity,
        "sold_at": datetime.utcnow().isoformat(),
    }).execute()

    return JSONResponse({"success": True, "sold": quantity - remaining})


@app.post("/api/stock/shelf-count")
async def shelf_count(
    barcode: str = Form(...),
    counted: int = Form(...),
):
    """Daily shelf count — adjusts stock to match what's actually on shelf."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    rows = (
        supabase.table("stock")
        .select("*")
        .eq("barcode", barcode)
        .gt("quantity", 0)
        .order("expiry_date")
        .execute()
    ).data

    total_in_system = sum(r["quantity"] for r in rows)
    diff = total_in_system - counted

    if diff > 0:
        supabase.table("shrinkage").insert({
            "barcode": barcode,
            "missing": diff,
            "recorded_at": datetime.utcnow().isoformat(),
        }).execute()

    return JSONResponse({
        "success": True,
        "system_count": total_in_system,
        "shelf_count": counted,
        "discrepancy": diff,
    })


# ---------- API: Waste ----------

@app.post("/api/waste/log")
async def log_waste(
    barcode: str = Form(...),
    name: str = Form(...),
    quantity: int = Form(...),
    reason: str = Form("expired"),
    cost_price: float = Form(0.0),
):
    """Log wasted items and reduce stock."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    supabase.table("waste").insert({
        "barcode": barcode,
        "name": name,
        "quantity": quantity,
        "reason": reason,
        "cost_price": cost_price,
        "total_loss": cost_price * quantity,
        "logged_at": datetime.utcnow().isoformat(),
    }).execute()

    rows = (
        supabase.table("stock")
        .select("*")
        .eq("barcode", barcode)
        .gt("quantity", 0)
        .order("expiry_date")
        .execute()
    ).data

    remaining = quantity
    for row in rows:
        if remaining <= 0:
            break
        take = min(remaining, row["quantity"])
        supabase.table("stock").update({"quantity": row["quantity"] - take}).eq("id", row["id"]).execute()
        remaining -= take

    return JSONResponse({"success": True, "wasted": quantity})


# ---------- API: Dashboard Stats ----------

@app.get("/api/dashboard/stats")
async def dashboard_stats():
    """Get overview stats for the owner dashboard."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    stock = supabase.table("stock").select("*").gt("quantity", 0).execute()
    total_items = sum(r["quantity"] for r in stock.data)

    cutoff = (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%d")
    expiring = (
        supabase.table("stock")
        .select("*")
        .gt("quantity", 0)
        .lte("expiry_date", cutoff)
        .execute()
    )
    expiring_count = sum(r["quantity"] for r in expiring.data)

    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    waste = supabase.table("waste").select("*").gte("logged_at", week_ago).execute()
    waste_cost = sum(r.get("total_loss", 0) for r in waste.data)
    waste_items = sum(r["quantity"] for r in waste.data)

    sales = supabase.table("sales").select("*").gte("sold_at", week_ago).execute()
    sales_count = sum(r["quantity"] for r in sales.data)

    return JSONResponse({
        "total_stock": total_items,
        "expiring_soon": expiring_count,
        "waste_this_week": {"items": waste_items, "cost": round(waste_cost, 2)},
        "sales_this_week": sales_count,
        "unique_products": len(set(r["barcode"] for r in stock.data)),
    })


@app.get("/api/dashboard/waste-trend")
async def waste_trend():
    """Get daily waste totals for the last 30 days."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    month_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
    waste = supabase.table("waste").select("*").gte("logged_at", month_ago).order("logged_at").execute()

    daily = {}
    for w in waste.data:
        day = w["logged_at"][:10]
        daily.setdefault(day, 0)
        daily[day] += w.get("total_loss", 0)

    return JSONResponse({
        "trend": [{"date": k, "cost": round(v, 2)} for k, v in sorted(daily.items())]
    })


@app.get("/api/dashboard/top-wasted")
async def top_wasted():
    """Get top 10 most wasted products."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    month_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
    waste = supabase.table("waste").select("*").gte("logged_at", month_ago).execute()

    by_product = {}
    for w in waste.data:
        name = w["name"]
        by_product.setdefault(name, {"quantity": 0, "cost": 0})
        by_product[name]["quantity"] += w["quantity"]
        by_product[name]["cost"] += w.get("total_loss", 0)

    sorted_products = sorted(by_product.items(), key=lambda x: x[1]["cost"], reverse=True)[:10]
    return JSONResponse({
        "top_wasted": [{"name": k, **v} for k, v in sorted_products]
    })


# ---------- API: AI Insights ----------

@app.get("/api/ai/insights")
async def ai_insights():
    """Get AI-powered insights from Groq about waste patterns."""
    if not supabase or not GROQ_API_KEY:
        return JSONResponse({"insights": "AI not configured. Add GROQ_API_KEY to enable."})

    month_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
    waste = supabase.table("waste").select("*").gte("logged_at", month_ago).execute()
    stock = supabase.table("stock").select("*").gt("quantity", 0).execute()
    sales = supabase.table("sales").select("*").gte("sold_at", month_ago).execute()

    prompt = f"""You are an AI assistant for a UK convenience store. Analyse this data and give 3-5 specific, actionable recommendations to reduce waste and save money.

WASTE (last 30 days): {len(waste.data)} items wasted
{[{"name": w["name"], "qty": w["quantity"], "cost": w.get("total_loss", 0), "reason": w.get("reason", "expired")} for w in waste.data[:20]]}

CURRENT STOCK: {len(stock.data)} product lines
{[{"name": s["name"], "qty": s["quantity"], "expiry": s["expiry_date"]} for s in stock.data[:20]]}

SALES (last 30 days): {sum(s["quantity"] for s in sales.data)} items sold

Be specific with numbers. Example: "Reduce milk order from 13 to 9 — you sold 8 last week and wasted 4."
Keep it under 300 words. Use British English."""

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": "llama-3.1-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 600,
                "temperature": 0.3,
            },
            timeout=30,
        )

    if resp.status_code != 200:
        return JSONResponse({"insights": "AI temporarily unavailable."})

    insights = resp.json()["choices"][0]["message"]["content"]
    return JSONResponse({"insights": insights})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
