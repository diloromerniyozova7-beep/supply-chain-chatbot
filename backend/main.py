"""
main.py
-------
FastAPI backend for the AI-Powered Supply Chain Inventory Assistant.

Endpoints:
  POST /chat   — accepts a user message + session history,
                 calls Claude with tool definitions, returns AI reply.
  GET  /health — liveness check.

Run:
  uvicorn backend.main:app --reload
"""

import json
import os
from typing import Any

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

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
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="Supply Chain Chatbot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------
TOOLS: list[dict] = [
    {
        "name": "get_low_stock_items",
        "description": (
            "Identify products with low ordered quantities that may need "
            "reordering. Returns products whose order-line quantity falls at or "
            "below the given threshold. Use this for questions about stock levels, "
            "reorder alerts, or low-inventory items."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "threshold": {
                    "type": "integer",
                    "description": "Maximum order-line quantity to consider low-stock. Default 2.",
                    "default": 2,
                }
            },
        },
    },
    {
        "name": "get_late_delivery_risk",
        "description": (
            "Find orders flagged as high risk for late delivery. Optionally filter "
            "by region. Use for questions about delayed shipments, delivery risk, "
            "or logistics issues."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "min_risk": {
                    "type": "integer",
                    "description": "Minimum late_delivery_risk flag value (0 or 1). Default 1.",
                    "default": 1,
                },
                "region": {
                    "type": "string",
                    "description": "Optional order region filter, e.g. 'Western Europe'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return. Default 20.",
                    "default": 20,
                },
            },
        },
    },
    {
        "name": "get_profitability",
        "description": (
            "Analyse profit and sales by a chosen dimension. Use for questions "
            "about profit margins, which category/region/department earns most, "
            "or revenue breakdowns. group_by options: category, department, "
            "market, region, product, shipping_mode, customer_segment."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group_by": {
                    "type": "string",
                    "description": "Dimension to group by. One of: category, department, market, region, product, shipping_mode, customer_segment.",
                    "default": "category",
                },
                "region": {
                    "type": "string",
                    "description": "Optional region filter.",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                },
            },
        },
    },
    {
        "name": "get_loss_making_orders",
        "description": (
            "Return orders where profit is negative (loss-making). Use for "
            "questions about orders losing money, unprofitable transactions, "
            "or financial losses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
                "region": {"type": "string", "description": "Optional region filter."},
            },
        },
    },
    {
        "name": "get_order_volumes",
        "description": (
            "Count orders and total sales grouped by a dimension. Use for "
            "questions about which market/region/category has the most orders or "
            "highest sales volume. group_by options: market, region, category, "
            "department, customer_segment, shipping_mode, delivery_status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group_by": {
                    "type": "string",
                    "description": "Dimension to group by.",
                    "default": "market",
                },
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "get_top_products",
        "description": (
            "Rank the top products by sales, profit, quantity, or order count. "
            "Use for questions like 'which products sell most', 'top earners', "
            "or 'best-selling items'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "by": {
                    "type": "string",
                    "description": "Ranking metric: sales, profit, quantity, or orders.",
                    "default": "sales",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter.",
                },
                "limit": {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "get_shipping_performance",
        "description": (
            "Compare real vs scheduled shipping days and late-delivery rates by "
            "shipping mode. Use for questions about delivery speed, shipping "
            "method performance, or on-time delivery rates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "shipping_mode": {
                    "type": "string",
                    "description": "Optional filter: Standard Class, Second Class, First Class, Same Day.",
                }
            },
        },
    },
    {
        "name": "get_summary_stats",
        "description": (
            "Return high-level KPI snapshot of the entire dataset: total orders, "
            "products, sales, profit, late-delivery rate, and loss-making orders. "
            "Use for overview or summary questions."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_orders",
        "description": (
            "Search for orders by product name or category keyword. Use when the "
            "user asks about a specific product or category by name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Product name or category keyword to search for.",
                },
                "limit": {"type": "integer", "default": 15},
            },
            "required": ["keyword"],
        },
    },
]

# Map tool name → Python function
TOOL_FUNCTIONS: dict[str, Any] = {
    "get_low_stock_items":     get_low_stock_items,
    "get_late_delivery_risk":  get_late_delivery_risk,
    "get_profitability":       get_profitability,
    "get_loss_making_orders":  get_loss_making_orders,
    "get_order_volumes":       get_order_volumes,
    "get_top_products":        get_top_products,
    "get_shipping_performance": get_shipping_performance,
    "get_summary_stats":       get_summary_stats,
    "search_orders":           search_orders,
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an AI-powered Supply Chain Inventory Assistant for a business analytics team.

You have access to a live SQLite database populated with the DataCo Supply Chain Dataset
(180,000+ real order records) covering products, categories, regions, markets, delivery
status, profit, and shipping data.

IMPORTANT RULES:
1. NEVER invent or estimate numbers. Every factual claim about inventory, orders, profit,
   or delivery MUST come from a database tool call.
2. After receiving tool results, summarise the key findings clearly and concisely in
   plain English — bullet points are welcome for lists of items.
3. If a question requires multiple tool calls (e.g. profit by region AND top products),
   make them sequentially before composing your final answer.
4. Keep responses business-focused. Highlight actionable insights where possible.
5. If the database has no matching records, say so clearly rather than guessing.
6. Format large numbers with commas. Use $ for currency. Round percentages to 1 decimal.

You can answer questions about:
- Stock levels and reorder alerts
- Late delivery risks and logistics performance
- Profitability by product, category, region, or department
- Loss-making orders
- Order volumes and sales breakdowns
- Shipping mode performance
- Top-performing products
- Dataset-wide KPIs and summaries
"""

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class Message(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []


class ChatResponse(BaseModel):
    reply: str
    tool_calls_made: list[str] = []


# ---------------------------------------------------------------------------
# Helper: execute one tool call
# ---------------------------------------------------------------------------
def _execute_tool(name: str, inputs: dict) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = fn(**inputs)
        return json.dumps(result, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# /chat endpoint
# ---------------------------------------------------------------------------
@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # Build messages list including session history
    messages = [
        {"role": m.role, "content": m.content} for m in req.history
    ]
    messages.append({"role": "user", "content": req.message})

    tools_used: list[str] = []
    final_text = ""

    # Agentic loop: keep calling Claude until it returns a text response
    # without any pending tool_use blocks.
    MAX_ROUNDS = 6
    for _ in range(MAX_ROUNDS):
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Collect any tool_use blocks and text blocks
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        if not tool_use_blocks:
            # No tool calls — we're done
            final_text = " ".join(b.text for b in text_blocks)
            break

        # Append assistant message with all content blocks
        messages.append({
            "role": "assistant",
            "content": [
                {"type": b.type, **_block_to_dict(b)}
                for b in response.content
            ],
        })

        # Execute every tool call and build tool_result list
        tool_results = []
        for block in tool_use_blocks:
            tools_used.append(block.name)
            result_str = _execute_tool(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_str,
            })

        messages.append({"role": "user", "content": tool_results})

    else:
        raise HTTPException(
            status_code=500,
            detail="Max tool-call rounds exceeded without a final answer.",
        )

    return ChatResponse(reply=final_text, tool_calls_made=tools_used)


def _block_to_dict(block) -> dict:
    """Convert a content block object to a plain dict for the messages list."""
    if block.type == "text":
        return {"text": block.text}
    if block.type == "tool_use":
        return {"id": block.id, "name": block.name, "input": block.input}
    return {}


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Serve frontend index.html at root
# ---------------------------------------------------------------------------
@app.get("/")
async def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
