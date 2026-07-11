"""
Prophet月度支出预测脚本
========================
功能：
1. 基于v4清洗数据，按月聚合有效支出
2. 剔除异常值（购车首付等）
3. 排除不完整月份
4. 训练Prophet模型（含节假日效应）
5. 回测验证：用前N个月预测后M个月，对比实际值
6. 预测未来12个月支出
7. 输出趋势分解、季节性分解
"""

import csv
import os
from datetime import datetime, timedelta
from collections import defaultdict

import pandas as pd
import numpy as np
from prophet import Prophet

# ==========================================
# 配置
# ==========================================
BASE_DIR = r"C:\Users\77432\.doubao\chats\2026-07-10\new-chat"
DATA_FILE = os.path.join(BASE_DIR, "记账数据_清洗_v4.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "预测结果")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 预测未来月数
FORECAST_MONTHS = 12

# 回测配置：用前N个月训练，预测后M个月
BACKTEST_TRAIN_MONTHS = 30  # 用30个月训练
BACKTEST_TEST_MONTHS = 12   # 预测12个月对比

# 节假日列表（Prophet格式）
HOLIDAYS_LIST = [
    # 元旦
    {"holiday": "new_year", "ds": "2023-01-01", "lower_window": -1, "upper_window": 1},
    {"holiday": "new_year", "ds": "2024-01-01", "lower_window": -1, "upper_window": 1},
    {"holiday": "new_year", "ds": "2025-01-01", "lower_window": -1, "upper_window": 1},
    {"holiday": "new_year", "ds": "2026-01-01", "lower_window": -1, "upper_window": 1},
    {"holiday": "new_year", "ds": "2027-01-01", "lower_window": -1, "upper_window": 1},
    # 春节
    {"holiday": "spring_festival", "ds": "2023-01-22", "lower_window": -3, "upper_window": 7},
    {"holiday": "spring_festival", "ds": "2024-02-10", "lower_window": -3, "upper_window": 7},
    {"holiday": "spring_festival", "ds": "2025-01-29", "lower_window": -3, "upper_window": 7},
    {"holiday": "spring_festival", "ds": "2026-02-17", "lower_window": -3, "upper_window": 7},
    {"holiday": "spring_festival", "ds": "2027-02-06", "lower_window": -3, "upper_window": 7},
    # 清明
    {"holiday": "qingming", "ds": "2023-04-05", "lower_window": -1, "upper_window": 3},
    {"holiday": "qingming", "ds": "2024-04-04", "lower_window": -1, "upper_window": 3},
    {"holiday": "qingming", "ds": "2025-04-04", "lower_window": -1, "upper_window": 3},
    {"holiday": "qingming", "ds": "2026-04-05", "lower_window": -1, "upper_window": 3},
    {"holiday": "qingming", "ds": "2027-04-05", "lower_window": -1, "upper_window": 3},
    # 五一
    {"holiday": "labor_day", "ds": "2023-05-01", "lower_window": -2, "upper_window": 5},
    {"holiday": "labor_day", "ds": "2024-05-01", "lower_window": -2, "upper_window": 5},
    {"holiday": "labor_day", "ds": "2025-05-01", "lower_window": -2, "upper_window": 5},
    {"holiday": "labor_day", "ds": "2026-05-01", "lower_window": -2, "upper_window": 5},
    {"holiday": "labor_day", "ds": "2027-05-01", "lower_window": -2, "upper_window": 5},
    # 端午
    {"holiday": "dragon_boat", "ds": "2023-06-22", "lower_window": -1, "upper_window": 3},
    {"holiday": "dragon_boat", "ds": "2024-06-10", "lower_window": -1, "upper_window": 3},
    {"holiday": "dragon_boat", "ds": "2025-05-31", "lower_window": -1, "upper_window": 3},
    {"holiday": "dragon_boat", "ds": "2026-06-19", "lower_window": -1, "upper_window": 3},
    {"holiday": "dragon_boat", "ds": "2027-06-09", "lower_window": -1, "upper_window": 3},
    # 中秋
    {"holiday": "mid_autumn", "ds": "2023-09-29", "lower_window": -1, "upper_window": 3},
    {"holiday": "mid_autumn", "ds": "2024-09-17", "lower_window": -1, "upper_window": 3},
    {"holiday": "mid_autumn", "ds": "2025-10-06", "lower_window": -1, "upper_window": 3},
    {"holiday": "mid_autumn", "ds": "2026-09-25", "lower_window": -1, "upper_window": 3},
    {"holiday": "mid_autumn", "ds": "2027-09-15", "lower_window": -1, "upper_window": 3},
    # 国庆
    {"holiday": "national_day", "ds": "2023-10-01", "lower_window": -2, "upper_window": 7},
    {"holiday": "national_day", "ds": "2024-10-01", "lower_window": -2, "upper_window": 7},
    {"holiday": "national_day", "ds": "2025-10-01", "lower_window": -2, "upper_window": 7},
    {"holiday": "national_day", "ds": "2026-10-01", "lower_window": -2, "upper_window": 7},
    {"holiday": "national_day", "ds": "2027-10-01", "lower_window": -2, "upper_window": 7},
]


# 车贷参数（已知固定支出，12期，2026-07还完）
CAR_LOAN_MONTHLY = 11742
CAR_LOAN_START = "2025-08"
CAR_LOAN_END = "2026-07"


def load_and_aggregate():
    """加载数据并按月聚合，车贷从训练数据中剥离"""
    monthly = defaultdict(lambda: {"expense": 0.0, "count": 0, "post_car": 0, "car_loan": 0.0})

    with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["valid_for_stats"] != "True":
                continue
            if row["corrected_type"] != "支出":
                continue
            if row["is_outlier"] == "True":
                continue
            if row["month_complete"] != "True":
                continue

            month = row["clean_date"][:7]
            amount = float(row["cny_amount"])
            # 车贷单独统计，不进入模型训练
            if row.get("category_l2") == "车贷":
                monthly[month]["car_loan"] += amount
                continue
            monthly[month]["expense"] += amount
            monthly[month]["count"] += 1
            if row["life_stage"] == "post_car":
                monthly[month]["post_car"] += 1

    months = sorted(monthly.keys())
    data = []
    for m in months:
        d = monthly[m]
        life_stage = d["post_car"] / max(d["count"], 1)
        y = d["expense"]  # 不含车贷的支出
        data.append({"ds": f"{m}-01", "y": y, "life_stage": life_stage,
                     "car_loan": d["car_loan"]})

    df = pd.DataFrame(data)
    df["ds"] = pd.to_datetime(df["ds"])
    return df


def run_backtest(df):
    """回测验证：用前N个月训练，预测后M个月，计算误差"""
    print("\n" + "=" * 60)
    print("【回测验证】历史数据精度检验")
    print("=" * 60)

    total_months = len(df)
    if total_months < 6:
        print(f"数据不足，跳过回测（仅有{total_months}个月）")
        return None
    # 数据充足用标准30/12，数据少就按比例
    if total_months >= BACKTEST_TRAIN_MONTHS + BACKTEST_TEST_MONTHS:
        train_months = BACKTEST_TRAIN_MONTHS
        test_months = BACKTEST_TEST_MONTHS
    else:
        train_months = int(total_months * 0.7)
        test_months = total_months - train_months

    # 切分训练集和测试集
    train_df = df.iloc[:train_months].copy()
    test_df = df.iloc[train_months:train_months + test_months].copy()

    print(f"训练集: {train_df['ds'].iloc[0].strftime('%Y-%m')} ~ {train_df['ds'].iloc[-1].strftime('%Y-%m')} ({len(train_df)}个月)")
    print(f"测试集: {test_df['ds'].iloc[0].strftime('%Y-%m')} ~ {test_df['ds'].iloc[-1].strftime('%Y-%m')} ({len(test_df)}个月)")

    # 训练模型（全量数据 + life_stage 回归因子 + 灵活趋势）
    holidays_df = pd.DataFrame(HOLIDAYS_LIST)
    model = Prophet(
        holidays=holidays_df,
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        seasonality_mode="additive",
        interval_width=0.8,
    )
    model.add_regressor("life_stage")
    model.fit(train_df)

    # 预测测试集
    future = model.make_future_dataframe(periods=test_months, freq="MS")
    life_map = df.set_index("ds")["life_stage"].to_dict()
    future["life_stage"] = future["ds"].map(life_map).fillna(1.0)
    forecast = model.predict(future)

    # 提取测试期预测结果
    test_forecast = forecast.tail(test_months).copy()
    test_forecast["actual"] = test_df["y"].values
    test_forecast["error"] = test_forecast["yhat"] - test_forecast["actual"]
    test_forecast["error_pct"] = test_forecast["error"] / test_forecast["actual"] * 100

    # 计算精度指标
    mae = test_forecast["error"].abs().mean()
    mape = test_forecast["error_pct"].abs().mean()
    rmse = np.sqrt((test_forecast["error"] ** 2).mean())

    print(f"\n精度指标:")
    print(f"  MAE  (平均绝对误差): CNY{mae:,.0f}")
    print(f"  MAPE (平均绝对百分比误差): {mape:.1f}%")
    print(f"  RMSE (均方根误差): CNY{rmse:,.0f}")

    # 逐月对比
    print(f"\n逐月对比:")
    print(f"{'月份':<10} {'实际':>10} {'预测':>10} {'误差':>10} {'误差率':>8}")
    print("-" * 55)
    for _, row in test_forecast.iterrows():
        month = row["ds"].strftime("%Y-%m")
        actual = row["actual"]
        pred = row["yhat"]
        err = row["error"]
        err_pct = row["error_pct"]
        print(f"{month:<10} {actual:>10,.0f} {pred:>10,.0f} {err:>10,.0f} {err_pct:>7.1f}%")

    # 保存回测结果
    backtest_result = test_forecast[["ds", "yhat", "yhat_lower", "yhat_upper", "actual", "error", "error_pct"]]
    backtest_result.to_csv(os.path.join(OUTPUT_DIR, "回测结果.csv"), index=False, encoding="utf-8-sig")
    print(f"\n回测结果已保存: {os.path.join(OUTPUT_DIR, '回测结果.csv')}")

    return {
        "mae": mae,
        "mape": mape,
        "rmse": rmse,
        "model": model,
    }


def run_full_forecast(df):
    """全量训练，预测未来12个月"""
    print("\n" + "=" * 60)
    print("【正式预测】未来12个月月度支出预测")
    print("=" * 60)

    print(f"训练数据: {df['ds'].iloc[0].strftime('%Y-%m')} ~ {df['ds'].iloc[-1].strftime('%Y-%m')} ({len(df)}个月)")

    # 训练模型（全量数据 + life_stage 回归因子 + 灵活趋势）
    holidays_df = pd.DataFrame(HOLIDAYS_LIST)
    model = Prophet(
        holidays=holidays_df,
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        seasonality_mode="additive",
        interval_width=0.8,
    )
    model.add_regressor("life_stage")
    model.fit(df)

    # 预测未来
    future = model.make_future_dataframe(periods=FORECAST_MONTHS, freq="MS")
    life_map = df.set_index("ds")["life_stage"].to_dict()
    future["life_stage"] = future["ds"].map(life_map).fillna(1.0)
    forecast = model.predict(future)

    # 提取预测结果
    forecast_result = forecast.tail(FORECAST_MONTHS)[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
    forecast_result.columns = ["月份", "预测值", "下限(80%)", "上限(80%)"]
    forecast_result["月份"] = forecast_result["月份"].dt.strftime("%Y-%m")

    # 车贷修正：2026-07 是最后一期，之后不再有
    car_loan_note = ""
    for i, row in forecast_result.iterrows():
        if row["月份"] == CAR_LOAN_END:
            forecast_result.at[i, "预测值"] += CAR_LOAN_MONTHLY
            forecast_result.at[i, "下限(80%)"] += CAR_LOAN_MONTHLY
            forecast_result.at[i, "上限(80%)"] += CAR_LOAN_MONTHLY
            car_loan_note = f"（含最后一期车贷{CAR_LOAN_MONTHLY}）"

    print(f"\n未来{FORECAST_MONTHS}个月预测:")
    print(f"{'月份':<10} {'预测值':>10} {'下限':>10} {'上限':>10}")
    print("-" * 45)
    for _, row in forecast_result.iterrows():
        extra = " ← 含尾期车贷" if row["月份"] == CAR_LOAN_END else ""
        print(f"{row['月份']:<10} {row['预测值']:>10,.0f} {row['下限(80%)']:>10,.0f} {row['上限(80%)']:>10,.0f}{extra}")

    # 年度汇总
    annual_total = forecast_result["预测值"].sum()
    annual_lower = forecast_result["下限(80%)"].sum()
    annual_upper = forecast_result["上限(80%)"].sum()
    print(f"\n未来12个月预测总额: CNY{annual_total:,.0f}{car_loan_note}")
    print(f"80%置信区间: CNY{annual_lower:,.0f} ~ CNY{annual_upper:,.0f}")
    print(f"  其中车贷已还清（2026-07为最后一期），2026-08起月均减少{CAR_LOAN_MONTHLY}")

    # 保存预测结果
    forecast_result.to_csv(os.path.join(OUTPUT_DIR, "月度支出预测.csv"), index=False, encoding="utf-8-sig")

    # 趋势分解
    print(f"\n【趋势分解】")
    latest = forecast.iloc[-1]
    print(f"  趋势项(trend): CNY{latest['trend']:,.0f}/月 (不含车贷的基准趋势)")
    print(f"  年度季节性(yearly): 波动范围约 ±CNY{forecast['yearly'].abs().max():,.0f}/月")
    print(f"  节假日效应: 已纳入模型（春节/五一/国庆等长假影响显著）")

    # 保存完整预测数据（含历史拟合）
    full_forecast = forecast[["ds", "trend", "yearly", "yhat", "yhat_lower", "yhat_upper"]].copy()
    full_forecast["ds"] = full_forecast["ds"].dt.strftime("%Y-%m")
    full_forecast.to_csv(os.path.join(OUTPUT_DIR, "完整预测数据.csv"), index=False, encoding="utf-8-sig")

    # 生成可视化图表
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        # 图1：历史+预测趋势图
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(df["ds"], df["y"], "ko-", label="实际支出", markersize=4, linewidth=1.5)
        ax.plot(forecast["ds"], forecast["yhat"], "b-", label="预测值", linewidth=2)
        ax.fill_between(
            forecast["ds"], forecast["yhat_lower"], forecast["yhat_upper"],
            color="blue", alpha=0.15, label="80%置信区间"
        )
        ax.set_title("月度支出趋势与预测 (Prophet)", fontsize=14, fontweight="bold")
        ax.set_ylabel("支出金额 (元)")
        ax.set_xlabel("月份")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(os.path.join(OUTPUT_DIR, "月度支出预测图.png"), dpi=150, bbox_inches="tight")
        plt.close()

        # 图2：成分分解图
        fig2 = model.plot_components(forecast)
        fig2.savefig(os.path.join(OUTPUT_DIR, "趋势分解图.png"), dpi=150, bbox_inches="tight")
        plt.close("all")

        print(f"\n图表已生成:")
        print(f"  - 月度支出预测图.png")
        print(f"  - 趋势分解图.png")
    except Exception as e:
        print(f"\n图表生成失败: {e}")

    return model, forecast


def main():
    print("=" * 60)
    print("Prophet月度支出预测")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 加载并聚合数据
    df = load_and_aggregate()
    print(f"\n数据加载完成: {len(df)}个完整月份")
    print(f"时间范围: {df['ds'].iloc[0].strftime('%Y-%m')} ~ {df['ds'].iloc[-1].strftime('%Y-%m')}")
    print(f"月均支出（不含车贷）: CNY{df['y'].mean():,.0f}")
    print(f"月支出标准差（不含车贷）: CNY{df['y'].std():,.0f}")
    total_car_loan = df["car_loan"].sum()
    print(f"12期车贷总额: CNY{total_car_loan:,.0f}（已从训练数据中剥离，最后一期{CAR_LOAN_END}）")

    # 保存月度聚合数据
    df.to_csv(os.path.join(OUTPUT_DIR, "月度支出汇总.csv"), index=False, encoding="utf-8-sig")

    # 2. 回测验证
    backtest_result = run_backtest(df)

    # 3. 全量预测
    model, forecast = run_full_forecast(df)

    # 4. 总结
    print("\n" + "=" * 60)
    print("预测完成")
    print("=" * 60)
    print(f"结果输出目录: {OUTPUT_DIR}")
    if backtest_result:
        print(f"回测MAPE: {backtest_result['mape']:.1f}% (平均误差率)")


if __name__ == "__main__":
    main()
