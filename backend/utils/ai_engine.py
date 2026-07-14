"""AI 财务分析引擎 — 后台自动生成洞察、回答问题"""
import json
import os
from datetime import datetime, timedelta

from utils.data_core import load_v4, load_unified
from utils.assets import get_overview, get_asset_history
from utils.budget import get_budget_status
from utils.transactions import _load_credit_card


# ===================== 洞察存储 =====================

def _get_conn():
    from utils import db
    db.init_db()
    return db.get_conn()


def init_insights_table():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            insight_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            priority INTEGER DEFAULT 0,
            is_read INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _save_insight(insight_type, title, content, priority=0):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO ai_insights (insight_type, title, content, priority, created_at) VALUES (?, ?, ?, ?, ?)",
        (insight_type, title, content, priority, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()


def get_unread_insights():
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, insight_type, title, content, priority, created_at FROM ai_insights WHERE is_read=0 ORDER BY priority DESC, created_at DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return [{"id": r[0], "type": r[1], "title": r[2], "content": r[3], "priority": r[4], "created_at": r[5]} for r in rows]


def mark_insight_read(insight_id):
    conn = _get_conn()
    conn.execute("UPDATE ai_insights SET is_read=1 WHERE id=?", (insight_id,))
    conn.commit()
    conn.close()


# ===================== 即时分析 =====================

def on_transaction_added(tx):
    """记账后即时分析：大额检测、预算预警"""
    insights = []
    amount = float(tx.get("amount", 0))
    category = tx.get("category", "")
    tx_type = tx.get("type", "支出")

    if tx_type != "支出":
        return insights

    # 1. 大额检测
    large = _check_large_transaction(category, amount)
    if large:
        _save_insight("large_tx", large["title"], large["content"], priority=1)
        insights.append(large)

    # 2. 预算预警
    budget_alert = _check_budget_alert(category, amount)
    if budget_alert:
        _save_insight("budget_alert", budget_alert["title"], budget_alert["content"], priority=1)
        insights.append(budget_alert)

    return insights


def _check_large_transaction(category, amount):
    """检测大额交易"""
    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]

    cat_data = expense[expense["category_l1"] == category]
    if len(cat_data) < 5:
        return None

    mean = cat_data["cny_amount"].mean()
    std = cat_data["cny_amount"].std()

    if std > 0 and amount > mean + 2 * std:
        return {
            "title": f"大额交易提醒：{category}",
            "content": f"这笔 ¥{amount:,.0f} 的{category}支出，高于该分类历史均值 ¥{mean:,.0f}（+{((amount/mean-1)*100):.0f}%）。建议关注预算。",
            "severity": "warning",
        }
    return None


def _check_budget_alert(category, amount):
    """检查预算预警"""
    month_str = datetime.now().strftime("%Y-%m")
    try:
        bd = get_budget_status(month_str)
        for item in bd["items"]:
            if item["category"] == category:
                new_ratio = (item["actual"] + amount) / item["budget"] * 100 if item["budget"] else 0
                if new_ratio >= 100:
                    return {
                        "title": f"预算超支预警：{category}",
                        "content": f"记账后{category}预算使用将达到 {new_ratio:.0f}%（¥{item['actual']+amount:,.0f}/¥{item['budget']:,.0f}），已超支。",
                        "severity": "high",
                    }
                elif new_ratio >= 80:
                    return {
                        "title": f"预算接近上限：{category}",
                        "content": f"记账后{category}预算使用将达到 {new_ratio:.0f}%，剩余 ¥{max(item['budget']-item['actual']-amount, 0):,.0f}。",
                        "severity": "medium",
                    }
    except Exception:
        pass
    return None


# ===================== 日报生成 =====================

def generate_daily_insight():
    """生成今日洞察"""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    month_str = now.strftime("%Y-%m")

    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]

    # 今日数据
    today_data = valid[valid["clean_date"].dt.strftime("%Y-%m-%d") == today]
    today_expense = today_data[today_data["corrected_type"] == "支出"]["cny_amount"].sum()
    today_income = today_data[today_data["corrected_type"] == "收入"]["cny_amount"].sum()
    today_count = len(today_data)

    # 本月累计
    month_data = valid[valid["month"] == month_str]
    month_expense = month_data[month_data["corrected_type"] == "支出"]["cny_amount"].sum()
    month_income = month_data[month_data["corrected_type"] == "收入"]["cny_amount"].sum()

    # 历史月均
    expense = valid[valid["corrected_type"] == "支出"]
    recent = expense[expense["month"] >= "2025-09"]
    avg_monthly = recent.groupby("month")["cny_amount"].sum().mean()

    # 预测本月总额
    day_of_month = now.day
    if day_of_month > 0 and avg_monthly > 0:
        projected = month_expense / day_of_month * 30
        deviation = (projected - avg_monthly) / avg_monthly * 100
    else:
        projected = month_expense
        deviation = 0

    # 今日分类
    today_cats = today_data[today_data["corrected_type"] == "支出"].groupby("category_l1")["cny_amount"].sum()
    cat_detail = "、".join([f"{cat} ¥{amt:,.0f}" for cat, amt in today_cats.items()]) if len(today_cats) > 0 else "无支出"

    # 构建洞察文本
    lines = []
    lines.append(f"📊 今日（{today}）收支：支出 ¥{today_expense:,.0f}，收入 ¥{today_income:,.0f}，共 {today_count} 笔")
    lines.append(f"   分类：{cat_detail}")
    lines.append(f"📈 本月累计：支出 ¥{month_expense:,.0f}，收入 ¥{month_income:,.0f}")

    if deviation > 20:
        lines.append(f"⚠️ 按当前速度，月底预计支出 ¥{projected:,.0f}（高于历史月均 {deviation:.0f}%）")
    elif deviation < -20:
        lines.append(f"✅ 按当前速度，月底预计支出 ¥{projected:,.0f}（低于历史月均 {abs(deviation):.0f}%）")
    else:
        lines.append(f"ℹ️ 按当前速度，月底预计支出 ¥{projected:,.0f}（与历史月均持平）")

    # 信用卡
    try:
        cc = _load_credit_card()
        if cc["balance"] > 0:
            lines.append(f"💳 信用卡待还 ¥{cc['balance']:,.0f}")
    except Exception:
        pass

    content = "\n".join(lines)
    _save_insight("daily", f"📊 {today} 日报", content, priority=0)
    return content


def generate_weekly_report():
    """生成周报"""
    now = datetime.now()
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    week_end = now.strftime("%Y-%m-%d")
    month_str = now.strftime("%Y-%m")

    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]

    # 本周数据
    week_data = expense[(expense["clean_date"] >= week_start) & (expense["clean_date"] <= week_end)]
    week_total = week_data["cny_amount"].sum()
    week_cats = week_data.groupby("category_l1")["cny_amount"].sum().sort_values(ascending=False)

    # 本月累计
    month_data = expense[expense["month"] == month_str]
    month_total = month_data["cny_amount"].sum()

    lines = []
    lines.append(f"📊 周报（{week_start} ~ {week_end}）")
    lines.append(f"本周总支出：¥{week_total:,.0f}")
    if len(week_cats) > 0:
        top3 = week_cats.head(3)
        lines.append(f"TOP3 分类：{'、'.join([f'{cat} ¥{amt:,.0f}' for cat, amt in top3.items()])}")
    lines.append(f"本月累计：¥{month_total:,.0f}")

    content = "\n".join(lines)
    _save_insight("weekly", f"📊 周报 {week_start}~{week_end}", content, priority=0)
    return content


# ===================== 对话增强 =====================

def build_context_for_llm():
    """构建 LLM 对话上下文"""
    try:
        ov = get_overview()
        month_str = datetime.now().strftime("%Y-%m")
        bd = get_budget_status(month_str)

        context = {
            "净资产": ov["net_worth"],
            "本月支出": ov["monthly_expense"],
            "流动性覆盖率": ov["liquidity_coverage"],
            "投资占比": ov["investment_ratio"],
            "预算执行": f"{bd['total_ratio']}%",
        }
        return json.dumps(context, ensure_ascii=False)
    except Exception:
        return "{}"
