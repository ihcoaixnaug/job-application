"""AI 求职智能匹配助手 — Streamlit 前端"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

import streamlit as st

from company_tiers import get_company_tier
from matcher import diagnose_resume, match_jobs
from resume_parser import parse_docx

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


# ── Session state 初始化 ────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "resume_text": "",
        "matched_jobs": None,
        "api_key": _read_secret("OPENROUTER_API_KEY"),
        "preferences": "数据运营/策略运营/数据分析",
        "diagnosis_result": None,
        "diagnosis_job_id": None,
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


def score_color(score: float) -> str:
    if score >= 80:
        return "🟢"
    if score >= 65:
        return "🟡"
    return "🔴"


def _read_secret(key: str) -> str:
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, "")


def set_api_key(key: str):
    st.session_state.api_key = key
    os.environ["OPENROUTER_API_KEY"] = key


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
        st.warning("⚠️ 未配置 API Key，将使用预计算结果")

    st.divider()
    st.subheader("📄 我的简历")
    resume_file = st.file_uploader("上传简历（.docx）", type=["docx"])
    resume_paste = st.text_area(
        "或粘贴简历文本", height=120, placeholder="将简历内容粘贴在此处..."
    )

    if resume_file:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(resume_file.read())
            tmp_path = tmp.name
        st.session_state.resume_text = parse_docx(tmp_path)
        st.success(f"✅ 已解析 {len(st.session_state.resume_text)} 字")
    elif resume_paste.strip():
        st.session_state.resume_text = resume_paste.strip()

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
            st.error("请先上传简历或粘贴文本")
        elif not st.session_state.api_key:
            st.error("请先填入 API Key")
        else:
            jobs_raw = load_jobs()
            with st.spinner("AI 分析中，请稍候…"):
                matched = asyncio.run(match_jobs(
                    st.session_state.resume_text,
                    [j.copy() for j in jobs_raw],
                    st.session_state.preferences,
                ))
            st.session_state.matched_jobs = matched
            st.session_state.diagnosis_result = None
            st.rerun()


# ── 主内容区 ────────────────────────────────────────────────────────────────────
st.title("🎯 AI 求职智能匹配助手")
st.caption("基于 DeepSeek 大模型，智能分析简历与岗位匹配度 · 129 条真实岗位数据")

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

    if st.session_state.matched_jobs:
        st.info("📌 显示 AI 重新匹配结果")
    else:
        st.info("📌 显示预计算匹配结果（上传简历后点击「AI 重新匹配」获取个性化评分）")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📋 当前岗位数", len(filtered))
    c2.metric("🌟 高匹配（≥80分）", sum(1 for j in filtered if j.get("match_score", 0) >= 80))
    c3.metric("🏆 大厂机会", sum(1 for j in filtered if get_company_tier(j.get("company", "")) == "大厂"))
    cities = {j.get("location", "").split("-")[0] for j in filtered if j.get("location")}
    c4.metric("📍 覆盖城市", len(cities))

    st.divider()

    for job in filtered:
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
        with st.expander(header, expanded=False):
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
    st.subheader("📋 简历诊断与优化建议")
    st.write(
        "选择一个目标岗位，AI 将深度诊断你的简历与该岗位的匹配情况，"
        "给出**可直接落地**的简历改写建议。"
    )

    diag_jobs = st.session_state.matched_jobs or load_jobs()
    diag_jobs_sorted = sorted(diag_jobs, key=lambda x: x.get("match_score", 0), reverse=True)[:50]

    job_options = {
        f"{j.get('title', '')} @ {j.get('company', '')}（{j.get('match_score', 0):.0f}分）": j
        for j in diag_jobs_sorted
    }
    selected_label = st.selectbox("选择目标岗位", list(job_options.keys()))
    selected_job = job_options[selected_label]

    col_btn, col_tip = st.columns([1, 3])
    with col_btn:
        run_diag = st.button("🔍 生成诊断报告", type="primary")
    with col_tip:
        if not st.session_state.resume_text:
            st.warning("⬅️ 请先在左侧上传简历")
        elif not st.session_state.api_key:
            st.warning("⬅️ 请先填入 API Key")

    if run_diag:
        if not st.session_state.resume_text:
            st.error("请先上传简历或粘贴文本")
        elif not st.session_state.api_key:
            st.error("请先填入 OpenRouter API Key")
        else:
            with st.spinner("AI 深度分析中，约需 10-20 秒…"):
                result = asyncio.run(diagnose_resume(
                    st.session_state.resume_text,
                    selected_job,
                    st.session_state.preferences,
                ))
            st.session_state.diagnosis_result = result
            st.session_state.diagnosis_job_id = selected_job.get("job_id") or selected_job.get("id")

    result = st.session_state.diagnosis_result
    cur_job_id = selected_job.get("job_id") or selected_job.get("id")
    if result and st.session_state.diagnosis_job_id == cur_job_id:
        st.divider()
        score_val = result.get("score", 0)
        st.metric("综合匹配分", f"{score_val} / 100")

        col_a, col_b = st.columns(2)
        with col_a:
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

        with col_b:
            improvements = result.get("improvements") or []
            if improvements:
                st.write("**✏️ 简历改写建议**")
                for i, tip in enumerate(improvements, 1):
                    st.info(f"{i}. {tip}")

        if result.get("summary"):
            st.divider()
            st.write(f"**💬 AI 总结：** {result['summary']}")


# ────────────────────────────────────────────────────────────────────────────────
# Tab 3：投递进度追踪
# ────────────────────────────────────────────────────────────────────────────────
with tab3:
    demo_jobs = load_demo_timeline_jobs()

    # ── 漏斗总览 ──
    st.subheader("📈 投递进度追踪")
    st.caption("演示数据：18 条岗位，覆盖从待投递到 Offer 的完整求职漏斗")

    funnel_order = ["pending", "applied", "viewed", "chatting",
                    "interview", "final_interview", "waiting", "offer", "rejected"]
    funnel_labels = {
        "pending": "待投递", "applied": "已投递", "viewed": "已查看",
        "chatting": "沟通中", "interview": "面试中",
        "final_interview": "终面", "waiting": "等待结果",
        "offer": "Offer", "rejected": "已拒绝",
    }
    counts = {s: sum(1 for j in demo_jobs if j.get("status") == s) for s in funnel_order}

    active_statuses = [s for s in funnel_order if s != "rejected"]
    cols = st.columns(len(active_statuses))
    for col, s in zip(cols, active_statuses):
        icon, label, _ = STATUS_CONFIG.get(s, ("", s, ""))
        col.metric(f"{icon} {label}", counts.get(s, 0))

    rejected_count = counts.get("rejected", 0)
    st.caption(f"另有 {rejected_count} 条已拒绝")

    st.divider()

    # ── 筛选 ──
    filter_cols = st.columns([2, 1])
    with filter_cols[0]:
        status_options = ["全部"] + [
            f"{STATUS_CONFIG[s][0]} {STATUS_CONFIG[s][1]}" for s in STATUS_ORDER
            if any(j.get("status") == s for j in demo_jobs)
        ]
        status_filter = st.selectbox("按状态筛选", status_options, label_visibility="collapsed")
    with filter_cols[1]:
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

        icon, label, color = STATUS_CONFIG.get(status_group, ("", status_group, "#666"))
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

### 解决方案

本系统通过两个 AI 智能体解决上述问题：

| 模块 | 功能 | 技术实现 |
|---|---|---|
| **岗位匹配智能体** | 对每条岗位评分（0-100）+ 匹配原因 + 亮点 + 风险点 | DeepSeek 结构化输出 |
| **简历诊断智能体** | 针对具体岗位给出可操作的简历改写建议 | DeepSeek 多维度分析 |

### 数据说明

- 129 条真实岗位数据，来源：Boss直聘 + 实习僧（Playwright 自动爬取）
- 涵盖数据运营、策略运营、数据分析等方向
- 覆盖北上广深成等主要城市，大/中/小厂均有
- 「投递追踪」模块含 18 条演示数据，覆盖从待投递到 Offer 的完整求职漏斗

### AI 工具选型

- **模型**：DeepSeek Chat V3（通过 OpenRouter 调用）
  - 中文能力强，理解招聘 JD 和简历的语义细节
  - 成本低（约 ¥0.1/千次），适合批量匹配场景
- **框架**：Streamlit — 快速构建可公开访问的 Web Demo
- **后端**：Python + OpenAI SDK（兼容 OpenRouter）

### 核心配置

```python
# 评分维度权重（matcher.py）
岗位方向匹配  25%
技能匹配      35%
经验匹配      25%
教育背景      15%
```

### 迭代记录

| 版本 | 变化 |
|---|---|
| v1 | FastAPI + 原生 JS，支持真实爬虫自动投递 |
| v2（当前）| Streamlit 重写，新增简历诊断 + 投递追踪模块，部署至公网 |
""")
