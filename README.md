# Whatnot Worker

Railway-hosted headless Chromium worker for Whatnot seller account automation. Built with Playwright + FastAPI, designed to be controlled by AI agents (OpenClaw, Hermes, etc.).

## Features

- 🤖 Headless Chromium with stealth anti-detection
- 🍪 Cookie-based session persistence (survives restarts)
- 🔌 Simple HTTP API for agent control
- 🚂 One-click Railway deployment
- 📸 Auto-screenshot on errors for debugging
- 🛡️ Built-in stealth: webdriver override, custom UA, human-like delays

## Architecture

```
AI Agent → HTTP POST → Railway (Playwright + Chromium) → Whatnot
```

## Quick Start

### Deploy to Railway

```bash
# Install Railway CLI
npm i -g @railway/cli
railway login

# Deploy
railway init
railway up

# Set environment variables
railway variables set HEADLESS=true
railway variables set SLOW_MO_MS=100
railway variables set PORT=8080
```

### Login (Google Auth)

Whatnot uses Google OAuth, so you need to restore your session once:

1. Log into Whatnot in your browser
2. Export cookies (DevTools → Application → Cookies → whatnot.com)
3. POST to worker:

```bash
curl -X POST https://<worker>.up.railway.app/login/restore \
  -H "Content-Type: application/json" \
  -d '{"cookies": [...]}'
```

Session persists across restarts automatically.

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Worker + browser status |
| `/exec` | POST | Run a Whatnot operation |
| `/login/start` | POST | Open login page |
| `/login/restore` | POST | Restore session from cookies |
| `/navigate` | POST | Free-form navigation |
| `/screenshot/latest` | GET | Latest screenshot info |

### Operations

```json
{"operation": "check_login", "params": {}}
{"operation": "get_storefront", "params": {"username": "myshop"}}
{"operation": "get_listings", "params": {}}
{"operation": "get_scheduled_shows", "params": {}}
{"operation": "screenshot", "params": {"label": "debug"}}
```

## Adding New Operations

1. Add `async def op_<name>(page: Page, ...) -> dict` in `scripts/server.py`
2. Register in `OPERATIONS` dict
3. Redeploy

## Local Development

```bash
cd scripts/
pip install -r requirements.txt
playwright install chromium
python server.py
```

## Cost

Railway medium plan (~$5/mo) is sufficient. Worker only consumes resources when called.

## License

MIT
