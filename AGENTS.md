# AGENTS.md — 求职助手 · AI Agent 与浏览器自动化设计文档

> 本文档面向后续接手的 AI 助手或开发者，描述系统所有自动化组件的角色、约束、输入输出规范与关键实现细节。**请在修改任何 Agent 相关逻辑前通读本文档。**

---

## ⚠️ 最重要的硬性约束

### Boss直聘必须运行真实（有头）浏览器

经实测验证：**Boss直聘对 CDP（Chrome DevTools Protocol）有深度检测**，以 `headless=True` 启动的 Chromium 会被识别为机器人，导致岗位列表返回空、登录被拦截。即使使用 Patchright 的二进制反检测补丁，无头模式依然无法正常抓取。

**结论：**
- Boss直聘的爬取、登录、投递 **必须** 以 `headless=False`（有头模式）运行
- **服务器（无显示器）环境下，禁止尝试运行真实 Boss 爬虫**
- 在 Linux 服务器上，Boss 相关功能只能通过**演示模式**体验
- 只有在本地 Mac/Windows 有桌面显示的机器上，才能运行真实的 Boss 抓取和投递

```python
# scrapers/boss.py — 始终保持 headless=False
await self.browser = await playwright.chromium.launch(headless=False, ...)
```

---

## 系统概览

```
用户浏览器 (SPA)
      │  REST API (JSON)
      ▼
FastAPI (main.py) ──── BackgroundTasks ──┬── Matcher Agent (matcher.py)
      │                                  │        └── OpenRouter LLM
      │                                  └── Browser Agent (scrapers/)
      │                                           ├── BossZhipinScraper
      │                                           └── ShixisengScraper
      ▼
SQLite (data/jobs.db)
```

系统包含 **两类 Agent**：

| Agent | 文件 | 驱动 | 运行模式 |
|---|---|---|---|
| **Matcher Agent** | `matcher.py` | OpenRouter LLM | 服务器 / 本地均可 |
| **Browser Agent** | `scrapers/boss.py` | Patchright（Playwright 分支）| **仅本地有头模式** |
| **Browser Agent** | `scrapers/shixiseng.py` | Patchright | 本地优先，服务器仅演示 |

---

## 1. Matcher Agent（`matcher.py`）

### 三项核心功能

#### 1.1 `generate_search_keywords(preferences: str) -> List[str]`

将用户的自然语言求职意向（如"数据运营/策略运营/数据分析"）扩展为 6-10 个平台搜索关键词。

- **Prompt**：要求 LLM 输出 JSON 数组，包含同义词、行业别称、常用变体
- **降级**：无 API Key 时按 `/` 切分原始字符串
- **调用时机**：用户点击"🤖 AI 解析偏好"按钮 → `POST /api/generate-keywords`

#### 1.2 `match_jobs(resume: str, jobs: List[dict], preferences: str) -> List[dict]`

对搜索结果中每条岗位与用户简历做语义比对，输出结构化评分。

**输出 JSON schema（严格格式）**：
```json
{
  "score": 87,
  "reason": "数据分析经验高度吻合，Python 技能匹配",
  "highlights": ["2年数据分析经验", "SQL 熟练"],
  "concerns": ["缺少直播运营背景"]
}
```

评分维度（prompt 中声明，LLM 自主权重）：
- 岗位方向匹配（~25%）
- 技能匹配（~35%）
- 项目/实习经验（~25%）
- 教育背景（~15%）

- **降级**：无 API Key 时调用 `_mock_match()` 返回随机分（55-95），提示用户配置

#### 1.3 `generate_greeting(resume: str, job: dict, preferences: str) -> str`

基于简历摘要 + 岗位要求生成 60 字以内的个性化打招呼文案。

- **调用时机**：打招呼模式为"AI 个性化"时，`POST /api/jobs/{id}/apply` 触发
- **固定模板模式**：直接使用用户在设置里预设的文本，不调用 LLM

### OpenRouter 配置

| 参数 | 默认值 | 配置位置 |
|---|---|---|
| `base_url` | `https://openrouter.ai/api/v1` | 硬编码 |
| `model` | `deepseek/deepseek-chat-v3-0324` | DB `openrouter_model` / env `OPENROUTER_MODEL` |
| `api_key` | — | DB `openrouter_api_key` / env `OPENROUTER_API_KEY` |

推荐模型：

| 模型 | 中文能力 | 速度 | 费用估算 |
|---|---|---|---|
| `deepseek/deepseek-chat-v3-0324` | ★★★★★ | 快 | ~¥0.1/千次 |
| `anthropic/claude-haiku-4-5` | ★★★★☆ | 很快 | ~¥0.2/千次 |
| `openai/gpt-4o-mini` | ★★★★☆ | 快 | ~¥0.15/千次 |

---

## 2. Browser Agent — Boss直聘（`scrapers/boss.py`）

### ⚠️ 再次强调：必须有头模式运行

### 关键设计：会话全程复用同一 Context

Boss直聘将登录状态绑定在浏览器指纹上，重建 Context = 换设备 = 掉登录。因此 `_boss_scraper`（`BossZhipinScraper` 实例）在 FastAPI 进程启动后**全程以单例形式保活**，不关闭、不重建。

```python
# main.py
_boss_scraper: Optional[BossZhipinScraper] = None  # 全局单例
```

### 登录流程

```
_auto_init_boss()（启动时）
  ├── 检测 data/cookies/boss.json 是否存在
  ├── 存在 → load_cookies() 注入到 context → _check_logged_in()
  │         成功 → _boss_scraper = s（激活）
  │         失败 → 关闭，等待用户手动登录
  └── 不存在 → 跳过，等待用户点击"打开扫码窗口"

手动登录（POST /api/boss-login）
  └── open_login_page() → 打开 Boss QR 页 → 用户扫码
        └── 用户点"我已完成登录" → boss_save_session()
              └── save_cookies() 持久化到 data/cookies/boss.json
```

### Cookie 注意事项

- Cookie 存储在 `data/cookies/boss.json`（不入 git）
- Boss 的 session 与 IP + 浏览器指纹双绑定
- **换机器/换网络后 Cookie 大概率失效，需重新扫码登录**
- 切勿在多台机器上同时复用同一份 cookie 文件

### 方法清单

| 方法 | 描述 |
|---|---|
| `start(headless=False)` | 启动 Patchright Chromium（必须 False）|
| `open_login_page()` | 导航到 Boss QR 登录页 |
| `wait_for_login(timeout_ms)` | 轮询 URL 判断登录完成 |
| `_check_logged_in()` | 用保存的 Cookie 验证 session 有效性 |
| `search_jobs(keyword, city, page)` | 解析 `.job-card-wrapper`，返回结构化岗位 |
| `send_greeting(job_url, message)` | 点击"立即沟通"并发送消息 |
| `close()` | 关闭 browser（正常不会调用，进程结束时自动释放）|

### 反检测策略

- 使用 **Patchright**（Playwright 的二进制分支），在 Chromium 源码层面打了 CDP 特征补丁
- 不使用 `add_init_script` 注入（注入脚本本身可能暴露特征）
- 随机 User-Agent、随机视口尺寸（`scrapers/stealth.py:random_context_options()`）
- 人类化鼠标轨迹：`human_click()`、`human_scroll()`
- 页面间随机延迟：`page_delay()`、`between_pages_delay()`

### CSS 选择器（随 Boss 版本更新可能变化）

```python
job_cards  = ".job-card-wrapper"
title      = ".job-name"
company    = ".company-name"
salary     = ".salary"
location   = ".job-area"
hr_active  = ".boss-active-time, .active-time"
apply_btn  = '.btn-startchat, a:has-text("立即沟通")'
chat_input = ".chat-input textarea"
```

---

## 3. Browser Agent — 实习僧（`scrapers/shixiseng.py`）

### 方法清单

| 方法 | 描述 |
|---|---|
| `start(headless=False)` | 启动 Patchright Chromium |
| `goto_login_and_send_sms(phone)` | 导航到登录页并填写手机号触发短信 |
| `submit_sms_code(code)` | 填入验证码完成登录 |
| `search_jobs(keyword, city, page)` | 抓取岗位列表 |
| `apply_job(job_url)` | 点击"投递简历"完成投递 |

### 登录流程

```
POST /api/shixiseng-send-code（用户输入手机号）
  └── goto_login_and_send_sms(phone) → 短信发送
        └── POST /api/shixiseng-verify（用户输入验证码）
              └── submit_sms_code(code)
                    └── save_cookies("shixiseng") → 持久化
```

---

## 4. 演示模式（Demo Mode）

演示模式允许在**不启动任何真实爬虫**的情况下体验全部功能流程。

```python
# main.py
_demo_mode: bool = False  # GET/POST /api/demo-mode 切换
```

- **搜索**：直接加载 `demo_data.py:DEMO_JOBS`（30 条内置仿真岗位），跳过爬虫
- **投递**：`asyncio.sleep(0.6)` 模拟延迟后返回成功，不打开任何浏览器
- **数据隔离**：演示岗位以 `is_demo=1` 存入 SQLite，所有查询带 `WHERE is_demo = ?` 过滤，两套数据互不干扰
- **服务器部署**：在 Ubuntu 服务器上应默认开启演示模式，无需登录任何平台

---

## 5. 任务调度模式（BackgroundTasks + 轮询）

所有耗时操作（搜索、AI 匹配、投递）异步执行，前端通过轮询获取进度。

```
前端                          后端
 │                               │
 ├─ POST /api/search ───────────>│ 立即返回 {task_id}
 │                               ├─ _do_search() 在后台运行
 ├─ GET /api/task/{id} 每2秒 ──>│
 │<── {progress: 45, msg: "..."} ┤
 │         ...轮询...             │
 │<── {status: "completed"} ─────┤
 └─ GET /api/jobs 刷新看板 ─────>│
```

任务状态存在内存 `_tasks: Dict[str, Dict]`（进程重启丢失，属预期行为）。

---

## 6. 搜索去重机制

多关键词 × 多城市搜索时，同一岗位可能被多个关键词命中：

```python
seen_ids: set[tuple] = set()  # (platform, job_id)

for kw in kw_list:
    for city in city_list:
        for page in pages:
            jobs = await scraper.search_jobs(kw, city, page)
            for job in jobs:
                key = (job["platform"], job["job_id"])
                if key not in seen_ids:
                    seen_ids.add(key)
                    unique_jobs.append(job)
```

---

## 7. 扩展指南

### 新增招聘平台

1. 在 `scrapers/` 新建 `xxx.py`，实现 `start()` / `search_jobs()` / `apply_job()`
2. 在 `main.py:_do_search()` 增加 platform 分支
3. 在 `demo_data.py:DEMO_JOBS` 增加若干条该平台的仿真数据
4. `index.html` 中 platform checkbox 添加新选项

### 切换 AI 模型

在网页 ⚙️ 设置中填写任意 OpenRouter 支持的模型 ID，保存后立即生效，无需重启。

### 修改匹配提示词

编辑 `matcher.py:SYSTEM_TEMPLATE`，修改评分维度说明。LLM 会相应调整评分逻辑。注意保持输出 JSON schema 不变，否则解析会失败。
