"""
Build a fully synthetic product catalogue.

Names, PLUs, prices, and category mix are invented. This is not derived from a
real menu, PLU export, or brand list. Run: python build_products.py
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

OUT_PATH = "data/products.json"

# Invented codes in a range that does not resemble a typical 2-4 digit POS PLU list.
_next_plu = 41001


def _plu() -> str:
    global _next_plu
    code = str(_next_plu)
    _next_plu += 1
    return code


def _money(value: float) -> float:
    return round(round(value * 2) / 2, 2)


def _item(name: str, category: str, price: float, cost_ratio: float = 0.24) -> dict[str, Any]:
    price = _money(price)
    return {
        "plu": _plu(),
        "name": name,
        "category": category,
        "price": price,
        "price_delivery": _money(price + 1.5),
        "unit_cost": _money(price * cost_ratio),
    }


def _sized(names_and_prices: list[tuple[str, float]], category: str, cost_ratio: float) -> list[dict[str, Any]]:
    sizes = (("Small", 0.85), ("Regular", 1.0), ("Large", 1.2))
    items: list[dict[str, Any]] = []
    for name, base in names_and_prices:
        for size, factor in sizes:
            items.append(_item(f"{size} {name}", category, base * factor, cost_ratio))
    return items


def build_catalogue() -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []

    products.extend(
        _sized(
            [
                ("Flat White", 4.50),
                ("Latte", 4.50),
                ("Cappuccino", 4.50),
                ("Long Black", 4.00),
                ("Espresso", 3.50),
                ("Macchiato", 3.50),
                ("Mocha", 5.00),
                ("Hot Chocolate", 4.50),
                ("Filter Coffee", 4.00),
                ("Oat Latte", 5.00),
                ("Almond Flat White", 5.00),
                ("Piccolo", 3.50),
            ],
            "Coffee",
            0.18,
        )
    )

    products.extend(
        _sized(
            [
                ("Breakfast Tea", 3.50),
                ("Earl Grey", 3.50),
                ("Green Tea", 3.50),
                ("Peppermint Tea", 3.50),
                ("Chamomile Tea", 3.50),
                ("Chai Latte", 4.50),
                ("Matcha Latte", 5.00),
                ("Lemon Ginger Tea", 4.00),
            ],
            "Tea",
            0.16,
        )
    )

    products.extend(
        _sized(
            [
                ("Iced Latte", 5.00),
                ("Iced Mocha", 5.50),
                ("Iced Chocolate", 5.00),
                ("House Lemonade", 4.00),
                ("Citrus Fizz", 4.00),
                ("Ginger Beer", 4.00),
                ("House Cola", 3.50),
                ("Sparkling Water", 3.50),
                ("Still Water", 3.00),
                ("Peach Iced Tea", 4.00),
                ("Berry Cooler", 4.50),
                ("Mint Lime Soda", 4.50),
                ("Orange Juice", 4.50),
                ("Apple Juice", 4.50),
                ("Cucumber Soda", 4.50),
                ("Iced Tea", 4.00),
            ],
            "Cold Drinks",
            0.28,
        )
    )

    breakfast = [
        ("Bacon and Egg Roll", 8.50),
        ("Mushroom Toast", 9.00),
        ("Avocado Toast", 9.50),
        ("Breakfast Wrap", 10.00),
        ("Granola Cup", 7.50),
        ("Overnight Oats", 7.00),
        ("Yoghurt Bowl", 7.50),
        ("Porridge Cup", 6.50),
        ("Banana Bread Slice", 4.50),
        ("Hash Brown Pair", 4.00),
        ("Fruit Cup", 5.50),
        ("Egg and Cheese Muffin", 6.50),
        ("Tomato Toast", 8.00),
        ("Scrambled Egg Bowl", 9.00),
        ("Veggie Breakfast Plate", 11.00),
        ("Pancake Stack", 10.50),
        ("Bircher Muesli", 7.50),
        ("Savoury Muffin", 5.00),
        ("Cheese Toastie", 7.00),
        ("Baked Beans on Toast", 8.00),
        ("Spinach and Feta Roll", 6.50),
        ("Breakfast Burrito", 11.00),
        ("Cinnamon Toast", 6.00),
        ("Berry Compote Bowl", 8.00),
        ("Potato Rosti", 5.50),
        ("Halloumi Roll", 9.50),
        ("Smoked Salmon Toast", 12.00),
        ("Chia Pudding", 7.00),
        ("Apple Cinnamon Oats", 7.00),
        ("Herb Omelette", 10.00),
        ("Corn Fritters", 9.50),
        ("Tomato and Herb Shakshuka", 12.50),
        ("Maple Granola Jar", 8.00),
        ("Peanut Butter Toast", 6.50),
        ("Veggie Frittata Slice", 7.50),
        ("Rice Porridge", 6.50),
        ("Breakfast Salad", 11.50),
        ("Seeded Crumpets", 5.50),
        ("Warm Fruit Crumble Cup", 6.50),
        ("Cottage Cheese Bowl", 8.00),
    ]
    products.extend(_item(name, "Breakfast", price, 0.30) for name, price in breakfast)

    fillings = [
        ("Chicken and Avocado", 9.50),
        ("Roast Beef and Mustard", 9.50),
        ("Ham and Cheese", 8.00),
        ("Turkey and Cranberry", 9.00),
        ("Tuna and Celery", 8.50),
        ("Egg and Lettuce", 7.50),
        ("Cheese and Tomato", 7.00),
        ("Falafel and Slaw", 9.00),
        ("Grilled Vegetables", 8.50),
        ("Pesto Chicken", 9.50),
        ("Smoked Salmon and Dill", 11.00),
        ("BLT", 8.50),
        ("Chicken Schnitzel", 10.00),
        ("Caprese", 8.50),
        ("Hummus and Roast Veg", 8.50),
        ("Curried Egg", 7.50),
        ("Pulled Mushroom", 9.00),
        ("Lemon Herb Chicken", 9.50),
        ("Apple Slaw Pork", 10.00),
        ("Garden Club", 9.00),
    ]
    breads = ("White", "Grain", "Sourdough")
    for filling, price in fillings:
        for bread in breads:
            products.append(_item(f"{filling} on {bread}", "Sandwiches", price, 0.32))

    wrap_fillings = [
        ("Chicken", 9.00),
        ("Falafel", 8.50),
        ("Lamb", 10.00),
        ("Halloumi", 9.50),
        ("Beef", 10.00),
        ("Roast Pumpkin", 8.50),
        ("Tofu", 8.50),
        ("Crumbed Fish", 10.50),
        ("Greek Salad", 8.00),
        ("Spiced Cauliflower", 8.50),
        ("Turkey", 9.00),
        ("Chipotle Chicken", 9.50),
        ("Honey Soy Beef", 10.00),
        ("Green Goddess", 8.50),
        ("Moroccan Chickpea", 8.50),
        ("Prawn and Lime", 11.50),
    ]
    for filling, price in wrap_fillings:
        for size, factor in (("Regular", 1.0), ("Large", 1.25)):
            products.append(_item(f"{size} {filling} Wrap", "Wraps", price * factor, 0.30))

    salads = [
        ("Garden", 9.00),
        ("Caesar", 11.00),
        ("Roast Pumpkin", 11.50),
        ("Quinoa", 12.00),
        ("Noodle", 11.00),
        ("Couscous", 10.50),
        ("Kale and Apple", 11.50),
        ("Potato", 8.50),
        ("Tuna Nicoise", 13.00),
        ("Chicken and Grain", 12.50),
    ]
    for name, price in salads:
        for size, factor in (("Regular", 1.0), ("Large", 1.3)):
            products.append(_item(f"{size} {name} Salad", "Salads", price * factor, 0.32))

    bakery_bases = [
        ("Blueberry Muffin", 4.00),
        ("Chocolate Muffin", 4.00),
        ("Banana Muffin", 4.00),
        ("Cheese Scone", 3.50),
        ("Fruit Scone", 3.50),
        ("Cinnamon Scroll", 4.50),
        ("Almond Croissant", 5.00),
        ("Butter Croissant", 4.00),
        ("Pain au Chocolat", 5.00),
        ("Seeded Roll", 3.00),
        ("Olive Loaf Slice", 4.00),
        ("Lemon Slice", 4.00),
        ("Carrot Cake Slice", 5.00),
        ("Banana Cake Slice", 4.50),
        ("Anzac Biscuit", 2.50),
        ("Oat Cookie", 2.50),
        ("Chocolate Cookie", 2.50),
        ("Shortbread", 2.50),
        ("Apple Danish", 4.50),
        ("Custard Danish", 4.50),
    ]
    for name, price in bakery_bases:
        products.append(_item(name, "Bakery", price, 0.26))
        products.append(_item(f"Warm {name}", "Bakery", price + 0.50, 0.26))
        products.append(_item(f"Mini {name}", "Bakery", max(2.00, price - 1.00), 0.26))

    snacks = [
        ("Sea Salt Crisps", 3.50),
        ("Vinegar Crisps", 3.50),
        ("Sweet Chilli Crisps", 3.50),
        ("Cheese Twists", 3.50),
        ("Honey Nut Mix", 4.50),
        ("Roasted Almonds", 4.50),
        ("Trail Mix", 4.50),
        ("Rice Crackers", 3.00),
        ("Veggie Sticks", 4.00),
        ("Hummus Cup", 4.00),
        ("Yoghurt Pouch", 3.50),
        ("Cheese Stick Pack", 3.50),
        ("Popcorn Cup", 3.00),
        ("Pretzel Pack", 3.50),
        ("Seed Bar", 4.00),
        ("Oat Bar", 4.00),
        ("Cocoa Date Ball", 3.50),
        ("Apple Chips", 3.50),
        ("Rice Cakes", 3.00),
        ("Olive Cup", 4.00),
        ("Pickle Cup", 3.50),
        ("Edamame Cup", 4.50),
        ("Corn Chips", 3.50),
        ("Salsa Cup", 3.00),
        ("Garlic Bread", 4.50),
        ("Focaccia Square", 4.50),
        ("Cheese Toast Fingers", 4.50),
        ("Mini Spring Rolls", 5.50),
        ("Vegetable Samosa", 4.50),
        ("Corn Fritter Bite", 4.50),
        ("Soup Cup", 5.00),
        ("Miso Cup", 4.00),
        ("Noodle Cup", 5.50),
        ("Rice Paper Roll", 5.00),
        ("Cucumber Pack", 3.00),
        ("Carrot Stick Pack", 3.00),
        ("Boiled Egg Pack", 3.00),
        ("Sushi Pair", 6.50),
        ("Onigiri", 5.00),
        ("Steamed Bun", 4.50),
    ]
    products.extend(_item(name, "Snacks", price, 0.30) for name, price in snacks)

    combo_pairs = [
        ("Wrap and Drink", 13.50),
        ("Sandwich and Drink", 13.00),
        ("Salad and Drink", 14.00),
        ("Breakfast and Coffee", 12.50),
        ("Soup and Roll", 11.00),
        ("Toastie and Tea", 11.50),
        ("Muffin and Coffee", 8.50),
        ("Salad and Wrap", 16.50),
        ("Kids Snack Box", 9.50),
        ("Office Lunch Box", 17.00),
        ("Picnic Box", 18.00),
        ("Two Coffee Deal", 8.00),
    ]
    for name, price in combo_pairs:
        products.append(_item(f"{name} Combo", "Combos", price, 0.28))
        products.append(_item(f"Large {name} Combo", "Combos", price + 3.00, 0.28))
        products.append(_item(f"Weekday {name} Combo", "Combos", price - 1.00, 0.28))

    desserts = [
        ("Chocolate Brownie", 5.00),
        ("Lemon Tart", 5.50),
        ("Berry Cheesecake", 6.00),
        ("Apple Crumble", 6.00),
        ("Vanilla Slice", 5.00),
        ("Chocolate Mousse", 5.50),
        ("Banana Pudding", 5.00),
        ("Affogato", 6.50),
        ("Churros Pair", 5.50),
        ("Waffle Square", 6.00),
        ("Ice Cream Cup", 4.50),
        ("Sorbet Cup", 4.50),
        ("Tiramisu Cup", 6.50),
        ("Panna Cotta", 5.50),
        ("Lamington", 4.00),
        ("Fruit Tart", 5.50),
    ]
    for name, price in desserts:
        products.append(_item(name, "Desserts", price, 0.24))
        products.append(_item(f"Mini {name}", "Desserts", max(3.00, price - 1.50), 0.24))
        products.append(_item(f"Share {name}", "Desserts", price + 3.00, 0.24))

    hot_food = [
        ("Tomato Soup", 7.50),
        ("Pumpkin Soup", 7.50),
        ("Chicken Soup", 8.00),
        ("Minestrone", 8.00),
        ("Ham Toastie", 8.00),
        ("Kimchi Toastie", 8.50),
        ("Mushroom Toastie", 8.50),
        ("Lentil Stew", 9.50),
        ("Chicken Pasta", 10.50),
        ("Baked Gnocchi", 10.00),
        ("Macaroni Cup", 8.50),
        ("Fried Rice Cup", 9.00),
        ("Noodle Bowl", 11.00),
        ("Dumpling Bowl", 11.50),
        ("Baked Potato", 8.00),
    ]
    for name, price in hot_food:
        products.append(_item(name, "Hot Food", price, 0.32))
        products.append(_item(f"Large {name}", "Hot Food", price + 2.50, 0.32))

    return products


def main() -> None:
    products = build_catalogue()
    plus = {p["plu"] for p in products}
    names = [p["name"] for p in products]
    assert len(plus) == len(products), "PLUs must be unique"
    assert len(set(names)) == len(products), "Product names must be unique"

    counts = Counter(p["category"] for p in products)
    print(f"Wrote {len(products)} synthetic products")
    for category, n in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {n:3d}  {category}")

    with open(OUT_PATH, "w") as handle:
        json.dump(products, handle, indent=2)
        handle.write("\n")
    print(f"\nWritten to {OUT_PATH}")


if __name__ == "__main__":
    main()
