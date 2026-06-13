"""Offer捕手 — AI 求职全链路助手（Streamlit 前端）"""
import asyncio
import hashlib
import html as _html
import json
import os
import re
import tempfile
from collections import Counter
from datetime import date as _date
from pathlib import Path

import streamlit as st

from company_tiers import get_company_tier
from matcher import diagnose_resume, extract_profile_from_resume, generate_greeting, generate_interview_prep, match_jobs
from resume_parser import parse_resume
from tracker import (
    add_job_from_match, add_job_manual, add_timeline_event,
    delete_job, get_all_jobs as get_tracking_jobs, update_status,
    STATUS_LABELS,
)

def _esc(s: object) -> str:
    """HTML-escape a value for safe injection into card HTML."""
    return _html.escape(str(s) if s is not None else "")


def _clean(s: object) -> str:
    """Strip Boss直聘反爬字体私用区字符（U+E000–U+F8FF）及常见乱码字符。

    Boss直聘用私用区码点替换真实汉字防止爬虫，在普通字体中渲染为方块/空白。
    """
    if s is None:
        return ""
    out = []
    for ch in str(s):
        cp = ord(ch)
        # 跳过 Unicode 私用区（BMP 私用区 + 补充私用区）
        if 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0x10FFFF:
            continue
        # 跳过替换字符 U+FFFD
        if cp == 0xFFFD:
            continue
        out.append(ch)
    # 清理因删除字符产生的空括号、多余空格/连字符
    result = "".join(out)
    result = re.sub(r"[（(]\s*[）)]", "", result)          # 空括号
    result = re.sub(r"[-\s]{2,}", lambda m: " " if " " in m.group() else "-", result)
    return result.strip(" -·")

# ── 示例简历（一键体验用）────────────────────────────────────────────────────────
SAMPLE_RESUME = """教育背景
某985高校 | 应用经济学·数据科学方向 | 硕士 | GPA 3.9/4.0
核心课程：机器学习、大数据分析、应用计量经济学、时间序列分析

个人优势
数据科学与运营双线背景，熟练掌握 Python、SQL、R、Tableau；
具备 A/B 实验设计、用户分层（RFM）、因果推断（PSM-DID）等实战经验；
具备 Vibe Coding 能力，可独立上线 Web 产品原型。

实习经历
某知名 AI 公司 | AI 策略运营实习生 | 2026.01–2026.04
- 构建 AI 自动化数据标注方案，生成 985+ 结构化标签数据点，支撑多维筛选与语义推荐
- 设计端到端用户决策链路（意图识别→路径优化），核心任务完成率 89%，满意度 4.4/5
- 独立完成 Web 端产品原型，验证 Vibe Coding 可将孵化周期缩短约 70%

某文化公司 | 用户运营实习生 | 2023.08–2024.08
- 构建"推文曝光→社群咨询→线下参与"全链路漏斗模型，内容曝光量提升 85%，转化率提升 42%
- 运用 SQL 构建 RFM 模型，将私域用户分为 8 类画像，唤醒 15% 沉睡用户
- 独立对接 NGO 合作资源，单场活动 ROI 达过往同期 3.2 倍

项目经历
- 基于 LASSO 回归的受访者可接触性预测（AUC 0.72）
- 基于 PSM-DID 模型的政府补贴政策影响评估（优秀毕业论文）

技能
Python（Pandas/Sklearn）、SQL、R、Excel、Tableau、A/B 测试、用户分层、因果推断"""

def _load_sample_matched_jobs() -> list:
    """从 DB 读取已有 match_score 的岗位作为示例匹配结果，避免演示时需要等待 AI。"""
    import json as _json
    try:
        import sqlite3 as _sq3, os as _os
        _db = _os.path.join(_os.path.dirname(__file__), "data", "jobs.db")
        _conn = _sq3.connect(_db)
        _conn.row_factory = _sq3.Row
        _rows = _conn.execute(
            "SELECT * FROM jobs WHERE match_score IS NOT NULL ORDER BY match_score DESC LIMIT 30"
        ).fetchall()
        _conn.close()
        _out = []
        for _r in _rows:
            _d = dict(_r)
            for _f in ("match_highlights", "match_concerns"):
                if isinstance(_d.get(_f), str):
                    try: _d[_f] = _json.loads(_d[_f])
                    except Exception: _d[_f] = []
            _out.append(_d)
        return _out
    except Exception:
        return []

SAMPLE_MATCHED_JOBS = _load_sample_matched_jobs()

SKILL_KEYWORDS = [
    "Python", "SQL", "Excel", "R语言", "Tableau", "Power BI",
    "数据分析", "数据运营", "用户运营", "内容运营", "增长运营", "策略运营",
    "A/B测试", "A/B", "漏斗分析", "用户画像", "RFM", "用户分层",
    "数据看板", "BI", "指标体系", "商业分析",
    "直播", "电商", "短视频", "游戏", "教育",
]

# ── 页面配置 ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Offer捕手",
    page_icon="捕",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 全局样式 ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;0,9..40,800;1,9..40,400&family=DM+Serif+Display:ital@0;1&display=swap');

/* ══ 基础 ══ */
html, body, [class*="css"], .stApp, .stMarkdown {
    font-family: "DM Sans", -apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif !important;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
}

/* ══ 布局 & 背景 ══ */
.stApp { background: #f5f5f4 !important; }
header[data-testid="stHeader"] { display:none!important; }
section[data-testid="stSidebar"] { display:none!important; }
.block-container { padding-top: 76px !important; padding-bottom: 4rem !important; max-width:1140px!important; padding-left:2.5rem!important; padding-right:2.5rem!important; }

/* ══ 顶部导航栏 ══ */
.app-nav {
  position:fixed; top:0; left:0; right:0; z-index:9999;
  height:60px; background:rgba(255,255,255,.97);
  backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
  border-bottom:1px solid rgba(39,41,55,.07);
  display:flex; align-items:center; justify-content:space-between;
  padding:0 32px; box-shadow:0 1px 12px rgba(39,41,55,.06);
}
/* Logo */
.app-nav-brand { display:flex; align-items:center; gap:0; text-decoration:none!important; }
.app-nav-brand-name {
  font-family:'DM Serif Display',serif; font-style:italic; font-weight:400;
  font-size:1.32rem; line-height:1; letter-spacing:-.01em; text-decoration:none!important;
}
.app-nav-brand-name .brand-offer { color:#d64635; }
.app-nav-brand-name .brand-catch { color:#272937; }
/* Center nav links */
.app-nav-links { display:flex; align-items:center; gap:1px; }
.app-nav-link {
  display:flex; align-items:center; gap:6px; padding:7px 14px; border-radius:8px;
  font-size:.83rem; font-weight:500; color:rgba(39,41,55,.52);
  text-decoration:none!important; transition:all .15s ease; white-space:nowrap;
}
.app-nav-link:hover { color:#272937; background:rgba(39,41,55,.05); text-decoration:none!important; }
.app-nav-link.nav-active {
  color:#272937; background:rgba(39,41,55,.08); font-weight:600;
  border-bottom:2px solid #d64635;
}
.app-nav-link.nav-active svg { stroke:#d64635; }
/* Right cluster */
.app-nav-right { display:flex; align-items:center; gap:4px; }
.app-nav-icon-btn {
  width:34px; height:34px; border-radius:8px; display:flex; align-items:center; justify-content:center;
  color:rgba(39,41,55,.45); cursor:pointer; transition:all .15s; border:none; background:transparent;
  text-decoration:none!important; flex-shrink:0;
}
.app-nav-icon-btn:hover { background:rgba(39,41,55,.06); color:#111; text-decoration:none!important; }
/* Nav divider */
.app-nav-divider { width:1px; height:28px; background:rgba(39,41,55,.1); margin:0 6px; flex-shrink:0; }
.nav-user-btn {
  display:flex; align-items:center; gap:9px; padding:5px 10px 5px 5px;
  border-radius:10px; cursor:pointer; transition:background .15s;
  background:transparent; border:none; text-decoration:none!important;
}
.nav-user-btn:hover { background:rgba(39,41,55,.05); }
.app-nav-avatar {
  width:32px; height:32px; border-radius:50%; background:#272937; color:#efece8;
  display:flex; align-items:center; justify-content:center;
  font-size:.72rem; font-weight:700; flex-shrink:0;
}
.nav-user-info { display:flex; flex-direction:column; align-items:flex-start; line-height:1; }
.nav-user-name { font-size:.8rem; font-weight:600; color:#111; white-space:nowrap; }
.nav-user-plan {
  font-size:.66rem; color:rgba(39,41,55,.42); margin-top:2px;
}
.nav-user-caret { color:rgba(39,41,55,.35); flex-shrink:0; }

/* ══ 标题 ══ */
h1 { font-family:"DM Serif Display",serif!important; font-size:1.45rem!important; font-weight:400!important; letter-spacing:-.02em!important; line-height:1.3!important; color:#272937!important; }
h2 { font-size:1rem!important; font-weight:700!important; color:#272937!important; letter-spacing:-.01em; }
h3 { font-size:.88rem!important; font-weight:600!important; color:#272937!important; }
p, li, .stMarkdown p { font-size:.875rem!important; line-height:1.75!important; color:rgba(39,41,55,.65); }
[data-testid="stCaptionContainer"] p, small { font-size:.73rem!important; color:#aaa!important; line-height:1.5!important; }

/* ══ 指标卡 ══ */
[data-testid="stMetricLabel"] > div {
    font-size:.7rem!important; font-weight:600!important; color:#888!important;
    text-transform:uppercase; letter-spacing:.07em;
}
[data-testid="stMetricValue"] > div {
    font-size:1.8rem!important; font-weight:900!important; color:#111!important;
    letter-spacing:-.04em;
}
div[data-testid="stMetric"] {
    background:#fff; border-radius:12px; padding:16px 20px;
    border:1px solid rgba(39,41,55,.08);
    box-shadow: 0 1px 4px rgba(39,41,55,.05);
}

/* ══ 侧边栏 headers ══ */
section[data-testid="stSidebar"] h3 {
    font-size:.68rem!important; font-weight:700; color:#aaa!important;
    text-transform:uppercase; letter-spacing:.1em;
    margin:20px 0 8px!important; padding:0!important; border:none!important;
}

/* ══ Tab 区域 ══ */
div[data-testid="stTabs"] > div:last-child { background:#fff; border-radius:0 0 12px 12px; padding:24px 4px 8px; }
button[data-baseweb="tab"] { font-size:.83rem!important; font-weight:600!important; color:rgba(39,41,55,.4)!important; letter-spacing:.01em; }
button[data-baseweb="tab"][aria-selected="true"] { color:#272937!important; border-bottom-color:#d64635!important; }
div[data-testid="stTabs"] button[role="tab"] { flex:1 1 0!important; justify-content:center!important; }

/* ══ 按钮 ══ */
button[data-testid="baseButton-primary"] {
    background: #272937 !important;
    border: none !important; border-radius: 10px !important;
    font-size: .85rem !important; font-weight: 600 !important; letter-spacing: .01em !important;
    box-shadow: 0 2px 8px rgba(39,41,55,.2) !important;
    transition: all .2s ease !important;
}
button[data-testid="baseButton-primary"]:hover {
    background: #d64635 !important;
    box-shadow: 0 4px 16px rgba(214,70,53,.35) !important;
    transform: translateY(-1px) !important;
}
button[data-testid="baseButton-secondary"] {
    background: #fff !important; border-radius: 10px !important;
    border: 1.5px solid rgba(39,41,55,.15) !important; color: #272937 !important;
    font-size: .84rem !important; font-weight: 500 !important;
    transition: all .15s ease !important;
}
button[data-testid="baseButton-secondary"]:hover {
    border-color: #d64635 !important; color: #d64635 !important; background: rgba(214,70,53,.04) !important;
}

/* ══ 表单 label ══ */
[data-testid="stSelectbox"] label, [data-testid="stTextInput"] label,
[data-testid="stSlider"] label, [data-testid="stMultiSelect"] label,
[data-testid="stFileUploader"] label {
    font-size:.72rem!important; font-weight:700!important; color:#666!important;
    text-transform:uppercase; letter-spacing:.06em;
}

/* ══ 岗位卡片 ══ */
.jc {
    background:#fff; border:1px solid rgba(39,41,55,.08); border-radius:12px;
    padding:14px 16px 12px; margin:0 0 8px;
    transition: box-shadow .2s ease, border-color .2s ease;
    box-shadow: 0 1px 3px rgba(39,41,55,.04);
}
.jc:hover { box-shadow: 0 4px 16px rgba(39,41,55,.1); border-color: rgba(39,41,55,.2); }
.jc-hd    { display:flex; justify-content:space-between; align-items:flex-start; gap:8px }
.jc-title { font-weight:700; font-size:.91rem; color:#272937; flex:1; line-height:1.4 }
.jc-score { font-weight:800; font-size:1.15rem; white-space:nowrap; letter-spacing:-.02em; }
.sc-hi  { color:#272937 }
.sc-mid { color:#d64635 }
.sc-lo  { color:rgba(39,41,55,.35) }
.jc-meta  { display:flex; align-items:center; gap:5px; flex-wrap:wrap; margin-top:5px; font-size:.74rem; color:rgba(39,41,55,.45); line-height:1.4; }
.jc-bar-bg{ height:3px; background:rgba(39,41,55,.08); border-radius:99px; margin:8px 0 6px; overflow:hidden }
.jc-bar   { height:100%; border-radius:99px }
.bar-hi { background: #272937 }
.bar-mid{ background: #d64635 }
.bar-lo { background: rgba(39,41,55,.2) }
.jc-pills { display:flex; flex-wrap:wrap; gap:4px; margin-top:7px }
.jp       { font-size:.71rem; padding:3px 9px; border-radius:4px; line-height:1.5; font-weight:500; }
.jp-pos   { background:rgba(39,41,55,.06); color:#272937 }
.jp-neg   { background:rgba(214,70,53,.08); color:#d64635 }
.jp-tip   { background:rgba(39,41,55,.05); color:rgba(39,41,55,.6) }

/* ══ 徽章 ══ */
.bd { display:inline-block; font-size:.67rem; padding:2px 8px; border-radius:4px; font-weight:600; line-height:1.6; vertical-align:middle; }
.bd-big  { background:#272937; color:#efece8 }
.bd-mid  { background:rgba(39,41,55,.1); color:#272937 }
.bd-sml  { background:rgba(39,41,55,.06); color:rgba(39,41,55,.5) }
.bd-boss { background:#272937; color:#efece8 }
.bd-shix { background:#d64635; color:#fff }

/* ══ 看板 ══ */
.jc-compact { min-height:140px; display:flex; flex-direction:column }
.jc-compact .jc-pills { flex:1; align-content:flex-start }
.kb-hd  { font-weight:700; font-size:.78rem; display:flex; align-items:center; gap:6px; margin-bottom:4px; color:#272937; }
.kb-dot { width:8px; height:8px; border-radius:50%; display:inline-block }
.kb-cnt { background:rgba(39,41,55,.08); color:rgba(39,41,55,.5); font-size:.7rem; padding:1px 7px; border-radius:4px; font-weight:600 }
.kb-rule{ height:2px; border-radius:99px; margin-bottom:10px }
</style>
""", unsafe_allow_html=True)

# ── 卡片渲染辅助函数 ──────────────────────────────────────────────────────────────
def _job_card(job: dict, compact: bool = False) -> str:
    """生成岗位 HTML 卡片（与参考设计对标）。"""
    score  = job.get("match_score", 0)
    tier   = get_company_tier(job.get("company", ""))
    plat   = job.get("platform", "")
    salary = job.get("salary") or "薪资面议"
    city   = (job.get("location") or "").split("-")[0]

    tier_html = {"大厂": '<span class="bd bd-big">大厂</span>',
                 "中厂": '<span class="bd bd-mid">中厂</span>',
                 "小厂": '<span class="bd bd-sml">小厂</span>'}.get(tier, "")
    plat_html = {"boss":      '<span class="bd bd-boss">Boss</span>',
                 "shixiseng": '<span class="bd bd-shix">实习僧</span>'}.get(plat, "")

    # score=0 表示手动添加（无AI评分）—— 隐藏分数和进度条
    has_score = score > 0
    sc_cls    = "sc-hi" if score >= 80 else ("sc-mid" if score >= 65 else "sc-lo")
    bar_cls   = "bar-hi" if score >= 80 else ("bar-mid" if score >= 65 else "bar-lo")
    score_html = f'<span class="jc-score {sc_cls}">{score:.0f}</span>' if has_score else \
                 '<span class="jc-score" style="color:#9ca3af;font-size:.8em">手动</span>'
    bar_html   = (f'<div class="jc-bar-bg">'
                  f'<div class="jc-bar {bar_cls}" style="width:{score}%"></div>'
                  f'</div>') if has_score else ""

    highlights = (job.get("match_highlights") or [])[:3]
    concerns   = (job.get("match_concerns")   or [])[:2]

    if compact:
        pills = "".join(f'<span class="jp jp-pos">✓ {_esc(h)}</span>' for h in highlights[:2])
        pills += "".join(f'<span class="jp jp-neg">△ {_esc(c)}</span>' for c in concerns[:1])
    else:
        pills = "".join(f'<span class="jp jp-pos">✓ {_esc(h)}</span>' for h in highlights)
        pills += "".join(f'<span class="jp jp-neg">△ {_esc(c)}</span>' for c in concerns)
        if not highlights and not concerns and job.get("match_reason"):
            pills = f'<span class="jp jp-tip">💡 {_esc(job["match_reason"])[:60]}</span>'

    card_cls = "jc jc-compact" if compact else "jc"
    return (
        f'<div class="{card_cls}">'
        f'<div class="jc-hd">'
        f'<span class="jc-title">{_esc(job.get("title",""))}</span>'
        f'{score_html}'
        f'</div>'
        f'<div class="jc-meta">'
        f'<span>{_esc(job.get("company",""))}</span>{tier_html}{plat_html}'
        f'<span>·</span><span>{_esc(salary)}</span>'
        f'<span>·</span><span>{_esc(city)}</span>'
        f'</div>'
        f'{bar_html}'
        f'<div class="jc-pills">{pills}</div>'
        f'</div>'
    )


def _job_card_v2(job: dict) -> str:
    """Correlate AI 风格岗位卡片，用于岗位匹配页列表。"""
    score   = job.get("match_score", 0)
    company = job.get("company", "") or ""
    title   = job.get("title", "")
    salary  = job.get("salary") or "薪资面议"
    city    = (job.get("location") or "").split("-")[0]
    tier    = get_company_tier(company)
    plat    = job.get("platform", "")

    # 公司首字（优先汉字）
    initial = next((ch for ch in company if "一" <= ch <= "鿿"), None)
    if not initial:
        initial = company[0].upper() if company else "?"

    # logo 背景色按规模区分
    logo_bg = "#1e2235" if tier == "大厂" else ("#2d3748" if tier == "中厂" else "#374151")

    # 分数颜色
    if score >= 80:
        s_color, s_cls = "#2563eb", "jcv2-score-hi"
    elif score >= 65:
        s_color, s_cls = "#f59e0b", "jcv2-score-mid"
    else:
        s_color, s_cls = "#94a3b8", "jcv2-score-lo"
    score_html = (f'<span class="{s_cls}">{score:.0f}</span>' if score > 0
                  else '<span class="jcv2-score-lo" style="font-size:.8rem">手动</span>')

    # 标签
    highlights = (job.get("match_highlights") or [])[:2]
    concerns   = (job.get("match_concerns")   or [])[:1]
    tags  = "".join(f'<span class="tag-hi">✓ {_esc(h)}</span>' for h in highlights)
    tags += "".join(f'<span class="tag-lo">△ {_esc(c)}</span>' for c in concerns)
    if tier in ("大厂", "中厂", "小厂"):
        tags += f'<span class="tag-tier">{tier}</span>'
    plat_label = {"boss": "Boss直聘", "shixiseng": "实习僧"}.get(plat, "")
    if plat_label:
        tags += f'<span class="tag-plat">{plat_label}</span>'

    return f"""<div class="jcv2">
  <div class="jcv2-top">
    <div class="jcv2-logo" style="background:{logo_bg}">{_esc(initial)}</div>
    <div class="jcv2-body">
      <div class="jcv2-title-row">
        <span class="jcv2-title">{_esc(title)}</span>
        {score_html}
      </div>
      <div class="jcv2-meta">{_esc(company)} · {_esc(city)} · {_esc(salary)}</div>
      <div class="jcv2-tags">{tags}</div>
    </div>
  </div>
</div>"""


def _job_detail_panel(job: dict) -> str:
    """Correlate AI 风格两栏 JD 详情面板（左：内容，右：About 元数据）。"""
    desc  = (job.get("description")   or "").strip()
    req   = (job.get("requirements")  or "").strip()
    score = job.get("match_score", 0)
    city  = _esc((job.get("location") or "").split("-")[0])
    tier  = get_company_tier(job.get("company", ""))
    plat_label = {"boss": "Boss直聘", "shixiseng": "实习僧"}.get(job.get("platform", ""), "—")

    def _sec(icon_path: str, title: str, body: str) -> str:
        return f"""<div style="margin-bottom:20px">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
    <div style="width:28px;height:28px;border-radius:7px;background:rgba(37,99,235,.1);
         display:flex;align-items:center;justify-content:center;flex-shrink:0">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2563eb"
           stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        {icon_path}
      </svg>
    </div>
    <span style="font-size:.95rem;font-weight:700;color:#0f172a">{title}</span>
  </div>
  <div style="font-size:.83rem;color:#475569;line-height:1.8;white-space:pre-line">{_esc(body)}</div>
</div>"""

    left = ""
    if desc:
        left += _sec('<path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>',
                     "岗位描述", desc[:600] + ("…" if len(desc) > 600 else ""))
    if req:
        left += _sec('<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>',
                     "岗位要求", req[:500] + ("…" if len(req) > 500 else ""))
    if not left:
        left = '<div style="color:#94a3b8;font-size:.84rem;padding:8px 0">暂无岗位详情</div>'

    # Keywords pills
    highlights = (job.get("match_highlights") or [])[:5]
    concerns   = (job.get("match_concerns")   or [])[:3]
    kw_html = "".join(
        f'<span style="font-size:.73rem;padding:4px 11px;border-radius:99px;'
        f'border:1.5px solid #bbf7d0;color:#15803d;background:#fff">{_esc(h)}</span>'
        for h in highlights
    ) + "".join(
        f'<span style="font-size:.73rem;padding:4px 11px;border-radius:99px;'
        f'border:1.5px solid #fecaca;color:#dc2626;background:#fff">{_esc(c)}</span>'
        for c in concerns
    )

    # Score color
    sc = "#2563eb" if score >= 80 else ("#f59e0b" if score >= 65 else "#94a3b8")

    def _arow(icon_path: str, label: str, val: str) -> str:
        return f"""<div style="display:flex;align-items:center;gap:8px;padding:8px 0;
     border-bottom:1px solid #f1f5f9;font-size:.83rem">
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2"
       stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0">{icon_path}</svg>
  <span style="color:#94a3b8;width:60px;flex-shrink:0">{label}</span>
  <span style="color:#0f172a;font-weight:600">{val}</span>
</div>"""

    about = f"""<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:18px 20px">
  <div style="font-size:.95rem;font-weight:700;color:#0f172a;margin-bottom:14px">About</div>
  {_arow('<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/>',
         "地点", city)}
  {_arow('<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>',
         "薪资", _esc(job.get("salary") or "面议"))}
  {_arow('<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2"/>',
         "规模", tier)}
  {_arow('<path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 9.81 19.79 19.79 0 01.01 1.18 2 2 0 012 .01h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L6.09 7.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 14.92z"/>',
         "平台", _esc(plat_label))}
  {f"""<div style="margin-top:16px;padding-top:14px;border-top:1px solid #f1f5f9">
    <div style="font-size:.7rem;font-weight:700;color:#94a3b8;text-transform:uppercase;
         letter-spacing:.07em;margin-bottom:8px">AI 匹配分析</div>
    <div style="font-size:1.75rem;font-weight:800;color:{sc};line-height:1;margin-bottom:10px">{score:.0f} 分</div>
    <div style="display:flex;flex-wrap:wrap;gap:5px">{kw_html}</div>
  </div>""" if score > 0 else ""}
</div>"""

    return f"""<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;
     margin:4px 0 16px;overflow:hidden">
  <div style="display:grid;grid-template-columns:1fr 270px">
    <div style="padding:22px 24px;border-right:1px solid #e2e8f0">{left}</div>
    <div style="padding:20px">{about}</div>
  </div>
</div>"""


# ── 数据加载 ────────────────────────────────────────────────────────────────────
@st.cache_data
def load_jobs() -> list[dict]:
    path = Path(__file__).parent / "data" / "jobs_export.json"
    with open(path, encoding="utf-8") as f:
        jobs = json.load(f)
    for j in jobs:
        # 清洗文本字段中的爬虫编码乱码
        for tf in ("title", "company", "salary", "location", "description",
                   "requirements", "match_reason"):
            if j.get(tf):
                j[tf] = _clean(j[tf])
        for field in ("match_highlights", "match_concerns"):
            if isinstance(j.get(field), str):
                try:
                    j[field] = json.loads(j[field])
                except Exception:
                    j[field] = []
            if isinstance(j.get(field), list):
                j[field] = [_clean(x) for x in j[field]]
        if not j.get("company_tier"):
            j["company_tier"] = get_company_tier(j.get("company", ""))
    return jobs


# ── 工具函数 ────────────────────────────────────────────────────────────────────
def _read_secret(key: str) -> str:
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, "")


def set_api_key(key: str):
    st.session_state.api_key = key
    os.environ["OPENROUTER_API_KEY"] = key


def score_color(score: float) -> str:
    if score >= 80:
        return "🟢"
    if score >= 65:
        return "🟡"
    return "🔴"


def analyze_skill_gaps(jobs: list[dict]) -> list[tuple]:
    high_score_jobs = [j for j in jobs if j.get("match_score", 0) >= 70]
    req_text = " ".join(
        (j.get("requirements") or "") + " " + (j.get("description") or "")
        for j in high_score_jobs
    )
    freq = Counter()
    for kw in SKILL_KEYWORDS:
        count = len(re.findall(kw, req_text, re.IGNORECASE))
        if count > 0:
            freq[kw] = count
    return freq.most_common(8)


# ── Session state 初始化 ────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "resume_text": "",
        "matched_jobs": None,
        "api_key": _read_secret("OPENROUTER_API_KEY"),
        "preferences": "",
        "diagnosis_result": None,
        "diagnosis_job_id": None,
        "interview_result": None,
        "interview_job_id": None,
        "greetings": {},
        "t1_page": 0,
        "_t1_sig": None,
        "show_landing": True,
        "min_score": 60,
        "filter_platforms": [],
        "filter_tiers": [],
        "filter_cities": [],
        "sort_by_pref": "匹配分（高→低）",
        "pref_categories": [],
        "pref_subs": [],
        "show_api_input": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

_page = st.query_params.get("page", "dashboard")
if _page not in ("dashboard", "jobs", "resume", "progress", "settings"):
    _page = "dashboard"

# ── 常量 ────────────────────────────────────────────────────────────────────────
PLATFORM_NAME = {"boss": "Boss直聘", "shixiseng": "实习僧"}

JOB_CATEGORIES = {
    "运营": ["数据运营", "用户运营", "内容运营", "活动运营", "社群运营", "增长运营", "电商运营", "品牌运营"],
    "产品": ["产品经理", "产品策划", "产品运营", "AI产品", "B端产品", "C端产品", "游戏策划"],
    "数据": ["数据分析", "商业分析", "数据挖掘", "BI分析师", "数据产品", "算法工程师"],
    "市场": ["市场营销", "品牌策划", "公关传播", "市场调研", "新媒体运营", "SEO/SEM"],
    "技术": ["前端开发", "后端开发", "全栈开发", "算法研究", "数据工程", "测试开发", "移动开发"],
    "咨询/金融": ["管理咨询", "投资分析", "战略规划", "财务分析", "审计", "研究员"],
}

STATUS_CONFIG = {
    "offer":           ("🎉", "Offer"),
    "final_interview": ("🔥", "终面"),
    "waiting":         ("⏳", "等待结果"),
    "interview":       ("💬", "面试中"),
    "chatting":        ("💬", "沟通中"),
    "viewed":          ("👀", "已查看"),
    "applied":         ("📤", "已投递"),
    "pending":         ("📋", "待投递"),
    "rejected":        ("❌", "已拒绝"),
}

STATUS_ORDER = ["offer", "final_interview", "waiting", "interview", "chatting",
                "viewed", "applied", "pending", "rejected"]

TIMELINE_ICONS = {
    "已投递": "📤", "HR已查看": "👀", "面试邀请": "📅", "约面试": "📅",
    "一面": "💬", "二面": "💬", "终面": "🔥", "等待结果": "⏳",
    "offer": "🎉", "已拒绝": "❌", "沟通中": "💬",
}


# ────────────────────────────────────────────────────────────────────────────────
# Landing Page  —— 显示首页时隐藏侧边栏，st.stop() 阻止主app渲染
# ────────────────────────────────────────────────────────────────────────────────
if st.query_params.get("start") == "1":
    st.session_state.show_landing = False
    st.query_params.clear()
    st.rerun()

if st.query_params.get("show_landing") == "1":
    st.session_state.show_landing = True
    st.query_params.clear()
    st.rerun()

# 如果 URL 中带有 page= 参数，说明用户从导航栏点击进入 App，
# 无论 session_state 是否刚刚重置，都应跳过首页直接进入对应页面
_url_page = st.query_params.get("page", "")
if _url_page in ("dashboard", "jobs", "resume", "progress", "settings"):
    st.session_state.show_landing = False

if st.session_state.get("show_landing", True):
    st.markdown("""<style>
section[data-testid="stSidebar"] { display:none!important }
header[data-testid="stHeader"]   { display:none!important }
.main .block-container           { max-width:820px!important; padding:0 2.5rem 8rem!important; margin:0 auto!important }
.stApp { background:#efece8!important }

/* ════ NAV ════ */
.lp-nav {
    position:fixed; top:0; left:0; right:0; z-index:9999;
    height:64px; background:rgba(239,236,232,.96);
    backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
    border-bottom:1px solid rgba(39,41,55,.08);
    display:flex; align-items:center; justify-content:space-between; padding:0 10%;
}
.lp-logo { text-decoration:none!important; display:flex; align-items:center; }
.lp-logo * { text-decoration:none!important; }
.lp-links { display:flex; gap:32px; }
.lp-links a { font-size:.85rem; font-weight:500; color:rgba(39,41,55,.5); text-decoration:none; cursor:pointer; transition:color .15s; position:relative; padding-bottom:2px; }
.lp-links a::after { content:''; position:absolute; bottom:-2px; left:0; right:0; height:2px; background:#d64635; border-radius:99px; transform:scaleX(0); transition:transform .2s ease; }
.lp-links a:hover { color:#272937; }
.lp-links a:hover::after { transform:scaleX(1); }

/* ════ HERO ANIMATIONS ════ */
@keyframes lp-fadeup {
  from { opacity:0; transform:translateY(30px); }
  to   { opacity:1; transform:translateY(0); }
}
.lp-h1  { animation: lp-fadeup .85s cubic-bezier(.22,1,.36,1) .05s both; }
.lp-sub { animation: lp-fadeup .85s cubic-bezier(.22,1,.36,1) .22s both; }
.lp-cta { animation: lp-fadeup .85s cubic-bezier(.22,1,.36,1) .38s both; }

/* ════ HERO ════ */
.lp-hero { text-align:center; height:100vh; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:0; margin-top:-76px; background:radial-gradient(ellipse 90% 70% at 50% 40%, rgba(214,70,53,.07) 0%, transparent 60%); scroll-margin-top:0; }
.lp-h1 { font-family:"DM Serif Display",serif; font-size:2.75rem; font-weight:400; letter-spacing:-.04em; line-height:1.15; color:#272937; margin:0 0 24px; }
.lp-h1-accent { color:#d64635; }
.lp-sub { font-size:1rem; line-height:1.9; color:rgba(39,41,55,.45); max-width:480px; margin:0 auto; text-align:center!important; }
.lp-cta { display:inline-block; margin-top:40px; padding:15px 48px; background:#d64635; color:#fff!important; font-size:1rem; font-weight:600; border-radius:99px; text-decoration:none!important; letter-spacing:.02em; transition:background .2s cubic-bezier(.4,0,.2,1), transform .15s cubic-bezier(.4,0,.2,1), box-shadow .2s; box-shadow:0 2px 16px rgba(214,70,53,.3); }
.lp-cta:hover { background:#c03d2f; transform:translateY(-2px); box-shadow:0 6px 24px rgba(214,70,53,.38); }

/* ════ FEATURES ════ */
.lp-section-label {
  display:block; text-align:center; margin-bottom:28px;
  font-family:"Noto Serif SC","Songti SC","STSong",serif; font-size:2.75rem; font-weight:700;
  letter-spacing:-.02em; color:#272937; text-transform:none; line-height:1.1;
}
.lp-section-label::before {
  content:'✦'; font-family:sans-serif;
  font-size:.48em; color:#d64635; opacity:.72;
  margin-right:16px; display:inline-block;
  vertical-align:top; margin-top:.18em;
}
.lp-section-label::after {
  content:'✦'; font-family:sans-serif;
  font-size:.3em; color:#d64635; opacity:.48;
  margin-left:14px; display:inline-block;
  vertical-align:middle;
}
.lp-hr { display:none; }
.lp-bars-area { display:flex; align-items:flex-end; height:128px; }
.lp-bar-col { flex:5; display:flex; flex-direction:column; align-items:center; height:100%; justify-content:flex-end; }
.lp-bar-mid { flex:3; display:flex; align-items:center; justify-content:center; padding-bottom:26px; }
.lp-bar-val { font-size:.8rem; font-weight:700; color:rgba(39,41,55,.4); margin-bottom:4px; line-height:1; }
.lp-bar-val.hi { color:#272937; }
.lp-bar-body { width:72%; border-radius:5px 5px 0 0; }
.lp-bar-before { background:rgba(39,41,55,.1); }
.lp-bar-after { background:#272937; }
.lp-bar-name { font-size:.63rem; color:rgba(39,41,55,.3); margin-top:7px; text-align:center; }
.lp-bar-name.hi { color:#d64635; font-weight:700; }
.lp-delta { font-size:.68rem; font-weight:800; color:#d64635; background:rgba(214,70,53,.07); border:1px solid rgba(214,70,53,.18); border-radius:99px; padding:4px 8px; white-space:nowrap; text-align:center; }

/* ════ TESTIMONIALS ════ */
.lp-quotes { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }
.lp-quote { background:#fff; border:1px solid rgba(39,41,55,.08); border-radius:14px; padding:26px 24px 28px; }
.lp-quote-hd { display:flex; align-items:center; gap:14px; margin-bottom:18px; }
.lp-quote-text { font-size:.86rem; color:rgba(39,41,55,.58); line-height:1.82; }
.lp-quote-name { font-size:.87rem; font-weight:700; color:#272937; line-height:1.3; }
.lp-quote-role { font-size:.68rem; color:rgba(39,41,55,.32); margin-top:3px; }

/* ════ FLOATING ACTIONS ════ */
.lp-fab { position:fixed; right:24px; bottom:32px; z-index:9998; display:flex; flex-direction:column; gap:12px; align-items:center; }
.lp-fab-btn { width:48px; height:48px; border-radius:50%; display:flex; align-items:center; justify-content:center; text-decoration:none!important; transition:transform .18s ease, box-shadow .18s ease, background .18s; cursor:pointer; }
.lp-fab-btn:hover { transform:scale(1.1); }
.lp-fab-mail { background:#fff; border:1.5px solid rgba(39,41,55,.12); color:#d64635!important; box-shadow:0 2px 10px rgba(39,41,55,.08); }
.lp-fab-mail:hover { background:rgba(214,70,53,.05); border-color:rgba(214,70,53,.2); color:#d64635!important; }
.lp-fab-top { background:#fff; border:1.5px solid rgba(39,41,55,.12); color:#d64635!important; box-shadow:0 2px 10px rgba(39,41,55,.08); }
.lp-fab-top:hover { background:rgba(214,70,53,.05); border-color:rgba(214,70,53,.2); color:#d64635!important; }

/* ════ CONTACT MODAL ════ */
.lp-modal { display:none; position:fixed; inset:0; z-index:99999; background:rgba(39,41,55,.5); backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px); align-items:center; justify-content:center; }
.lp-modal:target { display:flex; }
.lp-modal-box { background:#fff; border-radius:20px; padding:40px 36px 32px; width:calc(100% - 48px); max-width:420px; position:relative; box-shadow:0 32px 80px rgba(39,41,55,.22); }
.lp-modal-close { position:absolute; top:16px; right:16px; width:32px; height:32px; border-radius:50%; background:rgba(39,41,55,.06); display:flex; align-items:center; justify-content:center; text-decoration:none!important; color:rgba(39,41,55,.4); font-size:.78rem; font-weight:700; line-height:1; transition:background .15s; }
.lp-modal-close:hover { background:rgba(39,41,55,.12); color:#272937; }
.lp-modal-title { font-family:"DM Serif Display",serif; font-size:1.75rem; font-weight:400; color:#272937; margin:0 0 6px; line-height:1.2; }
.lp-modal-sub { font-size:.8rem; color:rgba(39,41,55,.38); margin:0 0 28px; }
.lp-modal-lbl { font-size:.66rem; font-weight:700; text-transform:uppercase; letter-spacing:.09em; color:rgba(39,41,55,.4); display:block; margin-bottom:7px; }
.lp-modal-field { width:100%; border:1.5px solid rgba(39,41,55,.1); border-radius:10px; padding:11px 14px; font-size:.84rem; color:#272937; background:#fafaf9; font-family:inherit; margin-bottom:18px; box-sizing:border-box; outline:none; transition:border-color .15s; -webkit-appearance:none; }
.lp-modal-field:focus { border-color:#d64635; background:#fff; }
.lp-modal-ta { height:96px; resize:none; }
.lp-modal-send { display:block; width:100%; background:#272937; color:#efece8!important; border:none; border-radius:10px; padding:13px; font-size:.88rem; font-weight:600; cursor:pointer; text-align:center; text-decoration:none!important; margin-top:6px; transition:background .15s; }
.lp-modal-send:hover { background:#d64635; }

/* ════ BOTTOM CTA ════ */
.lp-cta-banner { background:#272937; border-radius:20px; padding:60px 48px; text-align:center; }
.lp-cta-h2 { font-family:"DM Serif Display",serif; font-size:2.5rem; font-weight:400; color:#efece8; letter-spacing:-.02em; line-height:1.1; margin:0 0 14px; }
.lp-cta-h2 em { color:#d64635; font-style:italic; }
.lp-cta-sub { font-size:.95rem; color:rgba(239,236,232,.45); margin:0; line-height:1.7; }

/* reduce streamlit gap below hero on landing */
.main .block-container > div > div[data-testid="stVerticalBlockBorderWrapper"] + div { margin-top:-16px!important }

.lp-footer { display:flex; align-items:center; justify-content:center; gap:12px; padding:20px 0 20px; font-size:.72rem; color:rgba(39,41,55,.25); letter-spacing:.02em; }
.lp-footer-sep { width:1px; height:12px; background:rgba(39,41,55,.12); display:inline-block; }
html, section[data-testid="stMain"] { scroll-behavior:smooth !important; }
</style>""", unsafe_allow_html=True)

    # ── 固定导航栏 ──
    st.markdown("""
<nav class="lp-nav">
  <a class="lp-logo" href="#"><span style="font-family:'DM Serif Display',serif;font-style:italic;font-size:1.4rem;font-weight:400;letter-spacing:-.01em;"><span style="color:#d64635;">Offer</span><span style="color:#272937;">捕手</span></span></a>
  <div class="lp-links">
    <a href="#lp-home">首页</a>
    <a href="#lp-features">功能</a>
    <a href="#lp-reviews">评价</a>
    <a href="#lp-faq">常见问题</a>
  </div>
</nav>
""", unsafe_allow_html=True)

    # ── Hero ──
    st.markdown("""
<div id="lp-home" class="lp-hero">
<h1 class="lp-h1">简历投出去，<span class="lp-h1-accent">Offer</span>&nbsp;捕回来。</h1>
  <p class="lp-sub">AI 全力接管繁琐，你只管拿 Offer<br>精准匹配 · 简历诊断 · 打招呼文案 · 面试备考</p>
  <a href="?start=1" target="_self" class="lp-cta">开始使用</a>
</div>
""", unsafe_allow_html=True)

    # ── 功能模块（Correlate AI 风格图文交替） ──
    st.markdown("""<div id="lp-features" style="scroll-margin-top:80px;padding-top:56px"></div>""",
                unsafe_allow_html=True)

    st.components.v1.html("""<!DOCTYPE html><html><head><meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:#efece8;font-family:"Noto Serif SC","Songti SC","STSong","SimSun",serif;}

/* ── Feature row ── */
.fr{display:grid;grid-template-columns:1fr 1fr;gap:72px;padding:96px 0;border-top:1px solid rgba(39,41,55,.07);align-items:center;min-height:520px;}
.fr:first-child{border-top:none;}
.fr.shade{background:rgba(255,255,255,.55);border-radius:20px;padding-left:0;padding-right:0;}

/* text cell */
.ft{min-width:0;max-width:340px;}
.ft-l{margin-left:auto;}
.fnum{font-size:.68rem;font-weight:800;letter-spacing:.18em;color:rgba(214,70,53,.65);text-transform:uppercase;margin-bottom:18px;}
.ftitle{font-size:2.75rem;font-weight:700;color:#272937;line-height:1.1;margin-bottom:20px;letter-spacing:-.03em;}
.fdesc{font-size:1rem;color:rgba(39,41,55,.55);line-height:2;}

/* mockup cell */
.fm{min-width:0;display:flex;align-items:center;}
.fm-l{justify-content:flex-end;}
.fm .card{width:100%;}

/* ── Shared card shell ── */
.card{background:#fff;border:1px solid rgba(39,41,55,.09);border-radius:18px;padding:26px;box-shadow:0 4px 20px rgba(39,41,55,.08);max-width:340px;transition:box-shadow .25s cubic-bezier(.4,0,.2,1),transform .25s cubic-bezier(.4,0,.2,1);}
.card:hover{box-shadow:0 12px 40px rgba(39,41,55,.14);transform:translateY(-4px);}

/* ── F1: Job matching ── */
.job{display:flex;align-items:center;gap:12px;padding:12px 14px;border:1px solid rgba(39,41,55,.07);border-radius:12px;margin-bottom:10px;background:#faf9f7;}
.job:last-child{margin-bottom:0;}
.jl{width:36px;height:36px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;flex-shrink:0;}
.ji{flex:1;min-width:0;}
.jt{font-size:14px;font-weight:600;color:#272937;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.jc{font-size:12px;color:rgba(39,41,55,.35);margin-top:3px;}
.js{font-size:14px;font-weight:800;color:#d64635;background:rgba(214,70,53,.08);padding:4px 10px;border-radius:99px;flex-shrink:0;}

/* ── F2: Resume diagnosis ── */
.dscore{font-size:3rem;font-weight:800;color:#272937;letter-spacing:-.04em;line-height:1;margin-bottom:6px;}
.dscore sub{font-size:1rem;font-weight:400;color:rgba(39,41,55,.3);}
.dlabel{font-size:.7rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:rgba(39,41,55,.3);margin-bottom:16px;}
.dr{display:flex;align-items:flex-start;gap:10px;font-size:13px;padding:9px 0;border-bottom:1px solid rgba(39,41,55,.06);}
.dr:last-child{border-bottom:none;}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-top:3px;}

/* ── F3: Greeting ── */
.bubble{background:rgba(214,70,53,.07);border-radius:16px 16px 16px 4px;padding:16px 18px;font-size:14px;color:rgba(39,41,55,.72);line-height:1.85;margin-bottom:12px;}
.bmeta{display:flex;align-items:center;gap:8px;font-size:12px;color:rgba(39,41,55,.32);}
.btag{background:rgba(39,41,55,.07);border-radius:99px;padding:3px 10px;}

/* ── F4: Interview prep ── */
.qcard{padding:13px 0;border-bottom:1px solid rgba(39,41,55,.06);}
.qcard:last-child{border-bottom:none;}
.qtag{display:inline-block;font-size:11px;font-weight:800;color:#d64635;background:rgba(214,70,53,.09);border-radius:4px;padding:3px 9px;margin-bottom:7px;letter-spacing:.03em;}
.qtext{font-size:14px;color:#272937;font-weight:600;line-height:1.45;}
.qhint{font-size:12px;color:rgba(39,41,55,.38);margin-top:5px;}
</style></head><body>

<!-- F1: 岗位匹配 — mock left, text right — default bg -->
<div class="fr">
  <div class="fm fm-l">
    <div class="card">
      <div style="font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:rgba(39,41,55,.28);margin-bottom:12px;">AI 推荐岗位</div>
      <div class="job">
        <div class="jl" style="background:#fff0e6;color:#d64635;">字</div>
        <div class="ji"><div class="jt">数据运营实习生</div><div class="jc">字节跳动 · 北京</div></div>
        <div class="js">92分</div>
      </div>
      <div class="job">
        <div class="jl" style="background:#e8f4ff;color:#1a6dbf;">网</div>
        <div class="ji"><div class="jt">策略运营实习</div><div class="jc">网易 · 杭州</div></div>
        <div class="js">87分</div>
      </div>
      <div class="job">
        <div class="jl" style="background:#e8f9ee;color:#1a7a42;">阿</div>
        <div class="ji"><div class="jt">数据分析实习</div><div class="jc">阿里巴巴 · 上海</div></div>
        <div class="js">81分</div>
      </div>
    </div>
  </div>
  <div class="ft">
    <div class="fnum">01 · 岗位匹配</div>
    <div class="ftitle">精准岗位<br>自动发现</div>
    <div class="fdesc">实时抓取 Boss直聘 & 实习僧最新岗位，DeepSeek 从方向、技能、经历三个维度打分排序。高匹配机会优先呈现，告别漫无目的的大海捞针。</div>
  </div>
</div>

<!-- F2: 简历诊断 — text left, mock right — shaded -->
<div class="fr shade">
  <div class="ft ft-l">
    <div class="fnum">02 · 简历诊断</div>
    <div class="ftitle">逐行诊断，<br>针对 JD 改写</div>
    <div class="fdesc">AI 对照岗位 JD 逐条分析你的简历，精准指出优势与缺口，并给出可直接落笔的改写建议，而非模糊的泛化评语。</div>
  </div>
  <div class="fm">
    <div class="card">
      <div class="dscore">87<sub> 分</sub></div>
      <div class="dlabel">简历—JD 匹配度</div>
      <div class="dr"><div class="dot" style="background:#22c55e;"></div><span style="color:rgba(39,41,55,.65);">Python 数据分析能力与 JD 高度契合</span></div>
      <div class="dr"><div class="dot" style="background:#22c55e;"></div><span style="color:rgba(39,41,55,.65);">有真实项目数据支撑，说服力强</span></div>
      <div class="dr"><div class="dot" style="background:#f59e0b;"></div><span style="color:rgba(39,41,55,.55);">建议量化：「提升 XX%」优于「有提升」</span></div>
      <div class="dr"><div class="dot" style="background:#ef4444;"></div><span style="color:rgba(39,41,55,.45);">缺少直播运营相关经历，可补充</span></div>
    </div>
  </div>
</div>

<!-- F3: 打招呼文案 — mock left, text right — default bg -->
<div class="fr">
  <div class="fm fm-l">
    <div class="card">
      <div style="font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:rgba(39,41,55,.28);margin-bottom:10px;">生成的打招呼文案</div>
      <div class="bubble">您好！我是985院校数据专业应届生，曾主导校内电商运营项目，用 SQL + Python 完成用户留存分析，ROI 提升 23%。对贵司数据运营岗位非常感兴趣，期待与您交流！</div>
      <div class="bmeta">
        <span class="btag">✓ 已针对 JD 定制</span>
        <span class="btag">58 字</span>
      </div>
    </div>
  </div>
  <div class="ft">
    <div class="fnum">03 · 打招呼文案</div>
    <div class="ftitle">一键生成，<br>HR 主动回复</div>
    <div class="fdesc">结合你的简历亮点与目标岗位 JD，生成 60 字以内的个性化开场白。不再复制粘贴千篇一律的模板，每条消息都针对当前职位定制。</div>
  </div>
</div>

<!-- F4: 面试备考 — text left, mock right — shaded -->
<div class="fr shade">
  <div class="ft ft-l">
    <div class="fnum">04 · 面试备考</div>
    <div class="ftitle">预测高频题，<br>提前备好答案</div>
    <div class="fdesc">结合岗位 JD 和你的简历，预测面试官最可能问到的问题，并给出回答要点和需要规避的弱点。从容应对，不再临场慌乱。</div>
  </div>
  <div class="fm">
    <div class="card">
      <div style="font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:rgba(39,41,55,.28);margin-bottom:12px;">面试预测题</div>
      <div class="qcard">
        <div class="qtag">高频必问</div>
        <div class="qtext">结合你的数据分析项目，说明你的分析思路和方法论</div>
        <div class="qhint">💡 强调数据驱动决策，给出具体 ROI 数据</div>
      </div>
      <div class="qcard">
        <div class="qtag">岗位相关</div>
        <div class="qtext">你如何理解「运营」与「数据」的关系？</div>
        <div class="qhint">💡 结合实习经历，避免纯理论回答</div>
      </div>
      <div class="qcard">
        <div class="qtag">弱点预警</div>
        <div class="qtext">你没有直播运营经验，如何快速上手？</div>
        <div class="qhint">💡 提前准备学习路径和迁移能力</div>
      </div>
    </div>
  </div>
</div>

<script>
function resizeFeatures(){
  var h=document.documentElement.scrollHeight;
  window.parent.postMessage({type:'streamlit:setFrameHeight',height:h},'*');
}
window.addEventListener('load',resizeFeatures);
setTimeout(resizeFeatures,300);
(function(){
  var obs=new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      if(e.isIntersecting){
        e.target.style.opacity='1';
        e.target.style.transform='translateY(0)';
        obs.unobserve(e.target);
      }
    });
  },{threshold:0.08,rootMargin:'0px 0px -32px 0px'});
  document.querySelectorAll('.fr').forEach(function(el,i){
    el.style.opacity='0';
    el.style.transform='translateY(40px)';
    el.style.transition='opacity .75s cubic-bezier(.22,1,.36,1) '+(i*.1)+'s,transform .75s cubic-bezier(.22,1,.36,1) '+(i*.1)+'s';
    obs.observe(el);
  });
})();
</script>
</body></html>""", height=2480, scrolling=False)

    # ── 评价（数据说话 + 用户评价合并） ──
    st.markdown("""
<div id="lp-reviews" style="scroll-margin-top:80px;padding-top:56px">
  <span class="lp-section-label">真实提效数据</span>
</div>
""", unsafe_allow_html=True)

    st.components.v1.html("""<!DOCTYPE html><html><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#efece8;font-family:"Noto Serif SC","Songti SC",serif;}
/* 三列文字说明 */
.stats-text{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-bottom:20px;margin-top:28px;}
.st-item{}
.st-title{font-size:15px;font-weight:700;color:#272937;margin-bottom:8px;}
.st-desc{font-size:13px;color:rgba(39,41,55,.52);line-height:1.75;}
/* 图表 */
.charts{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;}
.chart{background:#fff;border:1px solid rgba(39,41,55,.08);border-radius:20px;padding:24px 20px 16px;opacity:0;transform:translateY(16px);transition:opacity .5s ease,transform .5s ease;}
.chart.show{opacity:1;transform:translateY(0);}
.ct{font-size:13.5px;font-weight:600;color:#272937;margin-bottom:14px;line-height:1.45;}
svg.cg{width:100%;display:block;}
</style>
</head><body>

<!-- 三列文字说明 -->
<div class="stats-text">
  <div class="st-item">
    <div class="st-title">精准岗位匹配</div>
    <div class="st-desc">从每周 20 条泛投变为精准推荐 200+ 条高匹配岗位，命中率提升 10 倍。</div>
  </div>
  <div class="st-item">
    <div class="st-title">投递效率跃升</div>
    <div class="st-desc">单次投递从手动准备 25 分钟压缩至 2 分钟，节省 92% 的重复劳动。</div>
  </div>
  <div class="st-item">
    <div class="st-title">简历契合度优化</div>
    <div class="st-desc">AI 对标 JD 自动优化简历关键词，简历—岗位契合度从 40% 提升至 90%。</div>
  </div>
</div>

<!-- 三列图表 -->
<div class="charts">

<!-- ── Chart 1: 岗位发现量 ── -->
<div class="chart">
  <p class="ct">精准岗位发现量（条/周）</p>
  <svg class="cg" viewBox="0 0 260 222" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="ga" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#d64635" stop-opacity=".82"/>
        <stop offset="100%" stop-color="#d64635" stop-opacity=".20"/>
      </linearGradient>
      <marker id="mka" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">
        <path d="M1,1.5 L8,5 L1,8.5" fill="none" stroke="#d64635" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </marker>
    </defs>
    <line x1="8" y1="172" x2="252" y2="172" stroke="rgba(39,41,55,.06)" stroke-width="1.2"/>
    <!-- left bar: tiny -->
    <rect x="12" y="163" width="52" height="9" rx="4" fill="rgba(39,41,55,.1)"/>
    <!-- right bar: tall -->
    <rect x="196" y="26" width="52" height="146" rx="6" fill="url(#ga)"/>
    <!-- value labels -->
    <text x="38" y="157" text-anchor="middle" font-size="13" font-weight="600" fill="rgba(39,41,55,.30)">20</text>
    <text x="222" y="20" text-anchor="middle" font-size="20" font-weight="800" fill="#d64635" letter-spacing="-0.5">200</text>
    <!-- diagonal arc: starts lower-left, sweeps up-right; pill at upper-left safely avoids -->
    <path d="M 64,172 C 105,82 162,40 196,30" fill="none" stroke="rgba(39,41,55,.12)" stroke-width="5" stroke-linecap="round"/>
    <path d="M 64,172 C 105,82 162,40 196,30" fill="none" stroke="#d64635" stroke-width="2" stroke-linecap="round" marker-end="url(#mka)"/>
    <!-- pill: upper-left — when x<96, arrow y>109 (well below pill bottom 66) -->
    <rect x="4" y="40" width="92" height="26" rx="13" fill="rgba(255,246,244,.96)" stroke="rgba(214,70,53,.28)" stroke-width="1.2"/>
    <polyline points="13,58 17,53 21,56 27,47" fill="none" stroke="#d64635" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="57" y="58" text-anchor="middle" font-size="11.5" font-weight="700" fill="#d64635">提升 10 倍</text>
    <!-- x-labels -->
    <text x="38" y="200" text-anchor="middle" font-size="12" fill="rgba(39,41,55,.36)">手动搜索</text>
    <text x="222" y="200" text-anchor="middle" font-size="12" font-weight="700" fill="#d64635">Offer 捕手</text>
  </svg>
</div>

<!-- ── Chart 2: 准备时间（下降） ── -->
<div class="chart">
  <p class="ct">单次投递准备时间（分钟）</p>
  <svg class="cg" viewBox="0 0 260 222" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="gb" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#d64635" stop-opacity=".82"/>
        <stop offset="100%" stop-color="#d64635" stop-opacity=".20"/>
      </linearGradient>
      <marker id="mkb" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">
        <path d="M1,1.5 L8,5 L1,8.5" fill="none" stroke="#d64635" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </marker>
    </defs>
    <line x1="8" y1="172" x2="252" y2="172" stroke="rgba(39,41,55,.06)" stroke-width="1.2"/>
    <!-- left bar: tall -->
    <rect x="12" y="26" width="52" height="146" rx="6" fill="rgba(39,41,55,.1)"/>
    <!-- right bar: tiny -->
    <rect x="196" y="163" width="52" height="9" rx="4" fill="url(#gb)"/>
    <!-- value labels -->
    <text x="38" y="20" text-anchor="middle" font-size="20" font-weight="800" fill="rgba(39,41,55,.30)" letter-spacing="-0.5">25</text>
    <text x="222" y="157" text-anchor="middle" font-size="13" font-weight="600" fill="#d64635">2</text>
    <!-- downward arc; pill at upper-right, arrow enters x>112 only below y=70 -->
    <path d="M 64,30 C 64,148 196,124 196,165" fill="none" stroke="rgba(39,41,55,.12)" stroke-width="5" stroke-linecap="round"/>
    <path d="M 64,30 C 64,148 196,124 196,165" fill="none" stroke="#d64635" stroke-width="2" stroke-linecap="round" marker-end="url(#mkb)"/>
    <!-- pill: upper-right -->
    <rect x="112" y="28" width="90" height="26" rx="13" fill="rgba(255,246,244,.96)" stroke="rgba(214,70,53,.28)" stroke-width="1.2"/>
    <polyline points="121,36 125,41 129,37 135,46" fill="none" stroke="#d64635" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="166" y="46" text-anchor="middle" font-size="11.5" font-weight="700" fill="#d64635">节省 92%</text>
    <!-- x-labels -->
    <text x="38" y="200" text-anchor="middle" font-size="12" fill="rgba(39,41,55,.36)">手动准备</text>
    <text x="222" y="200" text-anchor="middle" font-size="12" font-weight="700" fill="#d64635">Offer 捕手</text>
  </svg>
</div>

<!-- ── Chart 3: JD契合度 ── -->
<div class="chart">
  <p class="ct">简历—JD 契合度</p>
  <svg class="cg" viewBox="0 0 260 222" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="gc" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#d64635" stop-opacity=".82"/>
        <stop offset="100%" stop-color="#d64635" stop-opacity=".20"/>
      </linearGradient>
      <marker id="mkc" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">
        <path d="M1,1.5 L8,5 L1,8.5" fill="none" stroke="#d64635" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </marker>
    </defs>
    <line x1="8" y1="172" x2="252" y2="172" stroke="rgba(39,41,55,.06)" stroke-width="1.2"/>
    <!-- left bar: medium 40% -->
    <rect x="12" y="104" width="52" height="68" rx="6" fill="rgba(39,41,55,.1)"/>
    <!-- right bar: tall 90% -->
    <rect x="196" y="26" width="52" height="146" rx="6" fill="url(#gc)"/>
    <!-- value labels -->
    <text x="38" y="98" text-anchor="middle" font-size="13" font-weight="600" fill="rgba(39,41,55,.30)">40%</text>
    <text x="222" y="20" text-anchor="middle" font-size="20" font-weight="800" fill="#d64635" letter-spacing="-0.5">90%</text>
    <!-- diagonal arc from left bar top; pill at upper-left safely avoids -->
    <path d="M 64,104 C 105,60 162,36 196,30" fill="none" stroke="rgba(39,41,55,.12)" stroke-width="5" stroke-linecap="round"/>
    <path d="M 64,104 C 105,60 162,36 196,30" fill="none" stroke="#d64635" stroke-width="2" stroke-linecap="round" marker-end="url(#mkc)"/>
    <!-- pill: upper-left — when x<96, arrow y>74 (below pill bottom 66) -->
    <rect x="4" y="40" width="92" height="26" rx="13" fill="rgba(255,246,244,.96)" stroke="rgba(214,70,53,.28)" stroke-width="1.2"/>
    <polyline points="13,58 17,53 21,56 27,47" fill="none" stroke="#d64635" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="57" y="58" text-anchor="middle" font-size="11.5" font-weight="700" fill="#d64635">提升 2.2 倍</text>
    <!-- x-labels -->
    <text x="38" y="200" text-anchor="middle" font-size="12" fill="rgba(39,41,55,.36)">凭感觉筛选</text>
    <text x="222" y="200" text-anchor="middle" font-size="12" font-weight="700" fill="#d64635">Offer 捕手</text>
  </svg>
</div>

</div>
<script>
(function(){
  function resize(){window.parent.postMessage({type:'streamlit:setFrameHeight',height:document.documentElement.scrollHeight},'*');}
  window.addEventListener('load',resize);setTimeout(resize,300);
  var cards=document.querySelectorAll('.chart');
  var io=new IntersectionObserver(function(es){
    es.forEach(function(e,i){
      if(e.isIntersecting){
        setTimeout(function(){e.target.classList.add('show');},i*120);
        io.unobserve(e.target);
      }
    });
  },{threshold:0.1});
  cards.forEach(function(c){io.observe(c);});
})();
</script>
</body></html>""", height=530)

    st.markdown("""<div style="padding-top:56px"><span class="lp-section-label">用户评价</span></div>""",
                unsafe_allow_html=True)

    st.components.v1.html("""<!DOCTYPE html><html><head><meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#efece8;font-family:"Noto Serif SC","Songti SC","STSong","SimSun",serif;}
.quotes{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:28px;}
.q{background:#fff;border:1px solid rgba(39,41,55,.08);border-radius:20px;padding:44px 36px 48px;}
.qhd{display:flex;align-items:center;gap:18px;margin-bottom:28px;}
.av{width:60px;height:60px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:600;flex-shrink:0;}
.qname{font-size:18px;font-weight:700;color:#272937;line-height:1.3;}
.qrole{font-size:13px;color:rgba(39,41,55,.32);margin-top:4px;}
.qtxt{font-size:16px;color:rgba(39,41,55,.58);line-height:2;}
</style></head><body>
<div class="quotes">
  <div class="q">
    <div class="qhd">
      <div class="av" style="background:#f5dfc8;color:#9c5a2a;">陈</div>
      <div><div class="qname">陈思瑶</div><div class="qrole">985 应届生 · 市场运营方向</div></div>
    </div>
    <div class="qtxt">打招呼文案比我自己写的专业多了，HR 回复率直接提了一大截。第一周就约到了 3 个面试，真的很惊喜。</div>
  </div>
  <div class="q">
    <div class="qhd">
      <div class="av" style="background:#c8dff5;color:#1e538a;">李</div>
      <div><div class="qname">李浩宇</div><div class="qrole">双非硕士 · 数据分析求职</div></div>
    </div>
    <div class="qtxt">简历诊断功能直接告诉我针对不同 JD 缺了什么、怎么改。修改后感觉简历通过率提高了很多，不再是石沉大海。</div>
  </div>
  <div class="q">
    <div class="qhd">
      <div class="av" style="background:#c8ecd8;color:#1e6b42;">王</div>
      <div><div class="qname">王晓雨</div><div class="qrole">文科应届生 · 转型数据运营</div></div>
    </div>
    <div class="qtxt">以前海投没有方向，AI 匹配直接告诉我哪些岗位最值得投、哪些不适合，省了大量精力，可以把时间用在备考上。</div>
  </div>
</div>
<script>
function resizeQuotes(){
  var h=document.documentElement.scrollHeight;
  window.parent.postMessage({type:'streamlit:setFrameHeight',height:h},'*');
}
window.addEventListener('load',resizeQuotes);
setTimeout(resizeQuotes,300);
(function(){
  var obs=new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      if(e.isIntersecting){e.target.style.opacity='1';e.target.style.transform='translateY(0)';obs.unobserve(e.target);}
    });
  },{threshold:0.1});
  document.querySelectorAll('.q').forEach(function(el,i){
    el.style.opacity='0';el.style.transform='translateY(24px)';
    el.style.transition='opacity .65s cubic-bezier(.22,1,.36,1) '+(i*.13)+'s,transform .65s cubic-bezier(.22,1,.36,1) '+(i*.13)+'s';
    obs.observe(el);
  });
})();
</script>
</body></html>""", height=460)

    st.markdown("""<div id="lp-faq" style="scroll-margin-top:80px;padding-top:56px"><span class="lp-section-label">常见问题</span></div>""",
                unsafe_allow_html=True)

    st.components.v1.html("""<!DOCTYPE html><html><head><meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#efece8;font-family:"Noto Serif SC","Songti SC","STSong","SimSun",serif;}
.wrap{background:rgba(39,41,55,.03);border:1px solid rgba(39,41,55,.08);border-radius:20px;overflow:visible;margin-top:28px;}
details{border-bottom:1px solid rgba(39,41,55,.07);}
details:last-child{border-bottom:none;}
summary{list-style:none;display:flex;align-items:center;justify-content:space-between;padding:22px 28px;cursor:pointer;font-size:15px;font-weight:600;color:#272937;line-height:1.4;gap:16px;}
summary::-webkit-details-marker{display:none;}
.ic{flex-shrink:0;width:22px;height:22px;border-radius:50%;border:1.5px solid rgba(39,41,55,.2);display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:300;color:rgba(39,41,55,.4);transition:transform .2s,border-color .2s,color .2s;line-height:1;}
details[open] summary{color:#d64635;}
details[open] .ic{transform:rotate(45deg);border-color:#d64635;color:#d64635;}
.ans{padding:0 28px 22px;font-size:13px;color:rgba(39,41,55,.5);line-height:1.85;}
</style></head><body>
<div class="wrap">
  <details>
    <summary>Offer捕手会保存我的简历信息吗？<span class="ic">+</span></summary>
    <div class="ans">不会。你的简历文本仅在当前会话中使用，用于 AI 匹配和诊断分析，页面关闭后不会被存储在任何服务器上。</div>
  </details>
  <details>
    <summary>AI 匹配分数是怎么计算的？<span class="ic">+</span></summary>
    <div class="ans">AI 从四个维度评估：岗位方向匹配（25%）、技能匹配（35%）、项目 / 实习经历相关性（25%）、教育背景（15%），综合得出 0–100 的匹配分数并排序。</div>
  </details>
  <details>
    <summary>支持哪些招聘平台？<span class="ic">+</span></summary>
    <div class="ans">目前支持 Boss直聘 和 实习僧 两个平台的实时岗位抓取，覆盖绝大多数互联网、消费品、金融等行业的应届生和实习岗位。</div>
  </details>
  <details>
    <summary>需要付费吗？<span class="ic">+</span></summary>
    <div class="ans">完全免费。你只需在设置中填入自己的 OpenRouter API Key（按量计费，调用成本极低），即可解锁全部 AI 功能。</div>
  </details>
  <details>
    <summary>没有技术背景可以使用吗？<span class="ic">+</span></summary>
    <div class="ans">当然可以。粘贴简历、填写求职意向、点击按钮，三步即可开始使用。无需任何编程知识，界面操作和普通网页一样简单。</div>
  </details>
</div>
<script>
function resize(){
  var h=document.documentElement.scrollHeight;
  window.parent.postMessage({type:'streamlit:setFrameHeight',height:h+8},'*');
}
document.querySelectorAll('details').forEach(function(d){
  d.addEventListener('toggle',function(){
    setTimeout(resize,50);
    setTimeout(resize,300);
  });
});
window.addEventListener('load',resize);
setTimeout(resize,200);
// Scroll-reveal FAQ items
(function(){
  var wrap=document.querySelector('.wrap');
  if(!wrap)return;
  wrap.style.opacity='0';wrap.style.transform='translateY(20px)';
  wrap.style.transition='opacity .7s cubic-bezier(.22,1,.36,1),transform .7s cubic-bezier(.22,1,.36,1)';
  var obs=new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      if(e.isIntersecting){wrap.style.opacity='1';wrap.style.transform='translateY(0)';obs.unobserve(e.target);}
    });
  },{threshold:0.05});
  obs.observe(wrap);
})();
</script>
</body></html>""", height=680, scrolling=False)

    st.markdown("""
<footer class="lp-footer">
  <span style="font-family:'DM Serif Display',serif;font-style:italic;font-size:.82rem;"><span style="color:rgba(214,70,53,.45);">Offer</span><span style="color:rgba(39,41,55,.3);">捕手</span></span>
  <span class="lp-footer-sep"></span>
  <span>© 2026</span>
</footer>

<!-- ── 悬浮按钮 ── -->
<div class="lp-fab">
  <a class="lp-fab-btn lp-fab-mail" href="#lp-contact" title="联系我们">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <rect x="2" y="4" width="20" height="16" rx="2.5"/>
      <path d="m2 7 10 6.5L22 7"/>
    </svg>
  </a>
  <a class="lp-fab-btn lp-fab-top" href="#lp-home" title="回到顶部">
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 19V5M5 12l7-7 7 7"/>
    </svg>
  </a>
</div>

<!-- ── 联系我们 Modal（CSS :target 纯 CSS 实现） ── -->
<div class="lp-modal" id="lp-contact">
  <div class="lp-modal-box">
    <a class="lp-modal-close" href="#">✕</a>
    <p class="lp-modal-title">有什么可以帮您？</p>
    <p class="lp-modal-sub">建议、问题、反馈？随时告诉我们！</p>
    <label class="lp-modal-lbl">您的邮箱</label>
    <input class="lp-modal-field" type="email" placeholder="方便回复您的邮箱">
    <label class="lp-modal-lbl">主题</label>
    <select class="lp-modal-field">
      <option value="">请选择</option>
      <option>功能建议</option>
      <option>问题反馈</option>
      <option>合作咨询</option>
      <option>其他</option>
    </select>
    <label class="lp-modal-lbl">内容</label>
    <textarea class="lp-modal-field lp-modal-ta" placeholder="写下您的留言…"></textarea>
    <a class="lp-modal-send" href="mailto:guanxiaochi99@gmail.com?subject=Offer捕手反馈">发送</a>
  </div>
</div>
""", unsafe_allow_html=True)

    st.stop()   # 不渲染主 app



# ── 过滤器变量（从 session_state 读取，由设置页写入）────────────────────────────
min_score    = st.session_state.get("min_score", 60)
platforms    = st.session_state.get("filter_platforms", [])
tiers        = st.session_state.get("filter_tiers", [])
cities_filter = st.session_state.get("filter_cities", [])
sort_by      = st.session_state.get("sort_by_pref", "匹配分（高→低）")

# ── 顶部导航栏 ─────────────────────────────────────────────────────────────────
def _nav_link(label: str, page: str, icon_path: str = "", dot: bool = False) -> str:
    active = "nav-active" if _page == page else ""
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{icon_path}</svg>' if icon_path else ""
    badge = '<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#22c55e;margin-left:3px;margin-bottom:6px;flex-shrink:0"></span>' if dot else ""
    return f'<a href="?page={page}" target="_self" class="app-nav-link {active}">{svg}{label}{badge}</a>'

_icon_dash   = '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>'
_icon_jobs   = '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2"/><line x1="12" y1="12" x2="12" y2="12"/>'
_icon_saved  = '<path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/>'
_icon_resume = '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>'
_icon_prog   = '<path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/>'
_icon_bell   = '<path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/>'
_icon_help   = '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>'
_icon_set    = '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>'

def _svg(path: str, size: int = 16) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{path}</svg>'

_bell_svg = f'<svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{_icon_bell}</svg>'
_help_svg = f'<svg width="17" height="17" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{_icon_help}</svg>'
_caret_svg = '<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>'

_prof_saved = bool(st.session_state.get("prof_saved") or st.session_state.get("prof_lastname") or st.session_state.get("prof_school"))
st.markdown(f"""<nav class="app-nav"><a href="?show_landing=1" target="_self" class="app-nav-brand"><span class="app-nav-brand-name"><span class="brand-offer">Offer</span><span class="brand-catch">捕手</span></span></a><div class="app-nav-links">{_nav_link("我的","progress",_icon_prog,dot=_prof_saved)}{_nav_link("岗位匹配","jobs",_icon_jobs)}{_nav_link("仪表盘","dashboard",_icon_dash)}{_nav_link("简历诊断","resume",_icon_resume)}</div><div class="app-nav-right"><span class="app-nav-icon-btn" title="暂无通知">{_bell_svg}</span><a class="app-nav-icon-btn" href="?show_landing=1" target="_self" title="帮助">{_help_svg}</a><div class="app-nav-divider"></div><a href="?page=settings" target="_self" class="app-nav-icon-btn" title="设置">{_svg(_icon_set, 18)}</a></div></nav>""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════════
# 设置页  (page=settings)
# ════════════════════════════════════════════════════════════════════════════════
if _page == "settings":
    # ── settings page CSS ─────────────────────────────────────────────────────
    st.markdown("""
<style>
/* Settings page global bg */
section[data-testid="stMain"] > div:first-child { background: #f8f9fc !important; }
.set-section-card {
    background: #fff;
    border: 1px solid rgba(39,41,55,.08);
    border-radius: 16px;
    padding: 24px 24px 20px;
    margin-bottom: 18px;
    box-shadow: 0 1px 4px rgba(39,41,55,.05);
}
.set-section-title {
    display: flex; align-items: center; gap: 9px;
    font-size: .9rem; font-weight: 700; color: #272937;
    margin-bottom: 16px;
}
.set-section-icon {
    width: 28px; height: 28px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
}
/* AI status card */
.ai-status-connected {
    display: flex; align-items: center; gap: 12px;
    background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
    border: 1px solid #bbf7d0; border-radius: 12px;
    padding: 14px 16px; margin-bottom: 12px;
}
.ai-status-dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: #22c55e;
    box-shadow: 0 0 0 3px rgba(34,197,94,.2);
    flex-shrink: 0;
}
.ai-status-disconnected {
    background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
    border: 1px solid #fde68a; border-radius: 12px;
    padding: 16px 18px; margin-bottom: 12px;
}
.ai-step-row {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 8px 0; border-bottom: 1px solid rgba(251,191,36,.25);
}
.ai-step-row:last-child { border-bottom: none; }
.ai-step-num {
    width: 20px; height: 20px; border-radius: 50%;
    background: #f59e0b; color: #fff;
    font-size: .68rem; font-weight: 800;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.ai-step-text { font-size: .78rem; color: #92400e; line-height: 1.45; }
.ai-step-link { color: #d97706; font-weight: 600; text-decoration: none; }
.ai-step-link:hover { text-decoration: underline; }
/* Resume card status */
.resume-loaded-badge {
    display: inline-flex; align-items: center; gap: 6px;
    background: #eff6ff; border: 1px solid #bfdbfe;
    border-radius: 8px; padding: 8px 12px;
    font-size: .8rem; color: #1d4ed8; font-weight: 600; margin-bottom: 10px;
}
/* Category pills for job prefs */
.cat-tag {
    display: inline-block; padding: 4px 10px;
    border-radius: 20px; font-size: .75rem; font-weight: 600;
    border: 1.5px solid #e2e8f0; color: #475569;
    background: #f8fafc; margin: 2px 3px 2px 0; cursor: default;
}
</style>
""", unsafe_allow_html=True)

    st.markdown('<div style="font-size:1.35rem;font-weight:800;color:#272937;margin-bottom:20px">⚙️ 设置</div>', unsafe_allow_html=True)

    _c1, _c2 = st.columns(2, gap="large")

    # ── LEFT COLUMN ────────────────────────────────────────────────────────────
    with _c1:
        # ── 简历卡片 ────────────────────────────────────────────────────────────
        st.markdown("""
<div class="set-section-card">
  <div class="set-section-title">
    <div class="set-section-icon" style="background:#eff6ff">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
        <polyline points="10 9 9 9 8 9"/>
      </svg>
    </div>
    我的简历
  </div>
</div>
""", unsafe_allow_html=True)
        if st.session_state.resume_text:
            st.markdown(f"""
<div class="resume-loaded-badge">
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
    <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/>
  </svg>
  简历已加载 · {len(st.session_state.resume_text)} 字
</div>
""", unsafe_allow_html=True)
            with st.expander("查看简历全文"):
                st.text_area("内容", value=st.session_state.resume_text, height=240,
                             label_visibility="collapsed", key="set_resume_preview")
            if st.button("🔄 更换简历", use_container_width=True):
                st.session_state.resume_text = ""
                st.rerun()
        else:
            _rf = st.file_uploader("上传简历（.docx / .pdf）", type=["docx", "pdf"], key="set_resume_upload")
            if _rf:
                _suf = ".pdf" if _rf.name.lower().endswith(".pdf") else ".docx"
                with tempfile.NamedTemporaryFile(suffix=_suf, delete=False) as _tmp:
                    _tmp.write(_rf.read()); _tmp_path = _tmp.name
                st.session_state.resume_text = parse_resume(_tmp_path)
                st.rerun()
            if st.button("🎬 示例简历（一键演示）", use_container_width=True,
                         help="加载示例简历并预置匹配结果，无需等待 AI 运算"):
                st.session_state.resume_text    = SAMPLE_RESUME
                st.session_state.preferences    = "数据运营、数据分析、用户运营"
                st.session_state.pref_categories = ["运营", "数据"]
                st.session_state.pref_subs       = ["数据运营", "数据分析", "用户运营"]
                if SAMPLE_MATCHED_JOBS:
                    st.session_state.matched_jobs = SAMPLE_MATCHED_JOBS
                st.rerun()

        st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

        # ── 求职意向卡片 ─────────────────────────────────────────────────────────
        st.markdown("""
<div class="set-section-card">
  <div class="set-section-title">
    <div class="set-section-icon" style="background:#fdf4ff">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#a855f7" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/>
      </svg>
    </div>
    求职意向
  </div>
</div>
""", unsafe_allow_html=True)

        # Primary categories multiselect
        _cat_opts = list(JOB_CATEGORIES.keys())
        _sel_cats = st.multiselect(
            "感兴趣的方向（可多选）",
            options=_cat_opts,
            default=st.session_state.pref_categories,
            placeholder="选择大类，如：产品、运营…",
            key="set_pref_cats",
        )
        st.session_state.pref_categories = _sel_cats

        # Sub-category multiselect (dynamic)
        if _sel_cats:
            _all_subs = []
            for _cat in _sel_cats:
                _all_subs.extend(JOB_CATEGORIES.get(_cat, []))
            # filter previously saved subs that are still valid
            _valid_prev_subs = [s for s in st.session_state.pref_subs if s in _all_subs]
            _sel_subs = st.multiselect(
                "细分方向（可多选）",
                options=_all_subs,
                default=_valid_prev_subs,
                placeholder="选择具体岗位方向…",
                key="set_pref_subs",
            )
            st.session_state.pref_subs = _sel_subs
            # Build preferences string
            _pref_str = "、".join(_sel_subs) if _sel_subs else "、".join(_sel_cats)
            st.session_state.preferences = _pref_str
            if _pref_str:
                st.markdown(f"""
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;
     padding:10px 14px;margin-top:6px;font-size:.78rem;color:#475569">
  <span style="font-weight:600;color:#272937">当前偏好：</span>{_pref_str}
</div>
""", unsafe_allow_html=True)
        else:
            st.session_state.pref_subs = []
            st.session_state.preferences = ""
            st.markdown("""
<div style="background:#f8fafc;border:1px dashed #cbd5e1;border-radius:10px;
     padding:10px 14px;margin-top:6px;font-size:.78rem;color:#94a3b8;text-align:center">
  请先选择感兴趣的大方向
</div>
""", unsafe_allow_html=True)

    # ── RIGHT COLUMN ───────────────────────────────────────────────────────────
    with _c2:
        # ── 岗位筛选卡片 ─────────────────────────────────────────────────────────
        st.markdown("""
<div class="set-section-card">
  <div class="set-section-title">
    <div class="set-section-icon" style="background:#fff7ed">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#f97316" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
      </svg>
    </div>
    岗位筛选
  </div>
</div>
""", unsafe_allow_html=True)

        _ms = st.slider("最低匹配分", 0, 100, st.session_state.min_score, key="set_min_score")
        st.session_state.min_score = _ms
        _pl = st.multiselect("招聘平台", ["boss", "shixiseng"], default=st.session_state.filter_platforms,
            format_func=lambda x: PLATFORM_NAME.get(x, x), placeholder="不限", key="set_platforms")
        st.session_state.filter_platforms = _pl
        _ti = st.multiselect("公司规模", ["大厂", "中厂", "小厂"], default=st.session_state.filter_tiers, placeholder="不限", key="set_tiers")
        st.session_state.filter_tiers = _ti
        _sb = st.selectbox("排序方式", ["匹配分（高→低）", "公司规模（大厂优先）", "城市"],
            index=["匹配分（高→低）", "公司规模（大厂优先）", "城市"].index(st.session_state.sort_by_pref), key="set_sort")
        st.session_state.sort_by_pref = _sb

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        if st.button("🤖 AI 重新匹配", type="primary", use_container_width=True):
            if not st.session_state.resume_text:
                st.error("请先上传简历")
            elif not st.session_state.api_key:
                st.error("请先配置 AI 连接")
            else:
                _jraw = load_jobs()
                with st.spinner(f"AI 正在分析 {len(_jraw)} 条岗位…"):
                    _matched = asyncio.run(match_jobs(st.session_state.resume_text, [j.copy() for j in _jraw], st.session_state.preferences))
                st.session_state.matched_jobs = _matched
                st.session_state.diagnosis_result = None
                st.session_state.interview_result = None
                st.session_state.greetings = {}
                st.rerun()

    st.stop()

if _page == "dashboard":
    # ── 欢迎 Hero + 引导卡 ───────────────────────────────────────────────────────────
    # 步骤串联依赖：前一步未完成，后续步骤不计为完成
    _step1_done = bool(st.session_state.resume_text)
    _step2_done = bool(st.session_state.preferences) and _step1_done
    _step3_done = bool(st.session_state.matched_jobs) and _step1_done
    _applied_count = sum(
        1 for j in get_tracking_jobs()
        if j.get("status") not in ("pending", "rejected")
    )
    _step4_done = _applied_count > 0 and _step3_done
    _steps_done  = sum([_step1_done, _step2_done, _step3_done, _step4_done])

    def _step_html(num: int, label: str, sub: str, done: bool, active: bool,
                   link: str = "", done_link: str = "") -> str:
        """
        Always returns a single <div> — never wraps in <a> so CSS grid never breaks.
        - active+undone → "前往完成 →" CTA
        - done + done_link → "更换 →" secondary link (e.g. go to settings to replace)
        """
        if done:
            icon_bg  = "#d64635"; icon_color = "#fff"
            icon_svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" fill="none" '
                        'viewBox="0 0 24 24" stroke="currentColor" stroke-width="3">'
                        '<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>')
            border = "1.5px solid rgba(214,70,53,.3)"
            bg     = "rgba(214,70,53,.04)"
        elif active:
            icon_bg  = "#272937"; icon_color = "#fff"
            icon_svg = f'<span style="font-size:.73rem;font-weight:800;line-height:1">{num}</span>'
            border   = "2px solid #272937"
            bg       = "rgba(39,41,55,.03)"
        else:
            icon_bg  = "rgba(39,41,55,.07)"; icon_color = "rgba(39,41,55,.25)"
            icon_svg = f'<span style="font-size:.73rem;font-weight:700;color:rgba(39,41,55,.25);line-height:1">{num}</span>'
            border   = "1.5px solid rgba(39,41,55,.08)"
            bg       = "transparent"

        label_color = "#272937" if (done or active) else "rgba(39,41,55,.3)"
        sub_color   = "rgba(39,41,55,.48)" if (done or active) else "rgba(39,41,55,.22)"

        done_row = ""
        if done:
            change_link = (f'<a href="{done_link}" target="_self" style="font-size:.7rem;color:rgba(39,41,55,.38);'
                           f'text-decoration:none;margin-left:6px;transition:color .15s" '
                           f'onmouseover="this.style.color=\'#272937\'" '
                           f'onmouseout="this.style.color=\'rgba(39,41,55,.38)\'">更换 →</a>'
                           ) if done_link else ""
            done_row = (f'<div style="display:flex;align-items:center;margin-top:5px">'
                        f'<span style="font-size:.7rem;font-weight:700;color:#d64635;'
                        f'background:rgba(214,70,53,.1);padding:1px 7px;border-radius:99px">✓ 已完成</span>'
                        f'{change_link}</div>')

        cta = (
            f'<a href="{link}" target="_self" style="display:inline-flex;align-items:center;gap:2px;margin-top:7px;'
            f'font-size:.71rem;font-weight:700;color:#d64635;text-decoration:none;'
            f'padding:3px 9px;border-radius:99px;background:rgba(214,70,53,.09);'
            f'border:1px solid rgba(214,70,53,.18)">'
            f'前往完成 →</a>'
        ) if (link and active and not done) else ""

        return f"""<div style="display:flex;align-items:flex-start;gap:12px;padding:14px 16px;
border-radius:12px;border:{border};background:{bg};transition:border-color .2s">
  <div style="width:30px;height:30px;border-radius:50%;background:{icon_bg};color:{icon_color};
       display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px">
    {icon_svg}
  </div>
  <div style="min-width:0;flex:1">
    <div style="font-size:.86rem;font-weight:700;color:{label_color};line-height:1.35;margin-bottom:2px">
      {label}
    </div>
    <div style="font-size:.74rem;color:{sub_color};line-height:1.5">{sub}</div>
    {done_row}{cta}
  </div>
</div>"""

    _pct = int(_steps_done / 4 * 100)

    _greeting = "欢迎！先上传简历，开启求职之旅"
    if   _steps_done == 4: _greeting = "一切就绪，全力冲刺 Offer！"
    elif _steps_done == 3: _greeting = "最后一步，开始投递吧！"
    elif _steps_done == 2: _greeting = "已完成 2 步，点击「AI 重新匹配」"
    elif _steps_done == 1: _greeting = "继续完成设置，解锁全部功能"

    _matched_cnt = len(st.session_state.matched_jobs) if st.session_state.matched_jobs else 0
    _applied_disp = str(_applied_count) if _applied_count else "—"
    _matched_disp = str(_matched_cnt) if _matched_cnt else "—"

    st.markdown(f"""
    <style>
    .ob-hero {{
      background: linear-gradient(130deg, #272937 0%, #1e2030 55%, #1a1c2a 100%);
      border-radius: 18px; padding: 28px 36px; margin-bottom: 24px;
      display: flex; align-items: center; justify-content: space-between; gap: 24px;
      position: relative; overflow: hidden;
    }}
    .ob-hero::after {{
      content: ''; position: absolute; right: -60px; top: -60px;
      width: 280px; height: 280px; border-radius: 50%;
      background: radial-gradient(circle, rgba(255,255,255,.06) 0%, transparent 65%);
      pointer-events: none;
    }}
    .ob-hero-left {{ flex: 1; min-width: 0; position: relative; z-index: 1; }}
    .ob-hero-stats {{
      display: flex; gap: 24px; margin-top: 14px;
    }}
    .ob-stat-val {{ font-size: 1.45rem; font-weight: 800; color: #fff; line-height: 1; letter-spacing: -.02em; }}
    .ob-stat-lbl {{ font-size: .66rem; color: rgba(255,255,255,.55); margin-top: 3px; }}
    .ob-stat-divider {{ width: 1px; background: rgba(255,255,255,.15); align-self: stretch; margin: 2px 0; }}
    .ob-deco {{
      flex-shrink: 0; width: 180px; height: 120px;
      position: relative; z-index: 1; opacity: .85;
    }}
    </style>

    <div class="ob-hero">
      <div class="ob-hero-left">
        <div style="font-size:1.35rem;font-weight:700;color:#efece8;line-height:1.3;margin:0 0 6px;letter-spacing:-.01em">{_greeting}</div>
        <div class="ob-hero-stats">
          <div>
            <div class="ob-stat-val">{_steps_done}<span style="font-size:.85rem;font-weight:500;color:rgba(255,255,255,.45)">/4</span></div>
            <div class="ob-stat-lbl">步骤完成</div>
          </div>
          <div class="ob-stat-divider"></div>
          <div>
            <div class="ob-stat-val">{_applied_disp}</div>
            <div class="ob-stat-lbl">已投递</div>
          </div>
          <div class="ob-stat-divider"></div>
          <div>
            <div class="ob-stat-val">{_matched_disp}</div>
            <div class="ob-stat-lbl">匹配岗位</div>
          </div>
        </div>
      </div>
      <div class="ob-deco">
        <svg width="180" height="120" viewBox="0 0 180 120" fill="none" xmlns="http://www.w3.org/2000/svg">
          <!-- Back card -->
          <rect x="32" y="18" width="128" height="84" rx="12" fill="rgba(255,255,255,.07)" stroke="rgba(255,255,255,.12)" stroke-width="1"/>
          <!-- Main card -->
          <rect x="18" y="10" width="128" height="84" rx="12" fill="rgba(255,255,255,.12)" stroke="rgba(255,255,255,.18)" stroke-width="1"/>
          <!-- Logo chip -->
          <rect x="30" y="22" width="22" height="22" rx="6" fill="rgba(255,255,255,.18)"/>
          <text x="41" y="37" text-anchor="middle" font-family="-apple-system,sans-serif" font-size="10" font-weight="800" fill="white">字</text>
          <!-- Title bar -->
          <rect x="58" y="24" width="70" height="7" rx="3.5" fill="rgba(255,255,255,.22)"/>
          <!-- Sub bar -->
          <rect x="58" y="36" width="46" height="5" rx="2.5" fill="rgba(255,255,255,.1)"/>
          <!-- Score chip -->
          <rect x="126" y="20" width="14" height="18" rx="5" fill="rgba(255,255,255,.2)"/>
          <text x="133" y="32" text-anchor="middle" font-family="-apple-system,sans-serif" font-size="7" font-weight="800" fill="white">92</text>
          <!-- Divider -->
          <line x1="30" y1="54" x2="138" y2="54" stroke="rgba(255,255,255,.08)" stroke-width="1"/>
          <!-- Progress bar bg -->
          <rect x="30" y="62" width="108" height="5" rx="2.5" fill="rgba(255,255,255,.08)"/>
          <!-- Progress bar fill -->
          <rect x="30" y="62" width="99" height="5" rx="2.5" fill="rgba(255,255,255,.4)"/>
          <!-- Tag chips -->
          <rect x="30" y="74" width="36" height="13" rx="6.5" fill="rgba(255,255,255,.12)"/>
          <rect x="72" y="74" width="30" height="13" rx="6.5" fill="rgba(255,255,255,.1)"/>
          <rect x="108" y="74" width="26" height="13" rx="6.5" fill="rgba(255,255,255,.08)"/>
          <!-- Floating mini card -->
          <rect x="118" y="84" width="56" height="38" rx="9" fill="rgba(255,255,255,.1)" stroke="rgba(255,255,255,.14)" stroke-width="1"/>
          <circle cx="130" cy="97" r="6" fill="rgba(255,255,255,.15)"/>
          <text x="130" y="101" text-anchor="middle" font-family="-apple-system,sans-serif" font-size="7" font-weight="700" fill="white">网</text>
          <rect x="141" y="93" width="28" height="5" rx="2.5" fill="rgba(255,255,255,.18)"/>
          <rect x="141" y="102" width="20" height="4" rx="2" fill="rgba(255,255,255,.1)"/>
          <!-- Sparkle -->
          <path d="M163 6 L164 9.5 L167.5 10.5 L164 11.5 L163 15 L162 11.5 L158.5 10.5 L162 9.5 Z" fill="rgba(255,255,255,.5)"/>
          <!-- Dots -->
          <circle cx="10" cy="108" r="2.5" fill="rgba(255,255,255,.15)"/>
          <circle cx="4" cy="96" r="1.5" fill="rgba(255,255,255,.1)"/>
        </svg>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if _steps_done < 4:
        _s1 = _step_html(1,"上传简历","支持 .docx / .pdf，AI 自动解析内容",
                         _step1_done, not _step1_done,
                         link="?page=progress", done_link="?page=progress")
        _s2 = _step_html(2,"设置求职意向","在「设置」页选择感兴趣的岗位方向",
                         _step2_done, _step1_done and not _step2_done,
                         link="?page=settings", done_link="?page=settings")
        _s3 = _step_html(3,"AI 智能匹配","在「设置」页点击「AI 重新匹配」，或加载示例简历体验",
                         _step3_done, _step2_done and not _step3_done,
                         link="?page=settings")
        _s4 = _step_html(4,"开始投递","在「岗位匹配」页选择岗位并投递",
                         _step4_done, _step3_done and not _step4_done,
                         link="?page=jobs")
        st.markdown(f"""
<div style="background:#fff;border:1px solid rgba(39,41,55,.07);border-radius:18px;
     padding:22px 24px 22px;margin-bottom:16px;
     box-shadow:0 1px 6px rgba(39,41,55,.05)">
  <!-- Header row -->
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
    <div style="display:flex;align-items:center;gap:10px">
      <div style="width:30px;height:30px;border-radius:9px;background:#272937;
           display:flex;align-items:center;justify-content:center;flex-shrink:0">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#efece8" stroke-width="2.2">
          <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
        </svg>
      </div>
      <div>
        <div style="font-size:.9rem;font-weight:700;color:#272937;line-height:1.2">4 步快速开始</div>
        <div style="font-size:.7rem;color:rgba(39,41,55,.38);margin-top:1px">完成设置，解锁 AI 全链路求职功能</div>
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:8px">
      <span style="font-size:.74rem;font-weight:700;color:#d64635;
           background:rgba(214,70,53,.09);padding:3px 11px;border-radius:99px;white-space:nowrap">
        {_steps_done} / 4 完成</span>
    </div>
  </div>
  <!-- Progress bar -->
  <div style="height:4px;background:rgba(39,41,55,.07);border-radius:99px;overflow:hidden;margin:14px 0 16px">
    <div style="height:100%;width:{_pct}%;background:linear-gradient(90deg,#d64635,#e8614f);border-radius:99px;
         transition:width .5s cubic-bezier(.4,0,.2,1)"></div>
  </div>
  <!-- Steps grid -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
    {_s1}
    {_s2}
    {_s3}
    {_s4}
  </div>
</div>
""", unsafe_allow_html=True)

    # ── 简历操作区 ───────────────────────────────────────────────────────────────────
    if _step1_done:
        # 已有简历：显示简历预览条 + 清除按钮
        _resume_preview = st.session_state.resume_text[:80].replace("\n", " ").strip() + "…"
        _is_sample = st.session_state.resume_text == SAMPLE_RESUME
        _resume_label = "示例简历" if _is_sample else f"已加载简历（{len(st.session_state.resume_text)} 字）"
        _rc1, _rc2 = st.columns([5, 1])
        with _rc1:
            st.markdown(f"""
<div style="background:#fff;border:1px solid rgba(39,41,55,.07);border-radius:12px;
     padding:12px 16px;display:flex;align-items:center;gap:10px;margin-bottom:4px">
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.2" style="flex-shrink:0">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
    <polyline points="14 2 14 8 20 8"/>
    <polyline points="9 12 11 14 15 10"/>
  </svg>
  <span style="font-size:.82rem;font-weight:600;color:#272937">{_resume_label}</span>
  {"<span style='font-size:.72rem;color:rgba(39,41,55,.38);margin-left:4px'>· 可在设置页替换为真实简历</span>" if _is_sample else ""}
</div>""", unsafe_allow_html=True)
        with _rc2:
            if st.button("清除简历", use_container_width=True, key="dash_clear_resume"):
                st.session_state.resume_text = ""
                st.session_state.matched_jobs = None   # 清除匹配结果
                st.session_state.diagnosis_result = None
                st.session_state.greetings = {}
                st.rerun()
    # ── 进展面板 ─────────────────────────────────────────────────────────────────────
    _track_jobs   = get_tracking_jobs()
    _cnt_matched  = len(st.session_state.matched_jobs) if st.session_state.matched_jobs else 0
    _cnt_applied  = sum(1 for j in _track_jobs if j.get("status") not in ("pending", "rejected"))
    _cnt_inter    = sum(1 for j in _track_jobs if j.get("status") in ("interview", "chatting", "final_interview", "waiting"))
    _cnt_offer    = sum(1 for j in _track_jobs if j.get("status") == "offer")

    st.markdown(f"""
    <style>
    .prog-section {{ margin:8px 0 28px; }}
    .prog-section-title {{ font-size:1.05rem; font-weight:700; color:#272937; margin-bottom:14px; }}
    .prog-cards {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; }}
    .prog-card {{
      background:#fff; border:1px solid rgba(39,41,55,.07); border-radius:16px;
      padding:22px 20px 18px; cursor:default;
    }}
    .prog-card-val {{ font-size:2rem; font-weight:900; color:#272937; line-height:1; margin-bottom:6px; letter-spacing:-.03em; }}
    .prog-card-lbl {{ font-size:.74rem; font-weight:500; color:rgba(39,41,55,.42); letter-spacing:.02em; }}
    .prog-card-dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:6px; }}
    </style>
    <div class="prog-section">
      <div class="prog-section-title">我的进展</div>
      <div class="prog-cards">
        <div class="prog-card">
          <div class="prog-card-val">{_cnt_matched}</div>
          <div class="prog-card-lbl"><span class="prog-card-dot" style="background:#6366f1"></span>匹配岗位</div>
        </div>
        <div class="prog-card">
          <div class="prog-card-val">{_cnt_applied}</div>
          <div class="prog-card-lbl"><span class="prog-card-dot" style="background:#3b82f6"></span>已投递</div>
        </div>
        <div class="prog-card">
          <div class="prog-card-val">{_cnt_inter}</div>
          <div class="prog-card-lbl"><span class="prog-card-dot" style="background:#10b981"></span>面试中</div>
        </div>
        <div class="prog-card">
          <div class="prog-card-val">{_cnt_offer}</div>
          <div class="prog-card-lbl"><span class="prog-card-dot" style="background:#d64635"></span>Offer</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 推荐岗位轮播（Correlate AI 风格） ─────────────────────────────────────────────
    _rec_jobs = (st.session_state.matched_jobs or load_jobs())[:12]

    def _company_initial(name: str) -> str:
        for ch in name:
            if '一' <= ch <= '鿿':
                return ch
        return name[0].upper() if name else "?"

    # 公司名 → 官网域名，用于获取真实 logo（Google favicon 服务）
    _COMPANY_DOMAIN: dict[str, str] = {
        "字节跳动": "bytedance.com", "TikTok": "tiktok.com",
        "百度": "baidu.com", "阿里巴巴": "alibaba.com", "阿里": "alibaba.com",
        "腾讯": "tencent.com", "京东": "jd.com", "美团": "meituan.com",
        "哔哩哔哩": "bilibili.com", "网易": "netease.com", "快手": "kuaishou.com",
        "小米": "mi.com", "小红书": "xiaohongshu.com", "得物App": "dewu.com",
        "得物": "dewu.com", "知乎": "zhihu.com", "滴滴": "didiglobal.com",
        "滴滴出行": "didiglobal.com", "微博": "weibo.com", "爱奇艺": "iqiyi.com",
        "搜狐": "sohu.com", "大疆": "dji.com", "好未来": "100tal.com",
        "作业帮": "zybang.com", "科大讯飞": "iflytek.com",
        "同花顺": "10jqka.com.cn", "携程": "ctrip.com", "贝壳找房": "ke.com",
        "哈啰": "hellobike.com", "虎牙直播": "huya.com",
        "德勤": "deloitte.com", "明基BenQ": "benq.com", "明基": "benq.com",
        "NIO蔚来": "nio.com", "蔚来": "nio.com", "唯品会": "vip.com",
        "360集团": "360.cn", "蓝湖": "lanhuapp.com",
        "CHARLES&KEITH GROUP": "charleskeith.com",
        "博彦科技": "beyondsoft.com", "亚信科技": "asiainfo.com",
        "同道猎聘": "liepin.com", "猎聘": "liepin.com",
    }

    def _company_logo_url(name: str) -> str:
        domain = _COMPANY_DOMAIN.get(name, "")
        if domain:
            return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
        return ""

    _palette = ["#d64635","#3b82f6","#10b981","#8b5cf6","#f59e0b","#06b6d4","#ec4899","#6366f1"]
    _CPP = 3  # cards per page visible
    _num_pages = max(1, -(-len(_rec_jobs) // _CPP))  # ceil division

    # 生成所有卡片（扁平列表，scroll-snap）
    _all_cards_html = ""
    for _ri, _rj in enumerate(_rec_jobs):
        _col   = _palette[_ri % len(_palette)]
        _cname = _rj.get("company", "?")
        _init  = _company_initial(_cname)
        _logo_url = _company_logo_url(_cname)
        _co   = _esc(_cname)
        _ti   = _esc(_rj.get("title", ""))
        _loc  = _esc(_rj.get("location", "").split("-")[0])
        _sc   = _rj.get("match_score", 0)
        _tier = get_company_tier(_cname)
        # logo: img with fallback to letter
        if _logo_url:
            _logo_html = (
                f'<div class="rc-logo" style="background:{_col}20;color:{_col};overflow:hidden;padding:0">'
                f'<img src="{_logo_url}" width="42" height="42" style="object-fit:contain;border-radius:10px"'
                f' onerror="this.parentElement.innerHTML=\'<span style=&quot;font-size:1.1rem;font-weight:800&quot;>{_init}</span>\'">'
                f'</div>'
            )
        else:
            _logo_html = f'<div class="rc-logo" style="background:{_col}20;color:{_col}">{_init}</div>'
        _all_cards_html += f"""
    <div class="rc">
      <div class="rc-top">
        {_logo_html}
        <a href="#" class="rc-detail" onclick="navTo('jobs');return false;">查看详情 →</a>
      </div>
      <div class="rc-company">{_co}</div>
      <div class="rc-title">{_ti}</div>
      <div class="rc-loc">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" style="flex-shrink:0">
          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>
        </svg>{_loc}
      </div>
      <div class="rc-bottom">
        <span class="rc-score" style="color:{_col};background:{_col}18">{_sc:.0f}分</span>
        <span class="rc-tier">{_tier}</span>
      </div>
    </div>"""

    _dots_html = "".join(
        f'<button class="dot {"active" if i == 0 else ""}" onclick="goTo({i})"></button>'
        for i in range(_num_pages)
    )

    st.components.v1.html(f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
    <style>
    *{{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}}
    body{{background:transparent;}}
    .rec-hdr{{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;}}
    .rec-hdr-title{{font-size:1.05rem;font-weight:700;color:#272937;}}
    .rec-hdr-more{{font-size:.82rem;font-weight:600;color:#d64635;text-decoration:none;}}
    .rec-hdr-more:hover{{text-decoration:underline;}}
    .rec-track{{
      display:flex; gap:14px;
      overflow-x:scroll; scroll-snap-type:x mandatory; scroll-behavior:smooth;
      -webkit-overflow-scrolling:touch; scrollbar-width:none; cursor:grab;
    }}
    .rec-track::-webkit-scrollbar{{display:none;}}
    .rec-track.dragging{{cursor:grabbing; scroll-behavior:auto;}}
    .rc{{
      flex:0 0 calc(33.333% - 10px); scroll-snap-align:start;
      background:#fff; border:1px solid rgba(39,41,55,.08); border-radius:16px;
      padding:20px 18px 16px; display:flex; flex-direction:column;
      transition:box-shadow .18s,transform .18s;
    }}
    .rc:hover{{box-shadow:0 6px 24px rgba(39,41,55,.1); transform:translateY(-2px);}}
    .rc-top{{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px;}}
    .rc-logo{{width:42px;height:42px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:1.1rem;font-weight:800;flex-shrink:0;}}
    .rc-detail{{font-size:.74rem;font-weight:600;color:#d64635;text-decoration:none;white-space:nowrap;padding-top:4px;}}
    .rc-detail:hover{{text-decoration:underline;}}
    .rc-company{{font-size:.74rem;color:rgba(39,41,55,.42);margin-bottom:3px;}}
    .rc-title{{font-size:.88rem;font-weight:700;color:#272937;line-height:1.35;margin-bottom:8px;}}
    .rc-loc{{display:flex;align-items:center;gap:4px;font-size:.72rem;color:rgba(39,41,55,.38);flex:1;}}
    .rc-bottom{{display:flex;align-items:center;justify-content:space-between;margin-top:14px;padding-top:12px;border-top:1px solid rgba(39,41,55,.05);}}
    .rc-score{{font-size:.72rem;font-weight:800;padding:3px 10px;border-radius:99px;}}
    .rc-tier{{font-size:.68rem;color:rgba(39,41,55,.28);font-weight:500;}}
    .rec-dots{{display:flex;justify-content:center;gap:8px;margin-top:16px;}}
    .dot{{width:8px;height:8px;border-radius:50%;background:rgba(39,41,55,.15);cursor:pointer;transition:background .2s,transform .2s;border:none;padding:0;}}
    .dot.active{{background:#d64635;transform:scale(1.25);}}
    </style>
    </head><body>
    <div class="rec-hdr">
      <span class="rec-hdr-title">今日推荐岗位</span>
      <a href="#" class="rec-hdr-more" onclick="navTo('jobs');return false;">全部岗位 →</a>
    </div>
    <div class="rec-track" id="track">{_all_cards_html}</div>
    <div class="rec-dots" id="dots">{_dots_html}</div>
    <script>
    // 利用 allow-same-origin：在父页面创建 <a> 并 click()，绕过 iframe sandbox 的导航限制
    function navTo(page) {{
      try {{
        var a = window.parent.document.createElement('a');
        a.href = '?page=' + page;
        window.parent.document.body.appendChild(a);
        a.click();
        setTimeout(function() {{ try {{ window.parent.document.body.removeChild(a); }} catch(e) {{}} }}, 200);
      }} catch(e) {{
        // 兜底：直接赋值（部分环境可用）
        try {{ window.parent.location.href = '?page=' + page; }} catch(e2) {{}}
      }}
    }}
    var track = document.getElementById('track');
    var dots  = document.querySelectorAll('.dot');
    var cpp   = 3;
    var realNumPages = {_num_pages};

    // ── Clone 第一页卡片追加到末尾，实现向前循环翻页 ──────────────────
    var origCards = Array.from(track.querySelectorAll('.rc'));
    for (var ci = 0; ci < cpp && ci < origCards.length; ci++) {{
      var cl = origCards[ci].cloneNode(true);
      // 克隆节点上的 onclick 需要重新绑定（cloneNode 不复制事件）
      var clLinks = cl.querySelectorAll('a.rc-detail');
      clLinks.forEach(function(a) {{
        a.onclick = function() {{ navTo('jobs'); return false; }};
      }});
      track.appendChild(cl);
    }}

    // ── 圆点同步 ──────────────────────────────────────────────────────
    function updateDots(page) {{
      var p = Math.max(0, Math.min(page, realNumPages - 1));
      dots.forEach(function(d, i) {{ d.classList.toggle('active', i === p); }});
    }}

    // ── goTo：直接跳到第 n 页（n 可以是 realNumPages，即 clone 页）───
    function goTo(n) {{
      track.scrollLeft = n * track.offsetWidth;
    }}

    // ── 滚动监听：同步圆点 + 到达 clone 页后瞬间跳回第 0 页 ──────────
    var settleTimer = null;
    track.addEventListener('scroll', function() {{
      var raw = track.scrollLeft / (track.offsetWidth || 1);
      updateDots(Math.round(raw));
      clearTimeout(settleTimer);
      settleTimer = setTimeout(function() {{
        // 滚动停稳后，若在 clone 页（第 realNumPages 页），瞬间跳回第 0 页
        if (raw >= realNumPages - 0.05) {{
          track.style.scrollBehavior = 'auto';
          track.scrollLeft = 0;
          updateDots(0);
          requestAnimationFrame(function() {{
            requestAnimationFrame(function() {{ track.style.scrollBehavior = ''; }});
          }});
        }}
      }}, 160);
    }}, {{passive: true}});

    // ── 鼠标拖拽（不干扰 click）──────────────────────────────────────
    var dragOrigin = null;
    track.addEventListener('mousedown', function(e) {{
      if (e.button !== 0) return;
      dragOrigin = {{ x: e.clientX, scroll: track.scrollLeft }};
      track.classList.add('dragging');
    }});
    document.addEventListener('mousemove', function(e) {{
      if (!dragOrigin) return;
      track.scrollLeft = dragOrigin.scroll - (e.clientX - dragOrigin.x);
    }});
    document.addEventListener('mouseup', function(e) {{
      if (!dragOrigin) return;
      var dx = Math.abs(e.clientX - dragOrigin.x);
      dragOrigin = null;
      track.classList.remove('dragging');
      if (dx > 5) {{
        var blocker = function(ev) {{
          ev.preventDefault(); ev.stopPropagation();
          document.removeEventListener('click', blocker, true);
        }};
        document.addEventListener('click', blocker, true);
      }}
    }});

    // ── 自动播放：始终向前一页，越过末页进入 clone 页后自动回绕 ──────
    var autoTimer = null;
    function startAuto() {{
      autoTimer = setInterval(function() {{
        var cur = Math.round(track.scrollLeft / (track.offsetWidth || 1));
        goTo(cur + 1);   // 包括进入 clone 页（scroll 监听会在停稳后跳回 0）
      }}, 3500);
    }}
    function stopAuto() {{ clearInterval(autoTimer); autoTimer = null; }}
    startAuto();
    track.addEventListener('mouseenter', stopAuto);
    track.addEventListener('mouseleave', startAuto);
    track.addEventListener('touchstart', stopAuto, {{passive: true}});
    track.addEventListener('touchend', function() {{ setTimeout(startAuto, 2000); }}, {{passive: true}});
    </script>
    </body></html>""", height=310)

    # dashboard 页到此结束，后续内容属于其他页面
    st.stop()

# ════════════════════════════════════════════════════════════════════════════════
# 岗位匹配页  (page=jobs) — Correlate AI 风格重设计
# ════════════════════════════════════════════════════════════════════════════════
if _page == "jobs":
    # ── 页面级样式 ────────────────────────────────────────────────────────────
    st.markdown("""<style>
    /* Jobs page: light blue-gray background */
    .stApp { background: #f0f4f8 !important; }

    /* ── Toolbar ── */
    .jobs-bar {
      display:flex; align-items:center; justify-content:space-between;
      gap:12px; margin-bottom:20px; flex-wrap:wrap;
    }
    .jobs-bar-left  { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
    .jobs-bar-right { display:flex; align-items:center; gap:10px; }
    .pref-pill {
      display:inline-flex; align-items:center; gap:6px;
      padding:7px 14px; border:1.5px solid #cbd5e1; border-radius:99px;
      font-size:.82rem; font-weight:600; color:#334155;
      text-decoration:none!important; background:#fff;
      transition:border-color .15s,color .15s; white-space:nowrap;
    }
    .pref-pill:hover { border-color:#2563eb; color:#2563eb; }
    .filter-chip {
      display:inline-flex; align-items:center;
      padding:5px 11px; background:rgba(37,99,235,.08);
      border:1px solid rgba(37,99,235,.2); border-radius:99px;
      font-size:.74rem; font-weight:600; color:#2563eb; white-space:nowrap;
    }
    .jobs-count { font-size:.82rem; color:#94a3b8; white-space:nowrap; }

    /* ── Stat cards ── */
    .jobs-stats {
      display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px;
    }
    .jobs-stat-card {
      background:#fff; border:1px solid #e2e8f0; border-radius:12px;
      padding:14px 18px; display:flex; align-items:center; gap:12px;
    }
    .jobs-stat-icon {
      width:38px; height:38px; border-radius:10px;
      display:flex; align-items:center; justify-content:center; flex-shrink:0;
    }
    .jobs-stat-val { font-size:1.55rem; font-weight:800; color:#0f172a; line-height:1; }
    .jobs-stat-lbl { font-size:.7rem; color:#94a3b8; margin-top:3px; letter-spacing:.02em; }

    /* ── Job cards v2 ── */
    .jcv2 {
      background:#fff; border:1px solid #e2e8f0; border-radius:14px;
      padding:18px 20px 14px; margin-bottom:8px;
      transition:box-shadow .18s, border-color .18s;
      box-shadow:0 1px 3px rgba(0,0,0,.04);
    }
    .jcv2:hover { box-shadow:0 4px 18px rgba(0,0,0,.09); border-color:#cbd5e1; }
    .jcv2-top { display:flex; align-items:flex-start; gap:14px; }
    .jcv2-logo {
      width:44px; height:44px; border-radius:10px;
      display:flex; align-items:center; justify-content:center;
      font-size:1.1rem; font-weight:800; color:#fff; flex-shrink:0;
      font-family:-apple-system,"PingFang SC",sans-serif;
    }
    .jcv2-body { flex:1; min-width:0; }
    .jcv2-title-row { display:flex; align-items:flex-start; justify-content:space-between; gap:8px; }
    .jcv2-title { font-size:.95rem; font-weight:700; color:#0f172a; line-height:1.35; }
    .jcv2-score-hi  { font-size:1.2rem; font-weight:800; color:#2563eb; letter-spacing:-.02em; flex-shrink:0; }
    .jcv2-score-mid { font-size:1.2rem; font-weight:800; color:#f59e0b; letter-spacing:-.02em; flex-shrink:0; }
    .jcv2-score-lo  { font-size:1.2rem; font-weight:800; color:#94a3b8; letter-spacing:-.02em; flex-shrink:0; }
    .jcv2-meta { font-size:.78rem; color:#64748b; margin-top:4px; }
    .jcv2-tags { display:flex; flex-wrap:wrap; gap:5px; margin-top:10px; }
    .tag-hi   { font-size:.7rem; padding:3px 9px; border-radius:99px; border:1.2px solid #c7d2fe; color:#4f46e5; background:#fff; white-space:nowrap; }
    .tag-lo   { font-size:.7rem; padding:3px 9px; border-radius:99px; border:1.2px solid #fecaca; color:#ef4444; background:#fff; white-space:nowrap; }
    .tag-tier { font-size:.68rem; padding:3px 9px; border-radius:99px; border:1.2px solid #e2e8f0; color:#64748b; background:#fff; white-space:nowrap; }
    .tag-plat { font-size:.68rem; padding:3px 9px; border-radius:99px; border:1.2px solid #e2e8f0; color:#64748b; background:#fff; white-space:nowrap; }

    /* Override Streamlit divider color on this page */
    hr { border-color: #e2e8f0 !important; }
    </style>""", unsafe_allow_html=True)

    all_jobs = st.session_state.matched_jobs or load_jobs()

    _TIER_ORDER = {"大厂": 0, "中厂": 1, "小厂": 2}
    _pool = [
        j for j in all_jobs
        if j.get("match_score", 0) >= min_score
        and (not platforms or j.get("platform") in platforms)
        and (not tiers    or get_company_tier(j.get("company", "")) in tiers)
        and (not cities_filter or j.get("location", "").split("-")[0].strip() in cities_filter)
    ]
    if sort_by == "匹配分（高→低）":
        filtered = sorted(_pool, key=lambda x: x.get("match_score", 0), reverse=True)
    elif sort_by == "公司规模（大厂优先）":
        filtered = sorted(_pool, key=lambda x: (
            _TIER_ORDER.get(get_company_tier(x.get("company", "")), 3),
            -x.get("match_score", 0),
        ))
    else:
        filtered = sorted(_pool, key=lambda x: (
            x.get("location", "").split("-")[0],
            -x.get("match_score", 0),
        ))

    # ── Toolbar ─────────────────────────────────────────────────────────────
    _bar_left, _bar_right = st.columns([5, 1])
    with _bar_left:
        _fchips = ""
        if min_score > 0:
            _fchips += f'<span class="filter-chip">≥ {min_score} 分</span>'
        if platforms:
            _fchips += f'<span class="filter-chip">{"·".join(PLATFORM_NAME.get(p,p) for p in platforms)}</span>'
        if tiers:
            _fchips += f'<span class="filter-chip">{" / ".join(tiers)}</span>'
        st.markdown(f"""<div class="jobs-bar">
  <div class="jobs-bar-left">
    <a href="?page=settings" target="_self" class="pref-pill">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/>
        <line x1="3" y1="18" x2="21" y2="18"/>
      </svg>
      偏好设置
    </a>
    {_fchips}
  </div>
  <div class="jobs-bar-right">
    <span class="jobs-count">共 {len(filtered)} 条岗位</span>
  </div>
</div>""", unsafe_allow_html=True)
    with _bar_right:
        if st.button("⚡ AI 重新匹配", type="primary", use_container_width=True):
            if not st.session_state.resume_text:
                st.error("请先在「设置」上传简历")
            elif not st.session_state.api_key:
                st.error("请先在「设置」填入 API Key")
            else:
                _jraw2 = load_jobs()
                with st.spinner(f"分析 {len(_jraw2)} 条岗位…"):
                    _m2 = asyncio.run(match_jobs(
                        st.session_state.resume_text,
                        [j.copy() for j in _jraw2],
                        st.session_state.preferences,
                    ))
                st.session_state.matched_jobs = _m2
                st.session_state.diagnosis_result = None
                st.session_state.greetings = {}
                st.rerun()

    # ── Stat cards ──────────────────────────────────────────────────────────
    _cnt_high  = sum(1 for j in filtered if j.get("match_score", 0) >= 80)
    _cnt_big   = sum(1 for j in filtered if get_company_tier(j.get("company","")) == "大厂")
    _vis_cities = {j.get("location","").split("-")[0] for j in filtered if j.get("location")}

    st.markdown(f"""<div class="jobs-stats">
  <div class="jobs-stat-card">
    <div class="jobs-stat-icon" style="background:rgba(37,99,235,.09)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2"/>
      </svg>
    </div>
    <div><div class="jobs-stat-val">{len(filtered)}</div><div class="jobs-stat-lbl">匹配岗位</div></div>
  </div>
  <div class="jobs-stat-card">
    <div class="jobs-stat-icon" style="background:rgba(99,102,241,.09)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
      </svg>
    </div>
    <div><div class="jobs-stat-val">{_cnt_high}</div><div class="jobs-stat-lbl">高匹配 ≥80分</div></div>
  </div>
  <div class="jobs-stat-card">
    <div class="jobs-stat-icon" style="background:rgba(245,158,11,.09)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M6 9H4.5a2.5 2.5 0 010-5H6"/><path d="M18 9h1.5a2.5 2.5 0 000-5H18"/>
        <path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/>
        <path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/>
        <path d="M18 2H6v7a6 6 0 0012 0V2z"/>
      </svg>
    </div>
    <div><div class="jobs-stat-val">{_cnt_big}</div><div class="jobs-stat-lbl">大厂机会</div></div>
  </div>
  <div class="jobs-stat-card">
    <div class="jobs-stat-icon" style="background:rgba(16,185,129,.09)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/>
      </svg>
    </div>
    <div><div class="jobs-stat-val">{len(_vis_cities)}</div><div class="jobs-stat-lbl">覆盖城市</div></div>
  </div>
</div>""", unsafe_allow_html=True)

    # ── 策略洞察（折叠）────────────────────────────────────────────────────
    with st.expander("💡 求职策略洞察", expanded=False):
        ins_col1, ins_col2, ins_col3 = st.columns(3)
        with ins_col1:
            st.write("**🎯 优先投递 Top 5**")
            for i, job in enumerate(filtered[:5], 1):
                sc = job.get("match_score", 0)
                st.write(f"{i}. **{job.get('company', '')}** · {job.get('title', '')} — {score_color(sc)} {sc:.0f}分")
        with ins_col2:
            st.write("**📚 岗位高频需求技能**")
            skill_freq = analyze_skill_gaps(filtered or all_jobs)
            max_cnt = skill_freq[0][1] if skill_freq else 1
            for skill, cnt in skill_freq:
                st.write(f"`{skill}`")
                st.progress(cnt / max_cnt)
        with ins_col3:
            st.write("**💡 投递策略建议**")
            high = sum(1 for j in filtered if j.get("match_score", 0) >= 80)
            mid  = sum(1 for j in filtered if 65 <= j.get("match_score", 0) < 80)
            low  = sum(1 for j in filtered if j.get("match_score", 0) < 65)
            st.write(f"• 高匹配（≥80分）**{high}** 条 → 优先冲刺")
            st.write(f"• 中匹配（65-79分）**{mid}** 条 → 优化简历后投递")
            st.write(f"• 低匹配（<65分）**{low}** 条 → 保底备选")
            tier_dist = Counter(get_company_tier(j.get("company","")) for j in filtered[:20])
            st.write(f"• Top 20 中：大厂 **{tier_dist.get('大厂',0)}** / 中厂 **{tier_dist.get('中厂',0)}** / 小厂 **{tier_dist.get('小厂',0)}**")

    # ── 空状态 ──────────────────────────────────────────────────────────────
    if not filtered:
        st.markdown("""<div style="text-align:center;padding:48px 0;color:#94a3b8">
  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="1.5"
       style="margin-bottom:12px" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
  </svg>
  <div style="font-size:.9rem;font-weight:600;color:#64748b;margin-bottom:4px">未找到符合条件的岗位</div>
  <div style="font-size:.8rem">请前往「偏好设置」调整最低匹配分、平台或规模筛选</div>
</div>""", unsafe_allow_html=True)

    # ── 分页逻辑 ──────────────────────────────────────────────────────────
    PAGE_SIZE = 20
    _sig = hashlib.md5(
        json.dumps([min_score, sorted(platforms), sorted(tiers), sorted(cities_filter), sort_by],
                   ensure_ascii=False).encode()
    ).hexdigest()
    if st.session_state._t1_sig != _sig:
        st.session_state.t1_page = 0
        st.session_state._t1_sig = _sig

    total_pages = max(1, (len(filtered) + PAGE_SIZE - 1) // PAGE_SIZE)
    cur_page    = st.session_state.t1_page
    page_jobs   = filtered[cur_page * PAGE_SIZE : (cur_page + 1) * PAGE_SIZE]

    # ── 预加载追踪集合 ─────────────────────────────────────────────────────
    _tracked_ids = {str(j["job_id"]) for j in get_tracking_jobs()}

    # ── 岗位列表 ──────────────────────────────────────────────────────────
    for job in page_jobs:
        job_uid = str(job.get("job_id") or job.get("id", ""))

        # Correlate AI 风格卡片
        st.markdown(_job_card_v2(job), unsafe_allow_html=True)

        # 操作按钮行
        existing_greeting = st.session_state.greetings.get(job_uid)
        btn_c1, btn_c2, btn_c3, btn_c4 = st.columns([2, 2, 2, 2])

        with btn_c1:
            if existing_greeting:
                if st.button("📋 查看打招呼", key=f"show_g_{job_uid}", use_container_width=True):
                    st.session_state[f"expand_g_{job_uid}"] = not st.session_state.get(f"expand_g_{job_uid}", False)
            elif st.session_state.api_key:
                if st.button("✨ AI 打招呼", key=f"btn_greet_{job_uid}", use_container_width=True):
                    with st.spinner("生成中…"):
                        greeting = asyncio.run(generate_greeting(
                            st.session_state.resume_text or SAMPLE_RESUME,
                            job,
                            st.session_state.preferences,
                        ))
                    st.session_state.greetings[job_uid] = greeting
                    st.rerun()

        with btn_c2:
            if job.get("url"):
                st.link_button("🔗 查看原帖", job["url"], use_container_width=True)

        with btn_c3:
            desc = job.get("description") or ""
            req  = job.get("requirements") or ""
            if desc or req:
                _det_open = st.session_state.get(f"expand_d_{job_uid}", False)
                _det_label = "✕ 关闭详情" if _det_open else "📄 岗位详情"
                if st.button(_det_label, key=f"det_{job_uid}", use_container_width=True):
                    st.session_state[f"expand_d_{job_uid}"] = not _det_open
                    st.rerun()

        with btn_c4:
            if job_uid in _tracked_ids:
                st.button("✅ 已追踪", key=f"track_{job_uid}", disabled=True, use_container_width=True)
            else:
                if st.button("➕ 加入追踪", key=f"track_{job_uid}", use_container_width=True):
                    add_job_from_match(job)
                    st.toast(f"已将「{job.get('title', '')}」加入投递追踪 📋")
                    st.rerun()

        # 打招呼文案展开
        if existing_greeting and st.session_state.get(f"expand_g_{job_uid}"):
            st.code(existing_greeting, language=None)

        # Correlate AI 风格两栏详情面板
        if st.session_state.get(f"expand_d_{job_uid}"):
            st.markdown(_job_detail_panel(job), unsafe_allow_html=True)

    # ── 分页控制 ──────────────────────────────────────────────────────────
    if total_pages > 1:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        pg_c1, pg_c2, pg_c3 = st.columns([1, 3, 1])
        with pg_c1:
            if st.button("← 上一页", disabled=(cur_page == 0), use_container_width=True):
                st.session_state.t1_page -= 1
                st.rerun()
        with pg_c2:
            st.markdown(
                f"<div style='text-align:center;color:#94a3b8;font-size:.84rem;padding-top:7px'>"
                f"第 {cur_page+1} / {total_pages} 页 · 共 {len(filtered)} 条</div>",
                unsafe_allow_html=True,
            )
        with pg_c3:
            if st.button("下一页 →", disabled=(cur_page >= total_pages - 1), use_container_width=True):
                st.session_state.t1_page += 1
                st.rerun()


# ────────────────────────────────────────────────────────────────────────────────
# 简历诊断页  (page=resume)
# ────────────────────────────────────────────────────────────────────────────────
if _page != "resume": pass
else:
    st.subheader("📋 简历诊断 · 改写建议 · 面试备考")

    diag_jobs = st.session_state.matched_jobs or load_jobs()
    diag_jobs_sorted = sorted(diag_jobs, key=lambda x: x.get("match_score", 0), reverse=True)[:50]

    job_options = {
        f"{score_color(j.get('match_score',0))} {j.get('title', '')} @ {j.get('company', '')}（{j.get('match_score', 0):.0f}分）": j
        for j in diag_jobs_sorted
    }
    selected_label = st.selectbox("选择目标岗位", list(job_options.keys()))
    selected_job = job_options[selected_label]
    cur_job_id = str(selected_job.get("job_id") or selected_job.get("id", ""))

    # ── 目标岗位摘要 ──
    st.markdown(_job_card(selected_job, compact=False), unsafe_allow_html=True)

    ready = bool(st.session_state.resume_text and st.session_state.api_key)

    if not st.session_state.resume_text:
        st.info("👈 请先在左侧点击「💡 使用示例简历体验」，或上传你的 .docx / .pdf 简历，再点击下方按钮开始分析。")
    elif not st.session_state.api_key:
        st.info("👈 请先在左侧填入 OpenRouter API Key，即可解锁 AI 诊断功能。")

    btn_col1, btn_col2 = st.columns([2, 2])
    with btn_col1:
        run_diag = st.button("🔍 简历诊断 + 改写建议", type="primary", disabled=not ready)
    with btn_col2:
        run_interview = st.button("🎤 面试备考题", disabled=not ready)

    # ── 执行诊断 ──
    if run_diag and ready:
        with st.spinner("AI 深度分析简历，约 15 秒…"):
            result = asyncio.run(diagnose_resume(
                st.session_state.resume_text,
                selected_job,
                st.session_state.preferences,
            ))
        st.session_state.diagnosis_result = result
        st.session_state.diagnosis_job_id = cur_job_id

    # ── 执行面试备考 ──
    if run_interview and ready:
        with st.spinner("AI 生成面试题，约 10 秒…"):
            iv_result = asyncio.run(generate_interview_prep(
                st.session_state.resume_text,
                selected_job,
                st.session_state.preferences,
            ))
        st.session_state.interview_result = iv_result
        st.session_state.interview_job_id = cur_job_id

    # ── 结果区域：分为两个子 Tab ──
    has_diag = bool(
        st.session_state.diagnosis_result and
        st.session_state.diagnosis_job_id == cur_job_id
    )
    has_iv = bool(
        st.session_state.interview_result and
        st.session_state.interview_job_id == cur_job_id
    )

    if has_diag or has_iv:
        st.divider()
        res_tab1, res_tab2 = st.tabs(["🔍 简历诊断结果", "🎤 面试备考材料"])

        # ── 子 Tab 1：简历诊断结果 ──
        with res_tab1:
            if has_diag:
                result = st.session_state.diagnosis_result
                score_val = result.get("score", 0)

                diag_c1, diag_c2, diag_c3 = st.columns([1, 2, 2])
                with diag_c1:
                    st.metric("综合匹配分", f"{score_val} / 100")
                    st.progress(int(score_val) / 100)

                with diag_c2:
                    strengths = result.get("strengths") or []
                    if strengths:
                        st.write("**🎯 核心匹配优势**")
                        for s in strengths:
                            st.success(s)
                    gaps = result.get("gaps") or []
                    if gaps:
                        st.write("**⚠️ 主要差距**")
                        for g in gaps:
                            st.warning(g)

                with diag_c3:
                    improvements = result.get("improvements") or []
                    if improvements:
                        st.write("**✏️ 可落地的改写建议**")
                        for i, tip in enumerate(improvements, 1):
                            st.info(f"**{i}.** {tip}")

                if result.get("summary"):
                    st.divider()
                    st.markdown(f"> 💬 **AI 总结**：{result['summary']}")
            else:
                st.info("点击上方「🔍 简历诊断 + 改写建议」按钮生成诊断报告。")

        # ── 子 Tab 2：面试备考材料 ──
        with res_tab2:
            if has_iv:
                iv = st.session_state.interview_result
                iv_col1, iv_col2 = st.columns([3, 2])
                with iv_col1:
                    questions = iv.get("questions") or []
                    if questions:
                        st.write("**❓ 高频面试题 & 应答思路**")
                        for i, q in enumerate(questions, 1):
                            with st.expander(f"Q{i}. {q.get('q', '')}", expanded=(i == 1)):
                                st.write(f"💡 **应答要点**：{q.get('hint', '')}")

                with iv_col2:
                    key_points = iv.get("key_points") or []
                    if key_points:
                        st.write("**⭐ 面试中需重点强调**")
                        for kp in key_points:
                            st.success(kp)
                    red_flags = iv.get("red_flags") or []
                    if red_flags:
                        st.write("**🚩 需提前准备解释的弱点**")
                        for rf in red_flags:
                            st.warning(rf)
            else:
                st.info("点击上方「🎤 面试备考题」按钮生成面试备考材料。")


# ────────────────────────────────────────────────────────────────────────────────
# Tab 3：投递进度看板（SQLite 后端 · 拖拽式更新）
# ────────────────────────────────────────────────────────────────────────────────

# 看板列定义（icon, 标题, 包含的 status 列表, 左边框色）
_KANBAN_STAGES = [
    ("📋", "待投递",    ["pending"],                            "rgba(39,41,55,.2)"),
    ("📤", "已投递",    ["applied", "viewed"],                  "#272937"),
    ("💬", "面试中",    ["chatting", "interview"],              "#d64635"),
    ("🔥", "终面·等待", ["final_interview", "waiting"],         "#b5391f"),
    ("🎉", "Offer",    ["offer"],                              "#272937"),
]

_TL_STATUS_OPTIONS = [
    "待投递", "已投递", "HR已查看", "沟通中",
    "一面", "二面", "三面", "终面", "等待结果",
    "收到Offer", "已拒绝",
]

@st.dialog("📅 投递时间线")
def _show_timeline(job: dict):
    jid = str(job["job_id"])
    score = job.get("match_score", 0)

    col_title, col_score = st.columns([4, 1])
    with col_title:
        st.markdown(f"**{job.get('company', '')}** · {job.get('title', '')}")
        st.caption(f"{job.get('salary') or '薪资面议'} · {(job.get('location') or '').split('-')[0]}")
    with col_score:
        if score > 0:
            sc_color = "#272937" if score >= 80 else ("#d64635" if score >= 65 else "rgba(39,41,55,.3)")
            st.markdown(
                f"<div style='text-align:right;font-size:1.6em;font-weight:800;color:{sc_color}'>"
                f"{score:.0f}</div>",
                unsafe_allow_html=True,
            )

    st.divider()

    # ── 时间线记录 ──
    # 重新从 DB 拉取，确保显示最新数据
    fresh_jobs = get_tracking_jobs()
    fresh_job  = next((j for j in fresh_jobs if str(j["job_id"]) == jid), job)
    timeline   = fresh_job.get("timeline") or []
    if timeline:
        for ev in reversed(timeline):   # 最新在上
            tl_icon  = TIMELINE_ICONS.get(ev.get("status", ""), "•")
            note_str = f" — {ev['note']}" if ev.get("note") else ""
            st.write(f"`{ev['date']}` {tl_icon} **{ev['status']}**{note_str}")
    else:
        st.info("暂无时间线记录")

    if job.get("match_reason"):
        st.info(f"💡 {job['match_reason']}")

    st.divider()

    # ── 添加进展记录 ──
    st.markdown("**➕ 添加进展记录**")
    with st.form(f"tl_form_{jid}", border=False):
        tl_c1, tl_c2, tl_c3 = st.columns([2, 2, 3])
        ev_date   = tl_c1.date_input("日期", value=_date.today(), label_visibility="collapsed")
        ev_status = tl_c2.selectbox("状态", _TL_STATUS_OPTIONS, label_visibility="collapsed")
        ev_note   = tl_c3.text_input("备注（可选）", placeholder="如：HR约面，周四上午", label_visibility="collapsed")
        if st.form_submit_button("✅ 记录", use_container_width=True, type="primary"):
            add_timeline_event(jid, ev_status, ev_note, str(ev_date))
            st.toast("已记录进展 📅")
            st.rerun()

    st.divider()

    # ── 删除岗位（二次确认）──
    if not st.session_state.get(f"confirm_del_{jid}"):
        if st.button("🗑️ 从追踪中移除此岗位", use_container_width=True):
            st.session_state[f"confirm_del_{jid}"] = True
            st.rerun()
    else:
        st.warning("⚠️ 确认移除？此操作不可撤销，时间线记录一并删除。")
        cc1, cc2 = st.columns(2)
        if cc1.button("✅ 确认移除", type="primary", use_container_width=True, key=f"del_yes_{jid}"):
            delete_job(jid)
            st.session_state.pop(f"confirm_del_{jid}", None)
            st.toast("已移除 🗑️")
            st.rerun()
        if cc2.button("取消", use_container_width=True, key=f"del_no_{jid}"):
            st.session_state.pop(f"confirm_del_{jid}", None)
            st.rerun()


def _move_job(job_uid: str, old_status: str):
    """on_change 回调：检测到状态变化后立即写入 DB。"""
    new_s = st.session_state.get(f"kb_{job_uid}")
    if new_s and new_s != old_status:
        update_status(job_uid, new_s, "")


@st.dialog("✏️ 手动添加岗位")
def _dialog_add_manual():
    st.caption("手动录入一条岗位信息，加入投递追踪。")
    with st.form("manual_add_form", border=False):
        col_a, col_b = st.columns(2)
        title    = col_a.text_input("岗位名称 *", placeholder="如：数据运营实习生")
        company  = col_b.text_input("公司名称 *", placeholder="如：字节跳动")
        col_c, col_d = st.columns(2)
        salary   = col_c.text_input("薪资", placeholder="如：150元/天")
        location = col_d.text_input("城市", placeholder="如：北京")
        url      = st.text_input("岗位链接", placeholder="https://...")
        note     = st.text_input("备注", placeholder="可选，如：内推 / 朋友推荐 等")
        submitted = st.form_submit_button("➕ 加入追踪", type="primary", use_container_width=True)
    if submitted:
        if not title.strip() or not company.strip():
            st.error("岗位名称和公司名称为必填项。")
        else:
            add_job_manual(title, company, salary, location, url, note)
            st.toast(f"已添加「{title.strip()}」到投递追踪 📋")
            st.rerun()


@st.dialog("🎯 从匹配看板选取岗位", width="large")
def _dialog_add_from_pool():
    pool_jobs  = st.session_state.matched_jobs or load_jobs()
    tracked_ids = {str(j["job_id"]) for j in get_tracking_jobs()}
    untracked  = [j for j in pool_jobs if str(j.get("job_id") or j.get("id","")) not in tracked_ids]

    st.caption(f"共 **{len(untracked)}** 条尚未追踪的匹配岗位，点击「加入」即可加入投递追踪。")

    # 搜索框
    kw = st.text_input("🔍 搜索岗位 / 公司", placeholder="输入关键词快速过滤…", label_visibility="collapsed")
    if kw.strip():
        kw_lower = kw.strip().lower()
        untracked = [
            j for j in untracked
            if kw_lower in (j.get("title") or "").lower()
            or kw_lower in (j.get("company") or "").lower()
        ]

    # 排序：分数高→低
    untracked = sorted(untracked, key=lambda x: x.get("match_score", 0), reverse=True)

    if not untracked:
        st.info("没有符合条件的岗位，或全部已加入追踪。")
        return

    # 列表（最多展示 60 条，超出提示搜索缩小范围）
    display = untracked[:60]
    for job in display:
        jid   = str(job.get("job_id") or job.get("id", ""))
        score = job.get("match_score", 0)
        tier  = get_company_tier(job.get("company", ""))
        sc_color = "#272937" if score >= 80 else ("#d64635" if score >= 65 else "rgba(39,41,55,.3)")
        tier_tag = {"大厂": "🏆", "中厂": "🥈", "小厂": "🏅"}.get(tier, "")
        salary = job.get("salary") or "薪资面议"
        city   = (job.get("location") or "").split("-")[0]

        col_info, col_btn = st.columns([5, 1])
        with col_info:
            st.markdown(
                f"**{job.get('title','')}** &nbsp; {tier_tag} {job.get('company','')} "
                f"· {salary} · {city} &nbsp; "
                f"<span style='color:{sc_color};font-weight:700'>{score:.0f}分</span>",
                unsafe_allow_html=True,
            )
        with col_btn:
            if st.button("➕ 加入", key=f"pool_{jid}", use_container_width=True):
                add_job_from_match(job)
                st.toast(f"已添加「{job.get('title','')}」📋")
                st.rerun()

    if len(untracked) > 60:
        st.caption(f"仅展示前 60 条，使用搜索框缩小范围（共 {len(untracked)} 条）。")


if _page != "progress": pass
else:
    _has_resume  = bool(st.session_state.resume_text)
    _is_sample   = st.session_state.resume_text == SAMPLE_RESUME if _has_resume else False
    _resume_words = len(st.session_state.resume_text) if _has_resume else 0

    _STEPS = [
        ("上传简历",  "上传你的简历，AI 自动解析"),
        ("基本信息",  "完善联系方式等"),
        ("教育经历",  "填写学校、专业、学历"),
        ("工作经历",  "添加实习、工作经历"),
        ("求职意向",  "设置目标岗位和城市"),
        ("技能标签",  "填写你的核心技能"),
        ("附加信息",  "作品集、个人网站等"),
    ]

    if "profile_step" not in st.session_state:
        st.session_state.profile_step = 0

    _done = [
        _has_resume and not _is_sample,
        bool(st.session_state.get("prof_phone") or st.session_state.get("prof_location")),
        bool(st.session_state.get("prof_edu")),
        bool(st.session_state.get("prof_exp")),
        bool(st.session_state.get("preferences")),
        bool(st.session_state.get("prof_skills")),
        bool(st.session_state.get("prof_links")),
    ]

    _ps_param = st.query_params.get("ps", "")
    if _ps_param.isdigit() and 0 <= int(_ps_param) < len(_STEPS):
        st.session_state.profile_step = int(_ps_param)
        st.query_params.pop("ps", None)
        st.rerun()

    _step = st.session_state.profile_step
    _step_name, _step_sub = _STEPS[_step]

    # ── CSS ──────────────────────────────────────────────────────────────────
    # :has() lets us style columns by looking at what's inside them,
    # avoiding fragile positional selectors. Supported in all modern browsers.
    st.markdown("""<style>
/* Outer card: the stHorizontalBlock that contains our wizard */
div[data-testid="stHorizontalBlock"]:has(.pw-sidebar-inner) {
    background: #fff;
    border-radius: 16px;
    border: 1px solid rgba(39,41,55,.08);
    box-shadow: 0 1px 8px rgba(39,41,55,.06);
    overflow: hidden;
    gap: 0 !important;
    align-items: stretch !important;
    margin-top: 8px;
}
/* Sidebar column */
div[data-testid="stHorizontalBlock"]:has(.pw-sidebar-inner)
  > div[data-testid="column"]:first-child,
div[data-testid="stHorizontalBlock"]:has(.pw-sidebar-inner)
  > div[data-testid="stColumn"]:first-child {
    border-right: 1px solid rgba(39,41,55,.07);
    padding: 0 !important;
    background: #fff;
}
/* Panel column */
div[data-testid="stHorizontalBlock"]:has(.pw-sidebar-inner)
  > div[data-testid="column"]:last-child,
div[data-testid="stHorizontalBlock"]:has(.pw-sidebar-inner)
  > div[data-testid="stColumn"]:last-child {
    padding: 32px 36px !important;
    background: #fff;
}
/* Remove extra gap/padding Streamlit adds to inner stVerticalBlock */
div[data-testid="stHorizontalBlock"]:has(.pw-sidebar-inner)
  > div > div > [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}
/* Sidebar content */
.pw-sidebar-inner { padding: 24px 0; }
.pw-stitle { font-size:.95rem; font-weight:800; color:#272937; padding:0 22px 2px; }
.pw-ssub   { font-size:.7rem; color:rgba(39,41,55,.38); padding:0 22px 16px; }
.pw-sitem {
    display:flex; align-items:center; gap:10px; padding:11px 22px;
    border-left:3px solid transparent;
    text-decoration:none !important;
    color:inherit !important;
    transition:background .12s;
}
.pw-sitem:hover { background:rgba(39,41,55,.04); text-decoration:none !important; }
.pw-sitem.active { background:rgba(39,41,55,.055); border-left-color:#d64635; }
.pw-sitem-dot {
    width:8px; height:8px; border-radius:50%; flex-shrink:0;
    background:rgba(39,41,55,.15);
}
.pw-sitem.active .pw-sitem-dot { background:#d64635; }
.pw-sitem.sdone  .pw-sitem-dot { background:#272937; }
.pw-sitem-name { font-size:.82rem; font-weight:600; color:rgba(39,41,55,.38); line-height:1.25; }
.pw-sitem-desc { font-size:.67rem; color:rgba(39,41,55,.28); }
.pw-sitem.active .pw-sitem-name { color:#272937; }
.pw-sitem.sdone  .pw-sitem-name { color:rgba(39,41,55,.5); }
.pw-check { margin-left:auto; color:#272937; opacity:.4; flex-shrink:0; }
/* Panel styles */
.pw-panel-hdr { display:flex; align-items:center; justify-content:space-between; margin-bottom:5px; }
.pw-panel-title { font-size:1.1rem; font-weight:800; color:#272937; }
.pw-panel-sub { font-size:.82rem; color:rgba(39,41,55,.4); margin-bottom:20px; margin-top:0; }
.pw-badge { font-size:.67rem; font-weight:700; padding:3px 10px; border-radius:99px; letter-spacing:.04em; }
.pw-badge-prog { background:rgba(39,41,55,.07); color:rgba(39,41,55,.45); }
.pw-badge-done { background:rgba(39,41,55,.11); color:#272937; }
.pw-note {
    background:rgba(214,70,53,.05); border:1px solid rgba(214,70,53,.14);
    border-radius:10px; padding:10px 14px; font-size:.79rem;
    color:#272937; margin-bottom:16px; line-height:1.6;
}
.pw-note b { color:#d64635; }
.pw-flbl { font-size:.68rem; font-weight:700; color:rgba(39,41,55,.38);
    text-transform:uppercase; letter-spacing:.07em; margin-bottom:4px; margin-top:14px; }
.pw-divider { border:none; border-top:1px solid rgba(39,41,55,.07); margin:14px 0; }
/* Nested stHorizontalBlock (inner st.columns) – no card style */
div[data-testid="stHorizontalBlock"]:has(.pw-sidebar-inner)
  div[data-testid="stHorizontalBlock"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    border-radius: 0 !important;
    overflow: visible !important;
    margin-top: 0 !important;
}
div[data-testid="stHorizontalBlock"]:has(.pw-sidebar-inner)
  div[data-testid="stHorizontalBlock"] > div {
    padding: 0 !important;
}
/* ── st.container(border=True) 卡片样式 ── */
[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid rgba(39,41,55,.09) !important;
    border-radius: 14px !important;
    padding: 4px 8px 12px !important;
    margin-bottom: 14px !important;
    background: #fff !important;
}
.pw-sec-title {
    display:flex; align-items:center; gap:8px;
    font-size:.88rem; font-weight:700; color:#272937;
    padding: 14px 0 12px;
    border-bottom: 1px solid rgba(39,41,55,.06);
    margin-bottom: 4px;
}
/* ── 输入框主题红色边框 ──
   stVerticalBlockBorderWrapper 在当前 Streamlit 版本不存在，直接用 [data-baseweb="input"] */
[data-baseweb="input"],
[data-baseweb="textarea"] {
    outline: 1.5px solid rgba(214,70,53,.45) !important;
    outline-offset: -2px !important;
}
[data-baseweb="input"]:focus-within,
[data-baseweb="textarea"]:focus-within {
    outline: 2px solid #d64635 !important;
    outline-offset: -2px !important;
    box-shadow: 0 0 0 3px rgba(214,70,53,.15) !important;
}
</style>""", unsafe_allow_html=True)

    # ── Build sidebar HTML ────────────────────────────────────────────────────
    _chk = '<svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>'

    def _sitem(i):
        name, desc = _STEPS[i]
        cls = "pw-sitem"
        if i == _step: cls += " active"
        elif _done[i]: cls += " sdone"
        chk = _chk if _done[i] else ""
        return (
            f'<a class="{cls}" href="?page=progress&ps={i}" target="_self">'
            f'<span class="pw-sitem-dot"></span>'
            f'<span><div class="pw-sitem-name">{name}</div>'
            f'<div class="pw-sitem-desc">{desc}</div></span>'
            f'<span class="pw-check">{chk}</span></a>'
        )

    _sidebar_html = (
        '<div class="pw-sidebar-inner">'
        '<div class="pw-stitle">完善简历</div>'
        '<div class="pw-ssub">帮助 AI 更好地匹配岗位</div>'
        + "".join(_sitem(i) for i in range(len(_STEPS)))
        + '</div>'
    )

    _badge_cls = "pw-badge-done" if _done[_step] else "pw-badge-prog"
    _badge_txt = "已完成" if _done[_step] else "进行中"

    # ── Two-column layout: sidebar | panel ───────────────────────────────────
    _col_s, _col_p = st.columns([1.1, 2.5], gap="small")

    with _col_s:
        st.markdown(_sidebar_html, unsafe_allow_html=True)

    with _col_p:
        # Panel header
        st.markdown(
            f'<div class="pw-panel-hdr">'
            f'<div class="pw-panel-title">{_step_name}</div>'
            f'<span class="pw-badge {_badge_cls}">{_badge_txt}</span></div>'
            f'<p class="pw-panel-sub">{_step_sub}</p>',
            unsafe_allow_html=True,
        )

        # ── Step content ──────────────────────────────────────────────────────
        if _step == 0:
            if _has_resume and not _is_sample:
                st.success(f"已上传简历（{_resume_words} 字）", icon="✅")
            st.markdown(
                '<div class="pw-note"><b>说明：</b>支持 .docx / .pdf 格式，AI 自动解析内容用于岗位匹配。'
                '也可以直接在下方粘贴文本。</div>',
                unsafe_allow_html=True,
            )

            def _apply_resume_text(txt: str):
                """解析文本 → AI 提取字段 → 写入 session_state → 跳转 step 1。"""
                st.session_state.resume_text = txt
                _extracted = asyncio.run(extract_profile_from_resume(txt))
                if _extracted:
                    _dv = {"硕士", "本科", "博士", "专科", "其他"}
                    st.session_state.prof_lastname   = _extracted.get("lastname", "")
                    st.session_state.prof_firstname  = _extracted.get("firstname", "")
                    st.session_state.prof_email      = _extracted.get("email", "")
                    st.session_state.prof_phone      = _extracted.get("phone", "")
                    st.session_state.prof_location   = _extracted.get("location", "")
                    st.session_state.prof_bio        = _extracted.get("bio", "")
                    st.session_state.prof_github     = _extracted.get("github", "")
                    st.session_state.prof_portfolio  = _extracted.get("portfolio", "")
                    st.session_state.prof_linkedin   = _extracted.get("linkedin", "")
                    st.session_state.prof_school     = _extracted.get("school", "")
                    st.session_state.prof_major      = _extracted.get("major", "")
                    _deg = _extracted.get("degree", "本科")
                    st.session_state.prof_degree     = _deg if _deg in _dv else "本科"
                    st.session_state.prof_gpa        = _extracted.get("gpa", "")
                    st.session_state.prof_edu_dates  = _extracted.get("edu_dates", "")
                    st.session_state.prof_exp        = _extracted.get("exp", "")
                    st.session_state.prof_skills     = _extracted.get("skills", "")
                    if _extracted.get("preferences"):
                        st.session_state.preferences = _extracted["preferences"]
                    _cr = _extracted.get("cities", "")
                    if _cr:
                        st.session_state.filter_cities = [c.strip() for c in _cr.split(",") if c.strip()]
                    st.session_state.prof_saved = True
                st.session_state.profile_step = 1

            _uploaded = st.file_uploader(
                "上传简历文件", type=["pdf", "docx"], label_visibility="collapsed"
            )
            if _uploaded:
                with st.spinner("解析中，AI 自动提取信息…"):
                    try:
                        _suffix = ".pdf" if _uploaded.name.lower().endswith(".pdf") else ".docx"
                        with tempfile.NamedTemporaryFile(delete=False, suffix=_suffix) as _tmp:
                            _tmp.write(_uploaded.read())
                            _tmp_path = _tmp.name
                        _txt = parse_resume(_tmp_path)
                        os.unlink(_tmp_path)
                        _apply_resume_text(_txt)
                        st.rerun()
                    except Exception as _e:
                        st.error(f"解析失败：{_e}")

            # ── 示例简历 ──────────────────────────────────────────────────────
            st.markdown('<div class="pw-divider"></div>', unsafe_allow_html=True)
            _sample_path = Path(__file__).parent / "sample_resume.docx"
            if _sample_path.exists():
                _sc1, _sc2 = st.columns([3, 2])
                with _sc1:
                    st.markdown(
                        '<div style="font-size:.85rem;color:#64748b;padding-top:6px">'
                        '没有简历文件？用示例简历快速体验系统</div>',
                        unsafe_allow_html=True,
                    )
                with _sc2:
                    if st.button("📄 导入示例简历", use_container_width=True, key="pw_load_sample"):
                        with st.spinner("AI 解析示例简历…"):
                            try:
                                _stxt = parse_resume(str(_sample_path))
                                _apply_resume_text(_stxt)
                                st.rerun()
                            except Exception as _e:
                                st.error(f"示例简历加载失败：{_e}")

            st.markdown('<div class="pw-flbl">或直接粘贴简历文本</div>', unsafe_allow_html=True)
            _rt = st.text_area(
                "", value=st.session_state.resume_text or "",
                height=200, placeholder="将简历内容粘贴到这里…",
                label_visibility="collapsed", key="resume_ta_prof",
            )
            if _rt != st.session_state.resume_text:
                st.session_state.resume_text = _rt

        elif _step == 1:
            # JS 直接操作父文档 DOM，设置 inline style 绕过 emotion CSS
            import streamlit.components.v1 as _cv1
            _cv1.html("""<script>
(function(){
  /* outline ≠ border: React/BaseWeb never manages outline in its vdom,
     so these inline styles survive re-renders without being reset. */
  var RED = 'rgba(214,70,53,.45)';
  function applyOutline(){
    var doc = window.parent.document;
    doc.querySelectorAll('[data-baseweb="input"],[data-baseweb="textarea"]').forEach(function(b){
      b.style.setProperty('outline','1.5px solid '+RED,'important');
      b.style.setProperty('outline-offset','-2px','important');
    });
  }
  applyOutline();
  [100,300,800,2000].forEach(function(t){setTimeout(applyOutline,t);});
  var obs = new MutationObserver(function(){
    obs.disconnect();
    applyOutline();
    obs.observe(window.parent.document.body,{childList:true,subtree:true});
  });
  obs.observe(window.parent.document.body,{childList:true,subtree:true});
})();
</script>""", height=0, scrolling=False)

            st.markdown('<div class="pw-note"><b>说明：</b>以下字段已由 AI 根据简历自动填充，请核对后修改，确认无误后点击「下一步」。个人信息仅用于 AI 岗位推荐，不会对外共享。</div>', unsafe_allow_html=True)

            # ── 个人信息 ── st.container(border=True) 真正包裹 widgets ─────────
            with st.container(border=True):
                st.markdown("""<div class="pw-sec-title">
  <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="#272937" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
  个人信息
</div>""", unsafe_allow_html=True)
                _c1, _c2 = st.columns(2)
                with _c1:
                    _ln = st.text_input("姓", value=st.session_state.get("prof_lastname", ""),
                                        placeholder="如：管", key="pi_ln")
                    st.session_state.prof_lastname = _ln
                with _c2:
                    _fn = st.text_input("名", value=st.session_state.get("prof_firstname", ""),
                                        placeholder="如：笑池", key="pi_fn")
                    st.session_state.prof_firstname = _fn
                _c3, _c4 = st.columns(2)
                with _c3:
                    _em = st.text_input("邮箱", value=st.session_state.get("prof_email", ""),
                                        placeholder="your@email.com", key="pi_em")
                    st.session_state.prof_email = _em
                with _c4:
                    _ph = st.text_input("手机号", value=st.session_state.get("prof_phone", ""),
                                        placeholder="+86 138xxxxxxxx", key="pi_phone")
                    st.session_state.prof_phone = _ph
                _c5, _c6 = st.columns(2)
                with _c5:
                    _lc = st.text_input("所在城市", value=st.session_state.get("prof_location", ""),
                                        placeholder="如：北京", key="pi_loc")
                    st.session_state.prof_location = _lc
                with _c6:
                    _bi = st.text_input("一句话简介", value=st.session_state.get("prof_bio", ""),
                                        placeholder="如：应用经济学硕士，擅长数据分析", key="pi_bio")
                    st.session_state.prof_bio = _bi

            # ── 专业链接 ── st.container(border=True) 真正包裹 widgets ─────────
            with st.container(border=True):
                st.markdown("""<div class="pw-sec-title">
  <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="#272937" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>
  专业链接
</div>""", unsafe_allow_html=True)
                _lk_github = st.text_input("GitHub", value=st.session_state.get("prof_github", ""),
                                           placeholder="https://github.com/yourname", key="pi_github")
                st.session_state.prof_github = _lk_github
                _lk_portfolio = st.text_input("作品集 / 个人网站", value=st.session_state.get("prof_portfolio", ""),
                                              placeholder="https://your-portfolio.com", key="pi_portfolio")
                st.session_state.prof_portfolio = _lk_portfolio
                _lk_linkedin = st.text_input("LinkedIn", value=st.session_state.get("prof_linkedin", ""),
                                             placeholder="https://linkedin.com/in/yourname", key="pi_linkedin")
                st.session_state.prof_linkedin = _lk_linkedin
            st.markdown('</div>', unsafe_allow_html=True)

            # 更新完成标志
            st.session_state["prof_phone"] = st.session_state.get("prof_phone", "")
            st.session_state["prof_location"] = st.session_state.get("prof_location", "")

        elif _step == 2:
            st.markdown('<div class="pw-flbl">学校</div>', unsafe_allow_html=True)
            _sc = st.text_input("", value=st.session_state.get("prof_school", ""),
                                placeholder="如：北京大学", label_visibility="collapsed", key="pe_school")
            st.session_state.prof_school = _sc
            st.markdown('<div class="pw-flbl">专业</div>', unsafe_allow_html=True)
            _mj = st.text_input("", value=st.session_state.get("prof_major", ""),
                                placeholder="如：应用经济学", label_visibility="collapsed", key="pe_major")
            st.session_state.prof_major = _mj
            _dc, _gc = st.columns(2)
            with _dc:
                st.markdown('<div class="pw-flbl">学历</div>', unsafe_allow_html=True)
                _opts = ["硕士", "本科", "博士", "专科", "其他"]
                _dg = st.selectbox("", _opts,
                                   index=_opts.index(st.session_state.get("prof_degree", "硕士")),
                                   label_visibility="collapsed", key="pe_deg")
                st.session_state.prof_degree = _dg
            with _gc:
                st.markdown('<div class="pw-flbl">GPA</div>', unsafe_allow_html=True)
                _gp = st.text_input("", value=st.session_state.get("prof_gpa", ""),
                                    placeholder="如：3.9/4.0", label_visibility="collapsed", key="pe_gpa")
                st.session_state.prof_gpa = _gp
            st.markdown('<div class="pw-flbl">在校时间</div>', unsafe_allow_html=True)
            _ed = st.text_input("", value=st.session_state.get("prof_edu_dates", ""),
                                placeholder="如：2022.09 – 2025.06",
                                label_visibility="collapsed", key="pe_dates")
            st.session_state.prof_edu_dates = _ed
            st.session_state.prof_edu = _sc or _mj

        elif _step == 3:
            st.markdown('<div class="pw-flbl">工作 / 实习经历（可粘贴简历对应段落）</div>', unsafe_allow_html=True)
            _ex = st.text_area("", value=st.session_state.get("prof_exp", ""), height=260,
                               placeholder="公司名 | 岗位 | 时间\n- 主要职责与成果…",
                               label_visibility="collapsed", key="pexp_ta")
            st.session_state.prof_exp = _ex

        elif _step == 4:
            st.markdown('<div class="pw-flbl">目标岗位（逗号分隔）</div>', unsafe_allow_html=True)
            _pr = st.text_input("", value=st.session_state.get("preferences", ""),
                                placeholder="如：数据分析，用户运营，策略运营",
                                label_visibility="collapsed", key="pp_prefs")
            st.session_state.preferences = _pr
            st.markdown('<div class="pw-flbl">目标城市（逗号分隔）</div>', unsafe_allow_html=True)
            _ci = st.text_input("", value=",".join(st.session_state.get("filter_cities", [])),
                                placeholder="如：北京,上海,深圳",
                                label_visibility="collapsed", key="pp_cities")
            if _ci:
                st.session_state.filter_cities = [c.strip() for c in _ci.split(",") if c.strip()]
            st.markdown('<div class="pw-flbl">最低匹配分（0–100）</div>', unsafe_allow_html=True)
            _ms = st.slider("", 0, 100, st.session_state.get("min_score", 60),
                            label_visibility="collapsed", key="pp_minscore")
            st.session_state.min_score = _ms

        elif _step == 5:
            st.markdown('<div class="pw-note">技能填写越详细，AI 匹配准确度越高。建议列出工具、语言、方法论等。</div>', unsafe_allow_html=True)
            st.markdown('<div class="pw-flbl">技能（逗号分隔）</div>', unsafe_allow_html=True)
            _sk = st.text_area("", value=st.session_state.get("prof_skills", ""), height=130,
                               placeholder="如：Python, SQL, Tableau, A/B测试, 用户分层",
                               label_visibility="collapsed", key="psk_ta")
            st.session_state.prof_skills = _sk

        elif _step == 6:
            st.markdown('<div class="pw-flbl">个人网站 / 作品集 / GitHub</div>', unsafe_allow_html=True)
            _lk = st.text_area("", value=st.session_state.get("prof_links", ""), height=100,
                               placeholder="https://github.com/yourname\nhttps://your-portfolio.com",
                               label_visibility="collapsed", key="pli_ta")
            st.session_state.prof_links = _lk
            _nt = st.text_area("", value=st.session_state.get("prof_notes", ""), height=80,
                               placeholder="其他补充信息…",
                               label_visibility="collapsed", key="pno_ta")
            st.session_state.prof_notes = _nt

        # ── Back / Next ───────────────────────────────────────────────────────
        st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)
        _bc, _nc = st.columns([1, 2])
        with _bc:
            if _step > 0 and st.button("← 上一步", use_container_width=True, key="pw_back"):
                st.session_state.profile_step -= 1
                st.rerun()
        with _nc:
            _lbl = "完成 ✓" if _step == len(_STEPS) - 1 else "下一步 →"
            if st.button(_lbl, use_container_width=True, type="primary", key="pw_next"):
                if _step == 4 and not st.session_state.get("preferences", "").strip():
                    st.warning("建议填写目标岗位方向，AI 匹配效果更准确。")
                elif _step < len(_STEPS) - 1:
                    st.session_state.profile_step += 1
                    st.rerun()
                else:
                    st.session_state.prof_saved = True
                    st.success("资料已保存！前往「岗位匹配」开始 AI 匹配。")

# ────────────────────────────────────────────────────────────────────────────────
