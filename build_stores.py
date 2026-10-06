"""
Build the 31-store dataset.

Tier breakdown:
  - 4 flagship (high-traffic centres)
  - ~14 standard suburban
  - ~12 small format
  - 1 factory / production site

Store names are invented demo labels, not real suburbs or shopping centres.
"""

import json
import random
from collections import Counter

random.seed(31)

stores = [
    # --- Flagship (4) ---
    {
        "id": "ST001",
        "name": "Eastgate Hub",
        "region": "East",
        "tier": "flagship",
        "opened": "2018-04-12",
        "weekly_target": 26000,
    },
    {
        "id": "ST002",
        "name": "Rivermark Centre",
        "region": "West",
        "tier": "flagship",
        "opened": "2017-09-03",
        "weekly_target": 24000,
    },
    {
        "id": "ST003",
        "name": "Northbridge Mall",
        "region": "North",
        "tier": "flagship",
        "opened": "2019-02-18",
        "weekly_target": 22000,
    },
    {
        "id": "ST004",
        "name": "South Harbour",
        "region": "South",
        "tier": "flagship",
        "opened": "2018-07-30",
        "weekly_target": 23000,
    },
    # --- Factory site (1) ---
    {
        "id": "ST005",
        "name": "Harbour Works",
        "region": "South",
        "tier": "factory",
        "opened": "2014-01-15",
        "weekly_target": 19000,
    },
    # --- Standard (14) ---
    {
        "id": "ST006",
        "name": "Maple Crossing",
        "region": "East",
        "tier": "standard",
        "opened": "2019-08-20",
        "weekly_target": 16000,
    },
    {
        "id": "ST007",
        "name": "Ridgeway",
        "region": "East",
        "tier": "standard",
        "opened": "2020-05-14",
        "weekly_target": 15000,
    },
    {
        "id": "ST008",
        "name": "Westbridge",
        "region": "West",
        "tier": "standard",
        "opened": "2020-11-01",
        "weekly_target": 14500,
    },
    {
        "id": "ST009",
        "name": "Lakeside Court",
        "region": "West",
        "tier": "standard",
        "opened": "2021-03-22",
        "weekly_target": 14000,
    },
    {
        "id": "ST010",
        "name": "Hillcrest",
        "region": "North",
        "tier": "standard",
        "opened": "2020-02-10",
        "weekly_target": 14500,
    },
    {
        "id": "ST011",
        "name": "Ironbark Plaza",
        "region": "North",
        "tier": "standard",
        "opened": "2021-06-05",
        "weekly_target": 14000,
    },
    {
        "id": "ST012",
        "name": "Seaview Gate",
        "region": "South",
        "tier": "standard",
        "opened": "2019-11-25",
        "weekly_target": 17000,
    },
    {
        "id": "ST013",
        "name": "Redcliff",
        "region": "South",
        "tier": "standard",
        "opened": "2021-01-18",
        "weekly_target": 13500,
    },
    {
        "id": "ST014",
        "name": "Amberfield",
        "region": "East",
        "tier": "standard",
        "opened": "2020-08-12",
        "weekly_target": 15500,
    },
    {
        "id": "ST015",
        "name": "Duskwater",
        "region": "West",
        "tier": "standard",
        "opened": "2021-09-30",
        "weekly_target": 14000,
    },
    {
        "id": "ST016",
        "name": "Stoneford",
        "region": "North",
        "tier": "standard",
        "opened": "2022-02-28",
        "weekly_target": 13500,
    },
    {
        "id": "ST017",
        "name": "Bayfront",
        "region": "South",
        "tier": "standard",
        "opened": "2020-12-08",
        "weekly_target": 15000,
    },
    {
        "id": "ST018",
        "name": "Silverleaf",
        "region": "East",
        "tier": "standard",
        "opened": "2022-05-15",
        "weekly_target": 14500,
    },
    {
        "id": "ST019",
        "name": "Riverbend",
        "region": "West",
        "tier": "standard",
        "opened": "2022-09-19",
        "weekly_target": 13000,
    },
    # --- Small format (12) ---
    {
        "id": "ST020",
        "name": "Copse Hill",
        "region": "East",
        "tier": "small",
        "opened": "2022-11-10",
        "weekly_target": 11000,
    },
    {
        "id": "ST021",
        "name": "Fernvale",
        "region": "North",
        "tier": "small",
        "opened": "2023-01-25",
        "weekly_target": 9500,
    },
    {
        "id": "ST022",
        "name": "Ashmead",
        "region": "North",
        "tier": "small",
        "opened": "2023-04-14",
        "weekly_target": 9000,
    },
    {
        "id": "ST023",
        "name": "Brookhollow",
        "region": "North",
        "tier": "small",
        "opened": "2023-07-08",
        "weekly_target": 9500,
    },
    {
        "id": "ST024",
        "name": "Pinecrest",
        "region": "North",
        "tier": "small",
        "opened": "2023-10-22",
        "weekly_target": 10000,
    },
    {
        "id": "ST025",
        "name": "Cinderwell",
        "region": "West",
        "tier": "small",
        "opened": "2024-02-05",
        "weekly_target": 8500,
    },
    {
        "id": "ST026",
        "name": "Goldfinch",
        "region": "West",
        "tier": "small",
        "opened": "2024-05-19",
        "weekly_target": 9000,
    },
    {
        "id": "ST027",
        "name": "Saltmarsh",
        "region": "South",
        "tier": "small",
        "opened": "2024-08-03",
        "weekly_target": 9500,
    },
    {
        "id": "ST028",
        "name": "Lowlands",
        "region": "South",
        "tier": "small",
        "opened": "2024-10-27",
        "weekly_target": 8500,
    },
    {
        "id": "ST029",
        "name": "Copperfield",
        "region": "East",
        "tier": "small",
        "opened": "2025-02-11",
        "weekly_target": 10000,
    },
    {
        "id": "ST030",
        "name": "Windrow",
        "region": "East",
        "tier": "small",
        "opened": "2025-06-09",
        "weekly_target": 9500,
    },
    {
        "id": "ST031",
        "name": "Northgate",
        "region": "North",
        "tier": "small",
        "opened": "2026-02-14",
        "weekly_target": 8000,
    },
]

assert len(stores) == 31, f"Expected 31 stores, got {len(stores)}"

# Tier counts
tiers = Counter(s["tier"] for s in stores)
regions = Counter(s["region"] for s in stores)
print(f"Stores: {len(stores)}")
print(f"By tier: {dict(tiers)}")
print(f"By region: {dict(regions)}")
print(f"Total weekly target: ${sum(s['weekly_target'] for s in stores):,}")

with open("data/stores.json", "w") as f:
    json.dump(stores, f, indent=2)

print("\nWritten to data/stores.json")
