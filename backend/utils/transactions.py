"""实时记账 + 信用卡管理"""
import json
import os

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CREDIT_CARD_FILE
from utils.data_core import _file_locks, _atomic_write, _invalidate_unified_cache


# ---- 手动记账 (SQLite) ----

def _get_conn():
    from utils import db
    db.init_db()
    return db.get_conn()


def _load_transactions():
    """从 transactions 表加载手动记账记录（source='manual'）"""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            'SELECT id, "clean_date", "cny_amount", "category_l1", "corrected_type", '
            '"账户", "备注", "created_at" FROM transactions '
            "WHERE source='manual' ORDER BY id DESC"
        )
        rows = [{"id": r[0], "date": r[1], "amount": str(r[2]), "category": r[3],
                 "type": r[4], "account": r[5], "note": r[6], "created_at": r[7]}
                for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"[WARNING] _load_transactions failed: {e}")
        return []


def _save_transactions(rows):
    pass  # 兼容旧逻辑


TRANSACTIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "实时记账.csv")
DEFAULT_ACCOUNTS = ["招行储蓄卡", "微信零钱", "现金", "信用卡"]


# ---- 信用卡 ----

def _load_credit_card():
    if os.path.exists(CREDIT_CARD_FILE):
        with open(CREDIT_CARD_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 文件存在但无历史记录且余额为0：初始化为 config 默认值
        if not data.get("history") and data.get("balance", 0) == 0:
            from config import BILLS_PAYABLE
            data["balance"] = sum(BILLS_PAYABLE.values()) if BILLS_PAYABLE else 0
            _save_credit_card(data)
        return data
    # 首次加载：从 config.py 的 BILLS_PAYABLE 初始化
    from config import BILLS_PAYABLE
    initial = sum(BILLS_PAYABLE.values()) if BILLS_PAYABLE else 0
    data = {"balance": initial, "history": []}
    _save_credit_card(data)
    return data


def _save_credit_card(data):
    with _file_locks["credit_card"]:
        _atomic_write(CREDIT_CARD_FILE, data)


def add_credit_card_expense(amount, note="", date=None):
    from datetime import datetime
    amt = float(amount)
    if amt <= 0:
        return {"error": "消费金额必须大于0"}
    cc = _load_credit_card()
    cc["balance"] = round(cc["balance"] + amt, 2)
    cc["history"].append({
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "amount": round(float(amount), 2),
        "type": "消费",
        "note": note,
        "balance": cc["balance"],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
    })
    _save_credit_card(cc)
    return cc


def pay_credit_card(amount, account="招行储蓄卡"):
    from datetime import datetime
    amt = float(amount)
    if amt <= 0:
        return {"error": "还款金额必须大于0"}
    if amt < 0:
        return {"error": "还款金额不能为负数"}

    cc = _load_credit_card()
    original_amount = amt
    pay_amount = min(amt, cc["balance"])
    overpaid = amt > cc["balance"]

    cc["balance"] = round(cc["balance"] - pay_amount, 2)
    cc["history"].append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "amount": round(pay_amount, 2),
        "type": "还款",
        "note": f"还款（{account}）",
        "balance": cc["balance"],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
    })
    _save_credit_card(cc)

    balance_ok = True
    if account:
        if not _update_account_balance(account, -pay_amount):
            balance_ok = False

    result = cc.copy()
    result["balance_ok"] = balance_ok
    result["pay_amount"] = round(pay_amount, 2)
    result["overpaid"] = overpaid
    if overpaid:
        result["warning"] = f"还款金额 ¥{original_amount:,.0f} 超过待还 ¥{cc['balance'] + pay_amount:,.0f}，实际还款 ¥{pay_amount:,.0f}"
    if not balance_ok and account:
        result["warning"] = result.get("warning", "") + f" 账户「{account}」未在资产配置中找到"
    return result


def get_credit_card_status():
    cc = _load_credit_card()
    return {
        "balance": cc["balance"],
        "history": cc["history"][-10:],
    }


def _reverse_credit_card_expense(amount):
    """删除信用卡消费：移除原始记录（而非追加冲正）"""
    cc = _load_credit_card()
    cc["balance"] = round(cc["balance"] - float(amount), 2)

    # 找到并移除匹配的原始消费记录
    amt = round(float(amount), 2)
    new_history = []
    removed = False
    for h in cc["history"]:
        if not removed and h["type"] == "消费" and round(float(h["amount"]), 2) == amt:
            removed = True
            continue
        new_history.append(h)
    cc["history"] = new_history

    _save_credit_card(cc)


def _update_account_balance(account, change):
    from utils.assets import _load_asset_config, _save_asset_config
    asset_config = _load_asset_config()
    for layer_name, items in asset_config.items():
        if account in items:
            items[account] = round(items[account] + change, 2)
            _save_asset_config(asset_config)
            return True
    return False


def add_transaction(amount, category, note="", tx_type="支出", date=None, account=""):
    from datetime import datetime

    try:
        amt = round(float(amount), 2)
    except (ValueError, TypeError):
        return {"error": "金额必须是有效数字"}
    if amt <= 0:
        return {"error": "金额必须大于0"}
    if tx_type not in ("支出", "收入"):
        return {"error": "类型必须是支出或收入"}

    now = datetime.now()
    date_str = date or now.strftime("%Y-%m-%d")
    # 确保包含时间部分，与 CSV 数据格式一致（pandas 混合解析需要）
    if len(date_str) == 10:
        date_str = date_str + " " + now.strftime("%H:%M:%S")
    created_at = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    month_str = date_str[:7]

    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO transactions ("clean_date", "cny_amount", "category_l1", "corrected_type", '
        '"账户", "备注", "valid_for_stats", "is_outlier", "month", "source", "created_at") '
        "VALUES (?, ?, ?, ?, ?, ?, 'True', 'False', ?, 'manual', ?)",
        (date_str, amt, category, tx_type, account, note, month_str, created_at)
    )
    tx_id = cur.lastrowid
    conn.commit()
    conn.close()

    _invalidate_unified_cache()

    is_credit_card = account == "信用卡"
    balance_ok = True
    if tx_type == "支出" and is_credit_card:
        add_credit_card_expense(amt, note, date_str)
    elif tx_type == "支出" and account:
        if not _update_account_balance(account, -amt):
            balance_ok = False
    elif tx_type == "收入" and account:
        if not _update_account_balance(account, amt):
            balance_ok = False

    tx = {
        "id": tx_id,
        "date": date_str,
        "amount": str(amt),
        "category": category,
        "type": tx_type,
        "account": account,
        "note": note,
        "created_at": created_at,
    }

    result = _analyze_after_transaction(tx)

    # AI 即时分析：大额检测、预算预警
    try:
        from utils.ai_engine import on_transaction_added
        ai_insights = on_transaction_added(tx)
        if ai_insights:
            result["ai_insights"] = ai_insights
    except Exception:
        pass

    if not balance_ok and account:
        result["suggestions"].insert(0, f"⚠️ 账户「{account}」未在资产配置中找到，余额未更新")
    return result


def delete_transaction(tx_id):
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute("""SELECT "cny_amount", "corrected_type", "账户" FROM transactions WHERE id = ? AND source = 'manual'""", (tx_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "记录不存在"}

    amount, tx_type, account = row
    balance_ok = True

    is_credit_card = account == "信用卡"
    if tx_type == "支出" and is_credit_card:
        _reverse_credit_card_expense(float(amount))
    elif tx_type == "支出" and account:
        if not _update_account_balance(account, float(amount)):
            balance_ok = False
    elif tx_type == "收入" and account:
        if not _update_account_balance(account, -float(amount)):
            balance_ok = False

    cur.execute("DELETE FROM transactions WHERE id = ? AND source = 'manual'", (tx_id,))
    conn.commit()
    conn.close()

    _invalidate_unified_cache()

    result = {"success": True}
    if not balance_ok and account:
        result["warning"] = f"账户「{account}」未在资产配置中找到，余额未恢复"
    return result


def _analyze_after_transaction(tx):
    from datetime import datetime
    now = datetime.now()
    month_str = tx["date"][:7]

    transactions = _load_transactions()
    month_txs = [t for t in transactions if t["date"][:7] == month_str]

    expense_totals = {}
    income_totals = {}
    total_expense = 0
    total_income = 0

    for t in month_txs:
        cat = t["category"]
        amt = float(t["amount"])
        if t["type"] == "收入":
            income_totals[cat] = income_totals.get(cat, 0) + amt
            total_income += amt
        else:
            expense_totals[cat] = expense_totals.get(cat, 0) + amt
            total_expense += amt

    from utils.budget import _load_budget_config
    budget_config = _load_budget_config()
    budget_status = []
    for cat, budget in budget_config.items():
        if budget <= 0:
            continue
        spent = expense_totals.get(cat, 0)
        ratio = round(spent / budget * 100, 1) if budget else 0
        budget_status.append({
            "category": cat,
            "budget": budget,
            "spent": round(spent, 2),
            "remaining": round(max(budget - spent, 0), 2),
            "ratio": ratio,
            "status": "超支" if ratio > 100 else ("偏高" if ratio > 80 else "正常"),
        })

    total_budget = sum(b for b in budget_config.values() if b > 0)
    total_spent = total_expense
    total_remaining = max(total_budget - total_spent, 0)

    suggestions = []
    if total_income > 0:
        suggestions.append(f"💰 本月已记录收入 ¥{total_income:,.0f}")

    over_budget = [b for b in budget_status if b["ratio"] > 100]
    warn_budget = [b for b in budget_status if 80 <= b["ratio"] <= 100]

    if over_budget:
        for b in over_budget:
            over_amount = b["spent"] - b["budget"]
            suggestions.append(f"⚠️ {b['category']}已超支{b['ratio']:.0f}%（¥{b['spent']:,.0f}/¥{b['budget']:,.0f}），超支¥{over_amount:,.0f}")
            if b["category"] == "餐饮":
                suggestions.append(f"   💡 建议：减少外卖频率，每天自己做饭可省约¥{over_amount/30:,.0f}/天")
            elif b["category"] == "购物":
                suggestions.append(f"   💡 建议：设置48小时冷静期，非必需品延后购买")
            elif b["category"] == "娱乐":
                suggestions.append(f"   💡 建议：寻找免费替代活动（公园散步、免费展览等）")
            elif b["category"] == "交通":
                suggestions.append(f"   💡 建议：短途出行选择地铁/公交代替打车")
            elif b["category"] == "社交":
                suggestions.append(f"   💡 建议：下次聚餐选择AA制或人均更低的场所")
    if warn_budget:
        for b in warn_budget:
            suggestions.append(f"⚡ {b['category']}接近上限{b['ratio']:.0f}%，剩余¥{b['remaining']:,.0f}，本月剩余天数需控制在¥{b['remaining']/max(1,30-now.day):,.0f}/天")

    balance = total_income - total_expense
    if total_income > 0:
        if balance >= 0:
            savings_rate = round(balance / total_income * 100, 1)
            suggestions.append(f"✅ 本月结余 ¥{balance:,.0f}（储蓄率 {savings_rate}%）")
        else:
            suggestions.append(f"🔴 本月超支 ¥{abs(balance):,.0f}（收入 ¥{total_income:,.0f} - 支出 ¥{total_expense:,.0f}）")
            if total_income > 0:
                target_expense = total_income * 0.8
                reduce_needed = total_expense - target_expense
                if reduce_needed > 0:
                    suggestions.append(f"   💡 建议：将月支出控制在¥{target_expense:,.0f}以内（收入的80%），需减少¥{reduce_needed:,.0f}")

    try:
        from utils.data_core import load_unified
        import pandas as pd
        df = load_unified()
        valid = df[df["valid_for_stats"] == "True"]
        expense = valid[valid["corrected_type"] == "支出"]
        current_month = tx["date"][:7]
        current_expense = expense[expense["month"] == current_month]
        prev_month_str = f"{now.year}-{now.month-1:02d}" if now.month > 1 else f"{now.year-1}-12"
        prev_expense = expense[expense["month"] == prev_month_str]

        if not current_expense.empty and not prev_expense.empty:
            cur_cats = current_expense.groupby("category_l1")["cny_amount"].sum()
            prev_cats = prev_expense.groupby("category_l1")["cny_amount"].sum()
            for cat in cur_cats.index:
                if cat in prev_cats.index and prev_cats[cat] > 0:
                    growth = (cur_cats[cat] - prev_cats[cat]) / prev_cats[cat] * 100
                    if growth > 30:
                        suggestions.append(f"📈 {cat}支出比上月增长{growth:.0f}%，建议关注")
    except Exception:
        pass

    prev_month_str2 = f"{now.year}-{now.month-1:02d}" if now.month > 1 else f"{now.year-1}-12"
    prev_txs = [t for t in transactions if t["date"][:7] == prev_month_str2 and t["type"] != "收入"]
    prev_total = sum(float(t["amount"]) for t in prev_txs)
    if prev_total > 0:
        change = round((total_expense - prev_total) / prev_total * 100, 1)
        if change > 20:
            suggestions.append(f"📈 本月支出比上月同期增长{change}%，注意控制")
        elif change < -20:
            suggestions.append(f"📉 本月支出比上月同期减少{abs(change)}%，继续保持")

    recent_expense = [t for t in month_txs if t["type"] != "收入"]
    recent_5 = [{"date": t["date"], "amount": float(t["amount"]), "category": t["category"], "note": t["note"], "type": t["type"]} for t in recent_expense[-5:]]

    return {
        "recorded": tx,
        "month_summary": {
            "month": month_str,
            "total_expense": round(total_expense, 2),
            "total_income": round(total_income, 2),
            "balance": round(balance, 2),
            "count": len(month_txs),
            "expense_by_category": {k: round(v, 2) for k, v in sorted(expense_totals.items(), key=lambda x: -x[1])},
            "income_by_category": {k: round(v, 2) for k, v in sorted(income_totals.items(), key=lambda x: -x[1])},
        },
        "budget": {
            "total_budget": total_budget,
            "total_spent": round(total_spent, 2),
            "total_remaining": round(total_remaining, 2),
            "total_ratio": round(total_spent / total_budget * 100, 1) if total_budget else 0,
            "items": sorted(budget_status, key=lambda x: -x["ratio"]),
        },
        "suggestions": suggestions,
        "recent_5": recent_5,
        "overview": _lightweight_overview(),
    }


def _lightweight_overview():
    from utils.assets import _load_asset_config
    asset_config = _load_asset_config()
    total = sum(sum(items.values()) for items in asset_config.values())
    cc = _load_credit_card()
    return {
        "net_worth": round(total - cc["balance"], 2),
        "total_assets": round(total, 2),
    }


def get_quick_stats():
    from datetime import datetime
    month_str = datetime.now().strftime("%Y-%m")

    transactions = _load_transactions()
    month_txs = [t for t in transactions if t["date"][:7] == month_str]

    total = sum(float(t["amount"]) for t in month_txs)
    by_category = {}
    for t in month_txs:
        cat = t["category"]
        by_category[cat] = by_category.get(cat, 0) + float(t["amount"])

    return {
        "month": month_str,
        "total": round(total, 2),
        "count": len(month_txs),
        "by_category": {k: round(v, 2) for k, v in sorted(by_category.items(), key=lambda x: -x[1])},
    }
