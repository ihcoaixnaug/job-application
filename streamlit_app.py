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
from matcher import diagnose_resume, generate_greeting, generate_interview_prep, match_jobs
from resume_parser import parse_docx
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
    initial_sidebar_state="expanded",
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
.stApp { background: #efece8 !important; }
header[data-testid="stHeader"] { background: rgba(239,236,232,.96) !important; border-bottom: 1px solid rgba(39,41,55,.08) !important; backdrop-filter: blur(10px); }
section[data-testid="stSidebar"] > div:first-child { background: #efece8 !important; padding-top: 1.5rem; border-right: 1px solid rgba(39,41,55,.08); }
.block-container { padding-top: 2rem !important; padding-bottom: 4rem !important; }

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
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── 常量 ────────────────────────────────────────────────────────────────────────
PLATFORM_NAME = {"boss": "Boss直聘", "shixiseng": "实习僧"}

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
.lp-hero { text-align:center; height:100vh; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:0 0 0; background:radial-gradient(ellipse 90% 70% at 50% 40%, rgba(214,70,53,.07) 0%, transparent 60%); scroll-margin-top:0; }
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
  <a class="lp-logo" href="#"><span style="font-family:'DM Serif Display',serif;font-style:italic;font-size:1.4rem;font-weight:400;color:#d64635;letter-spacing:-.01em;">Offer捕手</span></a>
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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#efece8;font-family:"Noto Serif SC","Songti SC","STSong","SimSun",serif;}
.charts{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;padding:0 0 4px;}
.chart{background:#fff;border:1px solid rgba(39,41,55,.08);border-radius:20px;padding:36px 28px 32px;}
.ct{font-size:17px;font-weight:500;color:#272937;text-align:left;margin-bottom:28px;line-height:1.5;}
.ca{display:flex;align-items:flex-end;gap:0;}
.col{flex:5;display:flex;flex-direction:column;align-items:center;}
.mid{flex:3;display:flex;align-items:center;justify-content:center;padding-bottom:48px;}
.dlt{font-size:13px;font-weight:800;color:#d64635;background:rgba(214,70,53,.08);border:1px solid rgba(214,70,53,.2);border-radius:99px;padding:7px 13px;white-space:nowrap;}
.bz{width:100%;height:180px;position:relative;display:flex;align-items:flex-end;justify-content:center;border-bottom:1.5px solid rgba(39,41,55,.07);}
.bar{width:72px;border-radius:8px 8px 0 0;}
.vb{position:absolute;left:0;right:0;text-align:center;font-size:15px;font-weight:600;color:rgba(39,41,55,.32);}
.va{font-size:40px;font-weight:800;color:#d64635;letter-spacing:-.04em;line-height:1;margin-bottom:10px;}
.lbl{font-size:14px;color:rgba(39,41,55,.32);margin-top:14px;text-align:center;}
.lbl.hi{color:#d64635;font-weight:700;}
</style></head><body>
<div class="charts">
  <div class="chart">
    <p class="ct">精准岗位发现量<br>（条 / 周）</p>
    <div class="ca">
      <div class="col">
        <div class="bz">
          <div class="bar" style="height:18px;background:rgba(39,41,55,.1);"></div>
          <span class="vb" style="bottom:22px;">20</span>
        </div>
        <div class="lbl">手动搜索</div>
      </div>
      <div class="mid"><div class="dlt">↑ +10×</div></div>
      <div class="col">
        <div class="va">200</div>
        <div class="bz">
          <div class="bar" style="height:180px;background:#d64635;"></div>
        </div>
        <div class="lbl hi">Offer 捕手</div>
      </div>
    </div>
  </div>
  <div class="chart">
    <p class="ct">单次投递准备时间<br>（分钟）</p>
    <div class="ca">
      <div class="col">
        <div class="va" style="font-size:36px;color:rgba(39,41,55,.35);">25</div>
        <div class="bz">
          <div class="bar" style="height:180px;background:rgba(39,41,55,.1);"></div>
        </div>
        <div class="lbl">手动准备</div>
      </div>
      <div class="mid"><div class="dlt">↓ −92%</div></div>
      <div class="col">
        <div class="bz">
          <div class="bar" style="height:14px;background:#d64635;"></div>
          <span class="vb" style="bottom:18px;">2</span>
        </div>
        <div class="lbl hi">Offer 捕手</div>
      </div>
    </div>
  </div>
  <div class="chart">
    <p class="ct">简历—JD 契合度</p>
    <div class="ca">
      <div class="col">
        <div class="bz">
          <div class="bar" style="height:80px;background:rgba(39,41,55,.1);"></div>
          <span class="vb" style="bottom:84px;">40%</span>
        </div>
        <div class="lbl">凭感觉筛选</div>
      </div>
      <div class="mid"><div class="dlt">↑ ×2.2</div></div>
      <div class="col">
        <div class="va">90%</div>
        <div class="bz">
          <div class="bar" style="height:180px;background:#d64635;"></div>
        </div>
        <div class="lbl hi">Offer 捕手</div>
      </div>
    </div>
  </div>
</div>
<script>
function resizeCharts(){
  var h=document.documentElement.scrollHeight;
  window.parent.postMessage({type:'streamlit:setFrameHeight',height:h},'*');
}
window.addEventListener('load',resizeCharts);
setTimeout(resizeCharts,300);
(function(){
  var bars=document.querySelectorAll('.bar');
  var targets=Array.from(bars).map(function(b){return b.style.height;});
  bars.forEach(function(b){b.style.height='0';b.style.transition='height .9s cubic-bezier(.22,1,.36,1)';});
  var charts=document.querySelectorAll('.chart');
  var obs=new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      if(e.isIntersecting){
        bars.forEach(function(b,i){setTimeout(function(){b.style.height=targets[i];},i*80);});
        obs.unobserve(e.target);
      }
    });
  },{threshold:0.3});
  var obs2=new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      if(e.isIntersecting){e.target.style.opacity='1';e.target.style.transform='translateY(0)';obs2.unobserve(e.target);}
    });
  },{threshold:0.1});
  charts.forEach(function(c,i){
    c.style.opacity='0';c.style.transform='translateY(20px)';
    c.style.transition='opacity .6s ease '+(i*.12)+'s,transform .6s ease '+(i*.12)+'s';
    obs2.observe(c);if(i===0)obs.observe(c);
  });
})();
</script>
</body></html>""", height=480)

    st.markdown("""<div style="padding-top:56px"><span class="lp-section-label">用户评价</span></div>""",
                unsafe_allow_html=True)

    st.components.v1.html("""<!DOCTYPE html><html><head><meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#efece8;font-family:"Noto Serif SC","Songti SC","STSong","SimSun",serif;}
.quotes{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;}
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
.wrap{background:rgba(39,41,55,.03);border:1px solid rgba(39,41,55,.08);border-radius:20px;overflow:visible;}
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
  <span style="font-family:'DM Serif Display',serif;font-style:italic;color:rgba(39,41,55,.3);font-size:.82rem;">Offer捕手</span>
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


# ── 侧边栏 ──────────────────────────────────────────────────────────────────────
with st.sidebar:
    # ── 品牌 Header ──
    st.markdown("""
<div style="display:flex;align-items:center;gap:10px;padding:4px 0 12px">
  <span style="font-size:1.5rem;line-height:1">🎯</span>
  <div>
    <div style="font-size:1rem;font-weight:800;color:#d64635;letter-spacing:-.01em;line-height:1.2">Offer捕手</div>
    <div style="font-size:.7rem;color:#9ca3af;line-height:1.3">AI 求职全链路助手</div>
  </div>
</div>
""", unsafe_allow_html=True)
    if st.button("← 返回首页", use_container_width=True):
        st.session_state.show_landing = True
        st.rerun()
    st.divider()

    # API Key 输入框（始终显示，已配置时 placeholder 提示即可）
    _key_set = bool(st.session_state.api_key)
    api_key_input = st.text_input(
        "OpenRouter API Key",
        value="",
        type="password",
        placeholder="已配置，输入新 Key 可覆盖" if _key_set else "sk-or-v1-...",
        help="在 openrouter.ai 免费注册获取，支持 DeepSeek / Claude / GPT 等模型",
    )
    if api_key_input:
        set_api_key(api_key_input)
        st.rerun()
    st.caption("✅ 已配置" if _key_set else "⚠️ 未配置，将展示示例匹配分数")

    st.divider()

    # 简历
    st.subheader("📄 我的简历")
    if st.session_state.resume_text:
        # ── 已加载状态 ──
        st.success(f"✅ 已加载简历（{len(st.session_state.resume_text)} 字）")
        with st.expander("👁️ 查看简历全文"):
            st.text_area(
                "简历内容",
                value=st.session_state.resume_text,
                height=300,
                label_visibility="collapsed",
                key="resume_preview",
            )
        if st.button("🔄 换一份简历", use_container_width=True):
            st.session_state.resume_text = ""
            st.rerun()
    else:
        # ── 未加载状态 ──
        resume_file = st.file_uploader("上传简历（.docx）", type=["docx"])
        if resume_file:
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                tmp.write(resume_file.read())
                tmp_path = tmp.name
            st.session_state.resume_text = parse_docx(tmp_path)
            st.rerun()
        if st.button("💡 使用示例简历体验", use_container_width=True,
                     help="直接加载内置示例简历，无需上传"):
            st.session_state.resume_text = SAMPLE_RESUME
            st.rerun()

    st.divider()

    # 求职意向
    st.subheader("🎯 求职意向")
    preferences_input = st.text_input(
        "方向偏好", value=st.session_state.preferences,
        placeholder="如：数据运营、产品运营、商业分析",
    )
    st.session_state.preferences = preferences_input

    # 高级筛选（折叠，减少侧边栏视觉噪音）
    with st.expander("🔍 高级筛选"):
        min_score = st.slider("最低匹配分", 0, 100, 60)
        platforms = st.multiselect(
            "招聘平台（空 = 不限）", ["boss", "shixiseng"],
            default=[],
            format_func=lambda x: PLATFORM_NAME.get(x, x),
            placeholder="不限平台",
        )
        tiers = st.multiselect(
            "公司规模（空 = 不限）", ["大厂", "中厂", "小厂"],
            default=[],
            placeholder="不限规模",
        )
        _all_cities = sorted(set(
            j.get("location", "").split("-")[0].strip()
            for j in load_jobs()
            if j.get("location", "").strip()
        ))
        cities_filter = st.multiselect(
            "城市（空 = 不限）", _all_cities,
            default=[],
            placeholder="不限城市",
        )
        sort_by = st.selectbox(
            "排序方式",
            ["匹配分（高→低）", "公司规模（大厂优先）", "城市"],
        )
    st.divider()
    if st.button("🤖 AI 重新匹配", type="primary", use_container_width=True):
        if not st.session_state.resume_text:
            st.error("请先上传简历或点击「使用示例简历体验」")
        elif not st.session_state.api_key:
            st.error("请先填入 API Key")
        else:
            jobs_raw = load_jobs()
            with st.spinner(f"AI 正在分析 {len(jobs_raw)} 条岗位，约需 1-2 分钟…"):
                matched = asyncio.run(match_jobs(
                    st.session_state.resume_text,
                    [j.copy() for j in jobs_raw],
                    st.session_state.preferences,
                ))
            st.session_state.matched_jobs = matched
            st.session_state.diagnosis_result = None
            st.session_state.interview_result = None
            st.session_state.greetings = {}
            st.rerun()



# ── 主内容区 ────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "📊 岗位匹配看板",
    "📋 简历诊断与优化",
    "📈 投递进度追踪",
])


# ────────────────────────────────────────────────────────────────────────────────
# Tab 1：岗位匹配看板
# ────────────────────────────────────────────────────────────────────────────────
with tab1:
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
    else:  # 城市
        filtered = sorted(_pool, key=lambda x: (
            x.get("location", "").split("-")[0],
            -x.get("match_score", 0),
        ))

    # ── 概览指标 ──
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📋 匹配岗位", len(filtered))
    c2.metric("🌟 高匹配 ≥80分", sum(1 for j in filtered if j.get("match_score", 0) >= 80))
    c3.metric("🏆 大厂机会", sum(1 for j in filtered if get_company_tier(j.get("company", "")) == "大厂"))
    _vis_cities = {j.get("location", "").split("-")[0] for j in filtered if j.get("location")}
    c4.metric("📍 覆盖城市", len(_vis_cities))

    # ── 策略洞察（默认折叠，不遮挡岗位列表）──
    with st.expander("🧠 求职策略洞察", expanded=False):
        ins_col1, ins_col2, ins_col3 = st.columns(3)

        with ins_col1:
            st.write("**🎯 优先投递 Top 5**")
            for i, job in enumerate(filtered[:5], 1):
                score = job.get("match_score", 0)
                st.write(f"{i}. **{job.get('company', '')}** · {job.get('title', '')} — {score_color(score)} {score:.0f}分")

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
            mid = sum(1 for j in filtered if 65 <= j.get("match_score", 0) < 80)
            low = sum(1 for j in filtered if j.get("match_score", 0) < 65)
            st.write(f"• 高匹配（≥80分）**{high}** 条 → 优先冲刺")
            st.write(f"• 中匹配（65-79分）**{mid}** 条 → 优化简历后投递")
            st.write(f"• 低匹配（<65分）**{low}** 条 → 保底备选")
            tier_dist = Counter(get_company_tier(j.get("company", "")) for j in filtered[:20])
            st.write(f"• Top 20 中：大厂 **{tier_dist.get('大厂',0)}** 个 / 中厂 **{tier_dist.get('中厂',0)}** 个 / 小厂 **{tier_dist.get('小厂',0)}** 个")

    st.divider()

    # ── 空状态 ──
    if not filtered:
        st.info("📭 未找到符合条件的岗位，请调整左侧的「最低匹配分」、「招聘平台」或「公司规模」筛选条件。")

    # ── 分页逻辑 ──
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

    # ── 预加载已追踪的 job_id 集合（用于按钮状态）──
    _tracked_ids = {str(j["job_id"]) for j in get_tracking_jobs()}

    # ── 岗位卡片（对标参考设计：直接展示，无 expander）──
    for job in page_jobs:
        job_uid = str(job.get("job_id") or job.get("id", ""))

        # HTML 卡片
        st.markdown(_job_card(job, compact=False), unsafe_allow_html=True)

        # 操作按钮行（紧贴卡片底部）
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
                st.link_button("🔗 查看岗位", job["url"], use_container_width=True)

        with btn_c3:
            desc = job.get("description") or ""
            req  = job.get("requirements") or ""
            if desc or req:
                if st.button("📄 岗位详情", key=f"det_{job_uid}", use_container_width=True):
                    st.session_state[f"expand_d_{job_uid}"] = not st.session_state.get(f"expand_d_{job_uid}", False)

        with btn_c4:
            if job_uid in _tracked_ids:
                st.button("✅ 已追踪", key=f"track_{job_uid}", disabled=True, use_container_width=True)
            else:
                if st.button("➕ 加入追踪", key=f"track_{job_uid}", use_container_width=True):
                    add_job_from_match(job)
                    st.toast(f"已将「{job.get('title', '')}」加入投递追踪 📋")
                    st.rerun()

        # 可展开：打招呼文案（st.code 自带复制按钮）
        if existing_greeting and st.session_state.get(f"expand_g_{job_uid}"):
            st.code(existing_greeting, language=None)

        # 可展开：岗位详情
        if st.session_state.get(f"expand_d_{job_uid}"):
            desc = job.get("description") or ""
            req  = job.get("requirements") or ""
            with st.container(border=True):
                if desc:
                    st.markdown(f"**岗位描述**\n\n{desc[:400]}{'…' if len(desc) > 400 else ''}")
                if req:
                    st.markdown(f"**岗位要求**\n\n{req[:300]}{'…' if len(req) > 300 else ''}")

    # ── 分页控制栏 ──
    if total_pages > 1:
        st.divider()
        pg_c1, pg_c2, pg_c3 = st.columns([1, 3, 1])
        with pg_c1:
            if st.button("← 上一页", disabled=(cur_page == 0), use_container_width=True):
                st.session_state.t1_page -= 1
                st.rerun()
        with pg_c2:
            st.markdown(
                f"<div style='text-align:center;color:#6b7280;font-size:.87em;padding-top:6px'>"
                f"第 {cur_page+1} / {total_pages} 页 · 共 {len(filtered)} 条岗位</div>",
                unsafe_allow_html=True,
            )
        with pg_c3:
            if st.button("下一页 →", disabled=(cur_page >= total_pages - 1), use_container_width=True):
                st.session_state.t1_page += 1
                st.rerun()


# ────────────────────────────────────────────────────────────────────────────────
# Tab 2：简历诊断与优化
# ────────────────────────────────────────────────────────────────────────────────
with tab2:
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
        st.info("👈 请先在左侧点击「💡 使用示例简历体验」，或上传你的 .docx 简历，再点击下方按钮开始分析。")
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


with tab3:
    track_jobs = get_tracking_jobs()  # 每次从 DB 读取，确保即时更新
    counts = {s: sum(1 for j in track_jobs if j.get("status") == s) for s in STATUS_ORDER}

    st.subheader("📈 投递进度追踪")

    # ── 添加岗位操作区 ──
    add_c1, add_c2, _ = st.columns([2, 2, 6])
    with add_c1:
        if st.button("✏️ 手动添加岗位", use_container_width=True):
            _dialog_add_manual()
    with add_c2:
        if st.button("🎯 从匹配看板选取", use_container_width=True):
            _dialog_add_from_pool()

    # ── 关键指标 ──
    _applied_cnt  = sum(counts.get(s, 0) for s in ["applied", "viewed", "chatting", "interview", "final_interview", "waiting", "offer"])
    _interview_cnt = sum(counts.get(s, 0) for s in ["interview", "final_interview", "waiting", "offer"])
    _offer_cnt    = counts.get("offer", 0)
    _iv_rate      = f"{_interview_cnt/_applied_cnt*100:.0f}%" if _applied_cnt else "—"
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("📤 已投递", _applied_cnt)
    k2.metric("💬 面试中", sum(counts.get(s, 0) for s in ["interview", "final_interview"]))
    k3.metric("⏳ 等待结果", counts.get("waiting", 0))
    k4.metric("🎉 Offer", _offer_cnt)
    k5.metric("📈 面试率", _iv_rate)

    # ── 漏斗进度条 ──
    _funnel = [
        ("📤 已投递",   sum(counts.get(s, 0) for s in ["applied", "viewed", "chatting", "interview", "final_interview", "waiting", "offer"])),
        ("💬 进入面试",  sum(counts.get(s, 0) for s in ["interview", "final_interview", "waiting", "offer"])),
        ("⏳ 等待结果",  sum(counts.get(s, 0) for s in ["waiting", "offer"])),
        ("🎉 获得 Offer", counts.get("offer", 0)),
    ]
    _base = _funnel[0][1] or 1
    for _fl, _fv in _funnel:
        st.columns([3, 1])[0].progress(_fv / _base, text=f"{_fl}  {_fv} 条")

    st.divider()

    # ── 看板搜索 ──
    kb_search = st.text_input(
        "搜索看板",
        placeholder="🔍 按公司名或岗位名过滤…",
        label_visibility="collapsed",
        key="kb_search",
    )

    # ── 看板：逐行渲染，保证跨列对齐 ──────────────────────────────────────────
    # 1. 先按列整理好卡片列表（应用搜索过滤）
    _kb_kw = kb_search.strip().lower()
    _stage_job_lists = [
        [
            j for j in track_jobs
            if j.get("status") in stage_statuses
            and (
                not _kb_kw
                or _kb_kw in (j.get("title") or "").lower()
                or _kb_kw in (j.get("company") or "").lower()
            )
        ]
        for (_, _, stage_statuses, _) in _KANBAN_STAGES
    ]

    # 2. 表头行（一次性渲染）
    hdr_cols = st.columns(len(_KANBAN_STAGES))
    for col_obj, (icon, stage_lbl, stage_statuses, col_color), stage_jobs in zip(
        hdr_cols, _KANBAN_STAGES, _stage_job_lists
    ):
        with col_obj:
            st.markdown(
                f'<div class="kb-hd">'
                f'<span class="kb-dot" style="background:{col_color}"></span>'
                f'<span>{stage_lbl}</span>'
                f'<span class="kb-cnt">{len(stage_jobs)}</span>'
                f'</div>'
                f'<div class="kb-rule" style="background:{col_color}"></div>',
                unsafe_allow_html=True,
            )

    # 3. 卡片区：逐行渲染 — 每行新建一组 5 列，确保同行高度对齐
    max_rows = max((len(jl) for jl in _stage_job_lists), default=0)
    for row_idx in range(max_rows):
        row_cols = st.columns(len(_KANBAN_STAGES))
        for col_obj, (icon, stage_lbl, stage_statuses, col_color), stage_jobs in zip(
            row_cols, _KANBAN_STAGES, _stage_job_lists
        ):
            with col_obj:
                if row_idx >= len(stage_jobs):
                    # 占位：保持列宽但不渲染内容
                    st.empty()
                    continue
                job = stage_jobs[row_idx]
                job_uid = str(job["job_id"])
                cur_st  = job.get("status", "pending")

                st.markdown(_job_card(job, compact=True), unsafe_allow_html=True)
                st.selectbox(
                    "移至",
                    options=STATUS_ORDER,
                    index=STATUS_ORDER.index(cur_st) if cur_st in STATUS_ORDER else 0,
                    format_func=lambda s: f"{STATUS_CONFIG[s][0]} {STATUS_CONFIG[s][1]}",
                    key=f"kb_{job_uid}",
                    label_visibility="collapsed",
                    on_change=_move_job,
                    args=(job_uid, cur_st),
                )
                if st.button("📋 时间线", key=f"tl_{job_uid}", use_container_width=True):
                    _show_timeline(job)

    # ── 已拒绝（折叠，逐行对齐）──
    rejected_jobs = [j for j in track_jobs if j.get("status") == "rejected"]
    if rejected_jobs:
        st.divider()
        with st.expander(f"❌ 已拒绝 ({len(rejected_jobs)})", expanded=False):
            rej_cols_per_row = 5
            for row_start in range(0, len(rejected_jobs), rej_cols_per_row):
                row_batch = rejected_jobs[row_start : row_start + rej_cols_per_row]
                # pad to 5 so columns stay even
                padded = row_batch + [None] * (rej_cols_per_row - len(row_batch))
                rej_row_cols = st.columns(rej_cols_per_row)
                for col_obj, job in zip(rej_row_cols, padded):
                    with col_obj:
                        if job is None:
                            st.empty()
                            continue
                        job_uid = str(job["job_id"])
                        cur_st  = job.get("status", "rejected")
                        st.markdown(_job_card(job, compact=True), unsafe_allow_html=True)
                        st.selectbox(
                            "移至",
                            options=STATUS_ORDER,
                            index=STATUS_ORDER.index(cur_st) if cur_st in STATUS_ORDER else 0,
                            format_func=lambda s: f"{STATUS_CONFIG[s][0]} {STATUS_CONFIG[s][1]}",
                            key=f"kb_{job_uid}",
                            label_visibility="collapsed",
                            on_change=_move_job,
                            args=(job_uid, cur_st),
                        )


# ────────────────────────────────────────────────────────────────────────────────
