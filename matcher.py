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


def _mock_match(jobs: List[Dict]) -> List[Dict]:
    """Fallback scoring when no API key is configured."""
    import random
    for job in jobs:
        job["match_score"] = float(random.randint(55, 95))
        job["match_reason"] = "（演示模式）请在设置中填入 OpenRouter API Key 以启用 AI 匹配"
    jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return jobs
