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

# ── 示例简历（评委一键体验用）──────────────────────────────────────────────────
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

# ── 技能关键词列表（用于需求词频分析）────────────────────────────────────────
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


def score_bar_color(score: float) -> str:
    if score >= 80:
        return "normal"
    return "normal"


def analyze_skill_gaps(jobs: list[dict], top_n: int = 20) -> tuple[list, list]:
    """从高分岗位需求中提取高频技能，与内置技能列表比对。"""
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
    return freq.most_common(top_n)


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
        "greetings": {},       # job_id -> generated greeting text
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── 常量 ────────────────────────────────────────────────────────────────────────
TIER_BADGE = {"大厂": "🏆 大厂", "中厂": "🥈 中厂", "小厂": "🏅 小厂"}
PLATFORM_NAME = {"boss": "Boss直聘", "shixiseng": "实习僧"}

STATUS_CONFIG = {
    "offer":           ("🎉", "Offer",    "#28a745"),
    "final_interview": ("🔥", "终面",     "#fd7e14"),
    "waiting":         ("⏳", "等待结果", "#6c757d"),
    "interview":       ("💬", "面试中",   "#17a2b8"),
    "chatting":        ("💬", "沟通中",   "#17a2b8"),
    "viewed":          ("👀", "已查看",   "#007bff"),
    "applied":         ("📤", "已投递",   "#6610f2"),
    "pending":         ("📋", "待投递",   "#adb5bd"),
    "rejected":        ("❌", "已拒绝",   "#dc3545"),
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
    st.title("⚙️ 配置")

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
        st.warning("⚠️ 未配置 API Key，将展示预计算结果")

    st.divider()
    st.subheader("📄 我的简历")
    resume_file = st.file_uploader("上传简历（.docx）", type=["docx"])
    resume_paste = st.text_area(
        "或粘贴简历文本", height=100, placeholder="将简历内容粘贴在此处..."
    )

    if resume_file:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(resume_file.read())
            tmp_path = tmp.name
        st.session_state.resume_text = parse_docx(tmp_path)
        st.success(f"✅ 已解析 {len(st.session_state.resume_text)} 字")
    elif resume_paste.strip():
        st.session_state.resume_text = resume_paste.strip()

    # 一键体验按钮
    if st.button("💡 使用示例简历一键体验", use_container_width=True,
                 help="无需上传，直接加载内置示例简历并查看 AI 匹配效果"):
        st.session_state.resume_text = SAMPLE_RESUME
        st.success("✅ 示例简历已加载")

    if st.session_state.resume_text:
        st.caption(f"已加载简历：{len(st.session_state.resume_text)} 字")

    st.divider()
    st.subheader("🎯 求职意向")
    preferences_input = st.text_input(
        "方向偏好", value=st.session_state.preferences,
        placeholder="如：数据运营、产品运营、商业分析",
    )
    st.session_state.preferences = preferences_input

    st.divider()
    st.subheader("🔍 筛选条件")
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

    st.divider()
    if st.button("🤖 AI 重新匹配", type="primary", use_container_width=True):
        if not st.session_state.resume_text:
            st.error("请先上传简历或点击「一键体验」")
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
st.caption("基于 DeepSeek 大模型 · 129 条真实爬取岗位 · 覆盖求职全链路：匹配 → 诊断 → 沟通 → 面试 → 追踪")

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

    filtered = sorted(
        [
            j for j in all_jobs
            if j.get("match_score", 0) >= min_score
            and j.get("platform") in platforms
            and get_company_tier(j.get("company", "")) in tiers
        ],
        key=lambda x: x.get("match_score", 0),
        reverse=True,
    )

    # ── 概览指标 ──
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📋 筛选岗位", len(filtered))
    c2.metric("🌟 高匹配 ≥80分", sum(1 for j in filtered if j.get("match_score", 0) >= 80))
    c3.metric("📊 中匹配 60-79", sum(1 for j in filtered if 60 <= j.get("match_score", 0) < 80))
    c4.metric("🏆 大厂机会", sum(1 for j in filtered if get_company_tier(j.get("company", "")) == "大厂"))
    cities = {j.get("location", "").split("-")[0] for j in filtered if j.get("location")}
    c5.metric("📍 覆盖城市", len(cities))

    # ── 策略洞察 ──
    with st.expander("🧠 求职策略洞察（基于岗位需求分析）", expanded=True):
        ins_col1, ins_col2, ins_col3 = st.columns(3)

        with ins_col1:
            st.write("**🎯 优先投递 Top 5**")
            for i, job in enumerate(filtered[:5], 1):
                tier = get_company_tier(job.get("company", ""))
                score = job.get("match_score", 0)
                st.write(
                    f"{i}. {job.get('company', '')} · {job.get('title', '')} "
                    f"— {score_color(score)} {score:.0f}分"
                )

        with ins_col2:
            st.write("**📚 高频需求技能**")
            skill_freq = analyze_skill_gaps(filtered or all_jobs)
            for skill, cnt in skill_freq[:8]:
                bar_val = min(cnt / 20, 1.0)
                st.write(f"`{skill}` 出现 {cnt} 次")

        with ins_col3:
            st.write("**💡 投递策略建议**")
            high = sum(1 for j in filtered if j.get("match_score", 0) >= 80)
            mid = sum(1 for j in filtered if 65 <= j.get("match_score", 0) < 80)
            low = sum(1 for j in filtered if j.get("match_score", 0) < 65)
            st.write(f"• 高匹配（≥80分）{high} 条：**优先冲刺**，尽快投递")
            st.write(f"• 中匹配（65-79分）{mid} 条：**针对性优化简历**后投递")
            st.write(f"• 低匹配（<65分）{low} 条：**作为保底**，或暂缓投递")
            tier_dist = Counter(
                get_company_tier(j.get("company", "")) for j in filtered[:20]
            )
            st.write(f"• Top 20 中：大厂 {tier_dist.get('大厂',0)} 个 / "
                     f"中厂 {tier_dist.get('中厂',0)} 个 / "
                     f"小厂 {tier_dist.get('小厂',0)} 个")

    if st.session_state.matched_jobs:
        st.info("📌 显示 AI 重新匹配结果")
    else:
        st.info("📌 显示预计算匹配结果 — 上传简历后点击「AI 重新匹配」获取个性化评分")

    st.divider()

    # ── 岗位卡片 ──
    for job in filtered:
        score = job.get("match_score", 0)
        tier = get_company_tier(job.get("company", ""))
        platform_label = PLATFORM_NAME.get(job.get("platform", ""), "")
        salary = job.get("salary") or "薪资面议"
        job_uid = str(job.get("job_id") or job.get("id", ""))

        header = (
            f"{score_color(score)} **{score:.0f} 分** ｜ "
            f"{job.get('title', '')} @ **{job.get('company', '')}** "
            f"（{TIER_BADGE.get(tier, tier)}）｜ "
            f"{job.get('location', '')} ｜ {salary} ｜ {platform_label}"
        )
        with st.expander(header, expanded=False):
            st.progress(int(score) / 100, text=f"匹配度 {score:.0f}%")

            col_l, col_r = st.columns([3, 2])
            with col_l:
                if job.get("match_reason"):
                    st.info(f"💡 {job['match_reason']}")

                highlights = job.get("match_highlights") or []
                if highlights:
                    st.write("**✅ 匹配优势**")
                    for h in highlights:
                        st.write(f"- {h}")

                concerns = job.get("match_concerns") or []
                if concerns:
                    st.write("**⚠️ 待补强**")
                    for c in concerns:
                        st.write(f"- {c}")

                # ── 打招呼文案 ──
                st.write("**📨 打招呼文案**")
                greeting_key = f"greeting_{job_uid}"
                existing = st.session_state.greetings.get(job_uid)
                if existing:
                    st.text_area("复制使用：", value=existing, height=80,
                                 key=greeting_key, label_visibility="collapsed")
                else:
                    if st.button("✨ AI 生成打招呼", key=f"btn_greet_{job_uid}",
                                 disabled=not st.session_state.api_key):
                        with st.spinner("生成中…"):
                            greeting = asyncio.run(generate_greeting(
                                st.session_state.resume_text or SAMPLE_RESUME,
                                job,
                                st.session_state.preferences,
                            ))
                        st.session_state.greetings[job_uid] = greeting
                        st.rerun()
                    if not st.session_state.api_key:
                        st.caption("需配置 API Key")

            with col_r:
                desc = job.get("description") or ""
                req = job.get("requirements") or ""
                if desc:
                    st.write("**岗位描述**")
                    st.write(desc[:250] + "…" if len(desc) > 250 else desc)
                if req:
                    st.write("**岗位要求**")
                    st.write(req[:200] + "…" if len(req) > 200 else req)
                if job.get("url"):
                    st.link_button("🔗 查看原岗位", job["url"])


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

    ready = st.session_state.resume_text and st.session_state.api_key
    if not st.session_state.resume_text:
        st.warning("⬅️ 请先在左侧上传简历，或点击「使用示例简历一键体验」")
    elif not st.session_state.api_key:
        st.warning("⬅️ 请先填入 API Key")

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        run_diag = st.button("🔍 简历诊断 + 改写建议", type="primary", disabled=not ready)
    with btn_col2:
        run_interview = st.button("🎤 生成面试备考题", type="primary", disabled=not ready)

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
                st.write("**✏️ 可落地的简历改写建议**")
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
# Tab 3：投递进度追踪
# ────────────────────────────────────────────────────────────────────────────────
with tab3:
    demo_jobs = load_demo_timeline_jobs()

    st.subheader("📈 投递进度追踪")
    st.caption("演示数据：18 条岗位，覆盖从待投递到 Offer 的完整求职漏斗")

    # ── 漏斗 ──
    funnel_active = ["pending", "applied", "viewed", "chatting",
                     "interview", "final_interview", "waiting", "offer"]
    counts = {s: sum(1 for j in demo_jobs if j.get("status") == s) for s in STATUS_ORDER}

    cols = st.columns(len(funnel_active))
    for col, s in zip(cols, funnel_active):
        icon, label, _ = STATUS_CONFIG.get(s, ("", s, ""))
        col.metric(f"{icon} {label}", counts.get(s, 0))

    rejected_count = counts.get("rejected", 0)
    st.caption(f"另有 {rejected_count} 条已拒绝")

    # ── 简易漏斗可视化 ──
    total_active = sum(counts.get(s, 0) for s in funnel_active)
    if total_active > 0:
        with st.expander("📊 投递漏斗可视化", expanded=True):
            funnel_display = [
                ("📤 已投递", counts.get("applied", 0) + counts.get("viewed", 0) + counts.get("chatting", 0)),
                ("💬 进入面试", counts.get("interview", 0) + counts.get("final_interview", 0)),
                ("⏳ 等待结果", counts.get("waiting", 0)),
                ("🎉 获得 Offer", counts.get("offer", 0)),
            ]
            max_val = max(v for _, v in funnel_display) or 1
            for label, val in funnel_display:
                bar = val / max_val
                st.write(f"**{label}** — {val} 条")
                st.progress(bar)

    st.divider()

    # ── 筛选 ──
    filter_col1, filter_col2 = st.columns([2, 1])
    with filter_col1:
        status_options = ["全部"] + [
            f"{STATUS_CONFIG[s][0]} {STATUS_CONFIG[s][1]}"
            for s in STATUS_ORDER
            if any(j.get("status") == s for j in demo_jobs)
        ]
        status_filter = st.selectbox("按状态筛选", status_options, label_visibility="collapsed")
    with filter_col2:
        show_rejected = st.checkbox("显示已拒绝", value=True)

    # ── 岗位卡片 ──
    for status_group in STATUS_ORDER:
        group_jobs = [
            j for j in demo_jobs
            if j.get("status") == status_group
            and (show_rejected or status_group != "rejected")
            and (
                status_filter == "全部"
                or STATUS_CONFIG.get(status_group, ("", ""))[1] in status_filter
            )
        ]
        if not group_jobs:
            continue

        icon, label, _ = STATUS_CONFIG.get(status_group, ("", status_group, ""))
        st.markdown(f"### {icon} {label} ({len(group_jobs)})")

        for job in group_jobs:
            score = job.get("match_score", 0)
            tier = get_company_tier(job.get("company", ""))
            platform_label = PLATFORM_NAME.get(job.get("platform", ""), "")
            salary = job.get("salary") or "薪资面议"

            header = (
                f"{score_color(score)} **{score:.0f} 分** ｜ "
                f"{job.get('title', '')} @ **{job.get('company', '')}** "
                f"（{TIER_BADGE.get(tier, tier)}）｜ "
                f"{job.get('location', '')} ｜ {salary} ｜ {platform_label}"
            )
            with st.expander(header, expanded=(status_group in ("offer", "final_interview"))):
                tl_col, info_col = st.columns([2, 3])

                with tl_col:
                    timeline = job.get("timeline") or []
                    if timeline:
                        st.write("**📅 投递时间线**")
                        for event in timeline:
                            tl_icon = TIMELINE_ICONS.get(event.get("status", ""), "•")
                            note = f" — {event['note']}" if event.get("note") else ""
                            st.write(
                                f"`{event['date']}` {tl_icon} **{event['status']}**{note}"
                            )
                    else:
                        st.caption("暂未投递")

                with info_col:
                    if job.get("match_reason"):
                        st.info(f"💡 {job['match_reason']}")

                    highlights = job.get("match_highlights") or []
                    if highlights:
                        st.write("**✅ 匹配优势**")
                        for h in highlights:
                            st.write(f"- {h}")

                    concerns = job.get("match_concerns") or []
                    if concerns:
                        st.write("**⚠️ 待补强**")
                        for c in concerns:
                            st.write(f"- {c}")

                    if job.get("url"):
                        st.link_button("🔗 查看原岗位", job["url"])


# ────────────────────────────────────────────────────────────────────────────────
# Tab 4：项目说明
# ────────────────────────────────────────────────────────────────────────────────
with tab4:
    st.subheader("ℹ️ 项目说明")
    st.markdown("""
### 问题背景

学生求职面临两大核心痛点：
1. **海量岗位筛选难**：在数百条岗位中人工判断匹配度耗时且主观
2. **简历命中率低**：不知道简历与目标岗位的具体差距，无法针对性优化

### 解决方案：全链路 AI 求职智能体

本系统覆盖求职完整链路，通过 **4 个 AI 智能体模块**解决上述问题：

| 模块 | 解决的问题 | 技术实现 |
|---|---|---|
| **🎯 岗位匹配** | 129 条岗位秒级评分排序，优先级一目了然 | DeepSeek 结构化评分 |
| **🧠 策略洞察** | 分析高频需求技能，给出投递优先级建议 | Python 词频分析 |
| **📋 简历诊断** | 针对具体 JD 给出可落地的逐条改写建议 | DeepSeek 多维分析 |
| **🎤 面试备考** | 生成高概率面试题 + 应答要点 + 弱点预警 | DeepSeek 角色扮演 |
| **📈 投递追踪** | 可视化全链路进度，从待投递到 Offer | 数据可视化 |

### 数据说明

- **129 条真实岗位**：通过 Playwright 自动爬取自 Boss直聘 + 实习僧，非模拟数据
- **18 条演示投递记录**：覆盖从待投递到 Offer 的完整求职漏斗

### AI 工具选型

**DeepSeek Chat V3**（通过 OpenRouter 调用）
- 中文理解能力强，可精准识别 JD 与简历的语义匹配
- 支持结构化 JSON 输出，确保评分/建议格式稳定
- 成本极低（约 ¥0.1/千次），支持 129 条岗位批量分析

**Streamlit** — 快速部署至公网，0 运维成本

### 核心评分逻辑

```
岗位方向匹配  25%  ← 职位方向是否符合用户偏好
技能匹配      35%  ← 技术栈/工具与职位要求的重合度
经验匹配      25%  ← 项目/实习经历与岗位方向的相关性
教育背景      15%  ← 学历、专业是否符合要求
```

### 迭代记录

| 版本 | 主要功能 |
|---|---|
| v1 | FastAPI 后端 + 原生 JS，支持真实爬虫自动投递 |
| v2 | Streamlit 重构，接入 AI 匹配 + 简历诊断 |
| v3（当前）| 新增打招呼生成、面试备考、策略洞察、一键体验 Demo |
""")
