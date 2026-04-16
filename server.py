"""
Whatnot Worker - Playwright-based browser automation for Whatnot operations.

API server that receives commands from OpenClaw agent and executes them
via headless Chromium with anti-detection measures.
"""

import asyncio
import json
import os
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
STATE_DIR = Path(os.getenv("BROWSER_STATE_DIR", "/data/browser-state"))
STATE_FILE = STATE_DIR / "whatnot_state.json"
PORT = int(os.getenv("PORT", "8080"))
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
SLOW_MO = int(os.getenv("SLOW_MO_MS", "80"))  # human-like delay between actions

# Shared browser context (persists across requests within lifetime)
_browser: Browser | None = None
_context: BrowserContext | None = None


# ---------------------------------------------------------------------------
# Browser lifecycle
# ---------------------------------------------------------------------------
async def ensure_browser() -> BrowserContext:
    global _browser, _context
    if _context and not _context.pages:
        # context exists but all pages closed — recreate
        pass
    elif _context:
        return _context

    pw = await async_playwright().start()
    _browser = await pw.chromium.launch(
        headless=HEADLESS,
        slow_mo=SLOW_MO,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1920,1080",
        ],
    )
    _context = await _browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/New_York",
    )

    # Inject stealth scripts
    await _context.add_init_script("""
        // Override navigator.webdriver
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        // Override chrome runtime
        window.chrome = { runtime: {} };
        // Override plugins
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        // Override languages
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    """)

    # Restore saved state if exists
    if STATE_FILE.exists():
        await _context.add_cookies(json.loads(STATE_FILE.read_text()))
        print(f"[worker] Restored {len(json.loads(STATE_FILE.read_text()))} cookies")

    return _context


async def save_state():
    if _context:
        cookies = await _context.cookies()
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(cookies, indent=2))
        print(f"[worker] Saved {len(cookies)} cookies")


async def get_page() -> Page:
    ctx = await ensure_browser()
    if ctx.pages:
        return ctx.pages[0]
    return await ctx.new_page()


# ---------------------------------------------------------------------------
# Whatnot operations
# ---------------------------------------------------------------------------
async def op_check_login(page: Page) -> dict:
    """Check if currently logged into Whatnot."""
    await page.goto("https://www.whatnot.com", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)

    # Check for login indicator
    content = await page.content()
    if '/login' in page.url or 'Sign in' in content:
        return {"logged_in": False, "url": page.url}

    # Try to find user menu / profile indicator
    try:
        await page.wait_for_selector('[data-testid="user-menu"], [aria-label="Profile"]', timeout=5000)
        return {"logged_in": True, "url": page.url}
    except Exception:
        # Might be logged in but different UI
        return {"logged_in": "uncertain", "url": page.url}


async def op_get_storefront(page: Page, username: str | None = None) -> dict:
    """Scrape public storefront page."""
    url = f"https://www.whatnot.com/user/{username}" if username else "https://www.whatnot.com"
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)

    title = await page.title()
    return {
        "url": page.url,
        "title": title,
        "status": "loaded",
    }


async def op_get_listings(page: Page) -> dict:
    """Get current listings from seller dashboard (requires login)."""
    await page.goto("https://www.whatnot.com/sell", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    if "/login" in page.url:
        return {"error": "Not logged in", "url": page.url}

    title = await page.title()
    return {
        "url": page.url,
        "title": title,
        "status": "loaded",
        "note": "Full listing parse TBD — inspect page structure first",
    }


async def op_get_scheduled_shows(page: Page) -> dict:
    """Check scheduled live shows (requires login)."""
    await page.goto("https://www.whatnot.com/sell", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)

    if "/login" in page.url:
        return {"error": "Not logged in", "url": page.url}

    return {
        "url": page.url,
        "status": "loaded",
        "note": "Show schedule parse TBD — inspect page structure first",
    }


async def op_screenshot(page: Page, label: str = "default") -> dict:
    """Take a screenshot for debugging / inspection."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = STATE_DIR / f"screenshot_{label}_{ts}.png"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(path), full_page=True)
    return {"screenshot": str(path), "size_bytes": path.stat().st_size}


# ---------------------------------------------------------------------------
# Operation registry
# ---------------------------------------------------------------------------
OPERATIONS = {
    "check_login": op_check_login,
    "get_storefront": op_get_storefront,
    "get_listings": op_get_listings,
    "get_scheduled_shows": op_get_scheduled_shows,
    "screenshot": op_screenshot,
}


# ---------------------------------------------------------------------------
# API models
# ---------------------------------------------------------------------------
class Command(BaseModel):
    operation: str
    params: dict[str, Any] = {}


class LoginInitRequest(BaseModel):
    """Request to start an interactive login session."""
    callback_url: str | None = None  # URL to notify when login complete


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[worker] Starting up, initializing browser...")
    await ensure_browser()
    yield
    print("[worker] Shutting down, saving state...")
    await save_state()
    if _browser:
        await _browser.close()


app = FastAPI(title="Whatnot Worker", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "browser": _browser is not None,
        "context": _context is not None,
        "state_file": STATE_FILE.exists(),
        "operations": list(OPERATIONS.keys()),
    }


@app.post("/exec")
async def execute(cmd: Command):
    if cmd.operation not in OPERATIONS:
        raise HTTPException(400, f"Unknown operation: {cmd.operation}. Available: {list(OPERATIONS.keys())}")

    page = await get_page()
    op = OPERATIONS[cmd.operation]

    try:
        result = await op(page, **cmd.params)
        await save_state()
        return {"ok": True, "operation": cmd.operation, "result": result, "ts": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        # Take screenshot on failure for debugging
        try:
            await op_screenshot(page, label=f"error_{cmd.operation}")
        except Exception:
            pass
        return {"ok": False, "operation": cmd.operation, "error": str(e), "traceback": traceback.format_exc()}


@app.post("/login/start")
async def login_start():
    """
    Open Whatnot login page for interactive Google OAuth.
    In headless mode, this won't work interactively — use /login/restore instead.
    """
    page = await get_page()
    await page.goto("https://www.whatnot.com/login", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)

    # Click "Continue with Google" if available
    try:
        google_btn = page.locator('button:has-text("Google"), [data-testid="google-login"]')
        if await google_btn.count() > 0:
            await google_btn.first.click()
            await page.wait_for_timeout(3000)
            return {"ok": True, "status": "google_auth_page_opened", "url": page.url}
    except Exception:
        pass

    return {"ok": True, "status": "login_page_loaded", "url": page.url}


@app.post("/login/restore")
async def login_restore(cookies: list[dict] | None = None):
    """
    Restore login session from exported cookies.
    Use browser DevTools → Application → Cookies → export JSON,
    then POST here.
    """
    if not cookies:
        raise HTTPException(400, "Provide cookies as JSON array")

    ctx = await ensure_browser()
    await ctx.add_cookies(cookies)

    # Verify
    page = await get_page()
    result = await op_check_login(page)
    await save_state()

    return {"ok": True, "login_check": result}


@app.get("/screenshot/latest")
async def screenshot_latest():
    """Return the most recent screenshot file info."""
    screenshots = sorted(STATE_DIR.glob("screenshot_*.png"), reverse=True)
    if not screenshots:
        return {"ok": False, "error": "No screenshots found"}
    s = screenshots[0]
    return {"ok": True, "path": str(s), "size": s.stat().st_size}


@app.post("/navigate")
async def navigate(url: str, wait_seconds: int = 3):
    """Free-form navigation for debugging."""
    page = await get_page()
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(wait_seconds * 1000)
    title = await page.title()
    return {"ok": True, "url": page.url, "title": title}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
