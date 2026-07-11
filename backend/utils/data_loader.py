import csv
import json
import os
import pandas as pd
from collections import defaultdict
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import V4_FILE, DB_PATH, ASSET_LAYERS, CASH_LIQUID, INVESTMENT, RESTRICTED, RECEIVABLES, DEBT, BILLS_PAYABLE, ASSET_HISTORY_FILE, ASSET_CONFIG_FILE, BUDGET_CONFIG_FILE, MONTHLY_SALARY, QUARTERLY_BONUS, PORTFOLIO, MONTHLY_BUDGET, ALERTS_FILE, GOALS_FILE, FORECAST_FILE
from utils import db
db.set_db_path(DB_PATH)


def _load_asset_config():
    """从 JSON 加载资产配置，不存在则使用 config.py 默认值"""
    if os.path.exists(ASSET_CONFIG_FILE):
        with open(ASSET_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {k: dict(v) for k, v in ASSET_LAYERS.items()}


def _save_asset_config(data):
    with open(ASSET_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _layers_from_config(config):
    """将 JSON 配置拆为各层字典"""
    return (
        config.get("现金/活期", {}),
        config.get("投资资产", {}),
        config.get("受限资产", {}),
        config.get("应收", {}),
    )


def _deduplicate(df):
    """Remove duplicate rows by date + amount + project, keeping first occurrence."""
    before = len(df)
    dedup_cols = ["clean_date", "cny_amount", "clean_project"]
    # Only deduplicate if all columns exist
    existing = [c for c in dedup_cols if c in df.columns]
    if existing:
        df = df.drop_duplicates(subset=existing, keep="first")
    removed = before - len(df)
    return df, removed


def load_v4(force_csv=False):
    if not force_csv and db.is_migrated():
        conn = db.get_conn()
        df = pd.read_sql("SELECT * FROM transactions", conn)
        conn.close()
        df["cny_amount"] = pd.to_numeric(df["cny_amount"], errors="coerce")
        df["clean_date"] = pd.to_datetime(df["clean_date"], errors="coerce")
        df["month"] = df["clean_date"].dt.to_period("M").astype(str)
        df, removed = _deduplicate(df)
        if removed > 0:
            print(f"[data_loader] Deduplicated: removed {removed} duplicate rows")
        return df
    rows = []
    with open(V4_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    df = pd.DataFrame(rows)
    df["cny_amount"] = pd.to_numeric(df["cny_amount"], errors="coerce")
    df["clean_date"] = pd.to_datetime(df["clean_date"], errors="coerce")
    df["month"] = df["clean_date"].dt.to_period("M").astype(str)
    df, removed = _deduplicate(df)
    if removed > 0:
        print(f"[data_loader] Deduplicated: removed {removed} duplicate rows")
    return df


def flatten_assets(config=None):
    """将分层资产展平为 [{name, amount, layer}, ...]"""
    if config is None:
        config = _load_asset_config()
    result = []
    for layer, items in config.items():
        for name, amount in items.items():
            result.append({"name": name, "amount": amount, "layer": layer})
    return result


def get_overview():
    df = load_v4()
    monthly_income = MONTHLY_SALARY + QUARTERLY_BONUS / 3

    # 从运行时配置加载资产
    asset_config = _load_asset_config()
    cash_items, invest_items, restricted_items, receivables_items = _layers_from_config(asset_config)

    cash_total = sum(cash_items.values())
    invest_total = sum(invest_items.values())
    restricted_total = sum(restricted_items.values())
    receivables_total = sum(receivables_items.values())
    total_assets = cash_total + invest_total + restricted_total + receivables_total

    debt_total = sum(DEBT.values())
    bills_total = sum(BILLS_PAYABLE.values())
    net_worth = total_assets - bills_total

    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]
    income = valid[valid["corrected_type"] == "收入"]

    recent = expense[expense["month"] >= "2025-09"]
    avg_monthly_exp = recent.groupby("month")["cny_amount"].sum().mean()
    if pd.notna(avg_monthly_exp):
        avg_monthly_exp = round(avg_monthly_exp, 2)
    else:
        avg_monthly_exp = 0

    # 流动性覆盖率 = 可用资金 / 月均支出（能撑几个月）
    liquidity_coverage = round(cash_total / avg_monthly_exp, 1) if avg_monthly_exp > 0 else 0
    # 投资占比
    investment_ratio = round(invest_total / total_assets * 100, 1) if total_assets > 0 else 0

    # 分层资产列表
    assets_flat = flatten_assets(asset_config)
    assets_detail = [{"name": a["name"], "amount": a["amount"],
                      "layer": a["layer"],
                      "ratio": round(a["amount"] / total_assets * 100, 1)} for a in assets_flat]

    # 分层汇总
    layer_summary = [
        {"layer": "现金/活期", "total": round(cash_total, 2),
         "ratio": round(cash_total / total_assets * 100, 1) if total_assets else 0},
        {"layer": "投资资产", "total": round(invest_total, 2),
         "ratio": round(invest_total / total_assets * 100, 1) if total_assets else 0},
        {"layer": "受限资产", "total": round(restricted_total, 2),
         "ratio": round(restricted_total / total_assets * 100, 1) if total_assets else 0},
        {"layer": "应收", "total": round(receivables_total, 2),
         "ratio": round(receivables_total / total_assets * 100, 1) if total_assets else 0},
    ]

    return {
        "net_worth": round(net_worth, 2),
        "total_assets": round(total_assets, 2),
        "monthly_income": round(monthly_income, 2),
        "monthly_balance": round(monthly_income - avg_monthly_exp, 2),
        "monthly_expense": round(avg_monthly_exp, 2),
        "avg_monthly_expense": avg_monthly_exp,
        "cash_and_liquid": round(cash_total, 2),
        "investment": round(invest_total, 2),
        "restricted": round(restricted_total, 2),
        "receivables": round(receivables_total, 2),
        "debt": round(debt_total, 2),
        "bills_payable": round(bills_total, 2),
        "liquidity_coverage": liquidity_coverage,
        "investment_ratio": investment_ratio,
        "assets": assets_detail,
        "layers": layer_summary,
        "total_records": len(df),
        "date_from": df["clean_date"].min().strftime("%Y-%m-%d") if len(df) else "",
        "date_to": df["clean_date"].max().strftime("%Y-%m-%d") if len(df) else "",
    }


def get_spending(year=None):
    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]
    if year and year != "all":
        expense = expense[expense["clean_date"].dt.year == int(year)]
    cat = expense.groupby("category_l1").agg(amount=("cny_amount", "sum"), count=("cny_amount", "count")).sort_values("amount", ascending=False).reset_index()
    total = cat["amount"].sum()
    result = []
    for _, r in cat.iterrows():
        result.append({"category": r["category_l1"], "amount": round(r["amount"], 2), "count": int(r["count"]), "ratio": round(r["amount"] / total * 100, 1) if total else 0})
    monthly = expense.pivot_table(index="month", columns="category_l1", values="cny_amount", aggfunc="sum").fillna(0).reset_index()
    monthly.index = monthly["month"]
    monthly_trend = {str(k): {str(c): round(v, 2) for c, v in row.items() if c != "month"} for k, row in monthly.iterrows()}
    years = sorted(expense["clean_date"].dt.year.dropna().unique().astype(int).tolist())
    return {"categories": result, "total": round(total, 2), "monthly_trend": monthly_trend, "years": years}


def get_monthly_trend():
    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]
    income = valid[valid["corrected_type"] == "收入"]
    monthly_exp = expense.groupby("month")["cny_amount"].sum()
    monthly_inc = income.groupby("month")["cny_amount"].sum()
    combined = pd.DataFrame({"expense": monthly_exp, "income": monthly_inc}).fillna(0)
    combined["balance"] = combined["income"] - combined["expense"]
    result = []
    for idx, row in combined.iterrows():
        result.append({"month": str(idx), "expense": round(row["expense"], 2), "income": round(row["income"], 2), "balance": round(row["balance"], 2)})
    return result


def get_category_detail(category, year=None):
    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]
    expense = expense[expense["category_l1"] == category]
    if year and year != "all":
        expense = expense[expense["clean_date"].dt.year == int(year)]
    sub = expense.groupby("category_l2").agg(amount=("cny_amount", "sum"), count=("cny_amount", "count")).sort_values("amount", ascending=False).reset_index()
    result = []
    total = sub["amount"].sum()
    for _, r in sub.iterrows():
        result.append({"sub_category": r["category_l2"], "amount": round(r["amount"], 2), "count": int(r["count"]), "ratio": round(r["amount"] / total * 100, 1) if total else 0})
    monthly = expense.groupby("month")["cny_amount"].sum()
    trend = [{"month": str(k), "amount": round(v, 2)} for k, v in monthly.items()]
    return {"sub_categories": result, "total": round(total, 2), "trend": trend}


def get_income_analysis():
    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    income = valid[valid["corrected_type"] == "收入"]
    cat = income.groupby("category_l1").agg(amount=("cny_amount", "sum"), count=("cny_amount", "count")).sort_values("amount", ascending=False).reset_index()
    total = cat["amount"].sum()
    result = []
    for _, r in cat.iterrows():
        result.append({"category": r["category_l1"], "amount": round(r["amount"], 2), "count": int(r["count"]), "ratio": round(r["amount"] / total * 100, 1) if total else 0})
    monthly = income.groupby("month")["cny_amount"].sum()
    trend = [{"month": str(k), "amount": round(v, 2)} for k, v in monthly.items()]
    return {"categories": result, "total": round(total, 2), "trend": trend}


def get_asset_history():
    """读取月度资产快照，返回每月的分层资产数据"""
    if not os.path.exists(ASSET_HISTORY_FILE):
        return []
    rows = []
    with open(ASSET_HISTORY_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    df = pd.DataFrame(rows)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    result = []
    for month in sorted([m for m in df["month"].unique() if isinstance(m, str) and m]):
        month_data = df[df["month"] == month]
        layers = {}
        total = 0
        for _, r in month_data.iterrows():
            lay = r["layer"]
            amt = r["amount"]
            layers[lay] = layers.get(lay, 0) + amt
            total += amt
        result.append({
            "month": month,
            "total": round(total, 2),
            "cash_and_liquid": round(layers.get("现金/活期", 0), 2),
            "investment": round(layers.get("投资资产", 0), 2),
            "restricted": round(layers.get("受限资产", 0), 2),
            "receivables": round(layers.get("应收", 0), 2),
        })
    return result


def get_portfolio():
    """返回持仓盈亏明细（从运行时资产配置读取当前值）"""
    asset_config = _load_asset_config()
    invest_items = asset_config.get("投资资产", {})
    items = []
    total_cost = 0
    total_current = 0
    for p in PORTFOLIO:
        current = invest_items.get(p["account"], p["current"])
        cost = p["cost"]
        pnl = current - cost
        pnl_pct = round(pnl / cost * 100, 1) if cost else 0
        items.append({
            "account": p["account"],
            "type": p["type"],
            "cost": round(cost, 2),
            "current": round(current, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": pnl_pct,
        })
        total_cost += cost
        total_current += current
    return {
        "items": items,
        "total_cost": round(total_cost, 2),
        "total_current": round(total_current, 2),
        "total_pnl": round(total_current - total_cost, 2),
        "total_pnl_pct": round((total_current - total_cost) / total_cost * 100, 1) if total_cost else 0,
    }


def update_assets(new_assets):
    """更新资产配置并记录月度快照"""
    from datetime import datetime
    now = datetime.now()
    month_str = now.strftime("%Y-%m")

    # 校验格式：{ "现金/活期": { "招行储蓄卡": 123, ... }, ... }
    asset_config = _load_asset_config()
    for layer, items in new_assets.items():
        if layer in asset_config:
            for name, amount in items.items():
                if name in asset_config[layer]:
                    asset_config[layer][name] = float(amount)

    _save_asset_config(asset_config)

    # 追加月度快照（同月替换，跨月追加）
    import csv
    cash_items, invest_items, restricted_items, receivables_items = _layers_from_config(asset_config)
    new_rows = []
    for layer, items in [("现金/活期", cash_items), ("投资资产", invest_items),
                         ("受限资产", restricted_items), ("应收", receivables_items)]:
        for name, amount in items.items():
            new_rows.append({"month": month_str, "layer": layer, "item": name, "amount": amount})
    if os.path.exists(ASSET_HISTORY_FILE):
        with open(ASSET_HISTORY_FILE, "r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))
        old_rows = [r for r in reader if r["month"] != month_str]
        remaining = old_rows + new_rows
    else:
        remaining = new_rows
    with open(ASSET_HISTORY_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["month", "layer", "item", "amount"])
        writer.writeheader()
        writer.writerows(remaining)

    return _load_asset_config()


def backfill_asset_history():
    """
    回填历史资产快照：用收支数据估算过去每月净资产。
    从当前净资产出发，逐月倒推。
    已有实际数据的月份完全保留，只填充缺失月份。
    """
    import csv as csv_mod

    # 获取当前净资产
    overview = get_overview()
    current_net_worth = overview["net_worth"]

    # 获取月度收支数据
    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    monthly = valid.groupby(["month", "corrected_type"])["cny_amount"].sum().unstack(fill_value=0)

    # 按月排序
    months = sorted(monthly.index)

    # 从当前月往前倒推，计算每月净资产
    snapshots = []
    running_balance = current_net_worth

    for month in reversed(months):
        income = monthly.loc[month, "收入"] if "收入" in monthly.columns else 0
        expense = monthly.loc[month, "支出"] if "支出" in monthly.columns else 0
        net = income - expense

        snapshots.append({
            "month": month,
            "net_worth": round(running_balance, 2),
        })
        running_balance -= net

    snapshots.reverse()
    snapshot_map = {s["month"]: s["net_worth"] for s in snapshots}

    # 读取现有快照（保留原始行数据）
    existing_rows = []
    existing_months = set()
    if os.path.exists(ASSET_HISTORY_FILE):
        with open(ASSET_HISTORY_FILE, "r", encoding="utf-8-sig") as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                existing_rows.append(row)
                existing_months.add(row["month"])

    # 找出缺失月份
    missing_months = [s["month"] for s in snapshots if s["month"] not in existing_months]

    # 为缺失月份生成估算行
    new_rows = []
    for month in missing_months:
        nw = snapshot_map[month]
        # 按历史比例分配：现金20%，投资40%，受限30%，应收10%
        new_rows.append({"month": month, "layer": "现金/活期", "item": "estimation", "amount": round(nw * 0.20, 2)})
        new_rows.append({"month": month, "layer": "投资资产", "item": "estimation", "amount": round(nw * 0.40, 2)})
        new_rows.append({"month": month, "layer": "受限资产", "item": "estimation", "amount": round(nw * 0.30, 2)})
        new_rows.append({"month": month, "layer": "应收", "item": "estimation", "amount": round(nw * 0.10, 2)})

    # 合并：原有数据 + 新增估算数据
    all_rows = existing_rows + new_rows

    # 写入文件
    with open(ASSET_HISTORY_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv_mod.DictWriter(f, fieldnames=["month", "layer", "item", "amount"])
        writer.writeheader()
        writer.writerows(all_rows)

    return {"months": len(existing_months) + len(missing_months), "added": len(missing_months), "preserved": len(existing_months)}


def update_budget(new_budget):
    """更新预算设置"""
    _save_budget_config({k: float(v) for k, v in new_budget.items()})
    return _load_budget_config()


def get_seasonal_patterns():
    """分析季节性支出模式"""
    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]
    norm = expense[expense["is_outlier"] != "True"].copy()
    norm["month_num"] = norm["clean_date"].dt.month

    # 月度支出模式（跨年月均）
    monthly_avg = norm.groupby("month_num")["cny_amount"].mean()
    overall_avg = monthly_avg.mean()
    month_pattern = []
    for m in range(1, 13):
        diff = round((monthly_avg[m] - overall_avg) / overall_avg * 100, 1)
        month_pattern.append({
            "month": m,
            "avg": round(monthly_avg[m], 2),
            "diff_pct": diff,
            "label": "偏高" if diff > 15 else ("偏低" if diff < -15 else "正常"),
        })

    # 季节性类别
    cat_monthly = norm.groupby(["category_l1", "month_num"])["cny_amount"].sum().unstack(fill_value=0)
    seasonal = []
    for cat in cat_monthly.index:
        vals = cat_monthly.loc[cat]
        cv = round(vals.std() / vals.mean(), 2) if vals.mean() > 0 else 0
        if cv > 0.4:
            peak = int(vals.idxmax())
            seasonal.append({
                "category": cat,
                "cv": cv,
                "peak_month": peak,
                "avg": round(vals.mean(), 2),
                "peak_avg": round(vals[peak], 2),
            })
    seasonal.sort(key=lambda x: x["cv"], reverse=True)

    return {"month_pattern": month_pattern, "seasonal_categories": seasonal}


def _load_budget_config():
    if os.path.exists(BUDGET_CONFIG_FILE):
        with open(BUDGET_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return dict(MONTHLY_BUDGET)


def _save_budget_config(data):
    with open(BUDGET_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_budget_status(month=None):
    """当月预算执行情况"""
    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]
    norm = expense[expense["is_outlier"] != "True"]
    from datetime import datetime
    target_month = month or datetime.now().strftime("%Y-%m")
    month_data = norm[norm["month"] == target_month]
    actual = month_data.groupby("category_l1")["cny_amount"].sum()

    budget_config = _load_budget_config()
    total_budget = 0
    total_actual = 0
    items = []
    for cat, budget in budget_config.items():
        total_budget += budget
        spent = round(actual.get(cat, 0), 2)
        total_actual += spent
        ratio = round(spent / budget * 100, 1) if budget else 0
        status = "超支" if ratio > 100 else ("偏高" if ratio > 80 else ("正常" if ratio > 50 else "偏低"))
        items.append({
            "category": cat,
            "budget": budget,
            "actual": spent,
            "ratio": ratio,
            "status": status,
        })
    # 未做预算的类别
    uncategorized = {str(k): round(v, 2) for k, v in actual.items() if k not in budget_config}
    return {
        "month": target_month,
        "total_budget": total_budget,
        "total_actual": round(total_actual, 2),
        "total_ratio": round(total_actual / total_budget * 100, 1) if total_budget else 0,
        "items": items,
        "uncategorized": uncategorized,
    }


def get_monthly_report(month=None):
    """月度财务报告（增强版）"""
    from datetime import datetime
    target_month = month or datetime.now().strftime("%Y-%m")

    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]
    income = valid[valid["corrected_type"] == "收入"]
    norm_exp = expense[expense["is_outlier"] != "True"]

    month_exp = norm_exp[norm_exp["month"] == target_month]
    month_inc = income[income["month"] == target_month]

    exp_total = month_exp["cny_amount"].sum()
    inc_total = month_inc["cny_amount"].sum()
    balance = inc_total - exp_total

    # 日均支出
    days_in_month = len(month_exp["clean_date"].dt.day.unique()) if len(month_exp) else 1
    daily_avg = round(exp_total / days_in_month, 2) if days_in_month else 0

    # 储蓄率
    savings_rate = round(balance / inc_total * 100, 1) if inc_total else 0

    # TOP 分类
    all_cats = month_exp.groupby("category_l1")["cny_amount"].sum().sort_values(ascending=False)
    top_cats = all_cats.head(5)
    all_cats_list = [{"category": k, "amount": round(v, 2), "ratio": round(v / exp_total * 100, 1) if exp_total else 0}
                     for k, v in all_cats.items()]

    # 收入构成
    inc_cats = month_inc.groupby("category_l1")["cny_amount"].sum().sort_values(ascending=False)
    inc_breakdown = [{"category": k, "amount": round(v, 2), "ratio": round(v / inc_total * 100, 1) if inc_total else 0}
                     for k, v in inc_cats.items()]

    # 环比
    prev_month = _prev_month(target_month)
    prev = norm_exp[norm_exp["month"] == prev_month]
    prev_total = prev["cny_amount"].sum()
    mom_change = round((exp_total - prev_total) / prev_total * 100, 1) if prev_total else None

    # 环比分类级
    prev_cats = prev.groupby("category_l1")["cny_amount"].sum()
    mom_cats = []
    for k, v in all_cats.items():
        pv = prev_cats.get(k, 0)
        diff = round(v - pv, 2)
        mom_cats.append({
            "category": k, "current": round(v, 2), "previous": round(pv, 2),
            "diff": diff, "pct": round(diff / pv * 100, 1) if pv else None,
        })

    # 同比
    parts = target_month.split("-")
    yoy_m = f"{int(parts[0])-1}-{parts[1]}"
    yoy = norm_exp[norm_exp["month"] == yoy_m]
    yoy_total = yoy["cny_amount"].sum()
    yoy_change = round((exp_total - yoy_total) / yoy_total * 100, 1) if yoy_total else None

    # 同比分类级
    yoy_cats = yoy.groupby("category_l1")["cny_amount"].sum()
    yoy_cat_items = []
    for k, v in all_cats.items():
        yv = yoy_cats.get(k, 0)
        diff = round(v - yv, 2)
        yoy_cat_items.append({
            "category": k, "current": round(v, 2), "previous": round(yv, 2),
            "diff": diff, "pct": round(diff / yv * 100, 1) if yv else None,
        })

    # 资产变化
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

    # 流动资产变化
    cash_before = None
    cash_now_val = None
    for h in asset_history:
        if h["month"] == target_month:
            cash_now_val = h.get("cash_and_liquid", 0)
        elif h["month"] == _prev_month(target_month):
            cash_before = h.get("cash_and_liquid", 0)
    cash_change = round(cash_now_val - cash_before, 2) if cash_now_val is not None and cash_before is not None else None

    # 预算明细
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
        "mom_month": prev_month,
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


def get_financial_health():
    ov = get_overview()
    score_items = []
    total_score = 0

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
    df = load_v4()
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

    # 等级
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
    """返回指定月份的同比/环比数据"""
    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]

    cur_month = f"{year}-{int(month):02d}"
    # 环比上月
    parts = cur_month.split("-")
    py, pm = int(parts[0]), int(parts[1])
    if pm == 1:
        prev_month = f"{py-1}-12"
    else:
        prev_month = f"{py}-{pm-1:02d}"
    # 同比去年同月
    yoy_month = f"{py-1}-{pm:02d}"

    def _cat_data(m):
        d = expense[expense["month"] == m]
        return d.groupby("category_l1")["cny_amount"].sum().to_dict()

    cur_data = _cat_data(cur_month)
    mom_data = _cat_data(prev_month)
    yoy_data = _cat_data(yoy_month)

    all_cats = sorted(set(list(cur_data.keys()) + list(mom_data.keys()) + list(yoy_data.keys())))
    mom_items = []
    yoy_items = []
    for cat in all_cats:
        cur_v = cur_data.get(cat, 0)
        # MoM
        prev_v = mom_data.get(cat, 0)
        mom_diff = round(cur_v - prev_v, 2)
        mom_pct = round((cur_v - prev_v) / prev_v * 100, 1) if prev_v else None
        mom_items.append({"category": cat, "current": round(cur_v, 2), "previous": round(prev_v, 2), "diff": mom_diff, "pct": mom_pct})
        # YoY
        yoy_v = yoy_data.get(cat, 0)
        yoy_diff = round(cur_v - yoy_v, 2)
        yoy_pct = round((cur_v - yoy_v) / yoy_v * 100, 1) if yoy_v else None
        yoy_items.append({"category": cat, "current": round(cur_v, 2), "previous": round(yoy_v, 2), "diff": yoy_diff, "pct": yoy_pct})

    cur_total = sum(cur_data.values())
    mom_total = sum(mom_data.values())
    yoy_total = sum(yoy_data.values())

    return {
        "month": cur_month,
        "mom_month": prev_month,
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


def _prev_month(month_str):
    parts = month_str.split("-")
    y, m = int(parts[0]), int(parts[1])
    if m == 1:
        return f"{y-1}-12"
    return f"{y}-{m-1:02d}"


# ===================== 预警引擎 =====================

def _load_alerts():
    if os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_alerts(data):
    with open(ALERTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_alerts():
    """运行预警规则，合并已有预警记录"""
    from datetime import datetime
    now = datetime.now()
    month_str = now.strftime("%Y-%m")

    existing = _load_alerts()
    # Include ALL alerts (resolved + unresolved) in seen to prevent re-generation
    seen = {a.get("_sig", f"{a['type']}:{a.get('category','')}") for a in existing}
    new_alerts = []
    alert_idx = len(existing) + 1

    def _nid():
        nonlocal alert_idx
        i = alert_idx
        alert_idx += 1
        return f"alert_{i}"

    def _add(sig, item):
        if sig not in seen:
            seen.add(sig)
            item["_sig"] = sig
            new_alerts.append(item)

    # 规则1：预算超支
    budget_data = get_budget_status(month_str)
    for item in budget_data["items"]:
        if item["ratio"] >= 100:
            _add(f"budget_over:{item['category']}", {
                "id": _nid(), "type": "budget_over", "severity": "high",
                "category": item["category"],
                "message": f"{item['category']} 已超支：¥{item['actual']:,.0f} / ¥{item['budget']:,.0f}（{item['ratio']}%）",
                "created_at": now.strftime("%Y-%m-%d %H:%M"), "resolved": False,
            })
        elif item["ratio"] >= 80:
            _add(f"budget_warn:{item['category']}", {
                "id": _nid(), "type": "budget_warn", "severity": "medium",
                "category": item["category"],
                "message": f"{item['category']} 已用 {item['ratio']}%，接近预算上限",
                "created_at": now.strftime("%Y-%m-%d %H:%M"), "resolved": False,
            })

    # 规则2：流动性不足
    overview = get_overview()
    if overview["liquidity_coverage"] < 3:
        _add("liquidity:", {
            "id": _nid(), "type": "liquidity", "severity": "high", "category": "",
            "message": f"流动性覆盖率仅 {overview['liquidity_coverage']} 个月，低于安全线 3 个月",
            "created_at": now.strftime("%Y-%m-%d %H:%M"), "resolved": False,
        })

    # 规则3：异常交易（单笔 > 类目均值 3 倍）
    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]
    norm = expense[expense["is_outlier"] != "True"]
    cat_stats = norm.groupby("category_l1")["cny_amount"].agg(["mean", "std"])
    recent = norm[norm["month"] == month_str]
    for _, row in recent.iterrows():
        cat = row["category_l1"]
        if cat in cat_stats.index:
            mean = cat_stats.loc[cat, "mean"]
            std = cat_stats.loc[cat, "std"]
            if std > 0 and row["cny_amount"] > mean + 3 * std:
                # Use stable signature: type + category only (no date/amount)
                sig = f"abnormal:{cat}"
                _add(sig, {
                    "id": _nid(), "type": "abnormal", "severity": "medium",
                    "category": cat,
                    "message": f"异常支出：{cat} 中有一笔 ¥{row['cny_amount']:,.0f}（均值 ¥{mean:,.0f}）",
                    "created_at": now.strftime("%Y-%m-%d %H:%M"), "resolved": False,
                })

    all_alerts = new_alerts + existing
    _save_alerts(all_alerts)
    for a in all_alerts:
        a.pop("_sig", None)
    return all_alerts


def resolve_alert(alert_id):
    alerts = _load_alerts()
    for a in alerts:
        if a["id"] == alert_id:
            a["resolved"] = True
    _save_alerts(alerts)
    # Clean up internal fields before returning
    for a in alerts:
        a.pop("_sig", None)
    return alerts


# ===================== 目标管理 =====================

def _load_goals():
    if os.path.exists(GOALS_FILE):
        with open(GOALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_goals(data):
    with open(GOALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_goals():
    """获取所有目标及进度"""
    goals = _load_goals()
    overview = get_overview()
    budget_data = get_budget_status()
    result = []
    for g in goals:
        progress = _calc_goal_progress(g, overview, budget_data)
        result.append({**g, **progress})
    return result


def _calc_goal_progress(goal, overview, budget_data):
    gtype = goal.get("type", "save")
    target = float(goal["target"])
    current = 0
    if gtype == "save":
        current = overview["net_worth"] - float(goal.get("starting_net_worth", overview["net_worth"]))
        current = max(current, 0)
    elif gtype == "net_worth":
        current = overview["net_worth"]
    elif gtype == "expense_control":
        cat = goal.get("category", "")
        for item in budget_data["items"]:
            if item["category"] == cat:
                current = item["actual"]
                break
        target = float(goal["target"])
        # 对于支出控制，越低越好，进度 = 已用/预算
        ratio = round(current / target * 100, 1) if target else 0
        return {
            "current": round(current, 2),
            "target": target,
            "progress_pct": min(ratio, 100),
            "remaining": round(max(target - current, 0), 2),
            "on_track": current <= target,
        }

    ratio = round(current / target * 100, 1) if target else 0
    return {
        "current": round(current, 2),
        "target": target,
        "progress_pct": min(ratio, 100),
        "remaining": round(max(target - current, 0), 2),
        "on_track": True,
    }


def create_goal(data):
    goals = _load_goals()
    goal = {
        "id": f"goal_{len(goals) + 1}",
        "type": data.get("type", "save"),
        "name": data["name"],
        "target": float(data["target"]),
        "deadline": data.get("deadline", ""),
        "category": data.get("category", ""),
        "starting_net_worth": float(data.get("starting_net_worth", 0)),
        "created_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d"),
    }
    goals.append(goal)
    _save_goals(goals)
    return goals


def update_goal(goal_id, data):
    goals = _load_goals()
    for g in goals:
        if g["id"] == goal_id:
            for k, v in data.items():
                if k != "id":
                    g[k] = v
    _save_goals(goals)
    return goals


def delete_goal(goal_id):
    goals = _load_goals()
    goals = [g for g in goals if g["id"] != goal_id]
    _save_goals(goals)
    return goals


# ===================== 年度报告 =====================

def get_annual_report(year=None):
    """Generate annual financial report."""
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

    # Find best/worst months
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


# ===================== 预测回测 =====================

def get_forecast_backtest():
    """Compare historical predictions vs actual values."""
    import csv as csv_mod
    if not os.path.exists(FORECAST_FILE):
        return {"error": "预测结果文件不存在", "backtest": [], "mape": 0}

    predictions = []
    with open(FORECAST_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv_mod.DictReader(f)
        for row in reader:
            predictions.append({
                "month": row.get("月份", ""),
                "predicted": float(row.get("预测值", 0)),
            })

    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    actual = valid[valid["corrected_type"] == "支出"].groupby("month")["cny_amount"].sum()

    backtest = []
    for p in predictions:
        m = p["month"]
        if m in actual.index:
            actual_val = actual[m]
            error_pct = (p["predicted"] - actual_val) / actual_val * 100 if actual_val else 0
            backtest.append({
                "month": m,
                "predicted": round(p["predicted"], 2),
                "actual": round(actual_val, 2),
                "error_pct": round(error_pct, 1),
                "error_amount": round(p["predicted"] - actual_val, 2),
            })

    mape = sum(abs(b["error_pct"]) for b in backtest) / len(backtest) if backtest else 0

    return {
        "backtest": backtest,
        "mape": round(mape, 1),
        "summary": f"历史 {len(backtest)} 个月预测，平均误差 {mape:.1f}%",
    }


# ===================== 实时记账 =====================

TRANSACTIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "实时记账.csv")
TRANSACTION_FIELDS = ["date", "amount", "category", "type", "account", "note", "created_at"]

# 常用账户
DEFAULT_ACCOUNTS = ["招行储蓄卡", "微信零钱", "现金", "信用卡"]


def _get_manual_conn():
    """获取 SQLite 连接（manual_transactions 表）"""
    from utils import db
    db.init_db()
    return db.get_conn()


def _load_transactions():
    """从 SQLite 加载手动记账记录"""
    try:
        conn = _get_manual_conn()
        cur = conn.cursor()
        cur.execute("SELECT date, amount, category, type, account, note, created_at FROM manual_transactions ORDER BY created_at DESC")
        rows = [{"date": r[0], "amount": str(r[1]), "category": r[2], "type": r[3], "account": r[4], "note": r[5], "created_at": r[6]} for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def _save_transactions(rows):
    """兼容旧逻辑（不再使用）"""
    pass


def delete_transaction(created_at):
    """删除指定 created_at 的交易记录，并反向恢复账户余额"""
    conn = _get_manual_conn()
    cur = conn.cursor()

    # 先查询要删除的记录
    cur.execute("SELECT amount, type, account FROM manual_transactions WHERE created_at = ?", (created_at,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False

    amount, tx_type, account = row

    # 反向恢复余额
    if account:
        # 删除支出 = 加回余额，删除收入 = 扣回余额
        balance_change = float(amount) if tx_type == "支出" else -float(amount)
        _update_account_balance(account, balance_change)

    # 删除记录
    cur.execute("DELETE FROM manual_transactions WHERE created_at = ?", (created_at,))
    conn.commit()
    conn.close()
    return True


def add_transaction(amount, category, note="", tx_type="支出", date=None, account=""):
    """记一笔账并返回实时分析"""
    from datetime import datetime
    now = datetime.now()
    date_str = date or now.strftime("%Y-%m-%d")
    created_at = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    amt = round(float(amount), 2)

    # 1. 写入流水
    conn = _get_manual_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO manual_transactions (date, amount, category, type, account, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (date_str, amt, category, tx_type, account, note, created_at)
    )
    conn.commit()
    conn.close()

    # 2. 更新账户余额
    balance_change = -amt if tx_type == "支出" else amt
    if account:
        _update_account_balance(account, balance_change)

    tx = {
        "date": date_str,
        "amount": str(amt),
        "category": category,
        "type": tx_type,
        "account": account,
        "note": note,
        "created_at": created_at,
    }

    # 3. 实时分析（包含更新后的净资产）
    return _analyze_after_transaction(tx)


def _update_account_balance(account, change):
    """更新指定账户的余额"""
    asset_config = _load_asset_config()
    for layer_name, items in asset_config.items():
        if account in items:
            items[account] = round(items[account] + change, 2)
            _save_asset_config(asset_config)
            return True
    return False


def _analyze_after_transaction(tx):
    """记账后实时分析"""
    from datetime import datetime
    now = datetime.now()
    month_str = tx["date"][:7]

    transactions = _load_transactions()
    month_txs = [t for t in transactions if t["date"][:7] == month_str]

    # 区分支出和收入
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

    # 预算对比（仅支出）
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

    # 总预算（仅支出）
    total_budget = sum(b for b in budget_config.values() if b > 0)
    total_spent = total_expense
    total_remaining = max(total_budget - total_spent, 0)

    # AI 分析建议
    suggestions = []

    # 收入提示
    if total_income > 0:
        suggestions.append(f"💰 本月已记录收入 ¥{total_income:,.0f}")

    # 预算建议（仅支出）
    over_budget = [b for b in budget_status if b["ratio"] > 100]
    warn_budget = [b for b in budget_status if 80 <= b["ratio"] <= 100]

    if over_budget:
        for b in over_budget:
            suggestions.append(f"⚠️ {b['category']}已超支{b['ratio']:.0f}%（¥{b['spent']:,.0f}/¥{b['budget']:,.0f}），建议控制")
    if warn_budget:
        for b in warn_budget:
            suggestions.append(f"⚡ {b['category']}接近上限{b['ratio']:.0f}%，剩余¥{b['remaining']:,.0f}")

    # 结余提示
    balance = total_income - total_expense
    if total_income > 0:
        if balance >= 0:
            suggestions.append(f"✅ 本月结余 ¥{balance:,.0f}（收入 ¥{total_income:,.0f} - 支出 ¥{total_expense:,.0f}）")
        else:
            suggestions.append(f"🔴 本月超支 ¥{abs(balance):,.0f}（收入 ¥{total_income:,.0f} - 支出 ¥{total_expense:,.0f}）")

    # 与上月同期对比（仅支出）
    prev_month = f"{now.year}-{now.month-1:02d}" if now.month > 1 else f"{now.year-1}-12"
    prev_txs = [t for t in transactions if t["date"][:7] == prev_month and t["type"] != "收入"]
    prev_total = sum(float(t["amount"]) for t in prev_txs)
    if prev_total > 0:
        change = round((total_expense - prev_total) / prev_total * 100, 1)
        if change > 20:
            suggestions.append(f"📈 本月支出比上月同期增长{change}%，注意控制")
        elif change < -20:
            suggestions.append(f"📉 本月支出比上月同期减少{abs(change)}%，继续保持")

    # 最近5笔（支出）
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
        "overview": get_overview(),
    }


def get_quick_stats():
    """获取当前月快速统计（供首页展示）"""
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
