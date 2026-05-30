"""生成演示用岗位数据（含投递 timeline），写入 demo_timeline_jobs.json。"""
import json
from pathlib import Path

JOBS = [
    # ─── Offer ───────────────────────────────────────────────────────────────
    {
        "id": "d01", "platform": "boss", "title": "数据运营实习生",
        "company": "字节跳动", "location": "北京-海淀区", "salary": "400-500元/天",
        "description": "负责抖音内容数据分析，搭建运营看板，用数据驱动内容策略优化。",
        "requirements": "SQL、Python/Excel、数据分析基础，本科及以上，有运营经验优先",
        "url": "https://www.zhipin.com/job_detail/demo_d01.html",
        "match_score": 92, "company_tier": "大厂",
        "status": "offer",
        "match_reason": "数据分析背景与岗位高度匹配，Python/SQL 技能完全覆盖 JD 要求",
        "match_highlights": ["Python/SQL 双修", "数据驱动运营经验", "USC 数据科学背景"],
        "match_concerns": ["缺少短视频行业经验"],
        "timeline": [
            {"date": "2026-05-03", "status": "已投递", "note": "通过 Boss直聘 投递，附个性化打招呼"},
            {"date": "2026-05-05", "status": "HR已查看", "note": "HR 今日活跃，查看了简历"},
            {"date": "2026-05-07", "status": "面试邀请", "note": "约视频一面，5月9日 14:00"},
            {"date": "2026-05-09", "status": "一面", "note": "45分钟，考察 SQL 和数据分析思路，表现良好"},
            {"date": "2026-05-13", "status": "二面", "note": "与业务 Leader 沟通，聊运营策略方向"},
            {"date": "2026-05-20", "status": "offer", "note": "🎉 收到 Offer，薪资 450元/天，6月1日到岗"},
        ],
    },
    {
        "id": "d02", "platform": "boss", "title": "策略运营实习生",
        "company": "美团", "location": "北京-朝阳区", "salary": "350-450元/天",
        "description": "参与到家业务策略分析，输出数据报告，协助制定营销活动策略。",
        "requirements": "Python/SQL、数据分析、逻辑思维强，有互联网运营经验优先",
        "url": "https://www.zhipin.com/job_detail/demo_d02.html",
        "match_score": 88, "company_tier": "大厂",
        "status": "offer",
        "match_reason": "策略方向与用户背景高度契合，数据分析能力强",
        "match_highlights": ["策略分析经验", "RFM 用户分层实战", "结果导向思维"],
        "match_concerns": ["本地生活行业不熟悉"],
        "timeline": [
            {"date": "2026-05-05", "status": "已投递", "note": "实习僧投递，简历匹配分 88"},
            {"date": "2026-05-06", "status": "HR已查看", "note": "次日即查看"},
            {"date": "2026-05-08", "status": "面试邀请", "note": "约线上一面，5月10日 10:00"},
            {"date": "2026-05-10", "status": "一面", "note": "考察 A/B Testing 设计，回答顺畅"},
            {"date": "2026-05-15", "status": "二面", "note": "业务 PM 面，聊增长策略案例"},
            {"date": "2026-05-22", "status": "offer", "note": "🎉 Offer，400元/天，可远程"},
        ],
    },

    # ─── 终面/等待结果 ────────────────────────────────────────────────────────
    {
        "id": "d03", "platform": "boss", "title": "商业数据分析实习生",
        "company": "腾讯", "location": "深圳-南山区", "salary": "300-400元/天",
        "description": "支持微信支付商业化数据分析，构建业务指标体系，输出专项分析报告。",
        "requirements": "SQL 熟练、Python 数据处理、BI 工具（Tableau/Power BI）",
        "url": "https://www.zhipin.com/job_detail/demo_d03.html",
        "match_score": 85, "company_tier": "大厂",
        "status": "final_interview",
        "match_reason": "指标体系和数据分析能力强匹配，计量经济学背景加分",
        "match_highlights": ["Tableau 实战经验", "指标体系建设", "计量经济学背景"],
        "match_concerns": ["金融支付行业了解有限"],
        "timeline": [
            {"date": "2026-05-08", "status": "已投递", "note": "Boss直聘，附 Tableau 作品集链接"},
            {"date": "2026-05-10", "status": "HR已查看", "note": "HR 查看简历"},
            {"date": "2026-05-13", "status": "面试邀请", "note": "约一面，5月15日视频"},
            {"date": "2026-05-15", "status": "一面", "note": "技术面，SQL 笔试 + 案例分析"},
            {"date": "2026-05-19", "status": "二面", "note": "业务面，重点考察数据洞察逻辑"},
            {"date": "2026-05-27", "status": "final_interview", "note": "终面约在 5月29日，等待中…"},
        ],
    },
    {
        "id": "d04", "platform": "shixiseng", "title": "增长运营实习生",
        "company": "小红书", "location": "上海-静安区", "salary": "350-400元/天",
        "description": "参与社区内容增长策略，分析用户行为数据，支持活动效果评估。",
        "requirements": "数据分析能力、内容平台经验优先、Excel/Python",
        "url": "https://www.shixiseng.com/intern/demo_d04",
        "match_score": 83, "company_tier": "大厂",
        "status": "waiting",
        "match_reason": "内容运营背景与增长方向契合",
        "match_highlights": ["内容策略实战经验", "用户分层运营", "增长思维"],
        "match_concerns": ["UGC 社区经验较少"],
        "timeline": [
            {"date": "2026-05-10", "status": "已投递", "note": "实习僧投递"},
            {"date": "2026-05-12", "status": "HR已查看", "note": ""},
            {"date": "2026-05-16", "status": "一面", "note": "视频面试，聊内容增长案例"},
            {"date": "2026-05-21", "status": "二面", "note": "Team Leader 面，深聊运营策略"},
            {"date": "2026-05-28", "status": "waiting", "note": "面完等 HR 反馈，预计本周出结果"},
        ],
    },

    # ─── 面试进行中 ──────────────────────────────────────────────────────────
    {
        "id": "d05", "platform": "boss", "title": "数据产品运营实习生",
        "company": "阿里巴巴", "location": "杭州-余杭区", "salary": "400-500元/天",
        "description": "参与淘宝商家数据产品的运营工作，收集用户反馈，推动产品迭代。",
        "requirements": "数据分析、产品思维、SQL，有电商经验优先",
        "url": "https://www.zhipin.com/job_detail/demo_d05.html",
        "match_score": 80, "company_tier": "大厂",
        "status": "interview",
        "match_reason": "数据分析 + 运营背景匹配，产品思维有所体现",
        "match_highlights": ["数据驱动产品迭代经验", "SQL 熟练", "用户调研能力"],
        "match_concerns": ["电商领域背景薄弱"],
        "timeline": [
            {"date": "2026-05-12", "status": "已投递", "note": "Boss直聘"},
            {"date": "2026-05-14", "status": "HR已查看", "note": ""},
            {"date": "2026-05-20", "status": "面试邀请", "note": "约一面，5月22日 15:00"},
            {"date": "2026-05-22", "status": "interview", "note": "一面进行中，准备 SQL 和产品案例"},
        ],
    },
    {
        "id": "d06", "platform": "shixiseng", "title": "用户运营分析实习生",
        "company": "京东", "location": "北京-亦庄", "salary": "300-380元/天",
        "description": "参与用户生命周期管理，建立用户分层模型，输出专项运营策略。",
        "requirements": "SQL、Python、RFM 模型，有用户运营经验",
        "url": "https://www.shixiseng.com/intern/demo_d06",
        "match_score": 86, "company_tier": "大厂",
        "status": "interview",
        "match_reason": "RFM 模型实战经验与岗位完全吻合",
        "match_highlights": ["RFM 用户分层实战", "SQL 用户画像", "私域运营经验"],
        "match_concerns": ["电商行业了解有限"],
        "timeline": [
            {"date": "2026-05-14", "status": "已投递", "note": "简历命中率高，优先投递"},
            {"date": "2026-05-16", "status": "HR已查看", "note": "HR 同日查看"},
            {"date": "2026-05-23", "status": "面试邀请", "note": "约一面，5月26日线上"},
            {"date": "2026-05-26", "status": "interview", "note": "一面完成，待二面通知"},
        ],
    },

    # ─── 已查看/沟通中 ───────────────────────────────────────────────────────
    {
        "id": "d07", "platform": "boss", "title": "内容运营数据分析实习生",
        "company": "B站", "location": "上海-杨浦区", "salary": "300-350元/天",
        "description": "分析内容数据趋势，支持 UP 主运营策略，搭建内容健康度指标体系。",
        "requirements": "Python/SQL、数据可视化、对内容平台有兴趣",
        "url": "https://www.zhipin.com/job_detail/demo_d07.html",
        "match_score": 78, "company_tier": "大厂",
        "status": "viewed",
        "match_reason": "内容数据分析背景适配，可视化能力强",
        "match_highlights": ["数据可视化实战", "内容指标体系经验"],
        "match_concerns": ["二次元/游戏文化背景较少"],
        "timeline": [
            {"date": "2026-05-16", "status": "已投递", "note": "Boss直聘，打招呼"},
            {"date": "2026-05-18", "status": "viewed", "note": "HR 已查看简历，尚未回复"},
        ],
    },
    {
        "id": "d08", "platform": "boss", "title": "商业化运营实习生",
        "company": "快手", "location": "北京-海淀区", "salary": "350-400元/天",
        "description": "参与商业化产品运营，分析广告投放数据，协助制定增长策略。",
        "requirements": "数据分析能力、广告/商业化方向了解、Excel",
        "url": "https://www.zhipin.com/job_detail/demo_d08.html",
        "match_score": 72, "company_tier": "大厂",
        "status": "chatting",
        "match_reason": "商业分析方向吻合，但广告行业背景薄弱",
        "match_highlights": ["数据分析逻辑清晰", "商业策略案例丰富"],
        "match_concerns": ["广告/程序化购买经验欠缺"],
        "timeline": [
            {"date": "2026-05-18", "status": "已投递", "note": "Boss 打招呼"},
            {"date": "2026-05-19", "status": "chatting", "note": "HR 回复，表示有兴趣，询问到岗时间"},
        ],
    },
    {
        "id": "d09", "platform": "shixiseng", "title": "数据运营实习生",
        "company": "网易", "location": "广州-天河区", "salary": "280-350元/天",
        "description": "参与游戏产品数据分析，搭建游戏运营数据看板，支持活动效果评估。",
        "requirements": "SQL、Python，对游戏行业感兴趣",
        "url": "https://www.shixiseng.com/intern/demo_d09",
        "match_score": 70, "company_tier": "大厂",
        "status": "viewed",
        "match_reason": "数据技能匹配，但游戏行业背景空白",
        "match_highlights": ["SQL 数据提取能力", "看板搭建经验"],
        "match_concerns": ["游戏产品认知薄弱", "广州异地"],
        "timeline": [
            {"date": "2026-05-19", "status": "已投递", "note": "实习僧投递"},
            {"date": "2026-05-21", "status": "viewed", "note": "HR 已查看，无回复"},
        ],
    },

    # ─── 已投递/未查看 ───────────────────────────────────────────────────────
    {
        "id": "d10", "platform": "boss", "title": "产品数据分析实习生",
        "company": "滴滴", "location": "北京-海淀区", "salary": "350-400元/天",
        "description": "支持出行产品核心指标分析，参与用户分群建模和策略实验设计。",
        "requirements": "SQL 熟练、统计学基础、Python，有 A/B 实验经验优先",
        "url": "https://www.zhipin.com/job_detail/demo_d10.html",
        "match_score": 84, "company_tier": "大厂",
        "status": "applied",
        "match_reason": "统计学背景与实验设计能力高度匹配",
        "match_highlights": ["计量经济学实验设计背景", "PSM-DID 因果推断经验", "Python 数据处理"],
        "match_concerns": ["出行行业不熟悉"],
        "timeline": [
            {"date": "2026-05-22", "status": "applied", "note": "Boss直聘投递，等待查看"},
        ],
    },
    {
        "id": "d11", "platform": "shixiseng", "title": "运营数据分析师（实习）",
        "company": "拼多多", "location": "上海-长宁区", "salary": "400-480元/天",
        "description": "参与电商平台运营数据分析，支持供应链和营销活动决策。",
        "requirements": "SQL、Python、数据分析，电商行业经验优先",
        "url": "https://www.shixiseng.com/intern/demo_d11",
        "match_score": 75, "company_tier": "大厂",
        "status": "applied",
        "match_reason": "数据分析能力匹配，但缺电商背景",
        "match_highlights": ["量化分析能力", "数据可视化"],
        "match_concerns": ["无电商项目经验"],
        "timeline": [
            {"date": "2026-05-23", "status": "applied", "note": "实习僧投递"},
        ],
    },
    {
        "id": "d12", "platform": "boss", "title": "增长策略实习生",
        "company": "得物", "location": "上海-浦东新区", "salary": "300-380元/天",
        "description": "参与用户增长策略制定，分析拉新/留存漏斗，设计增长实验方案。",
        "requirements": "数据分析、增长思维、漏斗分析、Python/SQL",
        "url": "https://www.zhipin.com/job_detail/demo_d12.html",
        "match_score": 76, "company_tier": "中厂",
        "status": "applied",
        "match_reason": "增长思维和漏斗分析能力契合",
        "match_highlights": ["用户增长项目经验", "A/B 测试方法论"],
        "match_concerns": ["潮流电商行业认知薄弱"],
        "timeline": [
            {"date": "2026-05-24", "status": "applied", "note": "Boss直聘，今日活跃 HR"},
        ],
    },

    # ─── 待投递 ──────────────────────────────────────────────────────────────
    {
        "id": "d13", "platform": "boss", "title": "数据运营实习生",
        "company": "微博", "location": "北京-海淀区", "salary": "250-300元/天",
        "description": "负责内容数据日报，分析热点传播路径，支持运营活动复盘。",
        "requirements": "数据分析、内容平台经验、SQL/Excel",
        "url": "https://www.zhipin.com/job_detail/demo_d13.html",
        "match_score": 71, "company_tier": "中厂",
        "status": "pending",
        "match_reason": "内容运营背景匹配，数据分析能力覆盖 JD",
        "match_highlights": ["内容数据分析经验", "传播路径分析方法"],
        "match_concerns": ["薪资偏低，可作备选"],
        "timeline": [],
    },
    {
        "id": "d14", "platform": "shixiseng", "title": "商业分析实习生",
        "company": "唯品会", "location": "广州-番禺区", "salary": "200-280元/天",
        "description": "参与会员体系数据分析，支持促销活动效果归因，输出经营分析报告。",
        "requirements": "SQL、Excel、数据分析思维，有电商经验加分",
        "url": "https://www.shixiseng.com/intern/demo_d14",
        "match_score": 68, "company_tier": "中厂",
        "status": "pending",
        "match_reason": "会员体系和 RFM 经验匹配，但广州异地",
        "match_highlights": ["RFM 会员分层实战", "活动效果归因方法"],
        "match_concerns": ["异地，薪资偏低"],
        "timeline": [],
    },
    {
        "id": "d15", "platform": "boss", "title": "AI 产品运营实习生",
        "company": "百度", "location": "北京-海淀区", "salary": "350-400元/天",
        "description": "参与文心一言等 AI 产品的运营工作，分析用户使用行为，支持产品迭代策略。",
        "requirements": "数据分析、对 AI 产品感兴趣、Python/SQL",
        "url": "https://www.zhipin.com/job_detail/demo_d15.html",
        "match_score": 79, "company_tier": "大厂",
        "status": "pending",
        "match_reason": "AI + 运营交叉背景与岗位方向高度契合",
        "match_highlights": ["AI 产品实战经验（Scale AI）", "数据分析 + 运营双线背景"],
        "match_concerns": ["百度系产品生态不熟悉"],
        "timeline": [],
    },

    # ─── 已拒绝 ──────────────────────────────────────────────────────────────
    {
        "id": "d16", "platform": "shixiseng", "title": "数据分析实习生",
        "company": "猿辅导", "location": "北京-西城区", "salary": "200-260元/天",
        "description": "参与在线教育数据分析，构建学员学习行为模型，支持课程运营优化。",
        "requirements": "Python/SQL、数据分析、教育行业了解",
        "url": "https://www.shixiseng.com/intern/demo_d16",
        "match_score": 65, "company_tier": "中厂",
        "status": "rejected",
        "match_reason": "数据能力匹配，但教育行业背景不足",
        "match_highlights": ["Python 数据建模能力"],
        "match_concerns": ["无教育行业背景", "薪资偏低"],
        "timeline": [
            {"date": "2026-05-06", "status": "已投递", "note": "实习僧投递"},
            {"date": "2026-05-08", "status": "HR已查看", "note": ""},
            {"date": "2026-05-10", "status": "rejected", "note": "HR 回复：该岗位已满，感谢投递"},
        ],
    },
    {
        "id": "d17", "platform": "boss", "title": "直播运营数据实习生",
        "company": "虎牙直播", "location": "广州-天河区", "salary": "220-280元/天",
        "description": "参与直播间数据分析，支持主播运营策略制定，分析流量转化路径。",
        "requirements": "数据分析、直播/游戏行业了解、SQL",
        "url": "https://www.zhipin.com/job_detail/demo_d17.html",
        "match_score": 58, "company_tier": "中厂",
        "status": "rejected",
        "match_reason": "数据分析能力基础具备，但直播行业背景完全空白",
        "match_highlights": ["数据提取和报表能力"],
        "match_concerns": ["无直播行业背景", "无游戏/娱乐经验", "广州异地"],
        "timeline": [
            {"date": "2026-05-08", "status": "已投递", "note": "Boss直聘"},
            {"date": "2026-05-11", "status": "rejected", "note": "简历不通过，行业背景不符"},
        ],
    },
    {
        "id": "d18", "platform": "shixiseng", "title": "供应链数据分析实习生",
        "company": "菜鸟网络", "location": "杭州-余杭区", "salary": "300-350元/天",
        "description": "参与物流供应链数据分析，优化仓储调度模型，支持降本增效项目。",
        "requirements": "Python/SQL、运筹优化或供应链知识、数据建模",
        "url": "https://www.shixiseng.com/intern/demo_d18",
        "match_score": 60, "company_tier": "大厂",
        "status": "rejected",
        "match_reason": "数据能力具备，但供应链专业方向不符",
        "match_highlights": ["Python 建模能力"],
        "match_concerns": ["无供应链/物流行业背景", "运筹优化知识薄弱"],
        "timeline": [
            {"date": "2026-05-10", "status": "已投递", "note": "实习僧投递"},
            {"date": "2026-05-13", "status": "HR已查看", "note": ""},
            {"date": "2026-05-15", "status": "rejected", "note": "方向不符，HR 建议关注运营类岗位"},
        ],
    },
]


def main():
    out = Path(__file__).parent / "demo_timeline_jobs.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(JOBS, f, ensure_ascii=False, indent=2)
    print(f"✅ 写入 {len(JOBS)} 条 demo 岗位 → {out}")

    # 统计各状态分布
    from collections import Counter
    dist = Counter(j["status"] for j in JOBS)
    for k, v in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
