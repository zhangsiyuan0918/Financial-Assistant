"""预算管理"""
import json
import os

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BUDGET_CONFIG_FILE, MONTHLY_BUDGET
from utils.data_core import _file_locks, _atomic_write, load_unified


def _load_budget_config():
    if os.path.exists(BUDGET_CONFIG_FILE):
        with open(BUDGET_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return dict(MONTHLY_BUDGET)


def _save_budget_config(data):
    with _file_locks["budget"]:
        _atomic_write(BUDGET_CONFIG_FILE, data)


def update_budget(new_budget):
    _save_budget_config({k: float(v) for k, v in new_budget.items()})
    return _load_budget_config()


def get_budget_status(month=None):
    from datetime import datetime
    df = load_unified()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]
    norm = expense[expense["is_outlier"] != "True"]
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
    uncategorized = {str(k): round(v, 2) for k, v in actual.items() if k not in budget_config}
    return {
        "month": target_month,
        "total_budget": total_budget,
        "total_actual": round(total_actual, 2),
        "total_ratio": round(total_actual / total_budget * 100, 1) if total_budget else 0,
        "items": items,
        "uncategorized": uncategorized,
    }
