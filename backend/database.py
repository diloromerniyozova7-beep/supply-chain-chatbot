"""
database.py
-----------
Handles SQLite database creation and population from the DataCo Supply Chain CSV.

Usage:
    python database.py --csv path/to/DataCoSupplyChainDataset.csv

The script will:
  1. Load and clean the CSV with pandas
  2. Create supply_chain.db in the backend/ directory
  3. Populate the `orders` table with all cleaned records

Column mapping from DataCo dataset → SQLite column names:
  Original name (may vary by locale) → snake_case alias used in queries
"""

import argparse
import os
import sqlite3
import pandas as pd


DB_PATH = os.path.join(os.path.dirname(__file__), "supply_chain.db")

# ---------------------------------------------------------------------------
# Column normalisation map: DataCo original → internal snake_case name
# ---------------------------------------------------------------------------
COLUMN_MAP = {
    "Type": "type",
    "Days for shipping (real)": "days_for_shipping_real",
    "Days for shipment (scheduled)": "days_for_shipment_scheduled",
    "Benefit per order": "benefit_per_order",
    "Sales per customer": "sales_per_customer",
    "Delivery Status": "delivery_status",
    "Late_delivery_risk": "late_delivery_risk",
    "Category Id": "category_id",
    "Category Name": "category_name",
    "Customer City": "customer_city",
    "Customer Country": "customer_country",
    "Customer Email": "customer_email",
    "Customer Fname": "customer_fname",
    "Customer Id": "customer_id",
    "Customer Lname": "customer_lname",
    "Customer Password": "customer_password",
    "Customer Segment": "customer_segment",
    "Customer State": "customer_state",
    "Customer Street": "customer_street",
    "Customer Zipcode": "customer_zipcode",
    "Department Id": "department_id",
    "Department Name": "department_name",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Market": "market",
    "Order City": "order_city",
    "Order Country": "order_country",
    "Order Customer Id": "order_customer_id",
    "order date (DateOrders)": "order_date",
    "Order Id": "order_id",
    "Order Item Cardprod Id": "order_item_cardprod_id",
    "Order Item Discount": "order_item_discount",
    "Order Item Discount Rate": "order_item_discount_rate",
    "Order Item Id": "order_item_id",
    "Order Item Product Price": "order_item_product_price",
    "Order Item Profit Ratio": "order_item_profit_ratio",
    "Order Item Quantity": "order_item_quantity",
    "Sales": "sales",
    "Order Item Total": "order_item_total",
    "Order Profit Per Order": "order_profit_per_order",
    "Order Region": "order_region",
    "Order State": "order_state",
    "Order Status": "order_status",
    "Order Zipcode": "order_zipcode",
    "Product Card Id": "product_card_id",
    "Product Category Id": "product_category_id",
    "Product Description": "product_description",
    "Product Image": "product_image",
    "Product Name": "product_name",
    "Product Price": "product_price",
    "Product Status": "product_status",
    "shipping date (DateOrders)": "shipping_date",
    "Shipping Mode": "shipping_mode",
}


def load_and_clean(csv_path: str) -> pd.DataFrame:
    """Load CSV, rename columns, basic type coercion."""
    print(f"[db] Loading {csv_path} ...")
    # DataCo CSVs sometimes use latin-1 / cp1252 encoding
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(csv_path, encoding=enc, low_memory=False)
            print(f"[db] Read {len(df):,} rows with encoding={enc}")
            break
        except UnicodeDecodeError:
            continue

    # Rename only columns that exist in this version of the file
    rename = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Drop purely PII columns that add no analytical value
    drop_cols = [c for c in ("customer_email", "customer_password",
                              "customer_street", "product_image",
                              "product_description") if c in df.columns]
    df = df.drop(columns=drop_cols, errors="ignore")

    # Numeric coercions
    numeric_cols = [
        "benefit_per_order", "sales_per_customer", "late_delivery_risk",
        "order_item_discount", "order_item_discount_rate",
        "order_item_product_price", "order_item_profit_ratio",
        "order_item_quantity", "sales", "order_item_total",
        "order_profit_per_order", "product_price", "days_for_shipping_real",
        "days_for_shipment_scheduled",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    print(f"[db] Columns after cleaning: {list(df.columns)}")
    return df


def create_db(df: pd.DataFrame, db_path: str = DB_PATH) -> None:
    """Write the dataframe into SQLite."""
    print(f"[db] Writing to {db_path} ...")
    conn = sqlite3.connect(db_path)
    df.to_sql("orders", conn, if_exists="replace", index=False)

    # Basic indexes for common query patterns
    cur = conn.cursor()
    for col in ("late_delivery_risk", "delivery_status", "category_name",
                 "department_name", "market", "order_region", "product_name",
                 "order_item_quantity", "order_profit_per_order"):
        if col in df.columns:
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{col} ON orders ({col})"
            )
    conn.commit()
    conn.close()
    print(f"[db] Done — {len(df):,} rows loaded into 'orders' table.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Load DataCo Supply Chain CSV into SQLite"
    )
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to DataCoSupplyChainDataset.csv",
    )
    parser.add_argument(
        "--db",
        default=DB_PATH,
        help="Output SQLite path (default: backend/supply_chain.db)",
    )
    args = parser.parse_args()
    df = load_and_clean(args.csv)
    create_db(df, db_path=args.db)
