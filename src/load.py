import sqlite3
import pandas as pd
from .config import WAREHOUSE_DB

DDL = {
    "dim_customer": """
        CREATE TABLE IF NOT EXISTS dim_customer (
            customer_id TEXT PRIMARY KEY,
            name        TEXT,
            province    TEXT,
            email       TEXT
        )
    """,
    "dim_product": """
        CREATE TABLE IF NOT EXISTS dim_product (
            product_id   TEXT PRIMARY KEY,
            product_name TEXT,
            category     TEXT,
            price        REAL
        )
    """,
    "fact_sales": """
        CREATE TABLE IF NOT EXISTS fact_sales (
            order_id        TEXT PRIMARY KEY,
            customer_id     TEXT NOT NULL,
            product_id      TEXT NOT NULL,
            order_date      TEXT,
            qty             REAL,
            unit_price      REAL,
            discount_pct    REAL,
            status          TEXT,
            gross_amount    REAL,
            discount_amount REAL,
            sales_amount    REAL,
            FOREIGN KEY (customer_id) REFERENCES dim_customer (customer_id),
            FOREIGN KEY (product_id)  REFERENCES dim_product (product_id)
        )
    """,
}


def load_data(customers: pd.DataFrame, products: pd.DataFrame, sales: pd.DataFrame):
    """
    Load clean dimension/fact data into the SQLite warehouse.

    customer_id / product_id / order_id are enforced UNIQUE via PRIMARY KEY.
    dim_customer / dim_product use INSERT OR REPLACE (idempotent upsert on
    the natural key). fact_sales uses INSERT OR IGNORE keyed on order_id,
    so re-running the pipeline never duplicates fact rows.
    """
    WAREHOUSE_DB.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(WAREHOUSE_DB)
    try:
        cur = conn.cursor()
        for ddl in DDL.values():
            cur.execute(ddl)
        conn.commit()

        cust_rows = list(customers[["customer_id", "name", "province", "email"]].itertuples(index=False, name=None))
        cur.executemany(
            "INSERT OR REPLACE INTO dim_customer (customer_id, name, province, email) VALUES (?, ?, ?, ?)",
            cust_rows,
        )

        prod_rows = list(products[["product_id", "product_name", "category", "price"]].itertuples(index=False, name=None))
        cur.executemany(
            "INSERT OR REPLACE INTO dim_product (product_id, product_name, category, price) VALUES (?, ?, ?, ?)",
            prod_rows,
        )

        sales_df = sales.copy()
        sales_df["order_date"] = sales_df["order_date"].astype(str)
        sales_cols = [
            "order_id", "customer_id", "product_id", "order_date",
            "qty", "unit_price", "discount_pct", "status",
            "gross_amount", "discount_amount", "sales_amount",
        ]
        sales_rows = list(sales_df[sales_cols].itertuples(index=False, name=None))
        cur.executemany(
            """
            INSERT OR IGNORE INTO fact_sales
                (order_id, customer_id, product_id, order_date, qty, unit_price,
                 discount_pct, status, gross_amount, discount_amount, sales_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            sales_rows,
        )

        conn.commit()
    finally:
        conn.close()
