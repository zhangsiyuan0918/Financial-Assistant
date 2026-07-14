"""资产配置管理：加载、保存、概览、历史"""
import csv
import json
import os
import pandas as pd

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    ASSET_LAYERS, ASSET_HISTORY_FILE, ASSET_CONFIG_FILE,
    DEBT, BILLS_PAYABLE, MONTHLY_SALARY, QUARTERLY_BONUS,
)
from utils.data_core import _file_locks, _atomic_write, load_v4, load_unified


def _load_asset_config():
    if os.path.exists(ASSET_CONFIG_FILE):
        with open(ASSET_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {k: dict(v) for k, v in ASSET_LAYERS.items()}


def _save_asset_config(data):
    with _file_locks["asset"]:
        _atomic_write(ASSET_CONFIG_FILE, data)


def _layers_from_config(config):
    return (
        config.get("现金/活期", {}),
        config.get("投资资产", {}),
        config.get("受限资产", {}),
        config.get("应收", {}),
    )


def flatten_assets(config=None):
    if config is None:
        config = _load_asset_config()
    result = []
    for layer, items in config.items():
        for name, amount in items.items():
            result.append({"name": name, "amount": amount, "layer": layer})
    return result


def get_overview():
    from datetime import datetime
    df = load_unified()
    current_month = datetime.now().strftime("%Y-%m")

    asset_config = _load_asset_config()
    cash_items, invest_items, restricted_items, receivables_items = _layers_from_config(asset_config)

    cash_total = sum(cash_items.values())
    invest_total = sum(invest_items.values())
    restricted_total = sum(restricted_items.values())
    receivables_total = sum(receivables_items.values())
    total_assets = cash_total + invest_total + restricted_total + receivables_total

    debt_total = sum(DEBT.values())
    from utils.transactions import _load_credit_card
    cc_data = _load_credit_card()
    bills_total = cc_data["balance"]
    net_worth = total_assets - bills_total

    valid = df[df["valid_for_stats"] == "True"]

    # 当月实际收支
    cur_month = valid[valid["month"] == current_month]
    cur_income = cur_month[cur_month["corrected_type"] == "收入"]["cny_amount"].sum()
    cur_expense = cur_month[cur_month["corrected_type"] == "支出"]["cny_amount"].sum()
    monthly_income = round(cur_income, 2) if cur_income > 0 else 0
    monthly_expense = round(cur_expense, 2)

    # 历史月均支出（用于流动性覆盖率）
    expense = valid[valid["corrected_type"] == "支出"]
    recent = expense[expense["month"] >= "2025-09"]
    avg_monthly_exp = recent.groupby("month")["cny_amount"].sum().mean()
    if pd.notna(avg_monthly_exp):
        avg_monthly_exp = round(avg_monthly_exp, 2)
    else:
        avg_monthly_exp = 0

    liquidity_coverage = round(cash_total / avg_monthly_exp, 1) if avg_monthly_exp > 0 else 0
    investment_ratio = round(invest_total / total_assets * 100, 1) if total_assets > 0 else 0

    assets_flat = flatten_assets(asset_config)
    assets_detail = [{"name": a["name"], "amount": a["amount"],
                      "layer": a["layer"],
                      "ratio": round(a["amount"] / total_assets * 100, 1)} for a in assets_flat]

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
        "monthly_income": monthly_income,
        "monthly_balance": round(monthly_income - monthly_expense, 2),
        "monthly_expense": monthly_expense,
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


def get_asset_history():
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

    # 用当前实际值覆盖当月数据（快照可能过时）
    from datetime import datetime
    current_month = datetime.now().strftime("%Y-%m")
    asset_config = _load_asset_config()
    cash_items, invest_items, restricted_items, receivables_items = _layers_from_config(asset_config)
    real_cash = sum(cash_items.values())
    real_invest = sum(invest_items.values())
    real_restricted = sum(restricted_items.values())
    real_receivables = sum(receivables_items.values())
    real_total = real_cash + real_invest + real_restricted + real_receivables

    for entry in result:
        if entry["month"] == current_month:
            entry["total"] = round(real_total, 2)
            entry["cash_and_liquid"] = round(real_cash, 2)
            entry["investment"] = round(real_invest, 2)
            entry["restricted"] = round(real_restricted, 2)
            entry["receivables"] = round(real_receivables, 2)
            break
    else:
        # 当月没有快照，追加一条
        result.append({
            "month": current_month,
            "total": round(real_total, 2),
            "cash_and_liquid": round(real_cash, 2),
            "investment": round(real_invest, 2),
            "restricted": round(real_restricted, 2),
            "receivables": round(real_receivables, 2),
        })

    return sorted(result, key=lambda x: x["month"])


def get_portfolio():
    from config import PORTFOLIO
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
                asset_config[layer][name] = float(amount)
                added.append(name)

    _save_asset_config(asset_config)

    import csv as csv_mod
    cash_items, invest_items, restricted_items, receivables_items = _layers_from_config(asset_config)
    new_rows = []
    for layer, items in [("现金/活期", cash_items), ("投资资产", invest_items),
                         ("受限资产", restricted_items), ("应收", receivables_items)]:
        for name, amount in items.items():
            new_rows.append({"month": month_str, "layer": layer, "item": name, "amount": amount})
    if os.path.exists(ASSET_HISTORY_FILE):
        with open(ASSET_HISTORY_FILE, "r", encoding="utf-8-sig") as f:
            reader = list(csv_mod.DictReader(f))
        old_rows = [r for r in reader if r["month"] != month_str]
        remaining = old_rows + new_rows
    else:
        remaining = new_rows
    with open(ASSET_HISTORY_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv_mod.DictWriter(f, fieldnames=["month", "layer", "item", "amount"])
        writer.writeheader()
        writer.writerows(remaining)

    return _load_asset_config()


def backfill_asset_history():
    """回填历史资产快照：用收支数据估算过去每月净资产。
    使用当前实际资产比例分配，而非固定比例。"""
    import csv as csv_mod
    overview = get_overview()
    current_net_worth = overview["net_worth"]

    # 使用当前实际比例（而非固定 20/40/30/10）
    total_assets = overview["total_assets"]
    if total_assets > 0:
        ratio_cash = overview["cash_and_liquid"] / total_assets
        ratio_invest = overview["investment"] / total_assets
        ratio_restricted = overview["restricted"] / total_assets
        ratio_receivables = overview["receivables"] / total_assets
    else:
        ratio_cash, ratio_invest, ratio_restricted, ratio_receivables = 0.25, 0.25, 0.25, 0.25

    df = load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    monthly = valid.groupby(["month", "corrected_type"])["cny_amount"].sum().unstack(fill_value=0)

    months = sorted(monthly.index)
    snapshots = []
    running_balance = current_net_worth

    for month in reversed(months):
        income = monthly.loc[month, "收入"] if "收入" in monthly.columns else 0
        expense = monthly.loc[month, "支出"] if "支出" in monthly.columns else 0
        net = income - expense
        snapshots.append({"month": month, "net_worth": round(running_balance, 2)})
        running_balance -= net

    snapshots.reverse()
    snapshot_map = {s["month"]: s["net_worth"] for s in snapshots}

    existing_rows = []
    existing_months = set()
    if os.path.exists(ASSET_HISTORY_FILE):
        with open(ASSET_HISTORY_FILE, "r", encoding="utf-8-sig") as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                existing_rows.append(row)
                existing_months.add(row["month"])

    missing_months = [s["month"] for s in snapshots if s["month"] not in existing_months]

    # 重新估算所有 estimation 行（使用正确比例），保留实际数据行
    final_rows = []
    for row in existing_rows:
        if row["item"] == "estimation":
            # 用正确比例重新计算
            month = row["month"]
            if month in snapshot_map:
                nw = snapshot_map[month]
                layer = row["layer"]
                if layer == "现金/活期":
                    row["amount"] = str(round(nw * ratio_cash, 2))
                elif layer == "投资资产":
                    row["amount"] = str(round(nw * ratio_invest, 2))
                elif layer == "受限资产":
                    row["amount"] = str(round(nw * ratio_restricted, 2))
                elif layer == "应收":
                    row["amount"] = str(round(nw * ratio_receivables, 2))
        final_rows.append(row)

    # 添加缺失月份的估算行
    for month in missing_months:
        nw = snapshot_map[month]
        final_rows.append({"month": month, "layer": "现金/活期", "item": "estimation", "amount": str(round(nw * ratio_cash, 2))})
        final_rows.append({"month": month, "layer": "投资资产", "item": "estimation", "amount": str(round(nw * ratio_invest, 2))})
        final_rows.append({"month": month, "layer": "受限资产", "item": "estimation", "amount": str(round(nw * ratio_restricted, 2))})
        final_rows.append({"month": month, "layer": "应收", "item": "estimation", "amount": str(round(nw * ratio_receivables, 2))})

    with open(ASSET_HISTORY_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv_mod.DictWriter(f, fieldnames=["month", "layer", "item", "amount"])
        writer.writeheader()
        writer.writerows(final_rows)

    return {"months": len(existing_months) + len(missing_months), "added": len(missing_months), "updated": len([r for r in existing_rows if r["item"] == "estimation"]), "preserved": len([r for r in existing_rows if r["item"] != "estimation"])}
