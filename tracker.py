"""SQLite-backed job tracking — stores status updates across sessions."""
import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import List, Dict

DB_PATH = Path(__file__).parent / "data" / "tracking.db"
SEED_PATH = Path(__file__).parent / "data" / "demo_timeline_jobs.json"

STATUS_LABELS: Dict[str, str] = {
    "offer":           "收到 Offer",
    "final_interview": "终面",
    "waiting":         "等待结果",
    "interview":       "面试中",
    "chatting":        "沟通中",
    "viewed":          "HR已查看",
    "applied":         "已投递",
    "pending":         "待投递",
    "rejected":        "已拒绝",
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables and seed from demo JSON if the DB is empty."""
    with _conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tracking_jobs (
            job_id          TEXT PRIMARY KEY,
            title           TEXT,
            company         TEXT,
            salary          TEXT,
            location        TEXT,
            match_score     REAL,
            match_reason    TEXT,
            match_highlights TEXT,
            match_concerns  TEXT,
            url             TEXT,
            status          TEXT DEFAULT 'pending',
            company_tier    TEXT,
            platform        TEXT,
            updated_at      TEXT
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tracking_timeline (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id       TEXT,
            event_date   TEXT,
            event_status TEXT,
            note         TEXT
        )""")
        conn.commit()

        # Seed only if the jobs table is empty
        if conn.execute("SELECT COUNT(*) FROM tracking_jobs").fetchone()[0] == 0:
            jobs = json.loads(SEED_PATH.read_text(encoding="utf-8"))
            for j in jobs:
                jid = str(j.get("job_id") or j.get("id") or j.get("title", ""))
                conn.execute("""
                INSERT OR IGNORE INTO tracking_jobs
                (job_id, title, company, salary, location, match_score,
                 match_reason, match_highlights, match_concerns, url, status,
                 company_tier, platform, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    jid,
                    j.get("title"), j.get("company"),
                    j.get("salary"), j.get("location"),
                    j.get("match_score", 0), j.get("match_reason"),
                    json.dumps(j.get("match_highlights", []), ensure_ascii=False),
                    json.dumps(j.get("match_concerns", []), ensure_ascii=False),
                    j.get("url"), j.get("status", "pending"),
                    j.get("company_tier"), j.get("platform"),
                    date.today().isoformat(),
                ))
                for event in (j.get("timeline") or []):
                    conn.execute("""
                    INSERT INTO tracking_timeline (job_id, event_date, event_status, note)
                    VALUES (?,?,?,?)
                    """, (jid, event.get("date"), event.get("status"), event.get("note", "")))
            conn.commit()


def get_all_jobs() -> List[Dict]:
    """Return all tracking jobs with embedded timeline lists, ordered by match_score."""
    init_db()
    with _conn() as conn:
        jobs = []
        for row in conn.execute("SELECT * FROM tracking_jobs ORDER BY match_score DESC"):
            j = dict(row)
            j["match_highlights"] = json.loads(j.get("match_highlights") or "[]")
            j["match_concerns"]   = json.loads(j.get("match_concerns") or "[]")
            tl = conn.execute(
                "SELECT event_date, event_status, note FROM tracking_timeline "
                "WHERE job_id=? ORDER BY event_date, id",
                (j["job_id"],),
            ).fetchall()
            j["timeline"] = [{"date": r["event_date"], "status": r["event_status"], "note": r["note"]} for r in tl]
            jobs.append(j)
    return jobs


def update_status(job_id: str, new_status: str, note: str = "") -> None:
    """Update a job's status and append a timestamped timeline entry."""
    today = date.today().isoformat()
    label = STATUS_LABELS.get(new_status, new_status)
    with _conn() as conn:
        conn.execute(
            "UPDATE tracking_jobs SET status=?, updated_at=? WHERE job_id=?",
            (new_status, today, job_id),
        )
        conn.execute(
            "INSERT INTO tracking_timeline (job_id, event_date, event_status, note) VALUES (?,?,?,?)",
            (job_id, today, label, note),
        )
        conn.commit()


def reset_db() -> None:
    """Drop all data and re-seed from the demo JSON (for dev resets)."""
    DB_PATH.unlink(missing_ok=True)
    init_db()
