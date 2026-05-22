# AI-Powered Supply Chain Inventory Assistant

A conversational chatbot that lets analysts query 180,000+ supply chain records in plain English. Every answer is grounded in live database queries — the AI never invents numbers.

---

## Architecture

```
User (browser)
    │  HTTP POST /chat
    ▼
FastAPI  (backend/main.py)
    │  claude-sonnet-4 + tool calling
    ▼
Claude API
    │  calls one of 9 Python tool functions
    ▼
query_functions.py
    │  SQL queries
    ▼
SQLite  (supply_chain.db ← DataCo CSV)
```

---

## Quick Start

### 1. Clone & install dependencies

```bash
git clone <your-repo-url>
cd supply_chain_chatbot
pip install -r requirements.txt
```

### 2. Set your Anthropic API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Load the dataset

Copy your **DataCoSupplyChainDataset.csv** (from your Desktop) into the project root, then run:

```bash
python -m backend.database --csv DataCoSupplyChainDataset.csv
```

This creates `backend/supply_chain.db` with 180,000+ records and all indexes. Takes ~30 seconds.

### 4. Run the server

```bash
uvicorn backend.main:app --reload
```

### 5. Open the chat UI

Navigate to [http://localhost:8000](http://localhost:8000)

---

## Project Structure

```
supply_chain_chatbot/
├── backend/
│   ├── __init__.py
│   ├── database.py          # CSV → SQLite loader (run once)
│   ├── query_functions.py   # 9 typed Python query functions
│   └── main.py              # FastAPI app + Claude tool-calling loop
├── frontend/
│   └── index.html           # Chat UI (HTML/CSS/JS, no framework)
├── tests/
│   ├── __init__.py
│   └── test_query_functions.py  # pytest unit tests (40+ tests)
├── requirements.txt
└── README.md
```

---

## Available Tools (Claude's toolkit)

| Tool | Description |
|---|---|
| `get_summary_stats` | Dataset-wide KPIs: total orders, profit, late-delivery % |
| `get_low_stock_items` | Products with low order quantities (reorder alerts) |
| `get_late_delivery_risk` | Orders flagged for late delivery, optional region filter |
| `get_profitability` | Profit & sales grouped by category / region / market / etc. |
| `get_loss_making_orders` | Orders with negative profit |
| `get_order_volumes` | Order counts & sales by any dimension |
| `get_top_products` | Rank products by sales, profit, quantity, or orders |
| `get_shipping_performance` | Real vs scheduled shipping days, late rates by mode |
| `search_orders` | Free-text search by product or category name |

---

## Example Questions

- *"Give me a KPI snapshot of the whole dataset"*
- *"Which products are at risk of running out of stock?"*
- *"Show me the most delayed orders in Western Europe"*
- *"Which product categories have the worst profit margins?"*
- *"How many orders are losing us money?"*
- *"Compare shipping modes — which is fastest and most reliable?"*
- *"Top 10 products by revenue in the Footwear category"*
- *"Break down order volumes by market region"*

---

## Running Tests

Make sure the database is loaded first, then:

```bash
pytest tests/ -v
```

The test suite covers all 9 query functions with 40+ test cases including:
- Expected outputs and key assertions
- Edge cases (empty results, invalid filters)
- Boundary conditions (threshold values, limits)
- Parametrised dimension variants

If the database hasn't been loaded yet, tests are automatically skipped with an informative message.

---

## Design Principles

1. **Grounded responses** — Claude never generates figures from memory. Every factual claim triggers a database tool call.
2. **Tool-first routing** — Claude reads precise tool descriptions and selects the right function based on the user's intent.
3. **Session context** — Full conversation history is sent with each request so Claude can answer follow-up questions.
4. **Agentic loop** — The backend runs up to 6 tool-calling rounds per message for multi-part questions.

---

## Limitations

- The dataset is static (DataCo sample). Not connected to a live ERP or WMS.
- "Stock levels" are inferred from order quantities, not actual warehouse counts.
- The chatbot is scoped to the DataCo dataset columns only.

---

## Success Criteria (from Project Brief)

- [x] Natural language querying of inventory data
- [x] Late delivery risk identification
- [x] Low-stock / reorder alerts
- [x] Profitability analysis
- [x] Regional and category breakdowns
- [x] Conversation history within a session
- [x] Unit tests for all query functions
- [x] Deployed end-to-end without errors

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI Model | Claude Sonnet 4 (claude-sonnet-4-20250514) |
| Backend | FastAPI + Python |
| Data loading | Pandas |
| Database | SQLite (sqlite3) |
| Frontend | HTML / CSS / Vanilla JS |
| Tests | pytest |
| Version control | Git / GitHub |
