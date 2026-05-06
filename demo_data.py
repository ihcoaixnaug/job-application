"""Pre-fetched demo job dataset — used when demo mode is enabled.

30 realistic internship listings covering:
  • 大厂 / 中厂 / 小厂
  • Boss直聘 (with boss_activity) and 实习僧
  • Multiple cities, roles, salary ranges
"""

DEMO_JOBS = [
    # ── 大厂 · Boss ─────────────────────────────────────────────────────────────
    {
        "platform": "boss", "job_id": "demo_b01",
        "title": "数据运营实习生",
        "company": "字节跳动",
        "location": "北京-海淀区",
        "salary": "400-500元/天",
        "description": (
            "负责抖音/西瓜视频数据分析，搭建运营数据看板，用数据驱动内容策略优化。"
            "协助数据产品迭代，输出分析报告支持业务决策，与产品/研发协作推进指标体系建设。"
        ),
        "requirements": "SQL, Python/Excel, 数据分析基础, 本科及以上, 有运营经验优先",
        "url": "https://www.zhipin.com/job_detail/demo001.html",
        "boss_activity": "今日活跃",
    },
    {
        "platform": "boss", "job_id": "demo_b02",
        "title": "策略运营实习生",
        "company": "腾讯",
        "location": "深圳-南山区",
        "salary": "300-400元/天",
        "description": (
            "参与微信/视频号内容策略制定，通过数据分析优化用户增长路径，协助策划用户活动。"
            "负责核心指标追踪、竞品分析与策略方案输出。"
        ),
        "requirements": "数据分析, 逻辑思维, Excel/Python, 有产品/运营实习经验",
        "url": "https://www.zhipin.com/job_detail/demo002.html",
        "boss_activity": "今日活跃",
    },
    {
        "platform": "boss", "job_id": "demo_b03",
        "title": "产品运营实习生",
        "company": "阿里巴巴",
        "location": "杭州-余杭区",
        "salary": "350-450元/天",
        "description": (
            "参与淘宝/天猫频道运营，协助制定GMV增长策略，跟踪数据异动，输出运营报告。"
            "配合产品迭代，与商家运营团队协同推进大促活动。"
        ),
        "requirements": "Excel, SQL基础, 活跃用户思维, 电商行业了解",
        "url": "https://www.zhipin.com/job_detail/demo003.html",
        "boss_activity": "3天内活跃",
    },
    {
        "platform": "boss", "job_id": "demo_b04",
        "title": "数据分析实习生",
        "company": "美团",
        "location": "北京-朝阳区",
        "salary": "280-360元/天",
        "description": (
            "餐饮/零售数据分析，构建业务指标体系，输出洞察报告驱动业务决策。"
            "参与A/B实验设计与分析，协助搭建自动化报表系统。"
        ),
        "requirements": "Python/R, SQL, 统计学基础, Tableau/PowerBI加分",
        "url": "https://www.zhipin.com/job_detail/demo004.html",
        "boss_activity": "今日活跃",
    },
    {
        "platform": "boss", "job_id": "demo_b05",
        "title": "商业数据分析实习",
        "company": "小红书",
        "location": "上海-长宁区",
        "salary": "250-320元/天",
        "description": (
            "参与社区商业化数据分析，搭建广告效果评估模型，输出品牌投放策略报告。"
            "协助优化用户画像体系，支持算法团队特征工程。"
        ),
        "requirements": "Python, SQL, 统计学, 有互联网数据分析经验优先",
        "url": "https://www.zhipin.com/job_detail/demo005.html",
        "boss_activity": "今日活跃",
    },
    {
        "platform": "boss", "job_id": "demo_b06",
        "title": "增长运营实习生",
        "company": "快手",
        "location": "北京-海淀区",
        "salary": "260-340元/天",
        "description": (
            "用户生命周期管理，拉新/促活/留存策略设计，A/B测试分析，短视频平台用户增长实践。"
        ),
        "requirements": "数据驱动思维, SQL, Python, 了解用户增长方法论",
        "url": "https://www.zhipin.com/job_detail/demo006.html",
        "boss_activity": "本周活跃",
    },
    {
        "platform": "boss", "job_id": "demo_b07",
        "title": "数据运营实习生",
        "company": "哔哩哔哩",
        "location": "上海-杨浦区",
        "salary": "300-400元/天",
        "description": (
            "负责UP主生态数据分析，维护内容运营数据看板，支持创作者激励策略迭代。"
        ),
        "requirements": "SQL, Excel, Python基础, 有内容/社区平台实习优先",
        "url": "https://www.zhipin.com/job_detail/demo007.html",
        "boss_activity": "今日活跃",
    },
    # ── 中厂 · Boss ─────────────────────────────────────────────────────────────
    {
        "platform": "boss", "job_id": "demo_b08",
        "title": "内容运营实习生",
        "company": "知乎",
        "location": "北京-海淀区",
        "salary": "220-280元/天",
        "description": (
            "负责知乎专栏/话题内容运营，分析内容数据指标，参与创作者生态建设。"
        ),
        "requirements": "内容理解力, 数据分析, Excel, 有UGC平台运营经验优先",
        "url": "https://www.zhipin.com/job_detail/demo008.html",
        "boss_activity": "今日活跃",
    },
    {
        "platform": "boss", "job_id": "demo_b09",
        "title": "数据运营实习生",
        "company": "贝壳找房",
        "location": "北京-朝阳区",
        "salary": "250-320元/天",
        "description": (
            "负责房产交易数据分析，搭建城市/门店运营看板，支持业务决策。"
        ),
        "requirements": "SQL, Excel, Python基础, 逻辑清晰, 有地产行业经验优先",
        "url": "https://www.zhipin.com/job_detail/demo009.html",
        "boss_activity": "3天内活跃",
    },
    {
        "platform": "boss", "job_id": "demo_b10",
        "title": "数据分析实习生",
        "company": "大疆",
        "location": "深圳-南山区",
        "salary": "280-360元/天",
        "description": (
            "无人机销售数据分析，参与市场策略分析，输出竞品对比报告与价格策略建议。"
        ),
        "requirements": "Python/R, SQL, 统计学, 英语良好, 硬件产品了解加分",
        "url": "https://www.zhipin.com/job_detail/demo010.html",
        "boss_activity": "今日活跃",
    },
    {
        "platform": "boss", "job_id": "demo_b11",
        "title": "策略运营实习生",
        "company": "携程",
        "location": "上海-长宁区",
        "salary": "260-320元/天",
        "description": (
            "参与OTA平台酒店/机票营销策略分析，通过A/B测试优化转化漏斗，输出专项分析报告。"
        ),
        "requirements": "SQL, Excel/Python, 数据分析, 逻辑思维, 有旅游/电商经验加分",
        "url": "https://www.zhipin.com/job_detail/demo011.html",
        "boss_activity": "本周活跃",
    },
    {
        "platform": "boss", "job_id": "demo_b12",
        "title": "内容运营实习生",
        "company": "微博",
        "location": "北京-西城区",
        "salary": "200-260元/天",
        "description": (
            "参与热搜/话题运营，数据监测与内容质量评估，配合商业化团队进行营销活动策划。"
        ),
        "requirements": "内容理解力, 数据分析, 热点敏感度, Excel, 社交媒体运营经验",
        "url": "https://www.zhipin.com/job_detail/demo012.html",
        "boss_activity": "3天内活跃",
    },
    {
        "platform": "boss", "job_id": "demo_b13",
        "title": "产品运营实习生",
        "company": "科大讯飞",
        "location": "合肥-高新区",
        "salary": "180-240元/天",
        "description": (
            "负责AI教育产品用户运营，分析学员使用数据，输出产品优化建议，协助搭建用户反馈体系。"
        ),
        "requirements": "Excel, Python基础, 教育行业了解, 有AI产品体验优先",
        "url": "https://www.zhipin.com/job_detail/demo013.html",
        "boss_activity": "今日活跃",
    },
    # ── 小厂 · Boss ─────────────────────────────────────────────────────────────
    {
        "platform": "boss", "job_id": "demo_b14",
        "title": "数据运营实习生",
        "company": "互融云科技",
        "location": "北京-丰台区",
        "salary": "180-220元/天",
        "description": (
            "协助金融SaaS产品数据运营，维护客户数据报表，参与产品迭代需求梳理。"
        ),
        "requirements": "Excel, SQL基础, 金融行业了解, 认真负责",
        "url": "https://www.zhipin.com/job_detail/demo014.html",
        "boss_activity": "今日活跃",
    },
    {
        "platform": "boss", "job_id": "demo_b15",
        "title": "社区运营实习生",
        "company": "鱼乐无边（北京）",
        "location": "北京-朝阳区",
        "salary": "150-200元/天",
        "description": (
            "负责垂直内容社区运营，拉新/维活，内容数据分析，协助策划线上活动。"
        ),
        "requirements": "内容运营经验, 数据分析基础, 有社群运营经历优先",
        "url": "https://www.zhipin.com/job_detail/demo015.html",
        "boss_activity": "3天内活跃",
    },
    {
        "platform": "boss", "job_id": "demo_b16",
        "title": "行业运营实习生",
        "company": "云鸟科技",
        "location": "上海-静安区",
        "salary": "200-260元/天",
        "description": (
            "物流SaaS行业运营，维护行业客户关系，协助制定客户成功方案，输出客户行为数据报告。"
        ),
        "requirements": "Excel, 沟通能力, 数据分析基础, 物流/供应链了解优先",
        "url": "https://www.zhipin.com/job_detail/demo016.html",
        "boss_activity": "今日活跃",
    },
    {
        "platform": "boss", "job_id": "demo_b17",
        "title": "数据分析实习生",
        "company": "新思界信息",
        "location": "深圳-福田区",
        "salary": "180-240元/天",
        "description": (
            "协助市场研究报告撰写，收集并清洗行业数据，参与产业链调研与竞品分析。"
        ),
        "requirements": "Excel/Python, 数据收集整理, 文字能力强, 有市场研究经验优先",
        "url": "https://www.zhipin.com/job_detail/demo017.html",
        "boss_activity": "本周活跃",
    },
    # ── 大厂 · 实习僧 ────────────────────────────────────────────────────────────
    {
        "platform": "shixiseng", "job_id": "demo_s01",
        "title": "数据运营实习生",
        "company": "网易",
        "location": "杭州",
        "salary": "260-320元/天",
        "description": (
            "游戏/教育产品数据运营，设计用户分层策略，驱动DAU/留存提升，输出专项分析报告。"
        ),
        "requirements": "Excel, SQL, Python基础, 有数据分析/运营实习优先",
        "url": "https://www.shixiseng.com/intern/demo_s01",
        "boss_activity": "",
    },
    {
        "platform": "shixiseng", "job_id": "demo_s02",
        "title": "行业运营实习生",
        "company": "百度",
        "location": "北京",
        "salary": "280-360元/天",
        "description": (
            "负责百度营销平台行业客户运营，分析行业投放效果，输出优化方案，协助大客户增长。"
        ),
        "requirements": "Excel, SQL, 广告营销基础, 沟通能力强",
        "url": "https://www.shixiseng.com/intern/demo_s02",
        "boss_activity": "",
    },
    {
        "platform": "shixiseng", "job_id": "demo_s03",
        "title": "商业数据分析实习",
        "company": "京东",
        "location": "北京",
        "salary": "260-320元/天",
        "description": (
            "电商平台商业化数据分析，搭建广告/营销效果评估体系，支持ROI优化决策。"
        ),
        "requirements": "SQL, Python, 统计学, 电商行业了解, Tableau加分",
        "url": "https://www.shixiseng.com/intern/demo_s03",
        "boss_activity": "",
    },
    {
        "platform": "shixiseng", "job_id": "demo_s04",
        "title": "增长运营实习生",
        "company": "滴滴",
        "location": "北京",
        "salary": "260-340元/天",
        "description": (
            "出行平台用户增长运营，负责拉新/促活活动策划与效果分析，A/B测试设计与评估。"
        ),
        "requirements": "数据驱动思维, SQL, Python, 了解用户增长方法论",
        "url": "https://www.shixiseng.com/intern/demo_s04",
        "boss_activity": "",
    },
    {
        "platform": "shixiseng", "job_id": "demo_s05",
        "title": "产品运营实习生",
        "company": "小米",
        "location": "北京",
        "salary": "240-300元/天",
        "description": (
            "MIUI/小米社区产品运营，用户反馈收集与分析，参与版本迭代需求整理，输出用户洞察报告。"
        ),
        "requirements": "产品理解力, Excel, 数据分析, 有手机/IoT产品使用经验优先",
        "url": "https://www.shixiseng.com/intern/demo_s05",
        "boss_activity": "",
    },
    # ── 中厂 · 实习僧 ────────────────────────────────────────────────────────────
    {
        "platform": "shixiseng", "job_id": "demo_s06",
        "title": "数据分析实习生",
        "company": "同花顺",
        "location": "杭州",
        "salary": "200-280元/天",
        "description": (
            "金融数据平台分析，负责用户行为数据挖掘，支持产品迭代与营销活动效果评估。"
        ),
        "requirements": "Python/R, SQL, 统计学, 金融知识加分",
        "url": "https://www.shixiseng.com/intern/demo_s06",
        "boss_activity": "",
    },
    {
        "platform": "shixiseng", "job_id": "demo_s07",
        "title": "内容运营实习生",
        "company": "虎牙直播",
        "location": "广州",
        "salary": "200-260元/天",
        "description": (
            "直播平台内容运营，负责游戏/泛娱乐内容数据分析，主播生态维护，活动策划与执行。"
        ),
        "requirements": "数据分析基础, Excel, 对游戏/直播有热情, 有内容运营经验优先",
        "url": "https://www.shixiseng.com/intern/demo_s07",
        "boss_activity": "",
    },
    {
        "platform": "shixiseng", "job_id": "demo_s08",
        "title": "数据运营实习生",
        "company": "唯品会",
        "location": "广州",
        "salary": "210-270元/天",
        "description": (
            "电商特卖平台数据运营，分析用户购买行为，输出选品策略建议，协助搭建商品运营报表体系。"
        ),
        "requirements": "SQL, Excel, Python基础, 电商行业了解",
        "url": "https://www.shixiseng.com/intern/demo_s08",
        "boss_activity": "",
    },
    # ── 小厂 · 实习僧 ────────────────────────────────────────────────────────────
    {
        "platform": "shixiseng", "job_id": "demo_s09",
        "title": "产品运营实习生",
        "company": "晓羊教育",
        "location": "北京",
        "salary": "150-200元/天",
        "description": (
            "K12教育SaaS产品运营，协助学校客户数字化转型，维护客户数据档案，参与产品培训。"
        ),
        "requirements": "Excel, 沟通能力, 教育行业了解, 耐心细致",
        "url": "https://www.shixiseng.com/intern/demo_s09",
        "boss_activity": "",
    },
    {
        "platform": "shixiseng", "job_id": "demo_s10",
        "title": "数据分析实习生",
        "company": "蓝湖",
        "location": "北京",
        "salary": "180-240元/天",
        "description": (
            "设计协作SaaS平台用户行为分析，协助产品团队制定增长策略，维护核心指标看板。"
        ),
        "requirements": "SQL, Python基础, 有产品/设计行业了解, 数据驱动思维",
        "url": "https://www.shixiseng.com/intern/demo_s10",
        "boss_activity": "",
    },
    {
        "platform": "shixiseng", "job_id": "demo_s11",
        "title": "教育运营实习生",
        "company": "好未来",
        "location": "北京",
        "salary": "220-280元/天",
        "description": (
            "在线教育平台学员运营，负责用户分层精细化运营，设计学习激励体系，输出用户留存分析。"
        ),
        "requirements": "Excel, 数据分析基础, 教育行业热情, 有学生辅导/教育经历加分",
        "url": "https://www.shixiseng.com/intern/demo_s11",
        "boss_activity": "",
    },
    {
        "platform": "shixiseng", "job_id": "demo_s12",
        "title": "数据运营实习生",
        "company": "品茗股份",
        "location": "杭州",
        "salary": "160-220元/天",
        "description": (
            "建筑信息化SaaS平台数据运营，维护客户使用数据报表，协助客户成功团队提升留存率。"
        ),
        "requirements": "Excel, SQL基础, 认真负责, 建筑行业了解加分",
        "url": "https://www.shixiseng.com/intern/demo_s12",
        "boss_activity": "",
    },
    {
        "platform": "shixiseng", "job_id": "demo_s13",
        "title": "市场运营实习生",
        "company": "搜狐",
        "location": "北京",
        "salary": "160-220元/天",
        "description": (
            "互联网媒体市场运营，协助内容分发数据分析，参与广告主投放效果评估报告撰写。"
        ),
        "requirements": "Excel, 数据收集整理, 文字能力强, 媒体/广告行业了解优先",
        "url": "https://www.shixiseng.com/intern/demo_s13",
        "boss_activity": "",
    },
]
