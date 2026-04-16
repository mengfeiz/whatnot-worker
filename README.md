# Whatnot Worker

Dual-mode Whatnot seller automation: **official Seller API (GraphQL)** + **Playwright browser fallback**.

Built for AI agents (OpenClaw, Hermes, etc.) to operate Whatnot seller accounts.

## Features

- 🤖 Official Seller API client (GraphQL) for inventory, orders, products
- 🌐 Playwright browser worker with stealth anti-detection for UI-only features
- 🍪 Cookie-based session persistence (survives restarts)
- 🔌 Simple HTTP API for agent control
- 🚂 One-click Railway deployment
- 📸 Auto-screenshot on errors for debugging
- 🛡️ Built-in stealth: webdriver override, custom UA, human-like delays

## Architecture

```
AI Agent → Whatnot Worker
              ├── Seller API (GraphQL) — preferred for inventory/orders
              └── Playwright + Chromium — fallback for shows, UI features
```

## Quick Start

### Option A: Seller API (preferred)

```bash
export WHATNOT_API_TOKEN="wn_access_tk_..."

# Test connection
python api_client.py test

# List products
python api_client.py products

# List orders
python api_client.py orders
```

### Option B: Playwright Browser Worker

```bash
# Deploy to Railway
npm i -g @railway/cli && railway login
railway init && railway up
railway variables set HEADLESS=true SLOW_MO_MS=100 PORT=8080

# Restore login session (Google Auth)
curl -X POST https://<worker>.up.railway.app/login/restore \
  -H "Content-Type: application/json" \
  -d '{"cookies": [...]}'
```

### Seller API Status

⚠️ The Whatnot Seller API is currently in **Developer Preview** — not accepting new applicants as of April 2026. Monitor: https://developers.whatnot.com

If you have access, see `docs/seller-api.md` for full reference.

## API Client Reference

```python
from api_client import WhatnotClient

client = WhatnotClient(token="wn_access_tk_...")

# Products
products = client.list_products(first=20)
product = client.get_product("product_id")
client.create_product(title="...", variants=[...])
client.update_inventory("variant_id", quantity=50)
client.update_product_price("variant_id", price_cents=1999)
client.delete_product("product_id")

# Orders
orders = client.list_orders(first=20)
order = client.get_order("order_id")
client.add_tracking("order_id", "1Z999...", carrier="UPS")

# Categories
categories = client.list_categories()

# Schema discovery
schema = client.introspect()
```

## Playwright Worker API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Worker + browser status |
| `/exec` | POST | Run a browser operation |
| `/login/start` | POST | Open Whatnot login page |
| `/login/restore` | POST | Restore session from cookies |
| `/navigate` | POST | Free-form navigation |
| `/screenshot/latest` | GET | Latest screenshot info |

### Browser Operations

```json
{"operation": "check_login"}
{"operation": "get_storefront", "params": {"username": "myshop"}}
{"operation": "get_listings"}
{"operation": "get_scheduled_shows"}
{"operation": "screenshot", "params": {"label": "debug"}}
```

## Adding Operations

### Seller API
Add GraphQL queries/mutations in `api_client.py`.

### Playwright
1. Add `async def op_<name>(page, ...) -> dict` in `server.py`
2. Register in `OPERATIONS` dict
3. Redeploy

## Local Development

```bash
pip install -r requirements.txt
playwright install chromium

# API client
export WHATNOT_API_TOKEN="wn_access_tk_..."
python api_client.py test

# Browser worker
python server.py
```

## Cost

- **Seller API**: free, usage-based rate limit (10 req/sec)
- **Playwright worker**: Railway medium plan (~$5/mo)

## License

MIT
