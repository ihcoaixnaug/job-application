"""AI 求职智能匹配助手 — Streamlit 前端"""
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
    page_title="AI 求职智能匹配助手",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 全局卡片 CSS（对标参考设计）────────────────────────────────────────────────────
st.markdown("""
<style>
/* 卡片容器 */
.jc{background:#fff;border:1px solid #e5e7eb;border-radius:10px;
    padding:12px 14px 10px;margin:0 0 6px;
    box-shadow:0 1px 4px rgba(0,0,0,.07);font-family:-apple-system,sans-serif}
/* 标题行 */
.jc-hd{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.jc-title{font-weight:700;font-size:.94em;color:#111827;flex:1}
.jc-score{font-weight:800;font-size:1.2em;white-space:nowrap}
.sc-hi{color:#10b981}.sc-mid{color:#f59e0b}.sc-lo{color:#ef4444}
/* 元信息行 */
.jc-meta{display:flex;align-items:center;gap:5px;flex-wrap:wrap;
         margin-top:4px;font-size:.79em;color:#6b7280}
/* 分数进度条 */
.jc-bar-bg{height:4px;background:#e5e7eb;border-radius:2px;margin:6px 0;overflow:hidden}
.jc-bar{height:100%;border-radius:2px}
.bar-hi{background:linear-gradient(90deg,#10b981,#6ee7b7)}
.bar-mid{background:linear-gradient(90deg,#f59e0b,#fcd34d)}
.bar-lo{background:linear-gradient(90deg,#ef4444,#fca5a5)}
/* 匹配胶囊 */
.jc-pills{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.jp{font-size:.73em;padding:2px 8px;border-radius:12px}
.jp-pos{background:#dcfce7;color:#15803d}
.jp-neg{background:#fff7ed;color:#c2410c}
.jp-tip{background:#eff6ff;color:#1d4ed8}
/* 徽章 */
.bd{display:inline-block;font-size:.71em;padding:1px 6px;border-radius:4px;
    font-weight:600;line-height:1.6;vertical-align:middle}
.bd-big{background:#fef3c7;color:#d97706}
.bd-mid{background:#d1fae5;color:#059669}
.bd-sml{background:#f3f4f6;color:#6b7280}
.bd-boss{background:#1e293b;color:#fff}
.bd-shix{background:#0ea5e9;color:#fff}
/* 看板紧凑卡片 —— 独立 class，避免影响 Tab1 全卡片 */
.jc-compact{min-height:140px;display:flex;flex-direction:column}
.jc-compact .jc-pills{flex:1;align-content:flex-start}
/* 看板列头 */
.kb-hd{font-weight:700;font-size:.9em;display:flex;align-items:center;gap:6px;
       margin-bottom:4px}
.kb-dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.kb-cnt{background:#f3f4f6;color:#6b7280;font-size:.78em;
        padding:1px 7px;border-radius:10px;font-weight:600}
/* 看板列色条 */
.kb-rule{height:3px;border-radius:2px;margin-bottom:10px}
/* 按钮行与卡片之间紧贴 */
div[data-testid="stMarkdownContainer"]+div[data-testid="stHorizontalBlock"]{margin-top:-4px}
div[data-testid="stHorizontalBlock"]+div[data-testid="stMarkdownContainer"]{margin-top:4px}

/* ── 整体页面背景（浅灰，与参考一致）── */
.stApp{background:#F5F7FA}
section[data-testid="stSidebar"]>div:first-child{background:#F0F4F8;padding-top:1.2rem}

/* ── 侧边栏分区卡片感 ── */
section[data-testid="stSidebar"] .stTextInput>div,
section[data-testid="stSidebar"] .stFileUploader>div,
section[data-testid="stSidebar"] .stSelectbox>div{
    background:#fff;border-radius:8px}
section[data-testid="stSidebar"] h3{
    font-size:.9rem!important;font-weight:700;color:#134E4A;
    border-left:3px solid #0D9488;padding-left:8px;margin:14px 0 6px}

/* ── 主内容区（Tab 区域）白色卡片感 ── */
div[data-testid="stTabs"] > div:last-child{
    background:#fff;border-radius:12px;
    padding:16px 20px;
    box-shadow:0 1px 6px rgba(0,0,0,.06)}

/* ── 按钮样式 ── */
button[kind="primary"]{border-radius:6px!important;font-weight:600!important}
button[kind="secondary"]{border-radius:6px!important;border-color:#e5e7eb!important;
    color:#374151!important;font-weight:500!important}
button[kind="secondary"]:hover{background:#f9fafb!important;border-color:#0D9488!important}

/* ── 指标卡 ── */
div[data-testid="stMetric"]{
    background:#fff;border-radius:8px;padding:10px 14px;
    box-shadow:0 1px 3px rgba(0,0,0,.06);border:1px solid #e5e7eb}

/* ── Tab 标签 ── */
button[data-baseweb="tab"]{font-weight:600!important;font-size:.88rem!important}
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
        "preferences": "数据运营/策略运营/数据分析",
        "diagnosis_result": None,
        "diagnosis_job_id": None,
        "interview_result": None,
        "interview_job_id": None,
        "greetings": {},
        "t1_page": 0,
        "_t1_sig": None,
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


# ── 侧边栏 ──────────────────────────────────────────────────────────────────────
with st.sidebar:
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
    resume_file = st.file_uploader("上传简历（.docx）", type=["docx"])
    if resume_file:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(resume_file.read())
            tmp_path = tmp.name
        st.session_state.resume_text = parse_docx(tmp_path)
        st.success(f"✅ 已解析 {len(st.session_state.resume_text)} 字")

    if st.button("💡 使用示例简历体验", use_container_width=True,
                 help="直接加载内置示例简历，无需上传"):
        st.session_state.resume_text = SAMPLE_RESUME
        st.rerun()

    if st.session_state.resume_text:
        st.caption(f"当前简历：{len(st.session_state.resume_text)} 字")
        with st.expander("👁️ 查看简历全文"):
            st.text_area(
                "简历内容",
                value=st.session_state.resume_text,
                height=300,
                label_visibility="collapsed",
                key="resume_preview",
            )

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
st.title("🎯 AI 求职智能匹配助手")
st.caption("基于 DeepSeek 大模型 · 129 条真实岗位 · 覆盖求职全链路：匹配 → 诊断 → 沟通 → 面试 → 追踪")

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 岗位匹配看板",
    "📋 简历诊断与优化",
    "📈 投递进度追踪",
    "ℹ️ 项目说明",
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

    # ── 首屏引导横幅（仅在未加载简历时显示）──
    if not st.session_state.resume_text:
        st.markdown("""
<div style="background:linear-gradient(135deg,#0D9488 0%,#0F766E 60%,#115E59 100%);
            border-radius:12px;padding:24px 28px;margin-bottom:16px;color:#fff">
  <div style="font-size:1.35em;font-weight:800;margin-bottom:6px">
    🎯 129 条真实岗位 · AI 精准打分 · 一键生成打招呼文案
  </div>
  <div style="font-size:.93em;opacity:.9;margin-bottom:14px">
    上传简历（.docx）或点击「💡 使用示例简历体验」，即可解锁 AI 匹配、诊断、面试备考全链路功能。
  </div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;font-size:.82em;opacity:.85">
    <span>📊 匹配打分</span><span>·</span>
    <span>✏️ 简历改写建议</span><span>·</span>
    <span>🎤 面试备考</span><span>·</span>
    <span>📈 投递进度追踪</span>
  </div>
</div>
""", unsafe_allow_html=True)

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
    ("📋", "待投递",    ["pending"],                            "#9CA3AF"),
    ("📤", "已投递",    ["applied", "viewed"],                  "#60A5FA"),
    ("💬", "面试中",    ["chatting", "interview"],              "#34D399"),
    ("🔥", "终面·等待", ["final_interview", "waiting"],         "#F97316"),
    ("🎉", "Offer",    ["offer"],                              "#10B981"),
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
            sc_color = "#10b981" if score >= 80 else ("#f59e0b" if score >= 65 else "#ef4444")
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
        sc_color = "#10b981" if score >= 80 else ("#f59e0b" if score >= 65 else "#ef4444")
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
# Tab 4：项目说明
# ────────────────────────────────────────────────────────────────────────────────
with tab4:
    st.subheader("ℹ️ 项目说明")

    # ── 核心痛点 ──
    p1, p2 = st.columns(2)
    with p1:
        st.error("**😤 痛点 1：海量岗位筛选难**\n\n数百条岗位靠人工逐条判断匹配度，耗时且主观。")
    with p2:
        st.error("**😤 痛点 2：简历命中率低**\n\n不知道简历与目标 JD 的具体差距，无法针对性优化。")

    st.divider()

    # ── 解决方案模块 ──
    st.markdown("### 全链路 AI 求职智能体")
    m1, m2, m3, m4, m5 = st.columns(5)
    for col, icon, title, desc in [
        (m1, "🎯", "岗位匹配", "129 条岗位秒级评分，优先级一目了然"),
        (m2, "🧠", "策略洞察", "高频需求技能分析，投递优先级建议"),
        (m3, "📋", "简历诊断", "针对具体 JD 的逐条改写建议"),
        (m4, "🎤", "面试备考", "高频面试题 + 应答要点 + 弱点预警"),
        (m5, "📈", "投递追踪", "全链路进度可视化，从投递到 Offer"),
    ]:
        col.metric(f"{icon} {title}", "", desc)

    st.divider()

    # ── 技术 & 数据 ──
    t1, t2 = st.columns(2)
    with t1:
        st.markdown("**🤖 AI 选型：DeepSeek Chat V3**（via OpenRouter）")
        st.markdown("- 中文语义理解强，精准识别 JD ↔ 简历匹配度\n- 结构化 JSON 输出，评分格式稳定\n- 成本极低（约 ¥0.1/千次），支持批量分析")
        st.markdown("**📊 核心评分权重**")
        for label, w in [("岗位方向匹配", 25), ("技能匹配", 35), ("经验匹配", 25), ("教育背景", 15)]:
            st.progress(w / 100, text=f"{label}  {w}%")
    with t2:
        st.markdown("**📦 数据来源**")
        st.success("129 条真实岗位：Playwright 爬取自 Boss直聘 + 实习僧")
        st.info("18 条投递追踪记录：覆盖完整求职漏斗（待投递 → Offer）")
        st.markdown("**🔧 技术栈**")
        st.code(
            "前端：Python · Streamlit\n"
            "AI：OpenRouter API · DeepSeek V3\n"
            "持久化：SQLite（投递追踪）\n"
            "数据采集：Playwright 爬取 Boss直聘 + 实习僧",
            language="text",
        )

    st.divider()

    # ── 迭代记录（折叠，节省空间）──
    with st.expander("📋 版本迭代记录", expanded=False):
        st.markdown("""
| 版本 | 主要功能 |
|---|---|
| v1 | FastAPI 后端 + 原生 JS，支持真实爬虫自动投递 |
| v2 | Streamlit 重构，接入 AI 匹配 + 简历诊断 |
| v3 | 新增打招呼生成、面试备考、策略洞察、一键体验 |
| v4 | UI 精简：去除冗余控件，优化信息层级与交互流 |
| v5 | UX 强化：空状态引导、主色重设计、Tab4 视觉化重构 |
| v6 | 看板增强：卡片 CSS 对标参考设计，增加分数进度条、胶囊标签、徽章系统 |
| v7 | 安全与交互：XSS 转义、API Key 脱敏显示、SQLite 看板可拖动更新 |
| v8 | 全面优化：首屏引导横幅、卡片列表分页（每页20条）、Tab1→Tab3「加入追踪」联动、简历诊断/面试备考子 Tab、岗位详情 Markdown 渲染 |
| v9（当前）| 交互完善：时间线弹窗支持手动添加进展 + 删除岗位；看板逐行对齐 + 搜索过滤 + 面试率指标；手动添加岗位卡片隐藏0分；打招呼文案一键复制；Tab2 展示目标岗位摘要卡片 |
""")
