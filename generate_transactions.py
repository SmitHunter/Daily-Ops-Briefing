"""
Generate 30 days of transaction data across 31 stores.

Layered patterns:
  - Weekday/weekend variance (weekends ~40% busier)
  - Payday-week uplift (Thursday/Friday spike around payday)
  - Regional variation (East slightly outperforms, West softer)
  - Store-tier mix (flagships skew higher AOV with bundles, small format more individual items)
  - Channel mix (in-store / kiosk / web / app / delivery)
  - Pricing differs by channel (delivery uses price_delivery)
  - Combo bias per store
  - Deliberate anomalies (Westbridge + Northgate have sustained issues for the agent to find)

Usage: python generate_transactions.py
Outputs data/transactions.json
"""

import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta

random.seed(31)

with open("data/stores.json") as f:
    STORES = json.load(f)
with open("data/products.json") as f:
    PRODUCTS = json.load(f)

COFFEE = [p for p in PRODUCTS if p["category"] == "Coffee"]
TEA = [p for p in PRODUCTS if p["category"] == "Tea"]
COLD = [p for p in PRODUCTS if p["category"] == "Cold Drinks"]
BREAKFAST = [p for p in PRODUCTS if p["category"] == "Breakfast"]
SANDWICHES = [p for p in PRODUCTS if p["category"] == "Sandwiches"]
WRAPS = [p for p in PRODUCTS if p["category"] == "Wraps"]
SALADS = [p for p in PRODUCTS if p["category"] == "Salads"]
BAKERY = [p for p in PRODUCTS if p["category"] == "Bakery"]
SNACKS = [p for p in PRODUCTS if p["category"] == "Snacks"]
COMBOS = [p for p in PRODUCTS if p["category"] == "Combos"]
DESSERTS = [p for p in PRODUCTS if p["category"] == "Desserts"]
HOT_FOOD = [p for p in PRODUCTS if p["category"] == "Hot Food"]
SAVOURY = SANDWICHES + WRAPS + HOT_FOOD
DRINKS = COFFEE + TEA + COLD

print(
    f"Product buckets: {len(COFFEE)} coffee, {len(COMBOS)} combos, {len(SAVOURY)} savoury, "
    f"{len(BAKERY)} bakery, {len(BREAKFAST)} breakfast"
)

STORE_PERFORMANCE = {
    "ST001": 1.05,
    "ST002": 1.02,
    "ST003": 0.93,
    "ST004": 1.08,
    "ST005": 0.98,
    "ST006": 1.01,
    "ST007": 0.97,
    "ST008": 0.78,
    "ST009": 1.00,
    "ST010": 1.03,
    "ST011": 0.99,
    "ST012": 1.06,
    "ST013": 0.95,
    "ST014": 1.00,
    "ST015": 0.96,
    "ST016": 0.94,
    "ST017": 1.02,
    "ST018": 1.00,
    "ST019": 0.91,
    "ST020": 0.99,
    "ST021": 1.04,
    "ST022": 0.98,
    "ST023": 1.01,
    "ST024": 1.05,
    "ST025": 0.93,
    "ST026": 1.00,
    "ST027": 1.02,
    "ST028": 0.97,
    "ST029": 1.03,
    "ST030": 0.98,
    "ST031": 0.72,
}

CHANNEL_MIX = {
    "flagship": {"in_store": 0.45, "kiosk": 0.25, "web": 0.10, "app": 0.10, "delivery": 0.10},
    "standard": {"in_store": 0.55, "kiosk": 0.15, "web": 0.10, "app": 0.10, "delivery": 0.10},
    "small": {"in_store": 0.70, "kiosk": 0.05, "web": 0.10, "app": 0.10, "delivery": 0.05},
    "factory": {"in_store": 0.85, "kiosk": 0.00, "web": 0.05, "app": 0.05, "delivery": 0.05},
}

REGION_BIAS = {"East": 1.03, "West": 0.96, "North": 1.00, "South": 1.01}


def is_payday_week(d: datetime) -> bool:
    if d.weekday() in (3, 4):
        return d.day in range(11, 18) or d.day >= 25
    return False


def daily_target(store: dict, date: datetime) -> float:
    base = store["weekly_target"] / 7
    if date.weekday() >= 5:
        base *= 1.40
    elif date.weekday() == 0:
        base *= 0.85
    if is_payday_week(date):
        base *= 1.12
    base *= REGION_BIAS[store["region"]]
    base *= STORE_PERFORMANCE[store["id"]]
    return base


def pick_basket(tier: str) -> list:
    basket = []
    r = random.random()

    if r < 0.18 and COMBOS:
        basket.append((random.choice(COMBOS), 1))
        if random.random() < 0.40 and COFFEE:
            basket.append((random.choice(COFFEE), random.choice([1, 1, 2])))
    elif r < 0.34 and SAVOURY:
        basket.append((random.choice(SAVOURY), 1))
        if random.random() < 0.55 and DRINKS:
            basket.append((random.choice(DRINKS), 1))
    elif r < 0.62:
        if COFFEE:
            basket.append((random.choice(COFFEE), 1))
        if random.random() < 0.65:
            pool = BAKERY + SNACKS
            if pool:
                basket.append((random.choice(pool), random.choice([1, 1, 1, 2])))
    elif r < 0.80 and BREAKFAST:
        basket.append((random.choice(BREAKFAST), 1))
        if random.random() < 0.55 and DRINKS:
            basket.append((random.choice(DRINKS), 1))
    else:
        pool = BAKERY + DESSERTS + (COLD if tier != "factory" else [])
        n = random.choice([1, 1, 2, 2, 3])
        for _ in range(n):
            if pool:
                basket.append((random.choice(pool), 1))

    if not basket and COFFEE:
        basket.append((random.choice(COFFEE), 1))
    return basket


def pick_channel(tier: str) -> str:
    mix = CHANNEL_MIX[tier]
    r, cum = random.random(), 0
    for chan, p in mix.items():
        cum += p
        if r <= cum:
            return chan
    return "in_store"


END_DATE = datetime(2026, 4, 30)
START_DATE = END_DATE - timedelta(days=29)

transactions = []
tx_id = 1

for day_offset in range(30):
    date = START_DATE + timedelta(days=day_offset)
    date_str = date.strftime("%Y-%m-%d")

    for store in STORES:
        opened = datetime.strptime(store["opened"], "%Y-%m-%d")
        if date < opened:
            continue

        target = daily_target(store, date) * random.uniform(0.92, 1.08)
        running = 0

        while running < target:
            channel = pick_channel(store["tier"])
            basket = pick_basket(store["tier"])
            for product, qty in basket:
                unit_price = (
                    product["price_delivery"]
                    if (channel == "delivery" and product.get("price_delivery"))
                    else product["price"]
                )
                line_total = round(unit_price * qty, 2)
                transactions.append(
                    {
                        "transaction_id": f"TX{tx_id:08d}",
                        "store_id": store["id"],
                        "date": date_str,
                        "channel": channel,
                        "plu": product["plu"],
                        "product_name": product["name"],
                        "category": product["category"],
                        "quantity": qty,
                        "unit_price": unit_price,
                        "unit_cost": product["unit_cost"],
                        "line_total": line_total,
                    }
                )
                running += line_total
                tx_id += 1

with open("data/transactions.json", "w") as f:
    json.dump(transactions, f)

total = sum(t["line_total"] for t in transactions)
print(f"\nGenerated {len(transactions):,} transactions over 30 days")
print(f"Network revenue: ${total:,.2f}  ({total / 30 / 31:,.0f} avg per store-day)")

by_store = defaultdict(float)
for t in transactions:
    by_store[t["store_id"]] += t["line_total"]
ranked = sorted(by_store.items(), key=lambda x: x[1])

print("\nWorst 3 by 30-day revenue:")
for sid, rev in ranked[:3]:
    s = next(x for x in STORES if x["id"] == sid)
    target = s["weekly_target"] * 30 / 7
    print(f"  {sid} {s['name']:25s} ${rev:>10,.0f}  vs target ${target:>10,.0f}  ({(rev / target - 1) * 100:+.1f}%)")
print("\nBest 3:")
for sid, rev in ranked[-3:]:
    s = next(x for x in STORES if x["id"] == sid)
    target = s["weekly_target"] * 30 / 7
    print(f"  {sid} {s['name']:25s} ${rev:>10,.0f}  vs target ${target:>10,.0f}  ({(rev / target - 1) * 100:+.1f}%)")

ch_count = Counter(t["channel"] for t in transactions)
print(f"\nChannel mix: {dict(ch_count)}")
