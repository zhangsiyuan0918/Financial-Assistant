"""消费分析"""
import pandas as pd

from utils.data_core import load_v4, load_unified


def get_spending(year=None):
    df = load_unified()
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
    df = load_unified()
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
    df = load_unified()
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
    df = load_unified()
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


def get_seasonal_patterns():
    df = load_unified()
    valid = df[df["valid_for_stats"] == "True"]
    expense = valid[valid["corrected_type"] == "支出"]
    norm = expense[expense["is_outlier"] != "True"].copy()
    norm["month_num"] = norm["clean_date"].dt.month

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
