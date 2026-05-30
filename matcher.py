"""AI job-resume matcher powered by OpenRouter (OpenAI-compatible API)."""
import asyncio
import json
import os
import re
from typing import Dict, List

from openai import AsyncOpenAI

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-chat-v3-0324"

SYSTEM_TEMPLATE = """你是一个专业的求职助手，帮助在校学生和应届生分析岗位与简历的匹配度。

用户的目标岗位方向（优先考虑与此方向匹配的职位）：
{preferences}

评分维度（权重）：
- 岗位方向匹配（25%）：职位方向是否符合用户偏好
- 技能匹配（35%）：技术栈/工具与职位要求的重合度
- 经验匹配（25%）：项目/实习经历与岗位方向的相关性
- 教育背景（15%）：学历、专业是否符合要求

请严格以如下 JSON 格式返回，不要有多余内容：
{{"score": 85, "reason": "方向高度匹配，Python数据分析技能契合", "highlights": ["数据分析经验", "SQL熟练"], "concerns": ["缺少直播运营经验"]}}"""


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        base_url=OPENROUTER_BASE,
        default_headers={
            "HTTP-Referer": "https://github.com/job-assistant",
            "X-Title": "Job Application Assistant",
        },
    )


def _model() -> str:
    return os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)


async def match_jobs(resume: str, jobs: List[Dict], preferences: str = "") -> List[Dict]:
    """Score each job against the resume + preferences using OpenRouter."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return _mock_match(jobs)

    system = SYSTEM_TEMPLATE.format(preferences=preferences or "通用运营/数据分析")
    client = _client()
    results: List[Dict] = []

    for job in jobs:
        job_text = (
            f"职位：{job.get('title', '')}\n"
            f"公司：{job.get('company', '')}\n"
            f"薪资：{job.get('salary', '未知')}\n"
            f"地点：{job.get('location', '')}\n"
            f"职位描述：{job.get('description', '')}\n"
            f"岗位要求：{job.get('requirements', '')}"
        )
        try:
            resp = await client.chat.completions.create(
                model=_model(),
                max_tokens=400,
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": f"我的简历：\n{resume}\n\n目标岗位：\n{job_text}",
                    },
                ],
            )
            text = resp.choices[0].message.content or ""
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                parsed = json.loads(m.group())
                job["match_score"] = float(parsed.get("score", 50))
                job["match_reason"] = parsed.get("reason", "")
                job["match_highlights"] = parsed.get("highlights", [])
                job["match_concerns"] = parsed.get("concerns", [])
            else:
                job["match_score"] = 50.0
                job["match_reason"] = "分析完成"
        except Exception as e:
            job["match_score"] = 50.0
            job["match_reason"] = f"分析失败（{str(e)[:60]}）"
        results.append(job)

    results.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return results


async def generate_greeting(resume: str, job: Dict, preferences: str = "") -> str:
    """Generate a personalised Boss直聘 greeting (<60 chars)."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return f"您好，我对{job.get('company', '贵公司')}的{job.get('title', '该职位')}非常感兴趣，期待与您沟通！"

    client = _client()
    try:
        resp = await client.chat.completions.create(
            model=_model(),
            max_tokens=120,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"为以下职位生成一条打招呼消息（60字以内，简洁有力，突出核心优势，结合岗位方向）。\n\n"
                        f"我的简历摘要：{resume[:300]}\n"
                        f"目标方向偏好：{preferences}\n"
                        f"职位：{job.get('title')} @ {job.get('company')}\n"
                        f"要求：{job.get('requirements', '')[:100]}\n\n"
                        f"直接输出打招呼文字，不加任何前缀或解释。"
                    ),
                }
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return f"您好，我对{job.get('company', '贵公司')}的{job.get('title', '该职位')}非常感兴趣，期待与您沟通！"


async def generate_search_keywords(preferences: str) -> List[str]:
    """Expand job preferences into a deduplicated list of platform search keywords."""
    fallback = [p.strip() for p in preferences.replace("，", "/").split("/") if p.strip()]

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return fallback

    client = _client()
    try:
        resp = await client.chat.completions.create(
            model=_model(),
            max_tokens=250,
            messages=[{
                "role": "user",
                "content": (
                    f"根据以下求职意向，生成6-10个在Boss直聘/实习僧上搜索实习岗位的关键词。\n"
                    f"要求：关键词简洁（2-6字），覆盖原意向的不同表述角度，"
                    f"包含常见的平台搜索词（如\"数据运营实习\"\"运营分析\"等），去除完全重复项。\n"
                    f"求职意向：{preferences}\n\n"
                    f"直接以JSON数组格式输出，不加任何说明，例如：[\"数据运营\", \"策略运营\", \"数据分析\"]"
                ),
            }],
        )
        text = resp.choices[0].message.content or ""
        m = re.search(r'\[.*?\]', text, re.DOTALL)
        if m:
            kws = json.loads(m.group())
            result = [k.strip() for k in kws if isinstance(k, str) and k.strip()]
            return result if result else fallback
    except Exception as e:
        print(f"[matcher] generate_search_keywords error: {e}")
    return fallback


async def diagnose_resume(resume: str, job: Dict, preferences: str = "") -> Dict:
    """Deep per-job resume diagnosis: scores + concrete rewrite suggestions."""
    fallback = {
        "score": 0,
        "strengths": [],
        "gaps": [],
        "improvements": ["请配置 OpenRouter API Key 后使用此功能"],
        "summary": "未配置 API Key",
    }
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return fallback

    job_text = (
        f"职位：{job.get('title', '')}\n"
        f"公司：{job.get('company', '')}\n"
        f"岗位描述：{job.get('description', '')}\n"
        f"岗位要求：{job.get('requirements', '')}"
    )
    prompt = f"""你是一个资深 HR，正在帮助应聘者诊断简历与目标岗位的匹配情况。

目标岗位信息：
{job_text}

求职者意向：{preferences or "通用运营/数据分析"}

求职者简历：
{resume}

请从 HR 视角，输出以下 JSON（严格格式，不加多余内容）：
{{
  "score": 85,
  "strengths": ["与岗位高度匹配的优势1", "优势2"],
  "gaps": ["简历中缺失或不足的方面1", "不足2"],
  "improvements": [
    "【经历描述】将「XX」改为「XX，产出XX结果，支撑XX决策」，更量化更贴合JD",
    "【技能栏】补充「XX工具」，JD中明确提到但简历未体现",
    "【项目描述】突出与岗位相关的XX能力"
  ],
  "summary": "一句话总结：该候选人匹配度及最关键的提升方向"
}}

improvements 必须给出 3 条以上具体可操作的建议，直接告诉候选人该如何修改。"""

    client = _client()
    try:
        resp = await client.chat.completions.create(
            model=_model(),
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content or ""
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        fallback["summary"] = f"分析失败：{str(e)[:80]}"
    return fallback


async def generate_interview_prep(resume: str, job: Dict, preferences: str = "") -> Dict:
    """Generate likely interview questions + talking points for a specific job."""
    fallback = {
        "questions": [{"q": "请介绍一下你自己", "hint": "突出与岗位相关的经历"}],
        "key_points": ["请配置 API Key 后使用此功能"],
        "red_flags": [],
    }
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return fallback

    job_text = (
        f"职位：{job.get('title', '')}\n"
        f"公司：{job.get('company', '')}（{job.get('company_tier', '')}）\n"
        f"岗位描述：{job.get('description', '')}\n"
        f"岗位要求：{job.get('requirements', '')}"
    )
    prompt = f"""你是一个有丰富互联网大厂面试辅导经验的职业顾问。

目标岗位：
{job_text}

候选人简历：
{resume[:1500]}

请生成面试备考材料，输出以下 JSON（严格格式）：
{{
  "questions": [
    {{"q": "面试官最可能提问的问题1", "hint": "回答要点和思路"}},
    {{"q": "面试官最可能提问的问题2", "hint": "回答要点和思路"}},
    {{"q": "面试官最可能提问的问题3", "hint": "回答要点和思路"}},
    {{"q": "面试官最可能提问的问题4", "hint": "回答要点和思路"}}
  ],
  "key_points": ["面试中需要重点强调的亮点1", "亮点2", "亮点3"],
  "red_flags": ["面试中需要注意规避或提前准备解释的弱点1", "弱点2"]
}}

questions 必须结合该岗位 JD 和候选人简历，给出具体的、真实面试中会考察的问题。"""

    client = _client()
    try:
        resp = await client.chat.completions.create(
            model=_model(),
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content or ""
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        fallback["key_points"] = [f"分析失败：{str(e)[:80]}"]
    return fallback


def _mock_match(jobs: List[Dict]) -> List[Dict]:
    """Fallback scoring when no API key is configured."""
    import random
    for job in jobs:
        job["match_score"] = float(random.randint(55, 95))
        job["match_reason"] = "（演示模式）请在设置中填入 OpenRouter API Key 以启用 AI 匹配"
    jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return jobs
