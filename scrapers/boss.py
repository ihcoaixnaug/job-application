"""Boss直聘 Playwright automation."""
import asyncio
import re
from pathlib import Path
from typing import Dict, List, Optional

try:
    from patchright.async_api import Browser, BrowserContext, Page, async_playwright
except ImportError:
    from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from scrapers.stealth import (
    between_pages_delay,
    human_click,
    human_scroll,
    human_type,
    load_cookies,
    page_delay,
    random_context_options,
    save_cookies,
    short_delay,
    think_delay,
)

BOSS_PROFILE_DIR = Path("data/chrome_profiles/boss")


class BossZhipinScraper:
    def __init__(self):
        self._playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.logged_in = False

    async def start(self, headless: bool = True):
        self._playwright = await async_playwright().start()
        launch_kwargs = dict(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-automation",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-component-update",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
            ],
            ignore_default_args=["--enable-automation"],
        )
        self.browser = await self._playwright.chromium.launch(**launch_kwargs)
        ctx_opts = random_context_options()
        self.context = await self.browser.new_context(**ctx_opts)

        # Restore saved session to avoid re-login every run
        self._has_saved_cookies = await load_cookies(self.context, "boss")

        self.page = await self.context.new_page()

    async def _check_logged_in(self) -> bool:
        """Verify saved cookies are still valid on the jobs search page."""
        try:
            await self.page.goto(
                "https://www.zhipin.com/web/geek/jobs?query=test&city=101010100",
                wait_until="domcontentloaded",
            )
            await asyncio.sleep(6)
            final_url = self.page.url
            if "geek/jobs" not in final_url:
                print(f"[Boss] session check: redirected to {final_url[:80]}")
                return False
            job_box = await self.page.query_selector(".job-list-box, .job-card-wrapper")
            return job_box is not None
        except Exception:
            return False

    async def open_login_page(self):
        """Navigate to the QR-code login page."""
        await self.page.goto("https://www.zhipin.com/web/user/?ka=header-login")

    async def wait_for_login(self, timeout_ms: int = 120_000) -> bool:
        """Block until Boss lands on a real page (post-login, post-verification)."""
        try:
            await self.page.wait_for_function(
                """() => {
                    const u = location.href;
                    return u.includes('zhipin.com')
                        && !u.includes('/web/user/')
                        && !u.includes('/web/passport/')
                        && !u.includes('verify')
                        && !u.includes('security')
                        && u !== 'about:blank';
                }""",
                timeout=timeout_ms,
            )
            self.logged_in = True
            await save_cookies(self.context, "boss")
            return True
        except Exception:
            return False

    async def _ensure_on_site(self):
        """Visit homepage first to warm up the session before searching."""
        if not getattr(self, "_warmed_up", False):
            await self.page.goto("https://www.zhipin.com/", wait_until="domcontentloaded")
            await page_delay()
            await human_scroll(self.page, total_px=300)
            await think_delay()
            self._warmed_up = True

    async def search_jobs(self, keyword: str, city: str = "101010100", page_num: int = 1) -> List[Dict]:
        await self._ensure_on_site()

        url = f"https://www.zhipin.com/web/geek/jobs?query={keyword}&city={city}&page={page_num}"
        await self.page.goto(url, wait_until="domcontentloaded")
        await page_delay()

        if "/web/user/" in self.page.url or "passport" in self.page.url or self.page.url == "about:blank":
            print(f"[Boss] session expired (redirected to {self.page.url[:60]})")
            raise RuntimeError("Boss session expired — please re-login via settings")

        jobs: List[Dict] = []
        try:
            await self.page.wait_for_selector(".job-card-wrap, .job-list-container", timeout=30_000)
            await human_scroll(self.page)
            await think_delay()

            cards = await self.page.query_selector_all(".job-card-wrap")

            for card in cards:
                try:
                    job: Dict = {"platform": "boss"}

                    for sel, key in [
                        ("a.job-name", "title"),
                        (".boss-name", "company"),
                        (".job-salary", "salary"),
                        (".company-location", "location"),
                    ]:
                        el = await card.query_selector(sel)
                        job[key] = (await el.inner_text()).strip() if el else ""

                    # HR activity status (今日活跃 / 3天内活跃 / 本周活跃 / …)
                    for act_sel in [".active-time", ".boss-active-time", ".job-status-wrapper .time"]:
                        act_el = await card.query_selector(act_sel)
                        if act_el:
                            job["boss_activity"] = (await act_el.inner_text()).strip()
                            break
                    else:
                        job["boss_activity"] = ""

                    tag_els = await card.query_selector_all(".tag-list li")
                    job["requirements"] = ", ".join(
                        [(await t.inner_text()).strip() for t in tag_els]
                    )

                    link = await card.query_selector("a.job-name")
                    if link:
                        href = await link.get_attribute("href") or ""
                        job["url"] = f"https://www.zhipin.com{href}" if href else ""
                        m = re.search(r"/job_detail/(\w+)\.html", href)
                        job["job_id"] = m.group(1) if m else ""

                    if job.get("title") and job.get("company"):
                        jobs.append(job)
                except Exception:
                    continue

            if page_num > 1:
                await between_pages_delay()

        except Exception as e:
            print(f"[Boss] scrape error page={page_num}: {e}")

        return jobs

    async def get_job_detail(self, job_url: str) -> str:
        await self.page.goto(job_url, wait_until="domcontentloaded")
        await page_delay()
        await human_scroll(self.page, total_px=400)
        try:
            el = await self.page.query_selector(".job-detail-section")
            return (await el.inner_text()).strip() if el else ""
        except Exception:
            return ""

    async def send_greeting(self, job_url: str, message: Optional[str] = None) -> bool:
        await self.page.goto(job_url, wait_until="domcontentloaded")
        await page_delay()
        await think_delay()

        try:
            clicked = await human_click(self.page, ".btn-startchat")
            if not clicked:
                clicked = await human_click(self.page, 'a:has-text("立即沟通")')
            if not clicked:
                return False

            await page_delay()

            if message:
                inp_sel = ".chat-input textarea, .editor-input"
                inp = await self.page.query_selector(inp_sel)
                if inp:
                    await human_type(self.page, inp_sel, message)
                    await short_delay()
                    send = await self.page.query_selector('.send-btn, button:has-text("发送")')
                    if send:
                        await short_delay()
                        await send.click()
                        await short_delay()

            return True
        except Exception as e:
            print(f"[Boss] greeting error: {e}")
            return False

    async def send_resume_to_hr(self) -> bool:
        try:
            btn = await self.page.query_selector('button:has-text("发送简历"), .send-resume-btn')
            if btn:
                await short_delay()
                await btn.click()
                await short_delay()
                confirm = await self.page.query_selector('button:has-text("确认发送"), button:has-text("发送")')
                if confirm:
                    await confirm.click()
                    await short_delay()
                return True
        except Exception as e:
            print(f"[Boss] send resume error: {e}")
        return False

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
