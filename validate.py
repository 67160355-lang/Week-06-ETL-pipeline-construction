import sqlite3
import pandas as pd
from .config import WAREHOUSE_DB


def validate_data(source_sales: pd.DataFrame) -> dict:
    """
    Cross-check the transformed source sales against what actually landed
    in the warehouse. PASS only if row counts and total sales_amount match
    exactly and no duplicate order_id exists in fact_sales.
    """
    conn = sqlite3.connect(WAREHOUSE_DB)
    try:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM fact_sales")
        warehouse_rows = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) FROM (
                SELECT order_id FROM fact_sales GROUP BY order_id HAVING COUNT(*) > 1
            )
        """)
        duplicate_order_ids = cur.fetchone()[0]

        cur.execute("SELECT COALESCE(SUM(sales_amount), 0) FROM fact_sales")
        warehouse_total_sales = cur.fetchone()[0]
    finally:
        conn.close()

    source_valid_rows = int(len(source_sales))
    source_total_sales = float(source_sales["sales_amount"].sum())

    rows_match = source_valid_rows == warehouse_rows
    sales_match = round(source_total_sales, 2) == round(warehouse_total_sales, 2)
    status = "PASS" if (rows_match and sales_match and duplicate_order_ids == 0) else "FAIL"

    return {
        "source_valid_rows": source_valid_rows,
        "warehouse_rows": int(warehouse_rows),
        "duplicate_order_ids": int(duplicate_order_ids),
        "source_total_sales": round(source_total_sales, 2),
        "warehouse_total_sales": round(warehouse_total_sales, 2),
        "status": status,
    }
