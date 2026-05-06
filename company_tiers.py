"""Company tier classification for the Chinese tech / internet industry.

Tiers:
  大厂 — top-tier (BAT, ByteDance, Meituan, Xiaomi, Huawei, etc.)
  中厂 — mid-tier (知乎, 携程, 大疆, 商汤, etc.)
  小厂 — everything else
"""

# Lowercase keywords — first match within a tier wins
_TIER1 = [
    "字节跳动", "字节", "bytedance", "抖音", "tiktok", "今日头条",
    "腾讯", "tencent", "微信", "wechat",
    "阿里巴巴", "阿里", "alibaba", "淘宝", "taobao", "天猫", "支付宝",
    "蚂蚁集团", "蚂蚁", "阿里云", "钉钉", "高德", "菜鸟", "盒马", "饿了么",
    "百度", "baidu",
    "京东", "jd.com",
    "美团", "meituan", "大众点评",
    "滴滴", "didi",
    "小米", "xiaomi",
    "网易", "netease",
    "拼多多", "pinduoduo", "temu",
    "快手", "kuaishou",
    "哔哩哔哩", "bilibili", "b站",
    "小红书", "xiaohongshu",
    "华为", "huawei",
    "荣耀", "honor",
    "oppo", "vivo",
    "苹果", "apple", "谷歌", "google", "微软", "microsoft",
    "亚马逊", "amazon", "meta", "facebook",
]

_TIER2 = [
    "爱奇艺", "iqiyi",
    "优酷", "youku",
    "微博", "weibo",
    "知乎", "zhihu",
    "携程", "ctrip", "trip.com",
    "去哪儿", "qunar",
    "58同城", "安居客",
    "芒果tv", "芒果",
    "贝壳找房", "贝壳", "链家",
    "猎聘", "liepin",
    "拉勾", "lagou",
    "前程无忧", "51job",
    "智联招聘", "zhilian",
    "boss直聘", "kanzhun",
    "360", "奇虎",
    "商汤", "sensetime",
    "旷视", "megvii",
    "科大讯飞", "讯飞", "iflytek",
    "奇安信",
    "东方财富", "同花顺",
    "虎牙", "huya",
    "斗鱼", "douyu",
    "猫眼",
    "大疆", "dji",
    "宁德时代", "catl",
    "比亚迪", "byd",
    "中兴", "zte",
    "联想", "lenovo",
    "新东方", "好未来", "作业帮", "猿辅导",
    "keep",
    "货拉拉",
    "满帮",
    "得物",
    "唯品会", "vip.com",
    "汽车之家", "懂车帝",
    "soul",
    "陌陌", "momo",
    "搜狐", "sohu",
    "新浪", "sina",
    "转转", "闲鱼",
    "途虎", "瓜子",
    "喜马拉雅",
    "墨迹天气",
    "BOSS",
]


def get_company_tier(company: str) -> str:
    """Return '大厂' / '中厂' / '小厂' for the given company name."""
    name = (company or "").lower()
    for kw in _TIER1:
        if kw in name:
            return "大厂"
    for kw in _TIER2:
        if kw in name:
            return "中厂"
    return "小厂"
