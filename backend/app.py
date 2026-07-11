import json, os, sys, math, threading
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flask import Flask, jsonify, send_from_directory, request, session
from flask_cors import CORS

from config import FORECAST_FILE, MONTHLY_FILE, DATA_DIR, UPLOAD_DIR, V4_FILE, DB_PATH
from auth import login, check_token, require_auth, is_auth_configured
from utils import db, llm
db.set_db_path(DB_PATH)
from utils.query_engine import QueryEngine
from utils.data_loader import get_overview, get_spending, get_monthly_trend, get_category_detail, get_income_analysis, get_asset_history, get_portfolio, get_seasonal_patterns, get_budget_status, get_monthly_report, update_assets, update_budget, get_alerts, resolve_alert, get_goals, create_goal, update_goal, delete_goal, get_financial_health, get_comparison, get_annual_report, add_transaction, delete_transaction, get_quick_stats, pay_credit_card, get_credit_card_status, suggest_category, get_templates, create_template, delete_template, apply_template
from utils.pipeline import run_full_pipeline, run_forecast_only

app = Flask(__name__, static_folder=None)
CORS(app)
DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")

# ---- 认证中间件：拦截所有 /api/ 请求 ----
PUBLIC_API_ROUTES = {"/api/auth/login", "/api/auth/status", "/api/health"}


@app.before_request
def check_api_auth():
    """对所有 /api/ 路由强制认证（公开路由除外）"""
    if not request.path.startswith("/api/"):
        return None  # 非 API 请求放行
    if request.path in PUBLIC_API_ROUTES:
        return None  # 公开路由放行

    # 检查密码是否已配置
    from auth import _load_auth, check_token
    auth_data = _load_auth()
    if not auth_data or not auth_data.get("password_hash"):
        return None  # 未配置密码，放行（首次使用）

    # 检查 token
    token = request.headers.get("X-Auth-Token", "")
    if not token or not check_token(token):
        return jsonify({"error": "未认证，请先登录"}), 401

    return None


def serve_frontend(path="index.html"):
    file_path = os.path.join(DIST_DIR, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(DIST_DIR, path)
    # SPA fallback
    index_path = os.path.join(DIST_DIR, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(DIST_DIR, "index.html")
    return jsonify({"error": "frontend not built"}), 404


def load_json(path):
    if not os.path.exists(path):
        return None
    import csv
    rows = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def load_monthly_json():
    if not os.path.exists(MONTHLY_FILE):
        return None
    import csv
    rows = []
    with open(MONTHLY_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({"ds": row["ds"][:7], "y": round(float(row["y"]), 2)})
    return rows


# ---- API Routes ----

_query_engine = None
_conversations = defaultdict(list)  # session_id -> [{"role": ..., "content": ...}]
_conversation_lock = threading.Lock()

def get_query_engine():
    global _query_engine
    if _query_engine is None:
        from utils import data_loader as dl
        _query_engine = QueryEngine(dl)
    return _query_engine


@app.route("/api/query", methods=["POST"])
def api_query():
    data = request.get_json(force=True)
    question = data.get("question", "")
    session_id = data.get("session_id", "default")
    if not question:
        return jsonify({"answer": "请说点什么", "intent": "help"})

    # Get conversation history
    with _conversation_lock:
        history = list(_conversations[session_id])

    engine = get_query_engine()
    answer = engine.answer(question, history=history)

    # Append to history
    with _conversation_lock:
        _conversations[session_id].append({"role": "user", "content": question})
        _conversations[session_id].append({"role": "assistant", "content": answer})
        # Keep last 20 messages (10 turns)
        if len(_conversations[session_id]) > 20:
            _conversations[session_id] = _conversations[session_id][-20:]

    return jsonify({"answer": answer})


@app.route("/api/query/clear", methods=["POST"])
def api_query_clear():
    data = request.get_json(force=True)
    session_id = data.get("session_id", "default")
    with _conversation_lock:
        _conversations.pop(session_id, None)
    return jsonify({"status": "ok"})


@app.route("/api/overview")
def api_overview():
    return jsonify(get_overview())


@app.route("/api/quick-stats")
def api_quick_stats():
    return jsonify(get_quick_stats())


@app.route("/api/transaction", methods=["POST"])
def api_add_transaction():
    data = request.get_json(force=True)
    amount = data.get("amount")
    category = data.get("category")
    note = data.get("note", "")
    tx_type = data.get("type", "支出")
    date = data.get("date")
    account = data.get("account", "")

    if not amount or not category:
        return jsonify({"error": "金额和分类必填"}), 400

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "金额必须是有效数字"}), 400

    result = add_transaction(amount, category, note, tx_type, date, account)
    return jsonify(result)


@app.route("/api/analysis/current")
def api_current_analysis():
    """获取当前月分析（不创建交易记录）"""
    from utils.data_loader import _load_transactions, _load_budget_config
    from datetime import datetime
    month_str = datetime.now().strftime("%Y-%m")

    transactions = _load_transactions()
    month_txs = [t for t in transactions if t["date"][:7] == month_str]

    # 区分支出和收入
    total_expense = sum(float(t["amount"]) for t in month_txs if t["type"] != "收入")
    total_income = sum(float(t["amount"]) for t in month_txs if t["type"] == "收入")

    # 分类汇总
    expense_by_category = {}
    for t in month_txs:
        if t["type"] != "收入":
            cat = t["category"]
            expense_by_category[cat] = expense_by_category.get(cat, 0) + float(t["amount"])

    # 预算对比
    budget_config = _load_budget_config()
    budget_status = []
    for cat, budget in budget_config.items():
        if budget <= 0:
            continue
        spent = expense_by_category.get(cat, 0)
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
    balance = total_income - total_expense

    suggestions = []
    if total_income > 0:
        suggestions.append(f"💰 本月已记录收入 ¥{total_income:,.0f}")

    # 预算超支建议
    over_budget = [b for b in budget_status if b["ratio"] > 100]
    warn_budget = [b for b in budget_status if 80 <= b["ratio"] <= 100]
    if over_budget:
        for b in over_budget:
            over_amount = b["spent"] - b["budget"]
            suggestions.append(f"⚠️ {b['category']}已超支{b['ratio']:.0f}%（¥{b['spent']:,.0f}/¥{b['budget']:,.0f}），超支¥{over_amount:,.0f}")
    if warn_budget:
        for b in warn_budget:
            suggestions.append(f"⚡ {b['category']}接近上限{b['ratio']:.0f}%，剩余¥{b['remaining']:,.0f}")

    if balance >= 0 and total_income > 0:
        savings_rate = round(balance / total_income * 100, 1)
        suggestions.append(f"✅ 本月结余 ¥{balance:,.0f}（储蓄率 {savings_rate}%）")
    elif balance < 0 and total_income > 0:
        suggestions.append(f"🔴 本月超支 ¥{abs(balance):,.0f}")

    return jsonify({
        "month_summary": {
            "month": month_str,
            "total_expense": round(total_expense, 2),
            "total_income": round(total_income, 2),
            "balance": round(balance, 2),
            "count": len(month_txs),
            "expense_by_category": {k: round(v, 2) for k, v in sorted(expense_by_category.items(), key=lambda x: -x[1])},
        },
        "budget": {
            "total_budget": total_budget,
            "total_spent": round(total_expense, 2),
            "total_remaining": round(max(total_budget - total_expense, 0), 2),
            "total_ratio": round(total_expense / total_budget * 100, 1) if total_budget else 0,
            "items": sorted(budget_status, key=lambda x: -x["ratio"]),
        },
        "suggestions": suggestions,
    })


@app.route("/api/accounts")
def api_list_accounts():
    from utils.data_loader import DEFAULT_ACCOUNTS, _load_transactions
    txs = _load_transactions()
    used = list(set(t.get("account", "") for t in txs if t.get("account")))
    accounts = list(dict.fromkeys(DEFAULT_ACCOUNTS + used))
    return jsonify(accounts)


@app.route("/api/suggest-category")
def api_suggest_category():
    """根据输入文本推荐分类"""
    text = request.args.get("text", "")
    suggestions = suggest_category(text)
    return jsonify(suggestions)


@app.route("/api/credit-card")
def api_credit_card():
    return jsonify(get_credit_card_status())


@app.route("/api/credit-card/pay", methods=["POST"])
def api_pay_credit_card():
    data = request.get_json(force=True)
    amount = data.get("amount")
    account = data.get("account", "招行储蓄卡")
    if not amount:
        return jsonify({"error": "还款金额必填"}), 400
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "金额必须是有效数字"}), 400
    result = pay_credit_card(amount, account)
    return jsonify(result)


@app.route("/api/transactions")
def api_list_transactions():
    from utils.data_loader import _load_transactions
    month = request.args.get("month")
    txs = _load_transactions()
    if month:
        txs = [t for t in txs if t["date"][:7] == month]
    # 按日期倒序，附带原始索引
    txs.sort(key=lambda t: t["date"], reverse=True)
    return jsonify(txs)


@app.route("/api/transaction/<int:tx_id>", methods=["DELETE"])
def api_delete_transaction(tx_id):
    result = delete_transaction(tx_id)
    if result.get("success"):
        return jsonify(result)
    return jsonify(result), 404


@app.route("/api/health")
def api_health():
    return jsonify(get_financial_health())


@app.route("/api/comparison")
def api_comparison():
    year = request.args.get("year", "2026")
    month = request.args.get("month", "07")
    return jsonify(get_comparison(year, month))


@app.route("/api/spending")
def api_spending():
    year = request.args.get("year", "all")
    return jsonify(get_spending(year))


@app.route("/api/spending/<category>")
def api_spending_detail(category):
    year = request.args.get("year", "all")
    return jsonify(get_category_detail(category, year))


@app.route("/api/monthly")
def api_monthly():
    return jsonify(get_monthly_trend())


@app.route("/api/income")
def api_income():
    return jsonify(get_income_analysis())


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "请选择文件"}), 400
    f = request.files["file"]
    if not f.filename.endswith(".csv"):
        return jsonify({"error": "仅支持 CSV 文件"}), 400
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(UPLOAD_DIR, f"raw_{ts}.csv")
    f.save(path)
    import csv
    with open(path, "r", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    # Run full pipeline: merge → DB sync → forecast refresh
    pipeline_result = run_full_pipeline(path)

    return jsonify({
        "status": "ok",
        "filename": f.filename,
        "records": len(rows),
        "saved_as": f"raw_{ts}.csv",
        "pipeline": pipeline_result,
    })


@app.route("/api/forecast")
def api_forecast():
    data = load_json(FORECAST_FILE)
    if data is None:
        return jsonify({"error": "未生成预测结果，请先运行 prophet_forecast.py"}), 404
    result = []
    for r in data:
        result.append({
            "month": r["月份"],
            "prediction": round(float(r["预测值"]), 2),
            "lower": round(float(r["下限(80%)"]), 2),
            "upper": round(float(r["上限(80%)"]), 2),
        })
    total = sum(item["prediction"] for item in result)
    return jsonify({"data": result, "annual_total": round(total, 2)})


@app.route("/api/history")
def api_history():
    data = load_monthly_json()
    if data is None:
        return jsonify([])
    return jsonify(data)


@app.route("/api/assets", methods=["GET", "PUT"])
def api_assets():
    if request.method == "PUT":
        data = request.get_json(force=True)
        update_assets(data)
        return jsonify({"status": "ok"})
    return jsonify(get_overview())


@app.route("/api/assets/history")
def api_asset_history():
    return jsonify(get_asset_history())


@app.route("/api/assets/backfill", methods=["POST"])
def api_backfill_assets():
    from utils.data_loader import backfill_asset_history
    result = backfill_asset_history()
    return jsonify(result)


@app.route("/api/forecast/refresh", methods=["POST"])
def api_refresh_forecast():
    result = run_forecast_only()
    return jsonify(result)


@app.route("/api/portfolio")
def api_portfolio():
    return jsonify(get_portfolio())


@app.route("/api/spending/seasonal")
def api_seasonal():
    return jsonify(get_seasonal_patterns())


@app.route("/api/budget", methods=["GET", "PUT"])
def api_budget():
    if request.method == "PUT":
        data = request.get_json(force=True)
        update_budget(data)
        return jsonify({"status": "ok"})
    month = request.args.get("month")
    return jsonify(get_budget_status(month))


@app.route("/api/report/monthly")
def api_monthly_report():
    month = request.args.get("month")
    return jsonify(get_monthly_report(month))


@app.route("/api/report/annual")
def api_annual_report():
    year = request.args.get("year")
    return jsonify(get_annual_report(year))


@app.route("/api/forecast/backtest")
def api_forecast_backtest():
    from utils.data_loader import get_forecast_backtest
    return jsonify(get_forecast_backtest())


@app.route("/api/budget/check", methods=["POST"])
def api_budget_check():
    """Real-time budget overspend check for a category + amount."""
    data = request.get_json(force=True)
    category = data.get("category", "")
    amount = float(data.get("amount", 0))
    month = data.get("month")
    if not month:
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")

    bd = get_budget_status(month)
    for item in bd["items"]:
        if item["category"] == category:
            new_ratio = (item["actual"] + amount) / item["budget"] * 100 if item["budget"] else 0
            return jsonify({
                "category": category,
                "current_actual": float(item["actual"]),
                "budget": float(item["budget"]),
                "current_ratio": float(item["ratio"]),
                "new_ratio": round(float(new_ratio), 1),
                "would_overspend": bool(new_ratio >= 100),
                "would_warn": bool(new_ratio >= 80),
            })
    return jsonify({"category": category, "budget": 0, "would_overspend": False, "would_warn": False})


def _monthly_income():
    return 16000 + 10610 / 3


def _forward_project(balance, monthly_net, annual_rate, years):
    projection = []
    for y in range(1, years + 1):
        for _ in range(12):
            balance += monthly_net
            balance *= (1 + annual_rate / 100 / 12)
        projection.append({"year": y, "net_worth": round(balance, 2)})
    return projection, round(balance, 2)


@app.route("/api/simulation")
def api_simulation():
    expense_str = request.args.get("expense", "9622")
    rate_str = request.args.get("rate", "5")
    years_str = request.args.get("years", "10")

    monthly_expense = float(expense_str)
    annual_rate = float(rate_str)
    years = int(years_str)
    monthly_income = _monthly_income()
    monthly_net = monthly_income - monthly_expense

    overview = get_overview()
    balance = overview["net_worth"]
    projection, final = _forward_project(balance, monthly_net, annual_rate, years)

    return jsonify({
        "monthly_income": round(monthly_income, 2),
        "monthly_expense": monthly_expense,
        "monthly_net": round(monthly_net, 2),
        "initial_net_worth": overview["net_worth"],
        "projection": projection,
        "final_net_worth": final,
    })


# ---- Reverse Calculation（目标→所需参数） ----

def _pmt_needed(fv, pv, r, n):
    """每月需存入金额（r 为月利率）"""
    if r == 0:
        return (fv - pv) / n
    return (fv - pv * (1 + r) ** n) * r / ((1 + r) ** n - 1)


def _nper_needed(fv, pv, pmt, r):
    """达到目标需要的月数（r 为月利率）"""
    if pmt < 0:
        return 0
    if r == 0:
        return (fv - pv) / pmt if pmt > 0 else 0
    return math.log((fv * r + pmt) / (pv * r + pmt)) / math.log(1 + r)


def _rate_needed(fv, pv, pmt, n, guess=0.005):
    """用牛顿法求解月利率"""
    r = guess
    for _ in range(100):
        f = pv * (1 + r) ** n + pmt * ((1 + r) ** n - 1) / r - fv
        df = n * pv * (1 + r) ** (n - 1) + pmt * (n * r * (1 + r) ** (n - 1) - (1 + r) ** n + 1) / (r * r)
        if abs(df) < 1e-12:
            break
        r_new = r - f / df
        if abs(r_new - r) < 1e-10:
            break
        r = r_new
    return r


@app.route("/api/calculate/target")
def api_calc_target():
    """给定目标金额、年数、年化 → 每月需存多少"""
    target = float(request.args.get("target", "500000"))
    years = int(request.args.get("years", "10"))
    rate = float(request.args.get("rate", "5"))
    overview = get_overview()

    pv = overview["net_worth"]
    n = years * 12
    r = rate / 100 / 12
    pmt = _pmt_needed(target, pv, r, n)

    # 也给出对应的月支出
    monthly_income = _monthly_income()
    return jsonify({
        "target": round(target, 2),
        "years": years,
        "annual_rate": rate,
        "current_net_worth": round(pv, 2),
        "required_monthly_save": round(pmt, 2),
        "implied_monthly_expense": round(monthly_income - pmt, 2),
    })


@app.route("/api/calculate/years")
def api_calc_years():
    """给定目标金额、月存、年化 → 需要多少年"""
    target = float(request.args.get("target", "500000"))
    monthly_save = float(request.args.get("save", "8000"))
    rate = float(request.args.get("rate", "5"))
    overview = get_overview()

    pv = overview["net_worth"]
    r = rate / 100 / 12
    n = _nper_needed(target, pv, monthly_save, r)
    return jsonify({
        "target": round(target, 2),
        "monthly_save": monthly_save,
        "annual_rate": rate,
        "current_net_worth": round(pv, 2),
        "years": round(n / 12, 1),
        "months": round(n),
    })


@app.route("/api/calculate/rate")
def api_calc_rate():
    """给定目标金额、月存、年数 → 需要多高的年化收益"""
    target = float(request.args.get("target", "500000"))
    monthly_save = float(request.args.get("save", "8000"))
    years = int(request.args.get("years", "10"))
    overview = get_overview()

    pv = overview["net_worth"]
    n = years * 12
    r = _rate_needed(target, pv, monthly_save, n)
    return jsonify({
        "target": round(target, 2),
        "monthly_save": monthly_save,
        "years": years,
        "current_net_worth": round(pv, 2),
        "annual_rate": round(r * 12 * 100, 2),
    })


# ---- DB Migration ----

# ---- LLM Config ----

@app.route("/api/llm/config", methods=["GET", "POST"])
def api_llm_config():
    if request.method == "POST":
        data = request.get_json(force=True)
        llm.save_config({
            "api_key": data.get("api_key", ""),
            "base_url": data.get("base_url", "https://api.deepseek.com"),
            "model": data.get("model", "deepseek-v4-flash"),
        })
        return jsonify({"success": True})
    cfg = llm.load_config()
    return jsonify({
        "configured": bool(cfg.get("api_key")),
        "base_url": cfg.get("base_url", ""),
        "model": cfg.get("model", ""),
    })


@app.route("/api/db/status")
def api_db_status():
    return jsonify({
        "migrated": db.is_migrated(),
        "stats": db.get_table_stats() if db.is_migrated() else None,
    })


@app.route("/api/db/migrate", methods=["POST"])
def api_db_migrate():
    from config import V4_FILE
    try:
        db.init_db()
        count = db.migrate_from_csv(V4_FILE)
        stats = db.get_table_stats()
        return jsonify({"success": True, "records": count, "stats": stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/db/rollback", methods=["POST"])
def api_db_rollback():
    import os
    if DB_PATH and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "no database to rollback"}), 400


# ---- Alerts ----

@app.route("/api/alerts")
def api_alerts():
    return jsonify(get_alerts())


@app.route("/api/alerts/poll")
def api_poll_alerts():
    """Frontend polls this to check for new unresolved alerts."""
    from utils.data_loader import get_alerts
    alerts = get_alerts()
    unresolved = [a for a in alerts if not a.get("resolved")]
    return jsonify({"new_count": len(unresolved), "alerts": unresolved})


@app.route("/api/alerts/<alert_id>/resolve", methods=["POST"])
def api_resolve_alert(alert_id):
    return jsonify(resolve_alert(alert_id))


# ---- Goals ----

@app.route("/api/goals", methods=["GET", "POST"])
def api_goals():
    if request.method == "POST":
        data = request.get_json(force=True)
        return jsonify(create_goal(data))
    return jsonify(get_goals())


@app.route("/api/goals/<goal_id>", methods=["PUT", "DELETE"])
def api_goal_detail(goal_id):
    if request.method == "DELETE":
        return jsonify(delete_goal(goal_id))
    data = request.get_json(force=True)
    return jsonify(update_goal(goal_id, data))


# ---- Templates ----

@app.route("/api/templates", methods=["GET", "POST"])
def api_templates():
    if request.method == "GET":
        return jsonify(get_templates())
    # POST - 创建模板
    data = request.get_json(force=True)
    name = data.get("name")
    amount = data.get("amount")
    category = data.get("category")
    if not name or not amount or not category:
        return jsonify({"error": "名称、金额、分类必填"}), 400
    result = create_template(
        name=name, amount=float(amount), category=category,
        tx_type=data.get("type", "支出"), account=data.get("account", ""),
        note=data.get("note", ""), frequency=data.get("frequency", "monthly")
    )
    return jsonify(result)


@app.route("/api/templates/<template_id>", methods=["DELETE"])
def api_delete_template(template_id):
    result = delete_template(template_id)
    return jsonify(result)


@app.route("/api/templates/<template_id>/apply", methods=["POST"])
def api_apply_template(template_id):
    result = apply_template(template_id)
    return jsonify(result)


# ---- Auth ----

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    pwd = data.get("password", "")
    client_ip = request.remote_addr or "unknown"
    token, error = login(pwd, ip=client_ip)
    if token:
        return jsonify({"token": token})
    return jsonify({"error": error or "密码错误"}), 401


@app.route("/api/auth/status")
def api_auth_status():
    if not is_auth_configured():
        return jsonify({"authenticated": True, "configurable": False})
    token = request.headers.get("X-Auth-Token", "")
    if not token:
        return jsonify({"authenticated": False, "configurable": True})
    return jsonify({"authenticated": check_token(token), "configurable": True})


# ---- Serve frontend ----

@app.route("/")
def index():
    return serve_frontend("index.html")


@app.route("/<path:path>")
def static_proxy(path):
    if path.startswith("api/"):
        return jsonify({"error": "not found"}), 404
    return serve_frontend(path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Server starting at http://localhost:{port}")
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
