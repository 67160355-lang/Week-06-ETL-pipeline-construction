import pandas as pd
from .config import PROVINCE_MAP

# Date formats observed in the source system (mixed on purpose).
# Order matters: each candidate is tried only on rows still unparsed.
DATE_FORMATS = ["%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y"]

VALID_STATUSES = {"paid", "completed"}


def _parse_mixed_dates(series: pd.Series) -> pd.Series:
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    remaining = series.astype(str).str.strip()
    for fmt in DATE_FORMATS:
        mask = result.isna()
        if not mask.any():
            break
        parsed = pd.to_datetime(remaining[mask], format=fmt, errors="coerce")
        result.loc[mask] = parsed
    return result


def _clean_customers(customers: pd.DataFrame) -> pd.DataFrame:
    df = customers.copy()

    df["province"] = df["province"].fillna("").astype(str).str.strip()
    df["province"] = df["province"].str.lower().map(PROVINCE_MAP).fillna("Unknown")

    df["email"] = df["email"].fillna("").astype(str).str.strip()
    df["email"] = df["email"].replace("", "unknown@example.com")

    df = df.drop_duplicates(subset="customer_id", keep="first")
    return df.reset_index(drop=True)


def _clean_products(products: pd.DataFrame) -> pd.DataFrame:
    df = products.rename(columns={
        "category.name": "category",
        "pricing.price": "price",
    }).copy()

    df["category"] = df["category"].fillna("Unknown")
    df["category"] = df["category"].astype(str).replace({"": "Unknown", "None": "Unknown"})

    df["price"] = (
        df["price"].astype(str)
        .str.replace(",", "", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
    )

    df = df[["product_id", "product_name", "category", "price"]]
    df = df.drop_duplicates(subset="product_id", keep="first")
    return df.reset_index(drop=True)


def _clean_orders(orders: pd.DataFrame):
    """Type-cast, dedupe, and split orders into valid / invalid (rejected)."""
    df = orders.copy()

    df["status"] = df["status"].astype(str).str.strip().str.lower()
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df["discount_pct"] = pd.to_numeric(df["discount_pct"], errors="coerce")
    df["order_date"] = _parse_mixed_dates(df["order_date"])

    df = df.drop_duplicates(subset="order_id", keep="first")

    valid_mask = (
        df["qty"].notna() & (df["qty"] > 0)
        & df["unit_price"].notna() & (df["unit_price"] > 0)
        & df["discount_pct"].notna() & (df["discount_pct"] >= 0) & (df["discount_pct"] <= 100)
        & df["order_date"].notna()
    )

    valid_orders = df[valid_mask].copy()
    invalid_orders = df[~valid_mask].copy()
    invalid_orders["reject_reason"] = "invalid_order_fields"
    return valid_orders, invalid_orders


def transform_data(raw: dict):
    """
    Transform raw extracted data into clean dimension/fact frames.

    Returns
    -------
    clean_customers, clean_products, sales, rejects
    """
    clean_customers = _clean_customers(raw["customers"])
    clean_products = _clean_products(raw["products"])
    valid_orders, invalid_orders = _clean_orders(raw["orders"])

    reject_frames = [invalid_orders]

    # Keep only paid / completed orders.
    status_mask = valid_orders["status"].isin(VALID_STATUSES)
    kept_orders = valid_orders[status_mask].copy()

    dropped_status = valid_orders[~status_mask].copy()
    dropped_status["reject_reason"] = "status_not_paid_or_completed"
    reject_frames.append(dropped_status)

    # Join customers - reject orders with unknown customer_id.
    merged = kept_orders.merge(
        clean_customers[["customer_id"]], on="customer_id", how="left", indicator="_cust"
    )
    unknown_customer = merged[merged["_cust"] == "left_only"].drop(columns=["_cust"]).copy()
    unknown_customer["reject_reason"] = "unknown_customer"
    reject_frames.append(unknown_customer)
    merged = merged[merged["_cust"] == "both"].drop(columns=["_cust"])

    # Join products - reject orders with unknown product_id.
    merged = merged.merge(
        clean_products[["product_id", "price"]], on="product_id", how="left", indicator="_prod"
    )
    unknown_product = merged[merged["_prod"] == "left_only"].drop(columns=["_prod", "price"]).copy()
    unknown_product["reject_reason"] = "unknown_product"
    reject_frames.append(unknown_product)
    merged = merged[merged["_prod"] == "both"].drop(columns=["_prod"])

    # Note: unit_price on the order line is the transactional price actually
    # charged; the joined dim_product "price" is master-data reference only
    # and is not used in the amount calculations below.
    merged["gross_amount"] = merged["qty"] * merged["unit_price"]
    merged["discount_amount"] = merged["gross_amount"] * merged["discount_pct"] / 100
    merged["sales_amount"] = merged["gross_amount"] - merged["discount_amount"]

    sales_cols = [
        "order_id", "customer_id", "product_id", "order_date",
        "qty", "unit_price", "discount_pct", "status",
        "gross_amount", "discount_amount", "sales_amount",
    ]
    sales = merged[sales_cols].reset_index(drop=True)

    rejects = pd.concat(reject_frames, ignore_index=True, sort=False)

    return clean_customers, clean_products, sales, rejects
