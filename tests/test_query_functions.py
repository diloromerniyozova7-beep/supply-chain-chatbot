"""
tests/test_query_functions.py
------------------------------
Unit tests for every query function in backend/query_functions.py.

These tests run against the real supply_chain.db if it exists, or skip
gracefully if the database hasn't been loaded yet.

Run:
    pytest tests/ -v
"""

import os
import pytest
import sqlite3

# Import the functions under test
from backend.query_functions import (
    get_low_stock_items,
    get_late_delivery_risk,
    get_profitability,
    get_loss_making_orders,
    get_order_volumes,
    get_top_products,
    get_shipping_performance,
    get_summary_stats,
    search_orders,
    DB_PATH,
)


# ---------------------------------------------------------------------------
# Fixture: skip all tests if DB not yet populated
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def require_db():
    if not os.path.exists(DB_PATH):
        pytest.skip(
            f"Database not found at {DB_PATH}. "
            "Run: python backend/database.py --csv <path> to populate it first."
        )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def row_count() -> int:
    conn = sqlite3.connect(DB_PATH)
    n = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()
    return n


# ---------------------------------------------------------------------------
# get_summary_stats
# ---------------------------------------------------------------------------
class TestGetSummaryStats:
    def test_returns_dict(self):
        result = get_summary_stats()
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        result = get_summary_stats()
        for key in ("total_orders", "unique_products", "total_sales",
                     "total_profit", "late_delivery_pct", "loss_making_orders"):
            assert key in result, f"Missing key: {key}"

    def test_total_orders_positive(self):
        result = get_summary_stats()
        assert result["total_orders"] > 0

    def test_late_delivery_pct_range(self):
        result = get_summary_stats()
        pct = result["late_delivery_pct"]
        assert 0 <= pct <= 100, f"late_delivery_pct out of range: {pct}"


# ---------------------------------------------------------------------------
# get_low_stock_items
# ---------------------------------------------------------------------------
class TestGetLowStockItems:
    def test_default_threshold(self):
        result = get_low_stock_items()
        assert "threshold" in result
        assert result["threshold"] == 2

    def test_returns_items_list(self):
        result = get_low_stock_items(threshold=3)
        assert "items" in result
        assert isinstance(result["items"], list)

    def test_threshold_zero_returns_empty_or_list(self):
        result = get_low_stock_items(threshold=0)
        assert isinstance(result["items"], list)

    def test_high_threshold_returns_more_items(self):
        r_low = get_low_stock_items(threshold=1)
        r_high = get_low_stock_items(threshold=10)
        assert r_high["count"] >= r_low["count"]

    def test_items_respect_threshold(self):
        result = get_low_stock_items(threshold=2)
        for item in result["items"]:
            assert item["avg_qty_per_line"] <= 2


# ---------------------------------------------------------------------------
# get_late_delivery_risk
# ---------------------------------------------------------------------------
class TestGetLateDeliveryRisk:
    def test_returns_orders_key(self):
        result = get_late_delivery_risk()
        assert "orders" in result

    def test_total_at_risk_is_integer(self):
        result = get_late_delivery_risk()
        assert isinstance(result["total_at_risk"], int)

    def test_total_at_risk_gt_zero(self):
        result = get_late_delivery_risk()
        # DataCo dataset is known to have many late-risk orders
        assert result["total_at_risk"] > 0

    def test_region_filter_reduces_results(self):
        all_results = get_late_delivery_risk()
        region_results = get_late_delivery_risk(region="Western Europe")
        assert region_results["total_at_risk"] <= all_results["total_at_risk"]

    def test_invalid_region_returns_empty(self):
        result = get_late_delivery_risk(region="NONEXISTENT_REGION_XYZ")
        assert result["total_at_risk"] == 0

    def test_limit_respected(self):
        result = get_late_delivery_risk(limit=5)
        assert len(result["orders"]) <= 5


# ---------------------------------------------------------------------------
# get_profitability
# ---------------------------------------------------------------------------
class TestGetProfitability:
    def test_default_group_by(self):
        result = get_profitability()
        assert result["group_by"] == "category"

    def test_results_list(self):
        result = get_profitability()
        assert isinstance(result["results"], list)
        assert len(result["results"]) > 0

    def test_each_row_has_profit_field(self):
        result = get_profitability()
        for row in result["results"]:
            assert "total_profit" in row

    @pytest.mark.parametrize("dim", ["department", "market", "region", "shipping_mode"])
    def test_group_by_variants(self, dim):
        result = get_profitability(group_by=dim)
        assert len(result["results"]) > 0

    def test_results_ordered_by_profit_desc(self):
        result = get_profitability(group_by="category")
        profits = [r["total_profit"] for r in result["results"]]
        assert profits == sorted(profits, reverse=True)


# ---------------------------------------------------------------------------
# get_loss_making_orders
# ---------------------------------------------------------------------------
class TestGetLossMakingOrders:
    def test_returns_dict_with_orders(self):
        result = get_loss_making_orders()
        assert "orders" in result
        assert "total_loss_making" in result

    def test_total_loss_making_positive(self):
        result = get_loss_making_orders()
        assert result["total_loss_making"] > 0

    def test_all_returned_orders_are_negative(self):
        result = get_loss_making_orders(limit=50)
        for order in result["orders"]:
            assert order["order_profit_per_order"] < 0

    def test_limit(self):
        result = get_loss_making_orders(limit=10)
        assert len(result["orders"]) <= 10


# ---------------------------------------------------------------------------
# get_order_volumes
# ---------------------------------------------------------------------------
class TestGetOrderVolumes:
    def test_returns_results(self):
        result = get_order_volumes()
        assert len(result["results"]) > 0

    @pytest.mark.parametrize("dim", ["market", "region", "category",
                                      "department", "shipping_mode",
                                      "delivery_status"])
    def test_group_by_dimensions(self, dim):
        result = get_order_volumes(group_by=dim)
        assert isinstance(result["results"], list)
        assert len(result["results"]) > 0

    def test_total_orders_sums_to_row_count(self):
        result = get_order_volumes(group_by="market", limit=1000)
        total = sum(r["total_orders"] for r in result["results"])
        assert total == row_count()


# ---------------------------------------------------------------------------
# get_top_products
# ---------------------------------------------------------------------------
class TestGetTopProducts:
    def test_returns_products(self):
        result = get_top_products()
        assert "products" in result
        assert len(result["products"]) > 0

    def test_ranked_by_sales_default(self):
        result = get_top_products()
        assert result["ranked_by"] == "sales"

    def test_limit_respected(self):
        result = get_top_products(limit=5)
        assert len(result["products"]) <= 5

    @pytest.mark.parametrize("metric", ["sales", "profit", "quantity", "orders"])
    def test_ranking_metrics(self, metric):
        result = get_top_products(by=metric, limit=5)
        assert len(result["products"]) > 0

    def test_category_filter(self):
        # Fetch all categories first to get a valid name
        from backend.query_functions import get_order_volumes
        cats = get_order_volumes(group_by="category")
        if not cats["results"]:
            pytest.skip("No categories found")
        cat_name = cats["results"][0]["dimension"]
        result = get_top_products(category=cat_name, limit=5)
        for p in result["products"]:
            assert p["category_name"].lower() == cat_name.lower()


# ---------------------------------------------------------------------------
# get_shipping_performance
# ---------------------------------------------------------------------------
class TestGetShippingPerformance:
    def test_returns_results(self):
        result = get_shipping_performance()
        assert len(result["results"]) > 0

    def test_each_row_has_late_pct(self):
        result = get_shipping_performance()
        for row in result["results"]:
            assert "late_pct" in row
            assert 0 <= row["late_pct"] <= 100

    def test_shipping_mode_filter(self):
        result = get_shipping_performance(shipping_mode="Standard Class")
        assert len(result["results"]) <= 1  # filtered to one mode

    def test_avg_delay_is_numeric(self):
        result = get_shipping_performance()
        for row in result["results"]:
            assert isinstance(row["avg_delay_days"], (int, float))


# ---------------------------------------------------------------------------
# search_orders
# ---------------------------------------------------------------------------
class TestSearchOrders:
    def test_returns_dict(self):
        result = search_orders(keyword="Polo")
        assert "orders" in result
        assert "found" in result

    def test_keyword_in_product_or_category(self):
        result = search_orders(keyword="Shoe", limit=20)
        for order in result["orders"]:
            assert (
                "shoe" in order["product_name"].lower()
                or "shoe" in order["category_name"].lower()
            )

    def test_empty_keyword_returns_orders(self):
        # Empty keyword matches everything via LIKE %%
        result = search_orders(keyword="", limit=5)
        assert isinstance(result["orders"], list)

    def test_nonexistent_keyword(self):
        result = search_orders(keyword="XYZNONEXISTENTPRODUCT123")
        assert result["found"] == 0
        assert result["orders"] == []

    def test_limit_respected(self):
        result = search_orders(keyword="a", limit=7)
        assert len(result["orders"]) <= 7
