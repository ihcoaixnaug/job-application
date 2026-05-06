# 求职助手 — 技术架构文档

> 面向接手开发的工程师或 AI 助手。阅读本文档可快速掌握项目结构、数据流、API 全貌和关键约束。

---

## 一、项目定位

AI 驱动的校园求职全流程管理平台，核心能力：

1. **AI 关键词扩展**：自然语言意向 → 多维搜索词
2. **多平台全量抓取**：Boss直聘 + 实习僧，多城市 × 多关键词，自动去重
3. **简历-岗位 AI 匹配**：每条岗位给出 0-100 分 + 亮点/顾虑
4. **看板管理**：7 阶段拖拽看板 + 时间线记录
5. **AI 打招呼/投递**：生成个性化文案，自动在平台发送

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────┐
│               前端 SPA（原生 JS，无框架）                  │
│  static/index.html · static/app.js · static/style.css   │
│  看板/列表双视图 · 拖拽 · 模态弹窗 · Toast 通知            │
└──────────────────────────┬──────────────────────────────┘
                           │ REST API (JSON / HTTP)
┌──────────────────────────▼──────────────────────────────┐
│               后端 FastAPI（main.py）                     │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│   │  搜索引擎     │  │  AI 分析引擎  │  │  投递引擎     │  │
│   │  scrapers/   │  │  matcher.py  │  │  scrapers/   │  │
│   │  多平台爬虫   │  │  OpenRouter  │  │  Patchright  │  │
│   │  去重调度     │  │  DeepSeek V3 │  │  有头浏览器   │  │
│   └──────────────┘  └──────────────┘  └──────────────┘  │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                   数据层（SQLite）                         │
│          data/jobs.db · aiosqlite 全异步                  │
│    jobs / settings / resume_text / cookie files          │
└─────────────────────────────────────────────────────────┘
```

---

## 三、目录结构

```
job-application/
├── main.py                  # FastAPI 入口，所有 API 端点 (~670 行)
├── database.py              # SQLite 异步操作 + schema 迁移
├── matcher.py               # LLM 匹配评分 + 关键词扩展 + 打招呼生成
├── company_tiers.py         # 公司规模分类（大厂/中厂/小厂，100+ 关键词）
├── demo_data.py             # 30 条内置仿真岗位（演示模式用）
├── resume_parser.py         # python-docx 简历文本提取
├── scrapers/
│   ├── boss.py              # Boss直聘 Patchright 自动化
│   ├── shixiseng.py         # 实习僧 Patchright 自动化
│   └── stealth.py           # 反检测工具函数 + Cookie 持久化
├── static/
│   ├── index.html           # SPA 入口页
│   ├── app.js               # 前端逻辑 (~950 行)
│   └── style.css            # 样式 (~400 行)
├── deploy/
│   ├── nginx-site.conf      # Nginx 反向代理配置（含 Basic Auth）
│   └── job-assistant.service# systemd 服务单元
├── docs/
│   ├── ARCHITECTURE.md      # 本文档
│   └── ...                  # 比赛文档/讲解稿
├── AGENTS.md                # AI/浏览器 Agent 设计文档（含关键约束）
├── .env.example             # 环境变量模板
├── requirements.txt
└── data/                    # 运行时数据（不入 git）
    ├── jobs.db
    ├── cookies/boss.json
    ├── cookies/shixiseng.json
    └── resumes/
```

---

## 四、技术栈

| 层 | 技术 | 关键说明 |
|---|---|---|
| 后端框架 | FastAPI + Uvicorn | 异步，BackgroundTasks 处理搜索/AI 长任务 |
| 浏览器自动化 | **Patchright**（Playwright 分支）| 二进制级 CDP 反检测，见 §七 |
| AI 接口 | OpenRouter · DeepSeek V3 | 统一接口，可热切换模型，中文能力强 |
| 数据库 | SQLite + aiosqlite | 零部署，全异步，本地运行无需服务器 |
| 前端 | 原生 JS（无框架）| 无构建步骤，轻量快速 |
| 反向代理 | Nginx | Basic Auth + 超时配置，见 §八 |
| 简历解析 | python-docx | 提取段落 + 表格纯文本 |

---

## 五、数据库 Schema

### `jobs` 表

| 列 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增 |
| platform | TEXT | `boss` / `shixiseng` |
| job_id | TEXT | 平台内岗位 ID |
| title | TEXT | 职位名称 |
| company | TEXT | 公司名 |
| company_tier | TEXT | `大厂` / `中厂` / `小厂` |
| location | TEXT | 城市/地区 |
| salary | TEXT | 薪资范围 |
| description | TEXT | 职位描述 |
| requirements | TEXT | 岗位要求 |
| url | TEXT | 原帖链接 |
| match_score | REAL | AI 匹配分（0-100） |
| match_reason | TEXT | 一句话匹配原因 |
| match_highlights | TEXT | JSON 数组，匹配亮点 |
| match_concerns | TEXT | JSON 数组，潜在顾虑 |
| boss_activity | TEXT | Boss HR 活跃状态（今日活跃/3天内等）|
| status | TEXT | 看板阶段（见下） |
| timeline | TEXT | JSON 数组，时间线记录 |
| applied_at | TEXT | 投递时间 ISO8601 |
| created_at | TEXT | 入库时间 |
| is_demo | INTEGER | 0=真实 1=演示，所有查询必须带此过滤 |

**唯一约束**：`(platform, job_id, is_demo)`

### 看板状态流

```
pending（待投递）
  → applied（已投递）
  → screening（简历筛选中）
  → assessment（笔试/测评）
  → interviewing（面试中）
  → offered（Offer）
  → rejected（未通过）
```

### `settings` 表（key-value）

| key | 说明 |
|---|---|
| openrouter_api_key | LLM API Key |
| openrouter_model | 当前使用的模型 ID |
| job_preferences | 求职偏好文本 |
| resume_text | 简历纯文本（匹配时注入 prompt）|
| resume_filename | 当前简历文件名 |
| greeting_mode | `fixed` / `ai` |
| greeting_template | 固定模板文本 |
| shixiseng_phone | 实习僧手机号 |

---

## 六、完整 API 端点

### 基础

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 返回 `static/index.html` |
| GET | `/api/task/{id}` | 轮询任务状态：`{status, progress, message}` |

### 简历

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/resume` | 获取简历文本 + 文件名 |
| POST | `/api/resume/upload` | 上传 `.docx`，自动解析存入 DB |

### 搜索与 AI

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/generate-keywords` | AI 扩展求职意向为关键词列表 |
| POST | `/api/search` | 启动多平台搜索 + AI 匹配，返回 `task_id` |
| GET | `/api/demo-mode` | 获取演示模式状态 |
| POST | `/api/demo-mode` | 切换演示模式 `{enabled: bool}` |

### 岗位管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/jobs?demo=0` | 获取岗位列表（demo=0 真实，demo=1 演示）|
| GET | `/api/stats?demo=0` | 各看板阶段计数 |
| PUT | `/api/jobs/{id}/status` | 更新看板状态 |
| POST | `/api/jobs/{id}/timeline` | 追加时间线备注 |

### 投递

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/jobs/{id}/apply` | 投递单个岗位，返回 `task_id` |
| POST | `/api/apply-batch` | 批量投递 |

### 平台登录

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/boss-status` | Boss 是否已激活 |
| POST | `/api/boss-login` | 打开 Boss 扫码窗口（**需有头浏览器**）|
| POST | `/api/boss-save-session` | 确认登录完成，保存 Cookie |
| POST | `/api/shixiseng-send-code` | 触发短信验证码 |
| POST | `/api/shixiseng-verify` | 提交验证码完成登录 |
| POST | `/api/shixiseng-save-session` | 保存 Cookie |

### 设置 & 打招呼

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/settings` | API Key + 模型配置 |
| GET/POST | `/api/preferences` | 求职偏好文本 |
| GET/POST | `/api/greeting-settings` | 打招呼模式 + 模板 |

---

## 七、反爬技术细节

### 为什么用 Patchright 而不是原生 Playwright

Boss直聘对 CDP 有深度检测。原生 Playwright 以 headless=True 运行时会被识别为机器人，**以 headless=False 运行时也可能被 CDP 探针检测到**。Patchright 在 Chromium 二进制层面打了补丁，消除了这些特征。

### 关键反检测措施（`scrapers/stealth.py`）

```python
random_context_options()  # 随机 UA + 随机视口
human_click(page, el)     # 随机偏移 + 贝塞尔曲线鼠标移动
human_type(page, sel, text) # 随机字符间隔模拟真人打字
page_delay()              # 页面加载后随机等待
between_pages_delay()     # 翻页间随机延迟
```

### Boss 会话保活机制

```python
# main.py — 全局单例，进程存活期间不关闭
_boss_scraper: Optional[BossZhipinScraper] = None
```

Boss 的 session 绑定浏览器指纹，重建 Context = 掉登录。因此单例 scraper 保持整个进程生命周期，搜索和投递都复用它。

---

## 八、服务器部署（Nginx + systemd）

### 部署约束

| 功能 | 本地 Mac/Win（有桌面）| Ubuntu 服务器 |
|---|---|---|
| 演示模式 | ✅ | ✅ |
| AI 关键词/匹配 | ✅（需 API Key）| ✅（需 API Key）|
| Boss真实抓取 | ✅ | ❌（无头模式无法运行）|
| Boss真实投递 | ✅ | ❌ |
| 实习僧真实抓取 | ✅ | ❌ |

### Nginx 配置要点

见 `deploy/nginx-site.conf`：
- **Basic Auth**：`auth_basic_user_file /etc/nginx/.htpasswd`（公网必须）
- **超时**：`proxy_read_timeout 600s`（搜索+AI 分析可能超过5分钟）
- **上传限制**：`client_max_body_size 30M`（简历文件）
- **禁用缓冲**：`proxy_buffering off`（任务状态轮询实时返回）

### 快速部署步骤

```bash
# 1. 服务器安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（或在网页设置里填写 API Key）
cp .env.example .env

# 3. 配置 nginx
sudo cp deploy/nginx-site.conf /etc/nginx/sites-available/job-assistant
sudo ln -s /etc/nginx/sites-available/job-assistant \
           /etc/nginx/sites-enabled/job-assistant
sudo apt install apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd <用户名>
sudo nginx -t && sudo systemctl reload nginx

# 4. 配置 systemd 服务（编辑路径后）
sudo cp deploy/job-assistant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now job-assistant
```

---

## 九、演示模式数据

`demo_data.py:DEMO_JOBS` 包含 30 条仿真岗位：
- 平台分布：Boss直聘 / 实习僧各半
- 公司规模：大厂（字节/腾讯/阿里）+ 中厂 + 小厂
- 岗位类型：数据分析/运营/产品/技术
- 城市：北京/上海/深圳/广州/杭州
- 每条 Boss 岗位含 `boss_activity` 字段

演示数据存入 DB 时 `is_demo=1`，与真实数据完全隔离，前端用 Tab 切换。
