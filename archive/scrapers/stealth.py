"""
Shared anti-detection utilities for Playwright scrapers.

Strategy:
  1. Comprehensive JS stealth patches  – remove all headless/automation signals
  2. Realistic UA + viewport pool      – vary per session
  3. Cookie persistence                – reuse login state across runs
  4. Human-like timing                 – random delays, natural scrolling, per-key typing
"""

import asyncio
import json
import random
from pathlib import Path
from typing import Optional

try:
    from patchright.async_api import BrowserContext, Page
except ImportError:
    from playwright.async_api import BrowserContext, Page

COOKIE_DIR = Path("data/cookies")

# ── realistic Chrome/macOS user-agents ────────────────────────────────────────
# Keep versions close together so fingerprints look consistent
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Common macOS display resolutions
VIEWPORTS = [
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 800},
    {"width": 1512, "height": 945},   # MacBook Pro 14"
    {"width": 1680, "height": 1050},
    {"width": 1920, "height": 1080},
]

# ── stealth JS ─────────────────────────────────────────────────────────────────
# Injected as init script into every new page before any scripts run.
STEALTH_JS = """
(() => {
  // 1. Hide webdriver flag
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

  // 2. Realistic plugin list
  const _plugins = [
    { name: 'PDF Viewer',    filename: 'internal-pdf-viewer',       description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: '' },
    { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: '' },
    { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: '' },
  ];
  Object.defineProperty(navigator, 'plugins', {
    get: () => Object.assign(_plugins, { item: i => _plugins[i], namedItem: n => _plugins.find(p=>p.name===n), refresh: ()=>{} }),
  });

  // 3. Language spoofing
  Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });

  // 4. Realistic hardware fingerprint
  Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
  Object.defineProperty(navigator, 'deviceMemory',        { get: () => 8 });
  Object.defineProperty(navigator, 'platform',            { get: () => 'MacIntel' });

  // 5. Chrome runtime (headless Chrome lacks this)
  if (!window.chrome) {
    window.chrome = {
      runtime: { id: undefined, connect: ()=>{}, sendMessage: ()=>{} },
      loadTimes: () => ({ requestTime: Date.now()/1000 }),
      csi: () => ({}),
      app: {},
    };
  }

  // 6. Fix permissions API (headless returns 'denied' for notifications)
  const _origQuery = window.navigator.permissions.query.bind(navigator.permissions);
  window.navigator.permissions.query = (params) =>
    params.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission, onchange: null })
      : _origQuery(params);

  // 7. Remove playwright-specific globals
  const _del = ['__playwright', '__pw_manual', '__playwright__binding__'];
  _del.forEach(k => { try { delete window[k]; } catch(e){} });

  // 8. Realistic screen / window dimensions
  // In headless mode outerWidth/Height are 0; derive from innerWidth instead
  const _sw = window.innerWidth  || screen.width  || 1280;
  const _sh = window.innerHeight || screen.height || 800;
  Object.defineProperty(window, 'outerWidth',   { get: () => _sw });
  Object.defineProperty(window, 'outerHeight',  { get: () => _sh + 88 });
  Object.defineProperty(screen,  'width',        { get: () => _sw });
  Object.defineProperty(screen,  'height',       { get: () => _sh + 88 });
  Object.defineProperty(screen,  'availWidth',   { get: () => _sw });
  Object.defineProperty(screen,  'availHeight',  { get: () => _sh + 88 - 23 });
  Object.defineProperty(screen,  'colorDepth',   { get: () => 24 });
  Object.defineProperty(screen,  'pixelDepth',   { get: () => 24 });
})();
"""

# ── timing helpers ─────────────────────────────────────────────────────────────

async def short_delay():
    """0.4 – 1.2 s  — between small UI actions."""
    await asyncio.sleep(random.uniform(0.4, 1.2))

async def page_delay():
    """1.5 – 4.0 s  — after navigation / before extraction."""
    await asyncio.sleep(random.uniform(1.5, 4.0))

async def between_pages_delay():
    """3.0 – 7.0 s  — between fetching consecutive pages (throttle)."""
    await asyncio.sleep(random.uniform(3.0, 7.0))

async def think_delay():
    """0.6 – 2.0 s  — simulates user 'reading' before acting."""
    await asyncio.sleep(random.uniform(0.6, 2.0))

# ── human-like interactions ────────────────────────────────────────────────────

async def human_scroll(page: Page, total_px: int = 0):
    """
    Scroll through the page in uneven steps, pausing occasionally.
    If total_px == 0, scroll to ~80 % of page height.
    """
    if total_px == 0:
        total_px = await page.evaluate("() => document.body.scrollHeight * 0.8")
        total_px = int(total_px)

    scrolled = 0
    while scrolled < total_px:
        step = random.randint(200, 500)
        await page.mouse.wheel(0, step)
        scrolled += step
        await asyncio.sleep(random.uniform(0.15, 0.5))
        # occasional longer pause (simulating reading)
        if random.random() < 0.2:
            await asyncio.sleep(random.uniform(0.5, 1.2))


async def human_type(page: Page, selector: str, text: str):
    """
    Click the field then type each character with a random inter-key delay.
    Mimics realistic typing speed (~4-8 chars/second).
    """
    await page.click(selector)
    await short_delay()
    for char in text:
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.08, 0.22))


async def human_click(page: Page, selector: str):
    """
    Move mouse near element with slight offset, pause, then click.
    """
    el = await page.query_selector(selector)
    if not el:
        return False
    box = await el.bounding_box()
    if not box:
        return False
    x = box["x"] + box["width"]  * random.uniform(0.25, 0.75)
    y = box["y"] + box["height"] * random.uniform(0.25, 0.75)
    await page.mouse.move(x + random.uniform(-5, 5), y + random.uniform(-5, 5),
                          steps=random.randint(8, 20))
    await asyncio.sleep(random.uniform(0.1, 0.35))
    await page.mouse.click(x, y)
    return True

# ── cookie persistence ─────────────────────────────────────────────────────────

async def save_cookies(context: BrowserContext, platform: str):
    """Persist all cookies for a platform to disk."""
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    cookies = await context.cookies()
    path = COOKIE_DIR / f"{platform}.json"
    path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))
    print(f"[stealth] saved {len(cookies)} cookies → {path}")


async def load_cookies(context: BrowserContext, platform: str) -> bool:
    """Restore saved cookies; return True if file existed."""
    path = COOKIE_DIR / f"{platform}.json"
    if not path.exists():
        return False
    try:
        cookies = json.loads(path.read_text())
        await context.add_cookies(cookies)
        print(f"[stealth] loaded {len(cookies)} cookies for {platform}")
        return True
    except Exception as e:
        print(f"[stealth] cookie load error: {e}")
        return False


def clear_cookies(platform: str):
    """Delete saved cookies (call when session is confirmed expired)."""
    path = COOKIE_DIR / f"{platform}.json"
    if path.exists():
        path.unlink()
        print(f"[stealth] cleared cookies for {platform}")

# ── context factory ────────────────────────────────────────────────────────────

def random_context_options() -> dict:
    """Return randomised context kwargs for new_context()."""
    ua = random.choice(USER_AGENTS)
    vp = random.choice(VIEWPORTS)
    return dict(
        user_agent=ua,
        viewport=vp,
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        # Realistic extra headers
        extra_http_headers={
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        },
    )
