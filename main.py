"""Job Application Assistant — FastAPI backend."""
import asyncio
import os
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database
from company_tiers import get_company_tier
from demo_data import DEMO_JOBS
from matcher import generate_greeting, generate_search_keywords, match_jobs
from resume_parser import parse_docx
from scrapers.boss import BossZhipinScraper
from scrapers.shixiseng import ShixisengScraper

RESUME_DIR = Path("data/resumes")

app = FastAPI(title="求职助手")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

_tasks: Dict[str, Dict] = {}
_sxs_login_scraper: Optional[ShixisengScraper] = None
# Boss scraper kept alive after login — session cookies are fingerprint-bound
_boss_scraper: Optional[BossZhipinScraper] = None
# Demo mode: skip real scraping / real apply
_demo_mode: bool = False


# ── startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    await database.init_db()

    for env_key, db_key in [
        ("OPENROUTER_API_KEY", "openrouter_api_key"),
        ("OPENROUTER_MODEL", "openrouter_model"),
    ]:
        if not os.environ.get(env_key):
            val = await database.get_setting(db_key)
            if val:
                os.environ[env_key] = val

    if not await database.get_resume_text():
        docx_files = sorted(RESUME_DIR.glob("*.docx"))
        if docx_files:
            newest = docx_files[-1]
            text = parse_docx(newest)
            await database.save_resume_text(text)
            await database.save_resume_filename(newest.name)

    if Path("data/cookies/boss.json").exists():
        asyncio.create_task(_auto_init_boss())


# ── root ───────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ── pydantic models ────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    keyword: str = ""
    keywords: List[str] = []   # AI-expanded keyword list; overrides keyword when non-empty
    city: str = "101010100"
    cities: List[str] = []
    platforms: List[str] = ["boss", "shixiseng"]
    resume: str = ""
    preferences: str = ""
    max_pages: int = 2
    top_n: int = 30
    boss_active_today: bool = False


class KeywordsRequest(BaseModel):
    preferences: str


class ApplyRequest(BaseModel):
    job_ids: List[int]
    resume: str
    preferences: str = ""
    custom_message: Optional[str] = None


class StatusUpdateRequest(BaseModel):
    status: str


class PreferencesRequest(BaseModel):
    preferences: str


class SettingsRequest(BaseModel):
    openrouter_api_key: Optional[str] = None
    openrouter_model: Optional[str] = None
    shixiseng_phone: Optional[str] = None
    shixiseng_password: Optional[str] = None


class SmsCodeRequest(BaseModel):
    phone: str


class SmsVerifyRequest(BaseModel):
    code: str


class GreetingSettingsRequest(BaseModel):
    mode: Optional[str] = None          # "ai" | "fixed"
    template: Optional[str] = None


class DemoModeRequest(BaseModel):
    enabled: bool


# ── resume ─────────────────────────────────────────────────────────────────────

@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "只支持 .docx 格式")
    dest = RESUME_DIR / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    text = parse_docx(dest)
    await database.save_resume_text(text)
    await database.save_resume_filename(file.filename)
    return {"filename": file.filename, "char_count": len(text), "preview": text[:300]}


@app.get("/api/resume")
async def get_resume():
    return {
        "filename": await database.get_resume_filename(),
        "text": await database.get_resume_text(),
    }


# ── preferences ────────────────────────────────────────────────────────────────

@app.get("/api/preferences")
async def get_preferences():
    return {"preferences": await database.get_preferences()}


@app.post("/api/preferences")
async def save_preferences(req: PreferencesRequest):
    await database.save_preferences(req.preferences)
    return {"ok": True}


# ── keyword generation ────────────────────────────────────────────────────────

@app.post("/api/generate-keywords")
async def api_generate_keywords(req: KeywordsRequest):
    kws = await generate_search_keywords(req.preferences)
    return {"keywords": kws}


# ── greeting settings ──────────────────────────────────────────────────────────

@app.get("/api/greeting-settings")
async def get_greeting_settings():
    mode     = await database.get_setting("greeting_mode")     or "fixed"
    template = await database.get_setting("greeting_template") or database.DEFAULT_GREETING_TEMPLATE
    return {"mode": mode, "template": template}


@app.post("/api/greeting-settings")
async def save_greeting_settings(req: GreetingSettingsRequest):
    if req.mode is not None:
        await database.save_setting("greeting_mode", req.mode)
    if req.template is not None:
        await database.save_setting("greeting_template", req.template)
    return {"ok": True}


# ── demo mode ──────────────────────────────────────────────────────────────────

@app.get("/api/demo-mode")
async def get_demo_mode():
    return {"enabled": _demo_mode}


@app.post("/api/demo-mode")
async def set_demo_mode(req: DemoModeRequest):
    global _demo_mode
    _demo_mode = req.enabled
    return {"enabled": _demo_mode}


# ── search ─────────────────────────────────────────────────────────────────────

@app.post("/api/search")
async def search_jobs(req: SearchRequest, bg: BackgroundTasks):
    task_id = f"search_{int(time.time() * 1000)}"
    _tasks[task_id] = {"status": "running", "progress": 0, "message": "启动中..."}
    bg.add_task(_do_search, task_id, req)
    return {"task_id": task_id}


async def _do_search(task_id: str, req: SearchRequest):
    all_jobs: List[Dict] = []

    def prog(p: int, msg: str):
        _tasks[task_id].update({"progress": p, "message": msg})

    city_list = req.cities if req.cities else [req.city]
    # Keyword list: prefer multi-keyword list, fall back to single keyword
    kw_list = req.keywords if req.keywords else ([req.keyword] if req.keyword else ["实习"])

    try:
        # ── Demo mode: skip all scraping, load fixture data ────────────────────
        if _demo_mode:
            prog(20, "演示模式：加载本地示例数据...")
            await asyncio.sleep(0.8)
            for j in DEMO_JOBS:
                if j["platform"] in req.platforms:
                    all_jobs.append(dict(j))
            prog(50, f"加载了 {len(all_jobs)} 条示例职位")
            await asyncio.sleep(0.4)

        else:
            # ── Real scraping (iterate all keywords × cities) ──────────────────
            seen_ids: set = set()   # deduplicate across keyword searches

            def _add_unique(jobs: List[Dict]):
                for j in jobs:
                    key = (j.get("platform"), j.get("job_id"))
                    if key not in seen_ids:
                        seen_ids.add(key)
                        all_jobs.append(j)

            prog(5, "正在抓取 Boss直聘...")
            if "boss" in req.platforms:
                if _boss_scraper is None:
                    prog(30, "⚠️ Boss直聘：请先在设置中登录")
                else:
                    total_steps = len(kw_list) * len(city_list) * req.max_pages
                    step = 0
                    try:
                        for kw in kw_list:
                            for city in city_list:
                                for pg in range(1, req.max_pages + 1):
                                    _add_unique(await _boss_scraper.search_jobs(kw, city, pg))
                                    step += 1
                                    prog(5 + 25 * step // max(total_steps, 1),
                                         f"Boss直聘 [{kw}] {city} 第{pg}页")
                    except RuntimeError as e:
                        prog(30, f"⚠️ Boss直聘：{e}")
                        print(f"[Boss] {e}")
                    except Exception as e:
                        print(f"[Boss] scrape error: {e}")
                        _add_unique(_mock_jobs("boss", kw_list[0]))

            prog(35, "正在抓取 实习僧...")
            if "shixiseng" in req.platforms:
                try:
                    s = ShixisengScraper()
                    await s.start(headless=True)
                    phone = await database.get_setting("shixiseng_phone") or ""
                    pwd   = await database.get_setting("shixiseng_password") or ""
                    if phone and pwd:
                        await s.login(phone, pwd)
                    total_steps = len(kw_list) * len(city_list) * req.max_pages
                    step = 0
                    for kw in kw_list:
                        for city in city_list:
                            for pg in range(1, req.max_pages + 1):
                                _add_unique(await s.search_jobs(kw, city=city, page_num=pg))
                                step += 1
                                prog(35 + 20 * step // max(total_steps, 1),
                                     f"实习僧 [{kw}] {city} 第{pg}页")
                    await s.close()
                except Exception as e:
                    print(f"[Shixiseng] {e}")
                    _add_unique(_mock_jobs("shixiseng", kw_list[0]))

            # Filter Boss jobs by activity if requested
            if req.boss_active_today:
                before = len(all_jobs)
                all_jobs = [
                    j for j in all_jobs
                    if j.get("platform") != "boss" or j.get("boss_activity") == "今日活跃"
                ]
                print(f"[Boss] active-today filter: {before} → {len(all_jobs)} jobs")

        # Tag each job with company tier
        for j in all_jobs:
            j["company_tier"] = get_company_tier(j.get("company", ""))

        prog(60, "保存职位数据...")
        await database.save_jobs(all_jobs, is_demo=_demo_mode)

        prog(65, "AI 匹配分析中（约1-2分钟）...")
        preferences = req.preferences or await database.get_preferences()
        matched = await match_jobs(req.resume, all_jobs[: req.top_n], preferences)

        all_db  = await database.get_all_jobs(is_demo=_demo_mode)
        id_map  = {(j["platform"], j["job_id"]): j["id"] for j in all_db}
        for mj in matched:
            db_id = id_map.get((mj.get("platform"), mj.get("job_id")))
            if db_id:
                await database.update_job_match(
                    db_id,
                    mj.get("match_score", 0),
                    mj.get("match_reason", ""),
                    mj.get("match_highlights", []),
                    mj.get("match_concerns", []),
                )

        _tasks[task_id] = {
            "status": "completed",
            "progress": 100,
            "message": f"完成！匹配了 {len(matched)} 个岗位",
            "count": len(matched),
        }

    except Exception as e:
        _tasks[task_id] = {"status": "error", "progress": 0, "message": str(e)}


# ── task poll ──────────────────────────────────────────────────────────────────

@app.get("/api/task/{task_id}")
async def get_task(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(404, "Task not found")
    return _tasks[task_id]


# ── jobs ───────────────────────────────────────────────────────────────────────

@app.get("/api/jobs")
async def get_jobs(demo: int = Query(0)):
    return await database.get_all_jobs(is_demo=bool(demo))


@app.get("/api/stats")
async def get_stats(demo: int = Query(0)):
    jobs = await database.get_all_jobs(is_demo=bool(demo))
    return {s: sum(1 for j in jobs if (j["status"] or "pending") == s)
            for s in database.STATUSES}


@app.put("/api/jobs/{job_id}/status")
async def set_status(job_id: int, req: StatusUpdateRequest):
    await database.update_job_status(job_id, req.status)
    label_map = {
        "applied":     "已投递（自动投递）",
        "reviewing":   "简历筛选中",
        "testing":     "笔试/测评阶段",
        "interviewing":"进入面试",
        "offered":     "收到 Offer 🎉",
        "rejected":    "结果：未通过",
    }
    if req.status in label_map:
        await database.append_timeline(job_id, label_map[req.status])
    return {"ok": True}


class TimelineRequest(BaseModel):
    entry: str


@app.post("/api/jobs/{job_id}/timeline")
async def add_timeline(job_id: int, req: TimelineRequest):
    line = await database.append_timeline(job_id, req.entry)
    return {"ok": True, "line": line}


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int):
    await database.delete_job(job_id)
    return {"ok": True}


class GreetingPreviewRequest(BaseModel):
    resume: str = ""
    preferences: str = ""


@app.post("/api/jobs/{job_id}/preview-greeting")
async def preview_greeting(job_id: int, req: GreetingPreviewRequest):
    jobs = await database.get_all_jobs()
    job  = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        raise HTTPException(404, "Job not found")
    resume  = req.resume or await database.get_resume_text() or ""
    pref    = req.preferences or await database.get_preferences() or ""
    greeting = await generate_greeting(resume, job, pref)
    return {"greeting": greeting}


# ── apply ──────────────────────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/apply")
async def apply_one(job_id: int, req: ApplyRequest, bg: BackgroundTasks):
    jobs = await database.get_all_jobs()
    job  = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        raise HTTPException(404, "Job not found")
    task_id = f"apply_{job_id}_{int(time.time() * 1000)}"
    _tasks[task_id] = {"status": "running", "message": "投递中..."}
    preferences = req.preferences or await database.get_preferences()
    bg.add_task(_do_apply, task_id, job, req.resume, req.custom_message, preferences)
    return {"task_id": task_id}


@app.post("/api/apply-batch")
async def apply_batch(req: ApplyRequest, bg: BackgroundTasks):
    task_id = f"batch_{int(time.time() * 1000)}"
    _tasks[task_id] = {"status": "running", "progress": 0, "message": "批量投递中..."}
    preferences = req.preferences or await database.get_preferences()
    bg.add_task(_do_batch_apply, task_id, req, preferences)
    return {"task_id": task_id}


async def _do_apply(
    task_id: str,
    job: Dict,
    resume: str,
    custom_msg: Optional[str],
    preferences: str,
):
    try:
        # ── Demo mode: fake success ─────────────────────────────────────────────
        if _demo_mode:
            await asyncio.sleep(0.6)
            await database.update_job_status(job["id"], "applied")
            action = "（演示）Boss直聘打招呼" if job["platform"] == "boss" else "（演示）简历已投递"
            await database.append_timeline(job["id"], action)
            _tasks[task_id] = {"status": "completed", "message": "演示投递成功！"}
            return

        success = False
        if job["platform"] == "boss":
            if _boss_scraper is None:
                _tasks[task_id] = {"status": "error", "message": "请先在设置中登录 Boss直聘"}
                return
            greeting = custom_msg or await generate_greeting(resume, job, preferences)
            success = await _boss_scraper.send_greeting(job["url"], greeting)
        elif job["platform"] == "shixiseng":
            s = ShixisengScraper()
            await s.start(headless=False)
            success = await s.apply_job(job["url"])
            await s.close()

        if success:
            await database.update_job_status(job["id"], "applied")
            action = "Boss直聘打招呼已发送" if job["platform"] == "boss" else "实习僧简历已投递"
            await database.append_timeline(job["id"], action)
            _tasks[task_id] = {"status": "completed", "message": "投递成功！"}
        else:
            _tasks[task_id] = {"status": "error", "message": "投递失败，请确认已登录"}
    except Exception as e:
        _tasks[task_id] = {"status": "error", "message": str(e)}


async def _do_batch_apply(task_id: str, req: ApplyRequest, preferences: str):
    jobs    = await database.get_all_jobs()
    targets = [j for j in jobs if j["id"] in req.job_ids]
    results = []
    for i, job in enumerate(targets):
        sub_id = f"{task_id}_sub_{job['id']}"
        await _do_apply(sub_id, job, req.resume, req.custom_message, preferences)
        sub = _tasks.get(sub_id, {})
        results.append({"job_id": job["id"], "success": sub.get("status") == "completed"})
        _tasks[task_id].update(
            {"progress": int((i + 1) / len(targets) * 100), "message": f"已处理 {i+1}/{len(targets)}"}
        )

    success_n = sum(1 for r in results if r["success"])
    _tasks[task_id] = {
        "status": "completed",
        "progress": 100,
        "message": f"批量投递：{success_n}/{len(targets)} 成功",
        "results": results,
    }


# ── boss auto-init & login ─────────────────────────────────────────────────────

async def _auto_init_boss():
    global _boss_scraper
    try:
        s = BossZhipinScraper()
        await s.start(headless=False)
        await s.open_login_page()
        ok = await s.wait_for_login(timeout_ms=12_000)
        if ok:
            _boss_scraper = s
            print("[Boss] session auto-restored from saved cookies")
        else:
            await s.close()
            print("[Boss] auto-restore failed — user will need to login manually")
    except Exception as e:
        print(f"[Boss] auto-init error: {e}")


@app.get("/api/boss-status")
async def boss_status():
    return {"active": _boss_scraper is not None}


@app.post("/api/boss-login")
async def boss_login(bg: BackgroundTasks):
    task_id = f"boss_login_{int(time.time() * 1000)}"
    _tasks[task_id] = {"status": "running", "message": "正在打开浏览器，请稍候..."}
    bg.add_task(_do_boss_login, task_id)
    return {"task_id": task_id}


async def _do_boss_login(task_id: str):
    global _boss_scraper
    try:
        if _boss_scraper:
            await _boss_scraper.close()
        _boss_scraper = BossZhipinScraper()
        await _boss_scraper.start(headless=False)
        await _boss_scraper.open_login_page()
        _tasks[task_id] = {
            "status": "completed",
            "message": "浏览器已打开，请在浏览器中扫码登录，完成后回到此页点击\"我已完成登录\"",
        }
    except Exception as e:
        _tasks[task_id] = {"status": "error", "message": str(e)}
        _boss_scraper = None


@app.post("/api/boss-save-session")
async def boss_save_session():
    global _boss_scraper
    if not _boss_scraper:
        raise HTTPException(400, "没有活跃的登录浏览器，请先点击打开扫码窗口")
    try:
        page = _boss_scraper.page
        current_url = page.url if page else ""
        blocked = ("/web/user/" in current_url or "/web/passport/" in current_url
                   or "verify" in current_url or current_url in ("about:blank", ""))
        if blocked:
            raise HTTPException(400, "尚未完成登录验证，请在浏览器中完成所有步骤")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ── shixiseng SMS login ────────────────────────────────────────────────────────

@app.post("/api/shixiseng-send-code")
async def shixiseng_send_code(req: SmsCodeRequest, bg: BackgroundTasks):
    task_id = f"sxs_sms_{int(time.time() * 1000)}"
    _tasks[task_id] = {"status": "running", "message": "正在打开浏览器…"}
    bg.add_task(_do_shixiseng_send_code, task_id, req.phone)
    return {"task_id": task_id}


async def _do_shixiseng_send_code(task_id: str, phone: str):
    global _sxs_login_scraper
    try:
        if _sxs_login_scraper:
            await _sxs_login_scraper.close()
        _sxs_login_scraper = ShixisengScraper()
        await _sxs_login_scraper.start(headless=False)
        try:
            await _sxs_login_scraper.goto_login_and_send_sms(phone)
        except Exception as e:
            print(f"[Shixiseng] pre-fill warning: {e}")
        _tasks[task_id] = {"status": "completed", "message": "浏览器已打开，请在浏览器中完成登录"}
    except Exception as e:
        _tasks[task_id] = {"status": "error", "message": str(e)}
        _sxs_login_scraper = None


@app.post("/api/shixiseng-save-session")
async def shixiseng_save_session():
    global _sxs_login_scraper
    if not _sxs_login_scraper:
        raise HTTPException(400, "没有活跃的浏览器窗口，请先点击打开登录窗口")
    try:
        from scrapers.stealth import save_cookies
        await save_cookies(_sxs_login_scraper.context, "shixiseng")
        await _sxs_login_scraper.close()
        _sxs_login_scraper = None
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── settings ───────────────────────────────────────────────────────────────────

@app.post("/api/settings")
async def save_settings(req: SettingsRequest):
    if req.openrouter_api_key:
        await database.save_setting("openrouter_api_key", req.openrouter_api_key)
        os.environ["OPENROUTER_API_KEY"] = req.openrouter_api_key
    if req.openrouter_model:
        await database.save_setting("openrouter_model", req.openrouter_model)
        os.environ["OPENROUTER_MODEL"] = req.openrouter_model
    if req.shixiseng_phone:
        await database.save_setting("shixiseng_phone", req.shixiseng_phone)
    if req.shixiseng_password:
        await database.save_setting("shixiseng_password", req.shixiseng_password)
    return {"ok": True}


@app.get("/api/settings")
async def get_settings():
    model   = await database.get_setting("openrouter_model") or ""
    has_key = bool(await database.get_setting("openrouter_api_key"))
    phone   = await database.get_setting("shixiseng_phone") or ""
    return {"has_api_key": has_key, "model": model, "shixiseng_phone": phone}


# ── mock data ──────────────────────────────────────────────────────────────────

def _mock_jobs(platform: str, keyword: str) -> List[Dict]:
    base = [
        {"title": "数据运营实习生", "company": "字节跳动", "location": "北京-海淀区",
         "salary": "300-400元/天",
         "description": "负责抖音/西瓜视频数据分析，搭建运营数据看板，用数据驱动内容策略优化",
         "requirements": "SQL, Python/Excel, 数据分析基础, 有运营经验优先"},
        {"title": "策略运营实习生", "company": "腾讯", "location": "深圳-南山区",
         "salary": "280-380元/天",
         "description": "参与微信/视频号内容策略制定，通过数据分析优化用户增长路径",
         "requirements": "数据分析, 逻辑思维, Excel/Python, 有产品/运营实习经验"},
        {"title": "产品运营实习生", "company": "阿里巴巴", "location": "杭州-余杭区",
         "salary": "250-350元/天",
         "description": "参与淘宝/天猫频道运营，协助制定GMV增长策略，跟踪数据异动",
         "requirements": "Excel, SQL基础, 活跃用户思维, 电商行业了解"},
        {"title": "数据分析实习生", "company": "美团", "location": "北京-朝阳区",
         "salary": "280-360元/天",
         "description": "餐饮/零售数据分析，构建业务指标体系，输出洞察报告驱动业务决策",
         "requirements": "Python/R, SQL, 统计学基础, Tableau/PowerBI"},
    ]
    return [
        {
            "platform": platform,
            "job_id": f"mock_{platform}_{i}",
            "url": (
                f"https://www.zhipin.com/job_detail/mock_{i}.html"
                if platform == "boss"
                else f"https://www.shixiseng.com/intern/mock_{i}"
            ),
            **item,
        }
        for i, item in enumerate(base)
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
