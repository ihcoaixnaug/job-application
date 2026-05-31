"""AI 求职智能匹配助手 — Streamlit 前端"""
import asyncio
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path

import streamlit as st

from company_tiers import get_company_tier
from matcher import diagnose_resume, generate_greeting, generate_interview_prep, match_jobs
from resume_parser import parse_docx
from tracker import get_all_jobs as get_tracking_jobs, update_status

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

    sc_cls  = "sc-hi" if score >= 80 else ("sc-mid" if score >= 65 else "sc-lo")
    bar_cls = "bar-hi" if score >= 80 else ("bar-mid" if score >= 65 else "bar-lo")

    highlights = (job.get("match_highlights") or [])[:3]
    concerns   = (job.get("match_concerns")   or [])[:2]

    if compact:
        pills = "".join(f'<span class="jp jp-pos">✓ {h}</span>' for h in highlights[:2])
        pills += "".join(f'<span class="jp jp-neg">△ {c}</span>' for c in concerns[:1])
    else:
        pills = "".join(f'<span class="jp jp-pos">✓ {h}</span>' for h in highlights)
        pills += "".join(f'<span class="jp jp-neg">△ {c}</span>' for c in concerns)
        if not highlights and not concerns and job.get("match_reason"):
            pills = f'<span class="jp jp-tip">💡 {job["match_reason"][:50]}</span>'

    return (
        f'<div class="jc">'
        f'<div class="jc-hd">'
        f'<span class="jc-title">{job.get("title","")}</span>'
        f'<span class="jc-score {sc_cls}">{score:.0f}</span>'
        f'</div>'
        f'<div class="jc-meta">'
        f'<span>{job.get("company","")}</span>{tier_html}{plat_html}'
        f'<span>·</span><span>{salary}</span>'
        f'<span>·</span><span>{city}</span>'
        f'</div>'
        f'<div class="jc-bar-bg"><div class="jc-bar {bar_cls}" style="width:{score}%"></div></div>'
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
        for field in ("match_highlights", "match_concerns"):
            if isinstance(j.get(field), str):
                try:
                    j[field] = json.loads(j[field])
                except Exception:
                    j[field] = []
        if not j.get("company_tier"):
            j["company_tier"] = get_company_tier(j.get("company", ""))
    return jobs


@st.cache_data
def load_demo_timeline_jobs() -> list[dict]:
    path = Path(__file__).parent / "data" / "demo_timeline_jobs.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── 常量 ────────────────────────────────────────────────────────────────────────
TIER_BADGE = {"大厂": "🏆 大厂", "中厂": "🥈 中厂", "小厂": "🏅 小厂"}
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
    # API Key
    api_key_input = st.text_input(
        "OpenRouter API Key",
        value=st.session_state.api_key,
        type="password",
        help="在 openrouter.ai 免费注册获取，支持 DeepSeek / Claude / GPT 等模型",
    )
    if api_key_input != st.session_state.api_key:
        set_api_key(api_key_input)
    if st.session_state.api_key:
        st.success("✅ API Key 已配置")
    else:
        st.warning("⚠️ 未配置 API Key，将展示示例匹配分数")

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
            "招聘平台", ["boss", "shixiseng"],
            default=["boss", "shixiseng"],
            format_func=lambda x: PLATFORM_NAME.get(x, x),
        )
        tiers = st.multiselect(
            "公司规模", ["大厂", "中厂", "小厂"],
            default=["大厂", "中厂", "小厂"],
        )
        _all_cities = sorted(set(
            j.get("location", "").split("-")[0].strip()
            for j in load_jobs()
            if j.get("location", "").strip()
        ))
        cities_filter = st.multiselect("城市", _all_cities, default=_all_cities)
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
        and j.get("platform") in platforms
        and get_company_tier(j.get("company", "")) in tiers
        and j.get("location", "").split("-")[0].strip() in cities_filter
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

    # ── 岗位卡片（对标参考设计：直接展示，无 expander）──
    for job in filtered:
        job_uid = str(job.get("job_id") or job.get("id", ""))

        # HTML 卡片
        st.markdown(_job_card(job, compact=False), unsafe_allow_html=True)

        # 操作按钮行（紧贴卡片底部）
        existing_greeting = st.session_state.greetings.get(job_uid)
        btn_c1, btn_c2, btn_c3, _ = st.columns([2, 2, 2, 4])

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

        # 可展开：打招呼文案
        if existing_greeting and st.session_state.get(f"expand_g_{job_uid}"):
            st.text_area("打招呼文案", value=existing_greeting, height=70,
                         key=f"g_ta_{job_uid}", label_visibility="collapsed")

        # 可展开：岗位详情
        if st.session_state.get(f"expand_d_{job_uid}"):
            desc = job.get("description") or ""
            req  = job.get("requirements") or ""
            with st.container():
                if desc:
                    st.caption(f"**岗位描述** {desc[:300]}{'…' if len(desc) > 300 else ''}")
                if req:
                    st.caption(f"**岗位要求** {req[:250]}{'…' if len(req) > 250 else ''}")


# ────────────────────────────────────────────────────────────────────────────────
# Tab 2：简历诊断与优化
# ────────────────────────────────────────────────────────────────────────────────
with tab2:
    st.subheader("📋 简历诊断 · 改写建议 · 面试备考")
    st.write("选择目标岗位，AI 一站式诊断简历差距、给出改写建议、生成面试备考题。")

    diag_jobs = st.session_state.matched_jobs or load_jobs()
    diag_jobs_sorted = sorted(diag_jobs, key=lambda x: x.get("match_score", 0), reverse=True)[:50]

    job_options = {
        f"{score_color(j.get('match_score',0))} {j.get('title', '')} @ {j.get('company', '')}（{j.get('match_score', 0):.0f}分）": j
        for j in diag_jobs_sorted
    }
    selected_label = st.selectbox("选择目标岗位", list(job_options.keys()))
    selected_job = job_options[selected_label]
    cur_job_id = str(selected_job.get("job_id") or selected_job.get("id", ""))

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

    # ── 展示诊断结果 ──
    result = st.session_state.diagnosis_result
    if result and st.session_state.diagnosis_job_id == cur_job_id:
        st.divider()
        st.subheader("🔍 简历诊断结果")
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

    # ── 展示面试备考 ──
    iv = st.session_state.interview_result
    if iv and st.session_state.interview_job_id == cur_job_id:
        st.divider()
        st.subheader("🎤 面试备考材料")

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

@st.dialog("📅 投递时间线")
def _show_timeline(job: dict):
    st.markdown(f"**{job.get('company', '')}** · {job.get('title', '')}")
    st.caption(f"{score_color(job.get('match_score', 0))} {job.get('match_score', 0):.0f}分 · {job.get('salary') or '薪资面议'}")
    st.divider()
    timeline = job.get("timeline") or []
    if timeline:
        for ev in timeline:
            tl_icon = TIMELINE_ICONS.get(ev.get("status", ""), "•")
            note_str = f" — {ev['note']}" if ev.get("note") else ""
            st.write(f"`{ev['date']}` {tl_icon} **{ev['status']}**{note_str}")
    else:
        st.info("暂无时间线记录")
    if job.get("match_reason"):
        st.divider()
        st.info(f"💡 {job['match_reason']}")


def _move_job(job_uid: str, old_status: str):
    """on_change 回调：检测到状态变化后立即写入 DB。"""
    new_s = st.session_state.get(f"kb_{job_uid}")
    if new_s and new_s != old_status:
        update_status(job_uid, new_s, "")


with tab3:
    track_jobs = get_tracking_jobs()  # 每次从 DB 读取，确保即时更新
    counts = {s: sum(1 for j in track_jobs if j.get("status") == s) for s in STATUS_ORDER}

    st.subheader("📈 投递进度追踪")

    # ── 关键指标 ──
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📤 已投递", sum(counts.get(s, 0) for s in ["applied", "viewed", "chatting", "interview", "final_interview", "waiting", "offer"]))
    k2.metric("💬 面试中", sum(counts.get(s, 0) for s in ["interview", "final_interview"]))
    k3.metric("⏳ 等待结果", counts.get("waiting", 0))
    k4.metric("🎉 Offer", counts.get("offer", 0))

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

    # ── 看板（5 列）── 使用统一 CSS 系统
    kb_cols = st.columns(len(_KANBAN_STAGES))
    for col_obj, (icon, stage_lbl, stage_statuses, col_color) in zip(kb_cols, _KANBAN_STAGES):
        stage_jobs = [j for j in track_jobs if j.get("status") in stage_statuses]
        with col_obj:
            # 列标题：圆点 + 名称 + 计数徽章
            st.markdown(
                f'<div class="kb-hd">'
                f'<span class="kb-dot" style="background:{col_color}"></span>'
                f'<span>{stage_lbl}</span>'
                f'<span class="kb-cnt">{len(stage_jobs)}</span>'
                f'</div>'
                f'<div class="kb-rule" style="background:{col_color}"></div>',
                unsafe_allow_html=True,
            )
            for job in stage_jobs:
                job_uid = str(job["job_id"])
                cur_st  = job.get("status", "pending")

                # 紧凑版卡片（含分数条 + 匹配胶囊）
                st.markdown(_job_card(job, compact=True), unsafe_allow_html=True)

                # 移至下拉（on_change 直接保存 → 卡片即时跳列）
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

    # ── 已拒绝（折叠）──
    rejected_jobs = [j for j in track_jobs if j.get("status") == "rejected"]
    if rejected_jobs:
        st.divider()
        with st.expander(f"❌ 已拒绝 ({len(rejected_jobs)})", expanded=False):
            for job in rejected_jobs:
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
        st.code("Python · Streamlit · OpenRouter API\nPlaywright（爬虫，已归档）· DeepSeek V3", language="text")

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
| v5（当前）| UX 强化：空状态引导、主色重设计、Tab4 视觉化重构 |
""")
