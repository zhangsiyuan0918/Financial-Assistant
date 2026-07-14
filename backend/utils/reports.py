"""报告与分析：月度、年度、财务健康、同比环比"""
import pandas as pd

from utils.data_core import load_v4, load_unified
from utils.assets import get_overview, get_asset_history, get_portfolio
from utils.budget import get_budget_status


def _prev_month(month_str):
    parts = month_str.split("-")
    y, m = int(parts[0]), int(parts[1])
    if m == 1:
        return f"{y-1}-12"
    return f"{y}-{m-1:02d}"


def get_monthly_report(month=None):
    from datetime import datetime
    target_month = month or datetime.now().strftime("%Y-%m")

    df = load_unified()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]
    income = valid[valid["corrected_type"] == "收入"]
    norm_exp = expense[expense["is_outlier"] != "True"]

    month_exp = norm_exp[norm_exp["month"] == target_month]
    month_inc = income[income["month"] == target_month]

    exp_total = month_exp["cny_amount"].sum()
    inc_total = month_inc["cny_amount"].sum()
    balance = inc_total - exp_total

    days_in_month = len(month_exp["clean_date"].dt.day.unique()) if len(month_exp) else 1
    daily_avg = round(exp_total / days_in_month, 2) if days_in_month else 0

    savings_rate = round(balance / inc_total * 100, 1) if inc_total else 0

    all_cats = month_exp.groupby("category_l1")["cny_amount"].sum().sort_values(ascending=False)
    top_cats = all_cats.head(5)
    all_cats_list = [{"category": k, "amount": round(v, 2), "ratio": round(v / exp_total * 100, 1) if exp_total else 0}
                     for k, v in all_cats.items()]

    inc_cats = month_inc.groupby("category_l1")["cny_amount"].sum().sort_values(ascending=False)
    inc_breakdown = [{"category": k, "amount": round(v, 2), "ratio": round(v / inc_total * 100, 1) if inc_total else 0}
                     for k, v in inc_cats.items()]

    prev_month_str = _prev_month(target_month)
    prev = norm_exp[norm_exp["month"] == prev_month_str]
    prev_total = prev["cny_amount"].sum()
    mom_change = round((exp_total - prev_total) / prev_total * 100, 1) if prev_total else None

    prev_cats = prev.groupby("category_l1")["cny_amount"].sum()
    mom_cats = []
    for k, v in all_cats.items():
        pv = prev_cats.get(k, 0)
        diff = round(v - pv, 2)
        mom_cats.append({
            "category": k, "current": round(v, 2), "previous": round(pv, 2),
            "diff": diff, "pct": round(diff / pv * 100, 1) if pv else None,
        })

    parts = target_month.split("-")
    yoy_m = f"{int(parts[0])-1}-{parts[1]}"
    yoy = norm_exp[norm_exp["month"] == yoy_m]
    yoy_total = yoy["cny_amount"].sum()
    yoy_change = round((exp_total - yoy_total) / yoy_total * 100, 1) if yoy_total else None

    yoy_cats = yoy.groupby("category_l1")["cny_amount"].sum()
    yoy_cat_items = []
    for k, v in all_cats.items():
        yv = yoy_cats.get(k, 0)
        diff = round(v - yv, 2)
        yoy_cat_items.append({
            "category": k, "current": round(v, 2), "previous": round(yv, 2),
            "diff": diff, "pct": round(diff / yv * 100, 1) if yv else None,
        })

    asset_history = get_asset_history()
    prev_net_worth = None
    cur_net_worth = None
    asset_change_pct = None
    for h in asset_history:
        if h["month"] == target_month:
            cur_net_worth = h["total"]
        elif h["month"] == _prev_month(target_month):
            prev_net_worth = h["total"]
    if cur_net_worth and prev_net_worth and prev_net_worth > 0:
        asset_change_pct = round((cur_net_worth - prev_net_worth) / prev_net_worth * 100, 1)

    cash_before = None
    cash_now_val = None
    for h in asset_history:
        if h["month"] == target_month:
            cash_now_val = h.get("cash_and_liquid", 0)
        elif h["month"] == _prev_month(target_month):
            cash_before = h.get("cash_and_liquid", 0)
    cash_change = round(cash_now_val - cash_before, 2) if cash_now_val is not None and cash_before is not None else None

    budget_status = get_budget_status(target_month)

    return {
        "month": target_month,
        "income": round(inc_total, 2),
        "expense": round(exp_total, 2),
        "balance": round(balance, 2),
        "savings_rate": savings_rate,
        "daily_avg_expense": daily_avg,
        "transaction_count": len(month_exp),
        "mom_change": mom_change,
        "mom_month": prev_month_str,
        "yoy_change": yoy_change,
        "yoy_month": yoy_m,
        "top_categories": [{"category": k, "amount": round(v, 2)} for k, v in top_cats.items()],
        "all_categories": all_cats_list,
        "income_breakdown": inc_breakdown,
        "mom_categories": mom_cats,
        "yoy_categories": yoy_cat_items,
        "budget": {
            "total_budget": budget_status["total_budget"],
            "total_actual": budget_status["total_actual"],
            "total_ratio": budget_status["total_ratio"],
            "items": budget_status["items"],
        },
        "asset": {
            "month_start": prev_net_worth,
            "month_end": cur_net_worth,
            "change_pct": asset_change_pct,
            "cash_change": cash_change,
        },
    }


def get_annual_report(year=None):
    from datetime import datetime
    if year is None:
        year = str(datetime.now().year)

    months = [f"{year}-{m:02d}" for m in range(1, 13)]
    monthly_data = []
    for m in months:
        try:
            r = get_monthly_report(m)
            monthly_data.append(r)
        except Exception:
            monthly_data.append({"month": m, "income": 0, "expense": 0, "balance": 0, "savings_rate": 0})

    total_income = sum(d.get("income", 0) for d in monthly_data)
    total_expense = sum(d.get("expense", 0) for d in monthly_data)
    total_balance = total_income - total_expense
    avg_savings = sum(d.get("savings_rate", 0) for d in monthly_data if d.get("savings_rate")) / max(1, len([d for d in monthly_data if d.get("savings_rate")]))

    valid_months = [d for d in monthly_data if d.get("expense", 0) > 0]
    if valid_months:
        best_month = min(valid_months, key=lambda d: d["expense"])
        worst_month = max(valid_months, key=lambda d: d["expense"])
    else:
        best_month = worst_month = {"month": "-", "expense": 0}

    return {
        "year": year,
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "total_balance": round(total_balance, 2),
        "avg_savings_rate": round(avg_savings, 1),
        "best_month": {"month": best_month.get("month", ""), "expense": best_month.get("expense", 0)},
        "worst_month": {"month": worst_month.get("month", ""), "expense": worst_month.get("expense", 0)},
        "monthly_detail": monthly_data,
    }


def get_financial_health():
    ov = get_overview()
    score_items = []

    # 1. 流动性 (30%)
    cov = ov["liquidity_coverage"]
    if cov >= 6:
        liq = 100
    elif cov >= 3:
        liq = 70 + (cov - 3) / 3 * 30
    elif cov >= 1:
        liq = 30 + (cov - 1) / 2 * 40
    else:
        liq = cov * 30
    liq = max(0, min(100, liq))
    score_items.append({"name": "流动性", "score": round(liq, 1), "weight": 30, "detail": f"覆盖率 {cov} 个月"})

    # 2. 储蓄率 (25%)
    df = load_unified()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]
    income = valid[valid["corrected_type"] == "收入"]
    recent_months = sorted([m for m in valid["month"].unique() if isinstance(m, str) and m])[-6:]
    if recent_months:
        inc = income[income["month"].isin(recent_months)]["cny_amount"].sum()
        exp = expense[expense["month"].isin(recent_months)]["cny_amount"].sum()
        savings_rate = (inc - exp) / inc * 100 if inc > 0 else 0
    else:
        savings_rate = 0
    if savings_rate >= 40:
        sav = 100
    elif savings_rate >= 20:
        sav = 60 + (savings_rate - 20) / 20 * 40
    elif savings_rate >= 0:
        sav = 20 + savings_rate / 20 * 40
    else:
        sav = max(0, 20 + savings_rate / 20 * 20)
    sav = max(0, min(100, sav))
    score_items.append({"name": "储蓄率", "score": round(sav, 1), "weight": 25, "detail": f"近6月储蓄率 {savings_rate:.1f}%"})

    # 3. 投资收益率 (20%)
    port = get_portfolio()
    pnl_stats = port.get("pnl_stats", {})
    inv_rate = pnl_stats.get("total_pnl_pct", 0)
    if inv_rate >= 15:
        inv_sc = 100
    elif inv_rate >= 5:
        inv_sc = 60 + (inv_rate - 5) / 10 * 40
    elif inv_rate >= 0:
        inv_sc = 40 + inv_rate / 5 * 20
    elif inv_rate >= -10:
        inv_sc = 20 + (inv_rate + 10) / 10 * 20
    else:
        inv_sc = 0
    inv_sc = max(0, min(100, inv_sc))
    score_items.append({"name": "投资收益率", "score": round(inv_sc, 1), "weight": 20, "detail": f"累计盈亏 {inv_rate:.1f}%"})

    # 4. 负债率 (15%)
    debt_ratio = ov["bills_payable"] / ov["total_assets"] * 100 if ov["total_assets"] > 0 else 0
    if debt_ratio <= 0:
        debt_sc = 100
    elif debt_ratio <= 10:
        debt_sc = 80 + (10 - debt_ratio) / 10 * 20
    elif debt_ratio <= 30:
        debt_sc = 50 + (30 - debt_ratio) / 20 * 30
    elif debt_ratio <= 50:
        debt_sc = 20 + (50 - debt_ratio) / 20 * 30
    else:
        debt_sc = 0
    debt_sc = max(0, min(100, debt_sc))
    score_items.append({"name": "负债率", "score": round(debt_sc, 1), "weight": 15, "detail": f"负债率 {debt_ratio:.1f}%"})

    # 5. 分散度 (10%)
    layers = ov.get("layers", [])
    active = sum(1 for l in layers if l.get("ratio", 0) >= 5)
    if active >= 4:
        div = 100
    elif active == 3:
        div = 75
    elif active == 2:
        div = 50
    elif active == 1:
        div = 25
    else:
        div = 0
    score_items.append({"name": "资产分散度", "score": round(div, 1), "weight": 10, "detail": f"{active}/4 层配置 ≥5%"})

    total_score = round(sum(s["score"] * s["weight"] / 100 for s in score_items), 1)

    if total_score >= 85:
        level = "优秀"
        level_color = "#67c23a"
    elif total_score >= 70:
        level = "良好"
        level_color = "#409eff"
    elif total_score >= 50:
        level = "一般"
        level_color = "#e6a23c"
    else:
        level = "需关注"
        level_color = "#f56c6c"

    return {
        "total_score": total_score,
        "level": level,
        "level_color": level_color,
        "items": score_items,
    }


def get_comparison(year, month):
    df = load_unified()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]

    cur_month = f"{year}-{int(month):02d}"
    parts = cur_month.split("-")
    py, pm = int(parts[0]), int(parts[1])
    if pm == 1:
        prev_month_str = f"{py-1}-12"
    else:
        prev_month_str = f"{py}-{pm-1:02d}"
    yoy_month = f"{py-1}-{pm:02d}"

    def _cat_data(m):
        d = expense[expense["month"] == m]
        return d.groupby("category_l1")["cny_amount"].sum().to_dict()

    cur_data = _cat_data(cur_month)
    mom_data = _cat_data(prev_month_str)
    yoy_data = _cat_data(yoy_month)

    all_cats = sorted(set(list(cur_data.keys()) + list(mom_data.keys()) + list(yoy_data.keys())))
    mom_items = []
    yoy_items = []
    for cat in all_cats:
        cur_v = cur_data.get(cat, 0)
        prev_v = mom_data.get(cat, 0)
        mom_diff = round(cur_v - prev_v, 2)
        mom_pct = round((cur_v - prev_v) / prev_v * 100, 1) if prev_v else None
        mom_items.append({"category": cat, "current": round(cur_v, 2), "previous": round(prev_v, 2), "diff": mom_diff, "pct": mom_pct})
        yoy_v = yoy_data.get(cat, 0)
        yoy_diff = round(cur_v - yoy_v, 2)
        yoy_pct = round((cur_v - yoy_v) / yoy_v * 100, 1) if yoy_v else None
        yoy_items.append({"category": cat, "current": round(cur_v, 2), "previous": round(yoy_v, 2), "diff": yoy_diff, "pct": yoy_pct})

    cur_total = sum(cur_data.values())
    mom_total = sum(mom_data.values())
    yoy_total = sum(yoy_data.values())

    return {
        "month": cur_month,
        "mom_month": prev_month_str,
        "yoy_month": yoy_month,
        "mom": {
            "items": sorted(mom_items, key=lambda x: abs(x["pct"] or 0), reverse=True),
            "total_current": round(cur_total, 2),
            "total_previous": round(mom_total, 2),
            "total_diff": round(cur_total - mom_total, 2),
            "total_pct": round((cur_total - mom_total) / mom_total * 100, 1) if mom_total else None,
        },
        "yoy": {
            "items": sorted(yoy_items, key=lambda x: abs(x["pct"] or 0), reverse=True),
            "total_current": round(cur_total, 2),
            "total_previous": round(yoy_total, 2),
            "total_diff": round(cur_total - yoy_total, 2),
            "total_pct": round((cur_total - yoy_total) / yoy_total * 100, 1) if yoy_total else None,
        },
    }
