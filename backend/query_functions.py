"""
query_functions.py
------------------
Pure Python functions that query the SQLite database.
Each function is registered as a Claude tool in main.py.

Rules:
  - Each function accepts typed parameters only (str, int, float).
  - Each function returns a dict that is JSON-serialisable.
  - No function imports from main.py (prevents circular deps).
"""

import sqlite3
import os
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "supply_chain.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 1. Low-stock / reorder alerts
# ---------------------------------------------------------------------------
def get_low_stock_items(threshold: int = 2) -> dict:
    """
    Return products whose ordered quantity per order line falls at or
    below `threshold`.  A proxy for low-stock risk given the DataCo dataset
    doesn't contain warehouse on-hand counts.
    """
    conn = _conn()
    rows = conn.execute(
        """
        SELECT product_name,
               category_name,
               SUM(order_item_quantity)  AS total_ordered,
               COUNT(*)                  AS order_lines,
               AVG(order_item_quantity)  AS avg_qty_per_line
        FROM   orders
        WHERE  order_item_quantity <= ?
        GROUP  BY product_name, category_name
        ORDER  BY total_ordered ASC
        LIMIT  50
        """,
        (threshold,),
    ).fetchall()
    conn.close()
    return {
        "threshold": threshold,
        "count": len(rows),
        "items": _rows_to_list(rows),
    }


# ---------------------------------------------------------------------------
# 2. Late delivery risk
# ---------------------------------------------------------------------------
def get_late_delivery_risk(min_risk: int = 1,
                            region: Optional[str] = None,
                            limit: int = 20) -> dict:
    """
    Return orders flagged as high late-delivery risk.
    late_delivery_risk is a 0/1 binary flag in the DataCo dataset.
    Optionally filter by order_region.
    """
    conn = _conn()
    where = "WHERE late_delivery_risk >= ?"
    params: list = [min_risk]
    if region:
        where += " AND LOWER(order_region) = LOWER(?)"
        params.append(region)

    rows = conn.execute(
        f"""
        SELECT order_id, order_date, product_name, category_name,
               order_region, market, delivery_status,
               days_for_shipping_real, days_for_shipment_scheduled,
               late_delivery_risk, order_profit_per_order
        FROM   orders
        {where}
        ORDER  BY order_date DESC
        LIMIT  ?
        """,
        params + [limit],
    ).fetchall()

    total = conn.execute(
        f"SELECT COUNT(*) FROM orders {where}", params
    ).fetchone()[0]
    conn.close()
    return {
        "total_at_risk": total,
        "shown": len(rows),
        "filter_region": region,
        "orders": _rows_to_list(rows),
    }


# ---------------------------------------------------------------------------
# 3. Profitability analysis
# ---------------------------------------------------------------------------
def get_profitability(group_by: str = "category",
                       region: Optional[str] = None,
                       limit: int = 20) -> dict:
    """
    Summarise profit by a dimension.
    group_by options: 'category', 'department', 'market', 'region',
                      'product', 'shipping_mode', 'customer_segment'
    """
    dim_map = {
        "category":         "category_name",
        "department":       "department_name",
        "market":           "market",
        "region":           "order_region",
        "product":          "product_name",
        "shipping_mode":    "shipping_mode",
        "customer_segment": "customer_segment",
    }
    col = dim_map.get(group_by.lower(), "category_name")

    where = ""
    params: list = []
    if region:
        where = "WHERE LOWER(order_region) = LOWER(?)"
        params.append(region)

    conn = _conn()
    rows = conn.execute(
        f"""
        SELECT {col}                         AS dimension,
               COUNT(*)                      AS order_lines,
               ROUND(SUM(order_profit_per_order), 2)  AS total_profit,
               ROUND(AVG(order_profit_per_order), 2)  AS avg_profit,
               ROUND(SUM(sales), 2)          AS total_sales,
               ROUND(AVG(order_item_profit_ratio)*100, 1) AS avg_profit_pct
        FROM   orders
        {where}
        GROUP  BY {col}
        ORDER  BY total_profit DESC
        LIMIT  ?
        """,
        params + [limit],
    ).fetchall()
    conn.close()
    return {
        "group_by": group_by,
        "filter_region": region,
        "results": _rows_to_list(rows),
    }


# ---------------------------------------------------------------------------
# 4. Loss-making orders
# ---------------------------------------------------------------------------
def get_loss_making_orders(limit: int = 20,
                            region: Optional[str] = None) -> dict:
    """Return orders where order_profit_per_order is negative."""
    where = "WHERE order_profit_per_order < 0"
    params: list = []
    if region:
        where += " AND LOWER(order_region) = LOWER(?)"
        params.append(region)

    conn = _conn()
    rows = conn.execute(
        f"""
        SELECT order_id, order_date, product_name, category_name,
               order_region, market, order_profit_per_order, sales,
               order_item_discount_rate, order_item_quantity,
               delivery_status
        FROM   orders
        {where}
        ORDER  BY order_profit_per_order ASC
        LIMIT  ?
        """,
        params + [limit],
    ).fetchall()

    total = conn.execute(
        f"SELECT COUNT(*) FROM orders {where}", params
    ).fetchone()[0]
    conn.close()
    return {
        "total_loss_making": total,
        "shown": len(rows),
        "orders": _rows_to_list(rows),
    }


# ---------------------------------------------------------------------------
# 5. Order volumes by region / market / category
# ---------------------------------------------------------------------------
def get_order_volumes(group_by: str = "market",
                       limit: int = 20) -> dict:
    """
    Count orders and total sales grouped by a dimension.
    group_by: 'market', 'region', 'category', 'department',
              'customer_segment', 'shipping_mode', 'delivery_status'
    """
    dim_map = {
        "market":             "market",
        "region":             "order_region",
        "category":           "category_name",
        "department":         "department_name",
        "customer_segment":   "customer_segment",
        "shipping_mode":      "shipping_mode",
        "delivery_status":    "delivery_status",
    }
    col = dim_map.get(group_by.lower(), "market")
    conn = _conn()
    rows = conn.execute(
        f"""
        SELECT {col}               AS dimension,
               COUNT(*)            AS total_orders,
               SUM(order_item_quantity) AS total_units,
               ROUND(SUM(sales),2) AS total_sales,
               ROUND(AVG(sales),2) AS avg_order_value
        FROM   orders
        GROUP  BY {col}
        ORDER  BY total_orders DESC
        LIMIT  ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return {
        "group_by": group_by,
        "results": _rows_to_list(rows),
    }


# ---------------------------------------------------------------------------
# 6. Top products
# ---------------------------------------------------------------------------
def get_top_products(by: str = "sales",
                      category: Optional[str] = None,
                      limit: int = 10) -> dict:
    """
    Rank products.
    by: 'sales', 'profit', 'quantity', 'orders'
    """
    sort_map = {
        "sales":    "ROUND(SUM(sales),2) DESC",
        "profit":   "ROUND(SUM(order_profit_per_order),2) DESC",
        "quantity": "SUM(order_item_quantity) DESC",
        "orders":   "COUNT(*) DESC",
    }
    order_clause = sort_map.get(by.lower(), "ROUND(SUM(sales),2) DESC")

    where = ""
    params: list = []
    if category:
        where = "WHERE LOWER(category_name) = LOWER(?)"
        params.append(category)

    conn = _conn()
    rows = conn.execute(
        f"""
        SELECT product_name,
               category_name,
               COUNT(*)                              AS order_count,
               SUM(order_item_quantity)              AS total_units,
               ROUND(SUM(sales),2)                   AS total_sales,
               ROUND(SUM(order_profit_per_order),2)  AS total_profit,
               ROUND(AVG(order_item_product_price),2) AS avg_price
        FROM   orders
        {where}
        GROUP  BY product_name, category_name
        ORDER  BY {order_clause}
        LIMIT  ?
        """,
        params + [limit],
    ).fetchall()
    conn.close()
    return {
        "ranked_by": by,
        "filter_category": category,
        "products": _rows_to_list(rows),
    }


# ---------------------------------------------------------------------------
# 7. Shipping performance
# ---------------------------------------------------------------------------
def get_shipping_performance(shipping_mode: Optional[str] = None) -> dict:
    """
    Average real vs scheduled shipping days, late-delivery rate,
    optionally filtered by shipping_mode.
    """
    where = ""
    params: list = []
    if shipping_mode:
        where = "WHERE LOWER(shipping_mode) = LOWER(?)"
        params.append(shipping_mode)

    conn = _conn()
    rows = conn.execute(
        f"""
        SELECT shipping_mode,
               COUNT(*)                                       AS orders,
               ROUND(AVG(days_for_shipping_real),2)           AS avg_real_days,
               ROUND(AVG(days_for_shipment_scheduled),2)      AS avg_sched_days,
               ROUND(AVG(days_for_shipping_real -
                         days_for_shipment_scheduled),2)      AS avg_delay_days,
               ROUND(100.0*SUM(late_delivery_risk)/COUNT(*),1) AS late_pct
        FROM   orders
        {where}
        GROUP  BY shipping_mode
        ORDER  BY late_pct DESC
        """,
        params,
    ).fetchall()
    conn.close()
    return {
        "filter_mode": shipping_mode,
        "results": _rows_to_list(rows),
    }


# ---------------------------------------------------------------------------
# 8. Summary / KPI snapshot
# ---------------------------------------------------------------------------
def get_summary_stats() -> dict:
    """High-level KPIs across the entire dataset."""
    conn = _conn()
    r = conn.execute(
        """
        SELECT COUNT(DISTINCT order_id)              AS total_orders,
               COUNT(DISTINCT product_name)          AS unique_products,
               COUNT(DISTINCT category_name)         AS categories,
               COUNT(DISTINCT market)                AS markets,
               ROUND(SUM(sales),2)                   AS total_sales,
               ROUND(SUM(order_profit_per_order),2)  AS total_profit,
               ROUND(AVG(order_profit_per_order),2)  AS avg_profit_per_order,
               ROUND(100.0*SUM(late_delivery_risk)/COUNT(*),1) AS late_delivery_pct,
               SUM(CASE WHEN order_profit_per_order < 0 THEN 1 ELSE 0 END)
                                                      AS loss_making_orders
        FROM orders
        """
    ).fetchone()
    conn.close()
    return dict(r)


# ---------------------------------------------------------------------------
# 9. Search orders / free-text product lookup
# ---------------------------------------------------------------------------
def search_orders(keyword: str, limit: int = 15) -> dict:
    """
    Find orders whose product name or category name contains keyword.
    """
    like = f"%{keyword}%"
    conn = _conn()
    rows = conn.execute(
        """
        SELECT order_id, order_date, product_name, category_name,
               order_region, market, order_item_quantity, sales,
               order_profit_per_order, delivery_status, late_delivery_risk
        FROM   orders
        WHERE  LOWER(product_name) LIKE LOWER(?)
           OR  LOWER(category_name) LIKE LOWER(?)
        ORDER  BY order_date DESC
        LIMIT  ?
        """,
        (like, like, limit),
    ).fetchall()
    conn.close()
    return {
        "keyword": keyword,
        "found": len(rows),
        "orders": _rows_to_list(rows),
    }
