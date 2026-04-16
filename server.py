"""
Whatnot Worker - Playwright-based browser automation for Whatnot operations.

API server that receives commands from OpenClaw agent and executes them
via headless Chromium with anti-detection measures.
"""

import asyncio
import json
import os
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
STATE_DIR = Path(os.getenv("BROWSER_STATE_DIR", "/data/browser-state"))
STATE_FILE = STATE_DIR / "whatnot_state.json"
PORT = int(os.getenv("PORT", "8080"))
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
SLOW_MO = int(os.getenv("SLOW_MO_MS", "80"))

_browser: Browser | None = None
_context: BrowserContext | None = None


# ---------------------------------------------------------------------------
# Browser lifecycle
# ---------------------------------------------------------------------------
async def ensure_browser() -> BrowserContext:
    global _browser, _context
    if _context and _context.pages:
        return _context
    if _context:
        try:
            if _context.pages:
                return _context
        except Exception:
            pass

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

    await _context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    """)

    if STATE_FILE.exists():
        try:
            cookies = json.loads(STATE_FILE.read_text())
            await _context.add_cookies(cookies)
            print(f"[worker] Restored {len(cookies)} cookies from state file")
        except Exception as e:
            print(f"[worker] Failed to restore cookies: {e}")

    return _context


async def save_state():
    if _context:
        try:
            cookies = await _context.cookies()
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(cookies, indent=2))
            print(f"[worker] Saved {len(cookies)} cookies")
        except Exception as e:
            print(f"[worker] Failed to save state: {e}")


async def get_page() -> Page:
    ctx = await ensure_browser()
    if ctx.pages:
        return ctx.pages[0]
    return await ctx.new_page()


# ---------------------------------------------------------------------------
# Whatnot operations
# ---------------------------------------------------------------------------
async def op_check_login(page: Page) -> dict:
    await page.goto("https://www.whatnot.com", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    if "/login" in page.url:
        return {"logged_in": False, "url": page.url}

    content = await page.content()
    if "Sign in" in content and "Sell" not in content:
        return {"logged_in": False, "url": page.url}

    try:
        await page.wait_for_selector('[data-testid="user-menu"], [aria-label="Profile"], [data-testid="nav-profile"]', timeout=5000)
        return {"logged_in": True, "url": page.url}
    except Exception:
        # Check for seller indicators
        if "Seller Hub" in content or "seller" in page.url or "Sell" in content:
            return {"logged_in": True, "url": page.url, "confidence": "medium"}
        return {"logged_in": "uncertain", "url": page.url}


async def op_get_storefront(page: Page, username: str | None = None) -> dict:
    url = f"https://www.whatnot.com/user/{username}" if username else "https://www.whatnot.com"
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)
    title = await page.title()
    return {"url": page.url, "title": title, "status": "loaded"}


async def op_get_listings(page: Page) -> dict:
    await page.goto("https://www.whatnot.com/sell", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)
    if "/login" in page.url:
        return {"error": "Not logged in", "url": page.url}
    title = await page.title()
    return {"url": page.url, "title": title, "status": "loaded"}


async def op_get_scheduled_shows(page: Page) -> dict:
    await page.goto("https://www.whatnot.com/sell", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)
    if "/login" in page.url:
        return {"error": "Not logged in", "url": page.url}
    return {"url": page.url, "status": "loaded"}


async def op_screenshot(page: Page, label: str = "default") -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = STATE_DIR / f"screenshot_{label}_{ts}.png"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(path), full_page=True)
    return {"screenshot": str(path), "size_bytes": path.stat().st_size}


async def op_get_page_content(page: Page, url: str, wait_seconds: int = 3) -> dict:
    """Fetch any page and return its text content for analysis."""
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(wait_seconds * 1000)
    title = await page.title()
    # Get visible text
    text = await page.evaluate("""() => {
        const body = document.body;
        if (!body) return '';
        return body.innerText.substring(0, 5000);
    }""")
    return {"url": page.url, "title": title, "content_preview": text[:3000]}


OPERATIONS = {
    "check_login": op_check_login,
    "get_storefront": op_get_storefront,
    "get_listings": op_get_listings,
    "get_scheduled_shows": op_get_scheduled_shows,
    "screenshot": op_screenshot,
    "get_page_content": op_get_page_content,
}


# ---------------------------------------------------------------------------
# API models
# ---------------------------------------------------------------------------
class Command(BaseModel):
    operation: str
    params: dict[str, Any] = {}


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


app = FastAPI(title="Whatnot Worker", version="0.2.0", lifespan=lifespan)


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
        try:
            await op_screenshot(page, label=f"error_{cmd.operation}")
        except Exception:
            pass
        return {"ok": False, "operation": cmd.operation, "error": str(e), "traceback": traceback.format_exc()}


@app.post("/login/restore")
async def login_restore(request: dict):
    """
    Restore login session from exported cookies.
    Accepts two formats:
      - Direct array: [{"name":"...", "value":"...", ...}]
      - Wrapped: {"cookies": [...]}
    Also accepts Cookie-Editor export format (with domain, hostOnly, etc.)
    """
    # Support both formats
    if isinstance(request, list):
        cookies_raw = request
    elif isinstance(request, dict) and "cookies" in request:
        cookies_raw = request["cookies"]
    else:
        raise HTTPException(400, "Provide cookies as JSON array or {'cookies': [...]}")

    if not cookies_raw:
        raise HTTPException(400, "Empty cookies array")

    # Convert Cookie-Editor format to Playwright format
    cookies_pw = []
    for c in cookies_raw:
        pw_cookie: dict[str, Any] = {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "path": c.get("path", "/"),
        }

        # Domain handling: Cookie-Editor uses "domain" with or without leading dot
        domain = c.get("domain", "")
        if domain.startswith("."):
            pw_cookie["domain"] = domain
        else:
            pw_cookie["domain"] = domain

        # Secure
        pw_cookie["secure"] = c.get("secure", True)

        # SameSite
        same_site = c.get("sameSite", "Lax")
        if isinstance(same_site, str):
            ss = same_site.capitalize()
            if ss == "No_restriction":
                ss = "None"
            elif ss == "Strict":
                ss = "Strict"
            else:
                ss = "Lax"
            pw_cookie["sameSite"] = ss

        # Expires
        if c.get("expirationDate"):
            pw_cookie["expires"] = c["expirationDate"]
        elif c.get("expires"):
            pw_cookie["expires"] = c["expires"]

        # HttpOnly
        if c.get("httpOnly"):
            pw_cookie["httpOnly"] = True

        cookies_pw.append(pw_cookie)

    ctx = await ensure_browser()
    try:
        await ctx.add_cookies(cookies_pw)
    except Exception as e:
        raise HTTPException(400, f"Failed to set cookies: {e}")

    # Verify login
    page = await get_page()
    result = await op_check_login(page)
    await save_state()

    return {
        "ok": True,
        "cookies_restored": len(cookies_pw),
        "login_check": result,
    }


@app.post("/login/start")
async def login_start():
    page = await get_page()
    await page.goto("https://www.whatnot.com/login", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)
    try:
        google_btn = page.locator('button:has-text("Google"), [data-testid="google-login"]')
        if await google_btn.count() > 0:
            await google_btn.first.click()
            await page.wait_for_timeout(3000)
            return {"ok": True, "status": "google_auth_page_opened", "url": page.url}
    except Exception:
        pass
    return {"ok": True, "status": "login_page_loaded", "url": page.url}


@app.get("/screenshot/latest")
async def screenshot_latest():
    screenshots = sorted(STATE_DIR.glob("screenshot_*.png"), reverse=True)
    if not screenshots:
        return {"ok": False, "error": "No screenshots found"}
    s = screenshots[0]
    return {"ok": True, "path": str(s), "size": s.stat().st_size}


@app.post("/navigate")
async def navigate(url: str, wait_seconds: int = 3):
    page = await get_page()
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(wait_seconds * 1000)
    title = await page.title()
    return {"ok": True, "url": page.url, "title": title}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
