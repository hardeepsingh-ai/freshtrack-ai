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


def fetch_all_sales(start, end):
    """Fetch all sales in range, paginating past Supabase 1000-row limit."""
    all_rows = []
    offset = 0
    while True:
        batch = supabase.table("sales").select("*").gte("sold_at", start).lte("sold_at", end).range(offset, offset + 999).execute()
        all_rows.extend(batch.data)
        if len(batch.data) < 1000:
            break
        offset += 1000
    return all_rows


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


@app.get("/storeroom", response_class=HTMLResponse)
async def storeroom_page(request: Request):
    return templates.TemplateResponse("storeroom.html", {"request": request})


@app.get("/quicksale", response_class=HTMLResponse)
async def quicksale_page(request: Request):
    return templates.TemplateResponse("quicksale.html", {"request": request})


@app.get("/smartorder", response_class=HTMLResponse)
async def smartorder_page(request: Request):
    return templates.TemplateResponse("smartorder.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("brain.html", {"request": request})


@app.get("/brain", response_class=HTMLResponse)
async def brain_page(request: Request):
    return templates.TemplateResponse("brain.html", {"request": request})


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
    zone_code: str = Form(""),
    location_note: str = Form(""),
):
    """Add stock items with expiry dates and storeroom location."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    result = supabase.table("stock").insert({
        "barcode": barcode,
        "name": name,
        "quantity": quantity,
        "expiry_date": expiry_date,
        "cost_price": cost_price,
        "sell_price": sell_price,
        "zone_code": zone_code,
        "location_note": location_note,
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
                "model": "openai/gpt-oss-120b",
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


@app.get("/api/ai/smart-order")
async def smart_order(start: Optional[str] = None, end: Optional[str] = None):
    """AI analyses sales in a date range and predicts what to order for next week."""
    if not supabase or not GROQ_API_KEY:
        return JSONResponse({"error": "AI not configured"})

    # Use date range or default to 4 weeks
    if start and end:
        range_start = start + "T00:00:00"
        range_end = end + "T23:59:59"
        days_span = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days or 28
    else:
        days_span = 28
        range_start = (datetime.utcnow() - timedelta(days=days_span)).isoformat()
        range_end = datetime.utcnow().isoformat()

    weeks_count = max(1, days_span // 7)
    four_weeks_ago = range_start
    sales_data = fetch_all_sales(range_start, range_end)
    stock = supabase.table("stock").select("*").gt("quantity", 0).execute()
    waste = supabase.table("waste").select("*").gte("logged_at", range_start).lte("logged_at", range_end).execute()

    # Aggregate sales by product per week (week 0 = oldest, week 3 = most recent)
    start_dt = datetime.fromisoformat(range_start[:10])
    end_dt = datetime.fromisoformat(range_end[:10])
    total_days = (end_dt - start_dt).days
    product_sales = {}
    for s in sales_data:
        barcode = s["barcode"]
        sold_at = s["sold_at"][:10]
        day = datetime.fromisoformat(sold_at)
        days_from_start = max(0, (day - start_dt).days)
        week_num = min(3, days_from_start // 7)
        product_sales.setdefault(barcode, {"weeks": {0: 0, 1: 0, 2: 0, 3: 0}, "total": 0})
        product_sales[barcode]["weeks"][week_num] += s["quantity"]
        product_sales[barcode]["total"] += s["quantity"]

    # Build product summary with names from stock
    names = {s["barcode"]: s["name"] for s in stock.data}
    current_stock = {}
    for s in stock.data:
        current_stock.setdefault(s["barcode"], 0)
        current_stock[s["barcode"]] += s["quantity"]

    # Waste summary
    waste_by_product = {}
    for w in waste.data:
        waste_by_product.setdefault(w["barcode"], 0)
        waste_by_product[w["barcode"]] += w["quantity"]

    # Top 20 products by sales
    top_products = sorted(product_sales.items(), key=lambda x: x[1]["total"], reverse=True)[:20]

    summary_lines = []
    for barcode, data in top_products:
        name = names.get(barcode, barcode)
        w = data["weeks"]
        stock_now = current_stock.get(barcode, 0)
        wasted = waste_by_product.get(barcode, 0)
        summary_lines.append(
            f"- {name} (barcode:{barcode}): Week1(oldest)={w.get(0,0)}, Week2={w.get(1,0)}, "
            f"Week3={w.get(2,0)}, Week4(latest)={w.get(3,0)}, "
            f"CurrentStock={stock_now}, Wasted={wasted}"
        )

    prompt = f"""You are the AI brain of FreshTrack, a stock management system for a UK convenience store in Aberdeen.

Analyse these 4 weeks of sales data and predict EXACTLY what to order for next week.

SALES DATA (per product, weekly totals):
{chr(10).join(summary_lines)}

YOUR TASK:
For each product, output a JSON array. Each item must have:
- "name": product name
- "barcode": the barcode
- "week1": sales in week 1 (oldest)
- "week2": sales in week 2
- "week3": sales in week 3
- "week4": sales in week 4 (most recent)
- "current_stock": what's on shelf now
- "wasted": items wasted in 4 weeks
- "predicted_demand": your predicted demand for next week
- "order_qty": how many to order (predicted_demand minus current_stock, minimum 0)
- "confidence": "high", "medium", or "low"
- "pattern": one of "steady", "trending_up", "trending_down", "weekend_heavy", "regular_buyer", "seasonal"
- "reasoning": ONE short sentence explaining why (e.g. "Regular customer buys every other day" or "Sales trending up 20% weekly")

IMPORTANT RULES:
- Look for PATTERNS: steady demand, trending up/down, weekend spikes, regular buyers
- For items bought every other day (like alcohol), note it as a regular buyer pattern
- Account for waste: if an item is being wasted, suggest ordering LESS
- For trending products, weight recent weeks more
- If current stock covers predicted demand, order_qty should be 0
- Be specific with numbers, not vague

Return ONLY the JSON array, no other text. Start with [ and end with ]."""

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": "openai/gpt-oss-120b",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 5000,
                "temperature": 0.2,
            },
            timeout=45,
        )

    if resp.status_code != 200:
        detail = resp.text[:200] if resp.text else "no body"
        print(f"Groq API error {resp.status_code}: {detail}")
        return JSONResponse({"error": f"AI error ({resp.status_code}). Check server logs."})

    raw = resp.json()["choices"][0]["message"]["content"]

    # Parse JSON from response (handle markdown code blocks)
    import json as json_mod
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        clean = clean.rsplit("```", 1)[0]
    clean = clean.strip()

    try:
        predictions = json_mod.loads(clean)
    except Exception:
        return JSONResponse({"error": "AI returned invalid format", "raw": raw})

    return JSONResponse({"predictions": predictions})


@app.get("/api/ai/sales-summary")
async def sales_summary(start: Optional[str] = None, end: Optional[str] = None):
    """Get daily sales summary for the chart."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    if start and end:
        range_start = start + "T00:00:00"
        range_end = end + "T23:59:59"
    else:
        range_start = (datetime.utcnow() - timedelta(days=28)).isoformat()
        range_end = datetime.utcnow().isoformat()

    sales_data = fetch_all_sales(range_start, range_end)

    daily = {}
    for s in sales_data:
        day = s["sold_at"][:10]
        daily.setdefault(day, 0)
        daily[day] += s["quantity"]

    return JSONResponse({
        "daily_sales": [{"date": k, "qty": v} for k, v in sorted(daily.items())]
    })


@app.get("/api/ai/category-sales")
async def category_sales(start: Optional[str] = None, end: Optional[str] = None):
    """Get sales broken down by product category and product."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    if start and end:
        range_start = start + "T00:00:00"
        range_end = end + "T23:59:59"
    else:
        range_start = (datetime.utcnow() - timedelta(days=28)).isoformat()
        range_end = datetime.utcnow().isoformat()

    sales_data = fetch_all_sales(range_start, range_end)
    stock = supabase.table("stock").select("*").execute()

    zone_names = {"TS": "Crisps & Snacks", "RC": "Energy Drinks", "S1": "Small Bottles & Dairy",
                  "S2": "Mixed Stock", "FL": "Large Bottles"}
    stock_map = {}
    for s in stock.data:
        stock_map.setdefault(s["barcode"], {"name": s["name"], "zone": s.get("zone_code", "S2"),
                                             "cost": s.get("cost_price", 0), "sell": s.get("sell_price", 0),
                                             "qty": 0})
        stock_map[s["barcode"]]["qty"] += s["quantity"]

    products = {}
    for s in sales_data:
        bc = s["barcode"]
        products.setdefault(bc, {"sold": 0, "revenue": 0})
        products[bc]["sold"] += s["quantity"]

    categories = {}
    for bc, data in products.items():
        info = stock_map.get(bc, {"name": bc, "zone": "S2", "sell": 0, "qty": 0})
        zone = info["zone"]
        cat_name = zone_names.get(zone, zone)
        categories.setdefault(cat_name, {"products": [], "total_sold": 0, "total_revenue": 0})
        rev = round(data["sold"] * info["sell"], 2)
        categories[cat_name]["products"].append({
            "name": info["name"], "barcode": bc, "sold": data["sold"],
            "revenue": rev, "current_stock": info["qty"]
        })
        categories[cat_name]["total_sold"] += data["sold"]
        categories[cat_name]["total_revenue"] += rev

    for cat in categories.values():
        cat["products"].sort(key=lambda x: x["sold"], reverse=True)
        cat["total_revenue"] = round(cat["total_revenue"], 2)

    return JSONResponse({"categories": categories})


@app.get("/api/ai/brain-analysis")
async def brain_analysis():
    """The AI Brain: detects customer patterns, buying habits, and generates
    order recommendations with full reasoning and calculations."""
    if not supabase or not GROQ_API_KEY:
        return JSONResponse({"error": "AI not configured"})

    range_start = (datetime.utcnow() - timedelta(days=28)).strftime("%Y-%m-%dT00:00:00")
    range_end = datetime.utcnow().isoformat()
    sales_data = fetch_all_sales(range_start, range_end)
    stock = supabase.table("stock").select("*").gt("quantity", 0).execute()

    if not sales_data:
        return JSONResponse({"error": "No sales data found"})

    start_dt = datetime.fromisoformat(range_start[:10])

    # Build per-product daily sales grid
    product_daily = {}
    product_names = {}
    for s in sales_data:
        bc = s["barcode"]
        day = s["sold_at"][:10]
        product_daily.setdefault(bc, {})
        product_daily[bc].setdefault(day, 0)
        product_daily[bc][day] += s["quantity"]

    for s in stock.data:
        product_names[s["barcode"]] = s["name"]

    current_stock = {}
    for s in stock.data:
        current_stock.setdefault(s["barcode"], 0)
        current_stock[s["barcode"]] += s["quantity"]

    # Build compact daily breakdown for AI (top 12 products, short date keys)
    product_details = []
    for bc, daily in sorted(product_daily.items(), key=lambda x: sum(x[1].values()), reverse=True)[:3]:
        name = product_names.get(bc, bc)
        stock_now = current_stock.get(bc, 0)
        days_sorted = sorted(daily.items())
        daily_str = ",".join([f"{d[5:]}:{q}" for d, q in days_sorted])
        total = sum(daily.values())
        product_details.append(f"{name}|stock:{stock_now}|sold:{total}|days:[{daily_str}]")

    prompt = f"""/no_think
Analyze sales. Return ONLY compact JSON. Keep evidence and calculation SHORT (under 15 words each).
Rules: R1=regular buyers, R2=weekend spikes, R3=steady, R4=trending, R6=order=demand-stock+10%.
DATA:
{chr(10).join(product_details)}
JSON:{{"detected_patterns":[{{"product":"name","pattern_type":"steady|weekend_spike|regular_buyer|trending_up","evidence":"brief","customer_insight":"brief","calculation":"brief math","predicted_weekly_demand":N,"current_stock":N,"order_qty":N,"confidence":"high|medium","priority":"critical|important|normal"}}],"summary":{{"total_patterns_detected":N,"regular_buyers_found":N,"total_order_units":N,"key_insight":"1 sentence"}}}}"""

    import asyncio
    try:
        resp = None
        for attempt in range(3):
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    json={
                        "model": "qwen/qwen3.8-27b",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 950,
                        "temperature": 0.15,
                    },
                    timeout=90,
                )
            if resp.status_code == 429 and attempt < 2:
                # Parse Groq's reset header (e.g. "1m26.4s" or "180ms")
                reset_str = resp.headers.get("x-ratelimit-reset-tokens", "")
                wait = 60
                if "m" in reset_str and "s" in reset_str:
                    import re as _re
                    m = _re.match(r"(\d+)m([\d.]+)s", reset_str)
                    if m:
                        wait = int(m.group(1)) * 60 + float(m.group(2)) + 2
                elif reset_str.endswith("ms"):
                    wait = 2
                elif reset_str.endswith("s"):
                    wait = float(reset_str[:-1]) + 2
                wait = min(wait, 90)
                print(f"Brain: rate limited, retrying in {wait:.0f}s (attempt {attempt+1}, reset: {reset_str})")
                await asyncio.sleep(wait)
                continue
            break

        if resp.status_code != 200:
            detail = resp.text[:200] if resp.text else "no body"
            print(f"Groq Brain API error {resp.status_code}: {detail}")
            return JSONResponse({"error": f"AI error ({resp.status_code})"})

        msg = resp.json()["choices"][0]["message"]
        raw = msg.get("content", "") or ""
        # For reasoning models, the JSON may be in the reasoning field
        if not raw.strip() and msg.get("reasoning"):
            raw = msg["reasoning"]

        import json as json_mod
        import re
        clean = raw.strip()
        # Strip Qwen <think>...</think> reasoning tags
        clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.DOTALL).strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            clean = clean.rsplit("```", 1)[0]
        clean = clean.strip()

        # Try to find JSON object in the text
        result = None
        if clean.startswith("{"):
            result = json_mod.loads(clean)
        else:
            # Search for the first { ... } block
            match = re.search(r'\{.*\}', clean, re.DOTALL)
            if match:
                result = json_mod.loads(match.group())
            else:
                return JSONResponse({"error": "AI returned no JSON", "raw": clean[:300]})
        return JSONResponse(result)

    except json_mod.JSONDecodeError:
        return JSONResponse({"error": "AI returned invalid format", "raw": raw[:500]})
    except Exception as e:
        print(f"Brain analysis error: {e}")
        return JSONResponse({"error": str(e)})


# ---------- API: Storeroom / Zones ----------

@app.get("/api/zones")
async def get_zones():
    """Get all storeroom zones."""
    if not supabase:
        raise HTTPException(503, "Database not configured")
    result = supabase.table("zones").select("*").order("code").execute()
    return JSONResponse({"zones": result.data})


@app.post("/api/zones")
async def create_zone(
    name: str = Form(...),
    code: str = Form(...),
    description: str = Form(""),
    color: str = Form("#22c55e"),
    position_x: float = Form(0),
    position_y: float = Form(0),
    width: float = Form(100),
    height: float = Form(60),
):
    """Create a storeroom zone."""
    if not supabase:
        raise HTTPException(503, "Database not configured")
    result = supabase.table("zones").insert({
        "name": name, "code": code, "description": description,
        "color": color, "position_x": position_x, "position_y": position_y,
        "width": width, "height": height,
    }).execute()
    return JSONResponse({"success": True, "data": result.data})


@app.put("/api/zones/{zone_id}")
async def update_zone(
    zone_id: int,
    name: str = Form(...),
    description: str = Form(""),
    color: str = Form("#22c55e"),
    position_x: float = Form(0),
    position_y: float = Form(0),
    width: float = Form(100),
    height: float = Form(60),
):
    """Update a storeroom zone."""
    if not supabase:
        raise HTTPException(503, "Database not configured")
    result = supabase.table("zones").update({
        "name": name, "description": description, "color": color,
        "position_x": position_x, "position_y": position_y,
        "width": width, "height": height,
    }).eq("id", zone_id).execute()
    return JSONResponse({"success": True, "data": result.data})


@app.get("/api/locate/{barcode}")
async def locate_product(barcode: str):
    """Find where a product is in the storeroom."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    stock = (
        supabase.table("stock").select("*")
        .eq("barcode", barcode).gt("quantity", 0)
        .order("expiry_date").execute()
    )

    if not stock.data:
        return JSONResponse({"found": False, "barcode": barcode, "message": "Not in storeroom"})

    total_qty = sum(r["quantity"] for r in stock.data)
    zones_used = {}
    for s in stock.data:
        zc = s.get("zone_code") or "unassigned"
        if zc not in zones_used:
            zones_used[zc] = {"quantity": 0, "batches": [], "location_note": s.get("location_note", "")}
        zones_used[zc]["quantity"] += s["quantity"]
        zones_used[zc]["batches"].append({
            "quantity": s["quantity"],
            "expiry_date": s["expiry_date"],
            "id": s["id"],
        })

    # Get zone details
    zones_result = supabase.table("zones").select("*").execute()
    zone_map = {z["code"]: z for z in zones_result.data}

    locations = []
    for zc, info in zones_used.items():
        zone_detail = zone_map.get(zc, {})
        use_first = min(info["batches"], key=lambda b: b["expiry_date"])
        locations.append({
            "zone_code": zc,
            "zone_name": zone_detail.get("name", "Unassigned"),
            "zone_color": zone_detail.get("color", "#94a3b8"),
            "description": zone_detail.get("description", ""),
            "quantity": info["quantity"],
            "location_note": info["location_note"],
            "use_first_expiry": use_first["expiry_date"],
            "position_x": zone_detail.get("position_x", 0),
            "position_y": zone_detail.get("position_y", 0),
        })

    name = stock.data[0]["name"]
    return JSONResponse({
        "found": True,
        "barcode": barcode,
        "name": name,
        "total_quantity": total_qty,
        "locations": locations,
    })


# ---------- API: Reorder Alerts ----------

@app.get("/api/reorder/alerts")
async def reorder_alerts():
    """Get products below their reorder threshold."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    rules = supabase.table("reorder_rules").select("*").execute()
    stock = supabase.table("stock").select("*").gt("quantity", 0).execute()

    stock_totals = {}
    for s in stock.data:
        stock_totals.setdefault(s["barcode"], {"name": s["name"], "qty": 0})
        stock_totals[s["barcode"]]["qty"] += s["quantity"]

    alerts = []
    for rule in rules.data:
        current = stock_totals.get(rule["barcode"], {"name": rule["name"], "qty": 0})
        if current["qty"] < rule["min_quantity"]:
            alerts.append({
                "barcode": rule["barcode"],
                "name": rule["name"],
                "current_stock": current["qty"],
                "min_quantity": rule["min_quantity"],
                "shortage": rule["min_quantity"] - current["qty"],
                "supplier_note": rule.get("supplier_note", ""),
            })

    alerts.sort(key=lambda a: a["shortage"], reverse=True)
    return JSONResponse({"alerts": alerts, "total": len(alerts)})


@app.post("/api/reorder/rule")
async def set_reorder_rule(
    barcode: str = Form(...),
    name: str = Form(...),
    min_quantity: int = Form(10),
    supplier_note: str = Form(""),
):
    """Set reorder threshold for a product."""
    if not supabase:
        raise HTTPException(503, "Database not configured")

    existing = supabase.table("reorder_rules").select("id").eq("barcode", barcode).execute()
    if existing.data:
        supabase.table("reorder_rules").update({
            "name": name, "min_quantity": min_quantity, "supplier_note": supplier_note,
        }).eq("barcode", barcode).execute()
    else:
        supabase.table("reorder_rules").insert({
            "barcode": barcode, "name": name,
            "min_quantity": min_quantity, "supplier_note": supplier_note,
        }).execute()

    return JSONResponse({"success": True})


@app.get("/api/reorder/rules")
async def get_reorder_rules():
    """Get all reorder rules."""
    if not supabase:
        raise HTTPException(503, "Database not configured")
    result = supabase.table("reorder_rules").select("*").order("name").execute()
    return JSONResponse({"rules": result.data})


@app.delete("/api/stock/{stock_id}")
async def delete_stock(stock_id: int):
    """Delete a stock item."""
    if not supabase:
        raise HTTPException(503, "Database not configured")
    supabase.table("stock").delete().eq("id", stock_id).execute()
    return JSONResponse({"success": True})


if __name__ == "__main__":
    import uvicorn
    try:
        from pyngrok import ngrok
        tunnel = ngrok.connect(8000)
        print(f"\n{'='*50}")
        print(f"Open this on your phone:")
        print(f"{tunnel.public_url}")
        print(f"{'='*50}\n")
    except Exception as e:
        print(f"ngrok not available ({e}), use http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
