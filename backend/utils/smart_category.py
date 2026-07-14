"""智能分类推荐"""
import re
from collections import defaultdict

from utils.data_core import load_v4
from utils.transactions import _load_transactions


_PRESET_CATEGORY_MAP = {
    "餐饮": ["外卖", "餐厅", "吃饭", "午餐", "晚餐", "早餐", "奶茶", "咖啡", "火锅", "烧烤",
             "麦当劳", "肯德基", "星巴克", "瑞幸", "沙县", "兰州", "面馆", "食堂", "小吃",
             "必胜客", "海底捞", "喜茶", "奈雪", "茶百道", "蜜雪冰城", "美团", "饿了么",
             "正餐", "快餐", "便当", "盒饭", "汉堡", "披萨", "寿司", "日料", "韩料",
             "甜品", "蛋糕", "面包", "零食", "水果", "生鲜", "饮料", "酒水",
             "大排档", "夜宵", "下午茶", "brunch", "自助餐", "饮品"],
    "交通": ["打车", "滴滴", "地铁", "公交", "高铁", "飞机", "加油", "停车", "过路费",
             "共享单车", "哈啰", "青桔", "曹操", "高德", "12306", "携程",
             "出租", "顺风车", "代驾", "ETC", "高速", "火车", "机票",
             "油费", "充电", "洗车", "保养", "年检", "保险"],
    "购物": ["淘宝", "京东", "拼多多", "天猫", "超市", "商场", "便利店",
             "711", "全家", "盒马", "山姆", "Costco", "网购",
             "服装", "鞋子", "包包", "数码", "手机", "电脑", "家电",
             "日用品", "纸巾", "洗衣液", "牙膏", "洗发水"],
    "居住": ["房租", "水电", "燃气", "物业", "宽带", "话费", "电费", "水费",
             "房贷", "装修", "家具", "家电维修", "家政", "保洁"],
    "娱乐": ["电影", "游戏", "会员", "视频", "音乐", "KTV", "剧本杀", "密室",
             "演出", "演唱会", "展览", "博物馆", "游乐场", "健身", "瑜伽",
             "桌游", "网吧", "直播", "打赏"],
    "社交": ["红包", "礼物", "请客", "聚餐", "份子钱", "结婚", "随礼",
             "生日", "聚会", "团建", "请客吃饭", "AA"],
    "旅游": ["酒店", "民宿", "机票", "景点", "门票", "旅游", "旅行",
             "度假", "签证", "攻略", "导游", "租车"],
    "车辆": ["车贷", "保养", "维修", "洗车", "停车费", "ETC", "违章",
             "车险", "加油", "充电桩", "轮胎", "刹车"],
    "医疗": ["医院", "药店", "体检", "挂号", "门诊", "牙科", "眼科",
             "看病", "买药", "药房", "诊所", "医保", "住院"],
    "个护": ["理发", "美容", "护肤", "化妆品", "美甲", "spa",
             "美发", "造型", "香水", "防晒"],
    "学习": ["课程", "培训", "书籍", "考试", "学费",
             "网课", "知识付费", "得到", "极客时间", "Udemy"],
    "数字消费": ["话费", "流量", "会员", "订阅", "云服务", "域名",
              "iCloud", "Apple", "Google", "Netflix", "Spotify", "B站会员",
              "百度网盘", "阿里云", "腾讯云"],
    "其他": ["快递", "打印", "复印", "洗衣", "干洗", "搬家", "维修"],
}


def _build_keyword_category_map():
    mapping = defaultdict(lambda: defaultdict(int))

    try:
        df = load_v4()
        valid = df[df["valid_for_stats"] == "True"]
        for _, row in valid.iterrows():
            cat = row.get("category_l1", "")
            if not cat:
                continue
            project = str(row.get("clean_project", "")).strip()
            if project:
                for word in re.split(r"[\s,，.。、/\\()（）]+", project):
                    word = word.strip()
                    if len(word) >= 2:
                        mapping[word][cat] += 1
            raw_cat = str(row.get("分类", "")).strip()
            if raw_cat and raw_cat != cat:
                mapping[raw_cat][cat] += 5
            note = str(row.get("备注", "")).strip()
            if note:
                for word in re.split(r"[\s,，.。、/\\()（）]+", note):
                    word = word.strip()
                    if len(word) >= 2:
                        mapping[word][cat] += 1
    except Exception:
        pass

    try:
        txs = _load_transactions()
        for tx in txs:
            note = tx.get("note", "").strip()
            cat = tx.get("category", "")
            if note and cat:
                for word in re.split(r"[\s,，.。、/\\()（）]+", note):
                    word = word.strip()
                    if len(word) >= 2:
                        mapping[word][cat] += 2
    except Exception:
        pass

    return mapping


def suggest_category(text, top_n=3):
    if not text or not text.strip():
        return []

    text = text.strip()
    results = defaultdict(lambda: {"score": 0, "source": ""})

    for cat, keywords in _PRESET_CATEGORY_MAP.items():
        for kw in keywords:
            if kw in text:
                results[cat]["score"] += 10
                results[cat]["source"] = "常用规则"

    keyword_map = _build_keyword_category_map()
    for word, cat_counts in keyword_map.items():
        if word in text:
            for cat, count in cat_counts.items():
                results[cat]["score"] += count
                results[cat]["source"] = "历史数据"

    if not results:
        return []

    max_score = max(r["score"] for r in results.values())
    sorted_results = sorted(results.items(), key=lambda x: -x[1]["score"])[:top_n]

    return [
        {
            "category": cat,
            "confidence": round(data["score"] / max_score, 2) if max_score > 0 else 0,
            "source": data["source"],
        }
        for cat, data in sorted_results
    ]


def get_category_stats():
    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]

    stats = {}
    for cat in expense["category_l1"].unique():
        cat_data = expense[expense["category_l1"] == cat]
        stats[cat] = {
            "count": len(cat_data),
            "total": round(cat_data["cny_amount"].sum(), 2),
            "avg": round(cat_data["cny_amount"].mean(), 2),
            "top_projects": cat_data["clean_project"].value_counts().head(5).to_dict(),
        }
    return stats
