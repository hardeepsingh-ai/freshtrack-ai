"""Seed 4 weeks of realistic demo sales + stock data for the Tuesday owner demo."""
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client
import random

load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Realistic convenience store products with typical patterns
PRODUCTS = [
    # (barcode, name, avg_daily, pattern, cost, sell, zone)
    # DRINKS - high volume
    ("5000112637922", "Coca-Cola 500ml", 8, "steady", 0.65, 1.50, "FL"),
    ("5000112637939", "Diet Coke 500ml", 5, "steady", 0.65, 1.50, "FL"),
    ("5000112546415", "Fanta Orange 500ml", 4, "steady", 0.65, 1.50, "S1"),
    ("5449000000996", "Coca-Cola 2L", 3, "weekend_spike", 1.10, 2.49, "FL"),
    ("5000128065368", "Pepsi Max 500ml", 6, "steady", 0.60, 1.40, "FL"),
    ("5000128935692", "Irn-Bru 500ml", 7, "steady", 0.60, 1.40, "FL"),
    ("5060166694654", "Monster Energy 500ml", 10, "steady", 0.95, 1.89, "RC"),
    ("5060466515871", "Monster Ultra White 500ml", 6, "steady", 0.95, 1.89, "RC"),
    ("9002490100070", "Red Bull 250ml", 8, "steady", 0.90, 1.79, "RC"),
    ("5060517883065", "Prime Hydration 500ml", 4, "trending_up", 1.20, 2.49, "S1"),
    # ALCOHOL - pattern buyer (every other day for one customer)
    ("5010677014205", "Tennent's Lager 4-pack", 3, "every_other_day", 3.50, 5.99, "S2"),
    ("5010186017217", "Smirnoff Vodka 350ml", 2, "every_other_day", 6.50, 11.99, "S2"),
    ("5000299210048", "Buckfast 750ml", 2, "weekend_spike", 5.00, 8.99, "S2"),
    # CRISPS & SNACKS
    ("5000328374826", "Walkers Cheese & Onion", 12, "steady", 0.35, 1.00, "TS"),
    ("5000328374819", "Walkers Ready Salted", 10, "steady", 0.35, 1.00, "TS"),
    ("5000328363585", "Walkers Salt & Vinegar", 8, "steady", 0.35, 1.00, "TS"),
    ("5000328561172", "Doritos Cool Original", 5, "steady", 0.55, 1.50, "TS"),
    ("5000328523033", "Quavers Cheese", 4, "steady", 0.30, 0.85, "TS"),
    # MILK & DAIRY - perishable
    ("5000128840538", "Cravendale Semi-Skimmed 2L", 6, "steady", 1.30, 2.25, "S1"),
    ("5012035901003", "Graham's Whole Milk 1L", 4, "steady", 0.85, 1.55, "S1"),
    # BREAD - very perishable
    ("5010003000155", "Warburtons Toastie White", 5, "steady", 0.80, 1.50, "S2"),
    ("5010003000162", "Warburtons Toastie Wholemeal", 3, "steady", 0.80, 1.50, "S2"),
    # TOBACCO/VAPES (high value)
    ("5000171032001", "Elf Bar 600 Puffs", 8, "trending_up", 2.50, 5.99, "S2"),
    # SUNDRIES
    ("5000101153273", "Andrex Toilet Roll 4pk", 2, "steady", 1.80, 3.49, "S2"),
    ("50201926", "Paracetamol 16 Tablets", 2, "steady", 0.25, 0.89, "S2"),
]

def generate_daily_qty(avg, pattern, day_of_week, day_offset):
    """Generate realistic daily sales quantity based on pattern."""
    base = avg
    if pattern == "steady":
        base = max(0, avg + random.randint(-2, 2))
        # Slightly higher on weekends
        if day_of_week >= 5:
            base = int(base * 1.2)
    elif pattern == "weekend_spike":
        if day_of_week >= 4:  # Thu-Sun
            base = int(avg * 1.8) + random.randint(-1, 2)
        else:
            base = max(0, avg + random.randint(-2, 1))
    elif pattern == "every_other_day":
        # Regular customer pattern - buys every other day
        if day_offset % 2 == 0:
            base = avg + random.randint(0, 2)
        else:
            base = max(0, random.randint(0, 1))
    elif pattern == "trending_up":
        # Sales growing over 4 weeks
        week = day_offset // 7
        base = max(1, avg - 2 + week + random.randint(-1, 2))
        if day_of_week >= 5:
            base = int(base * 1.3)
    return max(0, base)


def seed():
    print("Seeding 4 weeks of demo data...")

    # Clear existing demo data
    print("Clearing old sales data...")
    try:
        supabase.table("sales").delete().neq("barcode", "NONE_MATCH").execute()
    except:
        pass

    # Clear old stock
    print("Clearing old stock data...")
    try:
        supabase.table("stock").delete().neq("barcode", "NONE_MATCH").execute()
    except:
        pass

    # Clear old waste
    print("Clearing old waste data...")
    try:
        supabase.table("waste").delete().neq("barcode", "NONE_MATCH").execute()
    except:
        pass

    now = datetime.utcnow()
    start = now - timedelta(days=28)

    all_sales = []
    waste_records = []
    total_sold = {}

    for day_offset in range(28):
        current_day = start + timedelta(days=day_offset)
        day_of_week = current_day.weekday()

        for barcode, name, avg, pattern, cost, sell, zone in PRODUCTS:
            qty = generate_daily_qty(avg, pattern, day_of_week, day_offset)
            if qty > 0:
                # Spread sales across the day (8am to 10pm)
                for _ in range(qty):
                    hour = random.randint(8, 22)
                    minute = random.randint(0, 59)
                    sale_time = current_day.replace(hour=hour, minute=minute)
                    all_sales.append({
                        "barcode": barcode,
                        "quantity": 1,
                        "sold_at": sale_time.isoformat(),
                    })

                total_sold.setdefault(barcode, 0)
                total_sold[barcode] += qty

        # Generate some waste for perishable items (milk, bread) ~ 15% of stock
        if day_of_week == 6:  # Sunday waste check
            for barcode, name, avg, pattern, cost, sell, zone in PRODUCTS:
                if name in ["Cravendale Semi-Skimmed 2L", "Graham's Whole Milk 1L",
                            "Warburtons Toastie White", "Warburtons Toastie Wholemeal"]:
                    wasted = random.randint(1, 3)
                    waste_records.append({
                        "barcode": barcode,
                        "name": name,
                        "quantity": wasted,
                        "reason": "expired",
                        "cost_price": cost,
                        "total_loss": round(wasted * cost, 2),
                        "logged_at": current_day.replace(hour=9).isoformat(),
                    })

    # Insert sales in batches
    print(f"Inserting {len(all_sales)} sales records...")
    batch_size = 500
    for i in range(0, len(all_sales), batch_size):
        batch = all_sales[i:i+batch_size]
        supabase.table("sales").insert(batch).execute()
        print(f"  Batch {i//batch_size + 1}: {len(batch)} records")

    # Insert waste
    print(f"Inserting {len(waste_records)} waste records...")
    if waste_records:
        supabase.table("waste").insert(waste_records).execute()

    # Add current stock (what's on shelves now)
    print("Adding current stock levels...")
    stock_records = []
    for barcode, name, avg, pattern, cost, sell, zone in PRODUCTS:
        # Current stock = roughly 3-5 days worth
        current_qty = avg * random.randint(3, 5)
        expiry_days = 7 if name.startswith(("Cravendale", "Graham's", "Warburtons")) else 90
        stock_records.append({
            "barcode": barcode,
            "name": name,
            "quantity": current_qty,
            "expiry_date": (now + timedelta(days=random.randint(2, expiry_days))).strftime("%Y-%m-%d"),
            "cost_price": cost,
            "sell_price": sell,
            "zone_code": zone,
            "location_note": "",
        })
    supabase.table("stock").insert(stock_records).execute()

    print(f"\nDone! Seeded:")
    print(f"  {len(all_sales)} sales over 28 days")
    print(f"  {len(waste_records)} waste records")
    print(f"  {len(stock_records)} stock items")
    print(f"  {len(PRODUCTS)} unique products")


if __name__ == "__main__":
    seed()
