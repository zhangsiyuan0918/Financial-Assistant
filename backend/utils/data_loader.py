import csv
import json
import os
import pandas as pd
from collections import defaultdict
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import V4_FILE, DB_PATH, ASSET_LAYERS, CASH_LIQUID, INVESTMENT, RESTRICTED, RECEIVABLES, DEBT, BILLS_PAYABLE, ASSET_HISTORY_FILE, ASSET_CONFIG_FILE, BUDGET_CONFIG_FILE, MONTHLY_SALARY, QUARTERLY_BONUS, PORTFOLIO, MONTHLY_BUDGET, ALERTS_FILE, GOALS_FILE, FORECAST_FILE, CREDIT_CARD_FILE, TEMPLATES_FILE
from utils import db
db.set_db_path(DB_PATH)

import threading

# 文件锁：每种 JSON 文件一把锁
_file_locks = {
    "asset": threading.Lock(),
    "credit_card": threading.Lock(),
    "budget": threading.Lock(),
    "goals": threading.Lock(),
    "alerts": threading.Lock(),
}


def _atomic_write(filepath, data):
    """原子写入：先写临时文件，再重命名，防止写入中途崩溃导致文件损坏"""
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # Windows 上 rename 需要先删除目标文件
    if os.path.exists(filepath):
        os.replace(tmp, filepath)
    else:
        os.rename(tmp, filepath)


def _load_asset_config():
    """从 JSON 加载资产配置，不存在则使用 config.py 默认值"""
    if os.path.exists(ASSET_CONFIG_FILE):
        with open(ASSET_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {k: dict(v) for k, v in ASSET_LAYERS.items()}


def _save_asset_config(data):
    with _file_locks["asset"]:
        _atomic_write(ASSET_CONFIG_FILE, data)


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
    # 信用卡余额从实时 JSON 读取，不再使用硬编码的 BILLS_PAYABLE
    cc_data = _load_credit_card()
    bills_total = cc_data["balance"]
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

    asset_config = _load_asset_config()
    added = []
    updated = []
    skipped = []

    for layer, items in new_assets.items():
        if layer not in asset_config:
            skipped.append(f"层级「{layer}」不存在")
            continue
        for name, amount in items.items():
            if name in asset_config[layer]:
                asset_config[layer][name] = float(amount)
                updated.append(name)
            else:
                # 新账户：添加到对应层级
                asset_config[layer][name] = float(amount)
                added.append(name)

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
    with _file_locks["budget"]:
        _atomic_write(BUDGET_CONFIG_FILE, data)


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
    with _file_locks["alerts"]:
        _atomic_write(ALERTS_FILE, data)


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
    with _file_locks["goals"]:
        _atomic_write(GOALS_FILE, data)


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
    from datetime import datetime
    goals = _load_goals()
    # 使用时间戳避免 ID 重复
    goal_id = f"goal_{datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]}"
    goal = {
        "id": goal_id,
        "type": data.get("type", "save"),
        "name": data["name"],
        "target": float(data["target"]),
        "deadline": data.get("deadline", ""),
        "category": data.get("category", ""),
        "starting_net_worth": float(data.get("starting_net_worth", 0)),
        "created_at": datetime.now().strftime("%Y-%m-%d"),
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
        cur.execute("SELECT id, date, amount, category, type, account, note, created_at FROM manual_transactions ORDER BY created_at DESC")
        rows = [{"id": r[0], "date": r[1], "amount": str(r[2]), "category": r[3], "type": r[4], "account": r[5], "note": r[6], "created_at": r[7]} for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"[WARNING] _load_transactions failed: {e}")
        return []


def _save_transactions(rows):
    """兼容旧逻辑（不再使用）"""
    pass


# ===================== 信用卡管理 =====================

def _load_credit_card():
    """加载信用卡账单"""
    if os.path.exists(CREDIT_CARD_FILE):
        with open(CREDIT_CARD_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"balance": 0, "history": []}


def _save_credit_card(data):
    with _file_locks["credit_card"]:
        _atomic_write(CREDIT_CARD_FILE, data)


def add_credit_card_expense(amount, note=""):
    """信用卡消费：不扣减资产，增加待还金额"""
    from datetime import datetime
    amt = float(amount)
    if amt <= 0:
        return {"error": "消费金额必须大于0"}
    cc = _load_credit_card()
    cc["balance"] = round(cc["balance"] + amt, 2)
    cc["history"].append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "amount": round(float(amount), 2),
        "type": "消费",
        "note": note,
        "balance": cc["balance"],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
    })
    _save_credit_card(cc)
    return cc


def pay_credit_card(amount, account="招行储蓄卡"):
    """信用卡还款：扣减资产，减少待还金额"""
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

    # 同时扣减资产账户
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
    if not balance_ok and account:
        result["warning"] = f"账户「{account}」未在资产配置中找到，余额未扣减"
    return result


def get_credit_card_status():
    """获取信用卡状态"""
    cc = _load_credit_card()
    return {
        "balance": cc["balance"],
        "history": cc["history"][-10:],  # 最近10条
    }


def delete_transaction(tx_id):
    """删除指定 ID 的交易记录，并反向恢复余额"""
    conn = _get_manual_conn()
    cur = conn.cursor()

    # 先查询要删除的记录
    cur.execute("SELECT amount, type, account FROM manual_transactions WHERE id = ?", (tx_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "记录不存在"}

    amount, tx_type, account = row
    balance_ok = True

    # 反向恢复余额
    is_credit_card = account == "信用卡"
    if tx_type == "支出" and is_credit_card:
        _reverse_credit_card_expense(float(amount))
    elif tx_type == "支出" and account:
        if not _update_account_balance(account, float(amount)):
            balance_ok = False
    elif tx_type == "收入" and account:
        if not _update_account_balance(account, -float(amount)):
            balance_ok = False

    # 删除记录
    cur.execute("DELETE FROM manual_transactions WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()

    result = {"success": True}
    if not balance_ok and account:
        result["warning"] = f"账户「{account}」未在资产配置中找到，余额未恢复"
    return result


def _reverse_credit_card_expense(amount):
    """反向恢复信用卡余额（删除消费时调用）"""
    from datetime import datetime
    cc = _load_credit_card()
    cc["balance"] = round(cc["balance"] - float(amount), 2)
    cc["history"].append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "amount": round(float(amount), 2),
        "type": "冲正",
        "note": "删除消费记录",
        "balance": cc["balance"],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
    })
    _save_credit_card(cc)


def add_transaction(amount, category, note="", tx_type="支出", date=None, account=""):
    """记一笔账并返回实时分析"""
    from datetime import datetime

    # 输入校验
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
    created_at = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    # 1. 写入流水
    conn = _get_manual_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO manual_transactions (date, amount, category, type, account, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (date_str, amt, category, tx_type, account, note, created_at)
    )
    tx_id = cur.lastrowid
    conn.commit()
    conn.close()

    # 2. 更新账户余额（信用卡消费不扣减资产，还款才扣减）
    is_credit_card = account == "信用卡"
    balance_ok = True
    if tx_type == "支出" and is_credit_card:
        add_credit_card_expense(amt, note)
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

    # 3. 实时分析（包含更新后的净资产）
    result = _analyze_after_transaction(tx)
    if not balance_ok and account:
        result["suggestions"].insert(0, f"⚠️ 账户「{account}」未在资产配置中找到，余额未更新")
    return result


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
            over_amount = b["spent"] - b["budget"]
            suggestions.append(f"⚠️ {b['category']}已超支{b['ratio']:.0f}%（¥{b['spent']:,.0f}/¥{b['budget']:,.0f}），超支¥{over_amount:,.0f}")
            # 给出具体省钱建议
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

    # 结余提示
    balance = total_income - total_expense
    if total_income > 0:
        if balance >= 0:
            savings_rate = round(balance / total_income * 100, 1)
            suggestions.append(f"✅ 本月结余 ¥{balance:,.0f}（储蓄率 {savings_rate}%）")
        else:
            suggestions.append(f"🔴 本月超支 ¥{abs(balance):,.0f}（收入 ¥{total_income:,.0f} - 支出 ¥{total_expense:,.0f}）")
            # 如果有收入，给出控制建议
            if total_income > 0:
                target_expense = total_income * 0.8  # 建议支出不超过收入的80%
                reduce_needed = total_expense - target_expense
                if reduce_needed > 0:
                    suggestions.append(f"   💡 建议：将月支出控制在¥{target_expense:,.0f}以内（收入的80%），需减少¥{reduce_needed:,.0f}")

    # 消费习惯分析（基于历史数据）
    try:
        df = load_v4()
        valid = df[df["valid_for_stats"] == "True"]
        expense = valid[valid["corrected_type"] == "支出"]
        current_month = tx["date"][:7]
        current_expense = expense[expense["month"] == current_month]
        prev_expense = expense[expense["month"] == prev_month] if prev_month else pd.DataFrame()

        if not current_expense.empty and not prev_expense.empty:
            # 找出增长最快的分类
            cur_cats = current_expense.groupby("category_l1")["cny_amount"].sum()
            prev_cats = prev_expense.groupby("category_l1")["cny_amount"].sum()
            for cat in cur_cats.index:
                if cat in prev_cats.index and prev_cats[cat] > 0:
                    growth = (cur_cats[cat] - prev_cats[cat]) / prev_cats[cat] * 100
                    if growth > 30:
                        suggestions.append(f"📈 {cat}支出比上月增长{growth:.0f}%，建议关注")
    except Exception:
        pass

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
        "overview": _lightweight_overview(),
    }


def _lightweight_overview():
    """轻量级概览，仅计算净资产，不调用重型 get_overview()"""
    asset_config = _load_asset_config()
    total = sum(sum(items.values()) for items in asset_config.values())
    cc = _load_credit_card()
    return {
        "net_worth": round(total - cc["balance"], 2),
        "total_assets": round(total, 2),
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


# ===================== 周期性交易模板 =====================

def _load_templates():
    """加载交易模板"""
    if os.path.exists(TEMPLATES_FILE):
        with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_templates(data):
    with _file_locks["goals"]:  # 复用一把锁
        _atomic_write(TEMPLATES_FILE, data)


def get_templates():
    """获取所有模板"""
    return _load_templates()


def create_template(name, amount, category, tx_type="支出", account="", note="", frequency="monthly"):
    """创建交易模板"""
    from datetime import datetime
    templates = _load_templates()
    template = {
        "id": f"tpl_{datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]}",
        "name": name,
        "amount": round(float(amount), 2),
        "category": category,
        "type": tx_type,
        "account": account,
        "note": note,
        "frequency": frequency,  # monthly/weekly/yearly
        "created_at": datetime.now().strftime("%Y-%m-%d"),
    }
    templates.append(template)
    _save_templates(templates)
    return templates


def delete_template(template_id):
    """删除模板"""
    templates = _load_templates()
    templates = [t for t in templates if t["id"] != template_id]
    _save_templates(templates)
    return templates


def apply_template(template_id):
    """应用模板创建一笔交易"""
    templates = _load_templates()
    for t in templates:
        if t["id"] == template_id:
            result = add_transaction(
                amount=t["amount"],
                category=t["category"],
                note=t["name"],
                tx_type=t["type"],
                account=t.get("account", ""),
            )
            return result
    return {"error": "模板不存在"}


# ===================== 智能分类推荐 =====================

# 预置关键词映射（常见消费场景）
_PRESET_CATEGORY_MAP = {
    "餐饮": ["外卖", "餐厅", "吃饭", "午餐", "晚餐", "早餐", "奶茶", "咖啡", "火锅", "烧烤",
             "麦当劳", "肯德基", "星巴克", "瑞幸", "沙县", "兰州", "面馆", "食堂", "小吃",
             "必胜客", "海底捞", "喜茶", "奈雪", "茶百道", "蜜雪冰城", "美团", "饿了么",
             "正餐", "快餐", "便当", "盒饭", "汉堡", "披萨", "寿司", "日料", "韩料",
             "甜品", "蛋糕", "面包", "零食", "水果", "生鲜", "饮料", "酒水",
             "大排档", "夜宵", "下午茶", "早餐", "brunch", "自助餐", "饮品"],
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
             "车险", "加油", "充电桩", "保养", "轮胎", "刹车"],
    "医疗": ["医院", "药店", "体检", "挂号", "门诊", "牙科", "眼科",
             "看病", "买药", "药房", "诊所", "医保", "住院"],
    "个护": ["理发", "美容", "护肤", "化妆品", "美甲", "spa",
             "美发", "造型", "护肤", "香水", "防晒"],
    "学习": ["课程", "培训", "书籍", "考试", "学费",
             "网课", "知识付费", "得到", "极客时间", "Udemy"],
    "数字消费": ["话费", "流量", "会员", "订阅", "云服务", "域名",
              "iCloud", "Apple", "Google", "Netflix", "Spotify", "B站会员",
              "百度网盘", "阿里云", "腾讯云"],
    "其他": ["快递", "打印", "复印", "洗衣", "干洗", "搬家", "维修"],
}


def _build_keyword_category_map():
    """从历史数据构建关键词→分类映射"""
    mapping = defaultdict(lambda: defaultdict(int))

    # 1. 从 CSV 历史数据学习（clean_project + 原始分类字段）
    try:
        df = load_v4()
        valid = df[df["valid_for_stats"] == "True"]
        for _, row in valid.iterrows():
            cat = row.get("category_l1", "")
            if not cat:
                continue

            # 从 clean_project 学习
            project = str(row.get("clean_project", "")).strip()
            if project:
                for word in re.split(r"[\s,，.。、/\\()（）]+", project):
                    word = word.strip()
                    if len(word) >= 2:
                        mapping[word][cat] += 1

            # 从原始分类字段学习（作为备选）
            raw_cat = str(row.get("分类", "")).strip()
            if raw_cat and raw_cat != cat:
                mapping[raw_cat][cat] += 5  # 原始分类权重更高

            # 从备注字段学习
            note = str(row.get("备注", "")).strip()
            if note:
                for word in re.split(r"[\s,，.。、/\\()（）]+", note):
                    word = word.strip()
                    if len(word) >= 2:
                        mapping[word][cat] += 1
    except Exception:
        pass

    # 2. 从手动记账数据学习
    try:
        txs = _load_transactions()
        for tx in txs:
            note = tx.get("note", "").strip()
            cat = tx.get("category", "")
            if note and cat:
                for word in re.split(r"[\s,，.。、/\\()（）]+", note):
                    word = word.strip()
                    if len(word) >= 2:
                        mapping[word][cat] += 2  # 手动记账权重更高
    except Exception:
        pass

    return mapping


def suggest_category(text, top_n=3):
    """
    根据输入文本推荐分类。
    返回 [{"category": "餐饮", "confidence": 0.85, "source": "历史数据"}, ...]
    """
    import re
    if not text or not text.strip():
        return []

    text = text.strip()
    results = defaultdict(lambda: {"score": 0, "source": ""})

    # 1. 预置关键词匹配
    for cat, keywords in _PRESET_CATEGORY_MAP.items():
        for kw in keywords:
            if kw in text:
                results[cat]["score"] += 10
                results[cat]["source"] = "常用规则"

    # 2. 历史数据匹配
    keyword_map = _build_keyword_category_map()
    for word, cat_counts in keyword_map.items():
        if word in text:
            for cat, count in cat_counts.items():
                results[cat]["score"] += count
                results[cat]["source"] = "历史数据"

    if not results:
        return []

    # 按分数排序，计算置信度
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
    """获取各分类的统计信息（用于智能推荐）"""
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


# ===================== 消费习惯分析 =====================

def get_spending_habits():
    """
    综合消费习惯分析，返回多维度洞察。
    """
    from datetime import datetime
    now = datetime.now()
    current_month = now.strftime("%Y-%m")

    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]

    result = {}

    # 1. 星期消费模式
    result["weekday_pattern"] = _analyze_weekday_pattern(expense)

    # 2. 月内消费节奏（每月哪几天花钱多）
    result["monthly_rhythm"] = _analyze_monthly_rhythm(expense)

    # 3. 分类趋势（最近6个月各分类变化）
    result["category_trends"] = _analyze_category_trends(expense)

    # 4. 消费频率分析
    result["spending_frequency"] = _analyze_spending_frequency(expense)

    # 5. 消费速度（本月 vs 历史月均）
    result["spending_velocity"] = _analyze_spending_velocity(expense, current_month)

    # 6. 消费集中度（TOP3分类占比）
    result["concentration"] = _analyze_concentration(expense, current_month)

    return result


def _analyze_weekday_pattern(expense):
    """分析星期消费模式"""
    day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    expense = expense.copy()
    expense["weekday"] = expense["clean_date"].dt.weekday

    weekday_stats = []
    for day in range(7):
        day_data = expense[expense["weekday"] == day]
        if len(day_data) > 0:
            weekday_stats.append({
                "day": day_names[day],
                "day_num": day,
                "total": round(day_data["cny_amount"].sum(), 2),
                "count": len(day_data),
                "avg": round(day_data["cny_amount"].mean(), 2),
            })

    # 找出消费最高和最低的星期
    if weekday_stats:
        peak = max(weekday_stats, key=lambda x: x["total"])
        low = min(weekday_stats, key=lambda x: x["total"])
        return {
            "data": weekday_stats,
            "peak_day": peak["day"],
            "low_day": low["day"],
            "insight": f"你通常在{peak['day']}花钱最多（¥{peak['total']:,.0f}），{low['day']}最少",
        }
    return {"data": [], "peak_day": "", "low_day": "", "insight": ""}


def _analyze_monthly_rhythm(expense):
    """分析月内消费节奏（每月上/中/下旬分布）"""
    expense = expense.copy()
    expense["day"] = expense["clean_date"].dt.day

    periods = [
        ("上旬", 1, 10),
        ("中旬", 11, 20),
        ("下旬", 21, 31),
    ]

    rhythm = []
    for name, start, end in periods:
        period_data = expense[(expense["day"] >= start) & (expense["day"] <= end)]
        if len(period_data) > 0:
            rhythm.append({
                "period": name,
                "total": round(period_data["cny_amount"].sum(), 2),
                "count": len(period_data),
                "avg": round(period_data["cny_amount"].mean(), 2),
            })

    if rhythm:
        peak = max(rhythm, key=lambda x: x["total"])
        return {
            "data": rhythm,
            "peak_period": peak["period"],
            "insight": f"你通常在{peak['period']}消费最多",
        }
    return {"data": [], "peak_period": "", "insight": ""}


def _analyze_category_trends(expense):
    """分析最近6个月各分类支出趋势"""
    from datetime import datetime
    now = datetime.now()

    # 获取最近6个月
    months = []
    for i in range(5, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        months.append(f"{y}-{m:02d}")

    # 按月按分类汇总
    trends = {}
    for month in months:
        month_data = expense[expense["month"] == month]
        cat_totals = month_data.groupby("category_l1")["cny_amount"].sum()
        for cat, total in cat_totals.items():
            if cat not in trends:
                trends[cat] = []
            trends[cat].append({"month": month, "amount": round(total, 2)})

    # 计算趋势（线性回归斜率）
    results = []
    for cat, data in trends.items():
        if len(data) >= 2:
            amounts = [d["amount"] for d in data]
            # 简单斜率：(最后一个月 - 第一个月) / 月数
            slope = (amounts[-1] - amounts[0]) / len(amounts)
            trend_pct = (amounts[-1] - amounts[0]) / amounts[0] * 100 if amounts[0] > 0 else 0
            results.append({
                "category": cat,
                "data": data,
                "slope": round(slope, 2),
                "trend_pct": round(trend_pct, 1),
                "trend": "上升" if slope > 0 else ("下降" if slope < 0 else "持平"),
            })

    results.sort(key=lambda x: abs(x["trend_pct"]), reverse=True)
    return results[:5]  # 返回变化最大的5个分类


def _analyze_spending_frequency(expense):
    """分析消费频率"""
    expense = expense.copy()
    expense["date"] = expense["clean_date"].dt.date

    # 每月平均消费天数
    daily = expense.groupby("month")["date"].nunique()
    avg_days = round(daily.mean(), 1) if len(daily) > 0 else 0

    # 每天平均消费笔数
    total_days = expense["date"].nunique()
    avg_tx_per_day = round(len(expense) / max(total_days, 1), 1)

    # 单笔平均金额
    avg_per_tx = round(expense["cny_amount"].mean(), 2) if len(expense) > 0 else 0

    # 大额消费占比（单笔>500）
    big_tx = expense[expense["cny_amount"] > 500]
    big_tx_ratio = round(len(big_tx) / max(len(expense), 1) * 100, 1)

    return {
        "avg_spend_days_per_month": avg_days,
        "avg_tx_per_day": avg_tx_per_day,
        "avg_per_transaction": avg_per_tx,
        "big_tx_ratio": big_tx_ratio,
        "insight": f"你平均每月{avg_days}天有消费，每天{avg_tx_per_day}笔，单笔均额¥{avg_per_tx:,.0f}",
    }


def _analyze_spending_velocity(expense, current_month):
    """分析消费速度（本月 vs 历史月均）"""
    from datetime import datetime
    now = datetime.now()
    day_of_month = now.day

    # 本月数据
    current = expense[expense["month"] == current_month]
    current_total = current["cny_amount"].sum()

    # 历史月均（排除本月）
    historical = expense[expense["month"] != current_month]
    if len(historical) > 0:
        monthly_totals = historical.groupby("month")["cny_amount"].sum()
        avg_monthly = monthly_totals.mean()
    else:
        avg_monthly = 0

    # 预测本月总额（按当前速度）
    if day_of_month > 0 and avg_monthly > 0:
        projected = current_total / day_of_month * 30
        deviation = (projected - avg_monthly) / avg_monthly * 100 if avg_monthly > 0 else 0
    else:
        projected = current_total
        deviation = 0

    if deviation > 20:
        status = "偏快"
        insight = f"本月消费速度比历史月均快{deviation:.0f}%，预计本月总额¥{projected:,.0f}"
    elif deviation < -20:
        status = "偏慢"
        insight = f"本月消费速度比历史月均慢{abs(deviation):.0f}%，预计本月总额¥{projected:,.0f}"
    else:
        status = "正常"
        insight = f"本月消费速度正常，预计本月总额¥{projected:,.0f}"

    return {
        "current_total": round(current_total, 2),
        "avg_monthly": round(avg_monthly, 2),
        "projected": round(projected, 2),
        "deviation_pct": round(deviation, 1),
        "status": status,
        "insight": insight,
    }


def _analyze_concentration(expense, current_month):
    """分析消费集中度"""
    current = expense[expense["month"] == current_month]
    if len(current) == 0:
        return {"top3_ratio": 0, "top3_categories": [], "insight": ""}

    cat_totals = current.groupby("category_l1")["cny_amount"].sum().sort_values(ascending=False)
    total = cat_totals.sum()

    top3 = cat_totals.head(3)
    top3_ratio = round(top3.sum() / total * 100, 1) if total > 0 else 0

    top3_info = [
        {"category": cat, "amount": round(amt, 2), "ratio": round(amt / total * 100, 1) if total > 0 else 0}
        for cat, amt in top3.items()
    ]

    if top3_ratio > 70:
        insight = f"消费高度集中在{top3_info[0]['category']}等{len(top3_info)}个分类（占比{top3_ratio}%）"
    elif top3_ratio > 50:
        insight = f"消费较集中，TOP3分类占比{top3_ratio}%"
    else:
        insight = "消费较分散，各分类占比均衡"

    return {
        "top3_ratio": top3_ratio,
        "top3_categories": top3_info,
        "total_categories": len(cat_totals),
        "insight": insight,
    }
