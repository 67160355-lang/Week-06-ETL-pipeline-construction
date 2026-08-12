import json
import sqlite3
import pandas as pd
from .config import RAW_DIR, SOURCE_DB


def extract_data():
    """
    Extract raw data from all sources:
      - customers.csv
      - orders.csv
      - products.json (nested JSON, flattened via json_normalize)
      - stores table in store.db

    Returns
    -------
    dict[str, pd.DataFrame]
        {"customers": ..., "orders": ..., "products": ..., "stores": ...}
    """
    customers = pd.read_csv(RAW_DIR / "customers.csv", dtype=str)
    orders = pd.read_csv(RAW_DIR / "orders.csv", dtype=str)

    with open(RAW_DIR / "products.json", "r", encoding="utf-8") as f:
        products_raw = json.load(f)
    products = pd.json_normalize(products_raw)

    with sqlite3.connect(SOURCE_DB) as conn:
        stores = pd.read_sql_query("SELECT * FROM stores", conn)

    return {
        "customers": customers,
        "orders": orders,
        "products": products,
        "stores": stores,
    }
