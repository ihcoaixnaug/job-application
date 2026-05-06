"""SQLite database layer — jobs, settings, preferences."""
import aiosqlite
from datetime import datetime
from typing import Dict, List, Optional

DB_PATH = "data/jobs.db"
DEFAULT_PREFERENCES = "数据运营/策略运营/产品运营/行业运营/数据分析"
DEFAULT_GREETING_TEMPLATE = (
    "您好，我是南加州大学应用经济学与计量经济学（数据科学方向）学生，"
    "5月可到岗，能实习至8月底，对该岗位很感兴趣，"
    "方便的话我可以发简历供您参考。"
)

# Canonical status pipeline for automated applications
STATUSES = ["pending", "applied", "reviewing", "testing", "interviewing", "offered", "rejected"]


async def init_db():
    import os
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                platform      TEXT NOT NULL,
                job_id        TEXT,
                title         TEXT NOT NULL,
                company       TEXT NOT NULL,
                location      TEXT,
                salary        TEXT,
                description   TEXT,
                requirements  TEXT,
                url           TEXT,
                match_score   REAL DEFAULT 0,
                match_reason  TEXT,
                match_highlights TEXT,
                match_concerns   TEXT,
                status        TEXT DEFAULT 'pending',
                timeline_log  TEXT DEFAULT '',
                applied_at    TEXT,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(platform, job_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # Migrate: add columns introduced after initial schema
        for col, definition in [
            ("timeline_log",     "TEXT DEFAULT ''"),
            ("match_highlights", "TEXT"),
            ("match_concerns",   "TEXT"),
            ("boss_activity",    "TEXT DEFAULT ''"),
            ("company_tier",     "TEXT DEFAULT ''"),
            ("is_demo",          "INTEGER DEFAULT 0"),
        ]:
            try:
                await db.execute(f"ALTER TABLE jobs ADD COLUMN {col} {definition}")
            except Exception:
                pass  # column already exists

        # Seed defaults
        for key, value in [
            ("job_preferences",    DEFAULT_PREFERENCES),
            ("greeting_mode",      "fixed"),
            ("greeting_template",  DEFAULT_GREETING_TEMPLATE),
        ]:
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        await db.commit()


# ── jobs ──────────────────────────────────────────────────────────────────────

async def save_jobs(jobs: List[Dict], is_demo: bool = False) -> int:
    flag = 1 if is_demo else 0
    async with aiosqlite.connect(DB_PATH) as db:
        count = 0
        for job in jobs:
            try:
                await db.execute("""
                    INSERT OR IGNORE INTO jobs
                        (platform, job_id, title, company, location, salary,
                         description, requirements, url, boss_activity, company_tier, is_demo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job.get("platform"), job.get("job_id"), job.get("title"),
                    job.get("company"), job.get("location"), job.get("salary"),
                    job.get("description"), job.get("requirements"), job.get("url"),
                    job.get("boss_activity", ""), job.get("company_tier", ""), flag,
                ))
                count += 1
            except Exception:
                pass
        await db.commit()
        return count


async def update_job_match(job_id: int, score: float, reason: str,
                           highlights: list | None = None, concerns: list | None = None):
    import json
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE jobs
               SET match_score = ?, match_reason = ?,
                   match_highlights = ?, match_concerns = ?
               WHERE id = ?""",
            (score, reason,
             json.dumps(highlights or [], ensure_ascii=False),
             json.dumps(concerns  or [], ensure_ascii=False),
             job_id),
        )
        await db.commit()


async def update_job_status(job_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.now().isoformat(timespec="seconds")
        if status == "applied":
            await db.execute(
                "UPDATE jobs SET status = ?, applied_at = ? WHERE id = ?",
                (status, now, job_id),
            )
        else:
            await db.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
        await db.commit()


async def append_timeline(job_id: int, entry: str):
    """Append a timestamped line to the job's timeline log."""
    ts = datetime.now().strftime("%m-%d %H:%M")
    line = f"{ts} {entry}"
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT timeline_log FROM jobs WHERE id = ?", (job_id,)) as cur:
            row = await cur.fetchone()
        current = (row[0] or "").strip() if row else ""
        updated = (current + "\n" + line).strip()
        await db.execute("UPDATE jobs SET timeline_log = ? WHERE id = ?", (updated, job_id))
        await db.commit()
    return line


async def get_all_jobs(is_demo: bool = False) -> List[Dict]:
    flag = 1 if is_demo else 0
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jobs WHERE is_demo = ? ORDER BY match_score DESC, created_at DESC",
            (flag,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_job(job_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        await db.commit()


# ── settings ──────────────────────────────────────────────────────────────────

async def get_setting(key: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def save_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
        await db.commit()


async def get_preferences() -> str:
    return (await get_setting("job_preferences")) or DEFAULT_PREFERENCES

async def save_preferences(prefs: str):
    await save_setting("job_preferences", prefs)

async def get_resume_text() -> str:
    return (await get_setting("resume_text")) or ""

async def save_resume_text(text: str):
    await save_setting("resume_text", text)

async def get_resume_filename() -> str:
    return (await get_setting("resume_filename")) or ""

async def save_resume_filename(name: str):
    await save_setting("resume_filename", name)
