"""实习僧 Playwright automation."""
import asyncio
import re
from typing import Dict, List, Optional


def _decode_sxs_salary(raw: str) -> str:
    """实习僧 obfuscates salary digits with a custom icon font mapped to Unicode
    Private Use Area (U+E000–U+F8FF).  We can't reverse the mapping without the
    font file, so strip the PUA chars and keep any visible ASCII/CJK around them.
    e.g. '-/天' → '面议/天' → '面议/天'
    """
    # Remove all PUA codepoints
    cleaned = re.sub(r'[-]', '', raw).strip().strip('-').strip()
    if not cleaned or cleaned in ('/', '/天', '天'):
        return '面议'
    # If suffix like /天 remains, prepend 面议
    if cleaned.startswith('/'):
        return '面议' + cleaned
    return cleaned

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


class ShixisengScraper:
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
        self._has_saved_cookies = await load_cookies(self.context, "shixiseng")

        self.page = await self.context.new_page()

    async def _session_valid(self) -> bool:
        """Check whether saved cookies are still active."""
        try:
            await self.page.goto("https://www.shixiseng.com/", wait_until="domcontentloaded")
            await think_delay()
            user_el = await self.page.query_selector(".user-avatar, .nav-user, .login-user")
            return user_el is not None
        except Exception:
            return False

    async def login(self, phone: str, password: str) -> bool:
        """Password-based login (legacy). Tries saved cookies first."""
        if self._has_saved_cookies and await self._session_valid():
            print("[Shixiseng] session still valid, skipping login")
            self.logged_in = True
            return True

        await self._open_login_modal()

        try:
            phone_sel = 'input[placeholder*="手机"]'
            phone_inp = await self.page.query_selector(phone_sel)
            if phone_inp:
                await human_type(self.page, phone_sel, phone)
                await short_delay()

            pwd_sel = 'input[type="password"]'
            pwd_inp = await self.page.query_selector(pwd_sel)
            if pwd_inp:
                await human_type(self.page, pwd_sel, password)
                await short_delay()

            clicked = await human_click(self.page, '.login-btn, button:has-text("登录")')
            if clicked:
                await page_delay()

            self.logged_in = True
            await save_cookies(self.context, "shixiseng")
            return True
        except Exception as e:
            print(f"[Shixiseng] login error: {e}")
            return False

    async def _open_login_modal(self) -> bool:
        """
        实习僧 removed /login page; we click the top-right 登录/注册 link instead.
        Returns True once the login modal / page is visible.
        """
        await self.page.goto("https://www.shixiseng.com/", wait_until="domcontentloaded")
        await page_delay()
        for sel in [
            'a:has-text("登录/注册")',
            'a:has-text("登录")',
            '.login-btn',
            '.nav-login',
            '[href*="login"]',
        ]:
            el = await self.page.query_selector(sel)
            if el:
                await el.click()
                await page_delay()
                return True
        return False

    async def goto_login_and_send_sms(self, phone: str) -> bool:
        """Navigate to login and trigger SMS code delivery."""
        if self._has_saved_cookies and await self._session_valid():
            print("[Shixiseng] session still valid, SMS login skipped")
            self.logged_in = True
            return True

        # 实习僧 removed /login — open from homepage nav
        reached = await self._open_login_modal()
        if not reached:
            print("[Shixiseng] could not reach login page")
            return False

        try:
            # Switch to SMS / verification-code tab if one exists
            for tab_sel in [
                'li:has-text("验证码登录")',
                'span:has-text("验证码登录")',
                'a:has-text("验证码登录")',
                '.tab:has-text("验证码")',
                'div:has-text("验证码登录")',
            ]:
                el = await self.page.query_selector(tab_sel)
                if el:
                    await el.click()
                    await short_delay()
                    break

            # Enter phone number
            phone_sel = 'input[placeholder*="手机"], input[type="tel"], input[name="phone"]'
            phone_inp = await self.page.query_selector(phone_sel)
            if not phone_inp:
                print("[Shixiseng] phone input not found")
                return False
            await human_type(self.page, phone_sel, phone)
            await short_delay()

            # Click "发送验证码"
            for btn_sel in [
                'button:has-text("发送验证码")',
                'span:has-text("发送验证码")',
                'a:has-text("发送验证码")',
                '.send-code',
                '.get-code',
            ]:
                clicked = await human_click(self.page, btn_sel)
                if clicked:
                    await short_delay()
                    return True

            print("[Shixiseng] send-code button not found")
            return False
        except Exception as e:
            print(f"[Shixiseng] send SMS error: {e}")
            return False

    async def submit_sms_code(self, code: str) -> bool:
        """Enter the received SMS code and complete login."""
        try:
            code_sel = 'input[placeholder*="验证码"], input[name="code"], input[maxlength="6"]'
            code_inp = await self.page.query_selector(code_sel)
            if not code_inp:
                print("[Shixiseng] code input not found")
                return False

            await human_type(self.page, code_sel, code)
            await short_delay()

            clicked = await human_click(self.page, '.login-btn, button:has-text("登录"), button:has-text("确认")')
            if not clicked:
                return False

            await page_delay()
            # Verify we actually left the login page
            if "login" in self.page.url:
                return False

            self.logged_in = True
            await save_cookies(self.context, "shixiseng")
            return True
        except Exception as e:
            print(f"[Shixiseng] SMS code submit error: {e}")
            return False

    async def search_jobs(self, keyword: str, city: str = "", page_num: int = 1) -> List[Dict]:
        city_param = f"&city={city}" if city else ""
        url = f"https://www.shixiseng.com/interns?keyword={keyword}&page={page_num}{city_param}"
        await self.page.goto(url, wait_until="domcontentloaded")
        await page_delay()
        await human_scroll(self.page)
        await think_delay()

        jobs: List[Dict] = []
        try:
            cards = await self.page.query_selector_all(".intern-item, .intern-wrap, .position-item")

            for card in cards:
                try:
                    job: Dict = {"platform": "shixiseng"}

                    # Job title: first .title inside the job section
                    for sel, key in [
                        (".intern-detail__job .title, .intern-detail__job a.title", "title"),
                        (".intern-detail__company .title, .intern-detail__company a", "company"),
                        (".day, .money, .salary", "salary"),
                        (".city, .location", "location"),
                    ]:
                        el = await card.query_selector(sel)
                        raw = (await el.inner_text()).strip() if el else ""
                        # 实习僧 uses Unicode Private Use Area chars (U+E000–U+F8FF) for
                        # font-obfuscated numbers. Detect and replace with readable label.
                        if any('' <= ch <= '' for ch in raw):
                            raw = _decode_sxs_salary(raw)
                        job[key] = raw

                    tag_els = await card.query_selector_all(".tags span, .skill-tag, .tip span")
                    job["requirements"] = ", ".join(
                        [(await t.inner_text()).strip() for t in tag_els if (await t.inner_text()).strip() not in ("|", "/")]
                    )

                    link = await card.query_selector("a[href*='/intern/']")
                    if link:
                        href = await link.get_attribute("href") or ""
                        job["url"] = href if href.startswith("http") else f"https://www.shixiseng.com{href}"
                        m = re.search(r"/intern/(\w+)", href)
                        job["job_id"] = m.group(1) if m else ""

                    # Accept if we have at least a title (company can be blank occasionally)
                    if job.get("title"):
                        jobs.append(job)
                except Exception:
                    continue

            if page_num > 1:
                await between_pages_delay()

        except Exception as e:
            print(f"[Shixiseng] scrape error page={page_num}: {e}")

        return jobs

    async def apply_job(self, job_url: str) -> bool:
        """Submit resume to a job on 实习僧."""
        await self.page.goto(job_url, wait_until="domcontentloaded")
        await page_delay()
        await human_scroll(self.page, total_px=300)
        await think_delay()

        try:
            apply_sel = '.btn-apply, button:has-text("投递简历"), .apply-btn, button:has-text("立即投递")'
            btn = await self.page.query_selector(apply_sel)
            if not btn:
                return False

            clicked = await human_click(self.page, apply_sel)
            if not clicked:
                return False

            await page_delay()

            confirm_sel = 'button:has-text("确认投递"), button:has-text("确定"), .confirm-btn'
            confirm = await self.page.query_selector(confirm_sel)
            if confirm:
                await short_delay()
                await human_click(self.page, confirm_sel)
                await short_delay()

            return True
        except Exception as e:
            print(f"[Shixiseng] apply error: {e}")
            return False

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
