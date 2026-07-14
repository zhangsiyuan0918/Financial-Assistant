import json, os, sys, threading
from datetime import datetime
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

from config import DATA_DIR, UPLOAD_DIR, V4_FILE, DB_PATH
from auth import login, check_token, is_auth_configured
from utils import db, llm
db.set_db_path(DB_PATH)
from utils.query_engine import QueryEngine
from utils.data_loader import (
    load_v4, get_budget_status, update_budget, add_transaction,
    suggest_category, get_overview, get_financial_health, get_spending,
    get_monthly_trend, backfill_asset_history, _invalidate_all_cache,
    clear_request_cache, _load_budget_config, get_portfolio,
)
from utils.pipeline import run_full_pipeline

app = Flask(__name__, static_folder=None)
CORS(app)
DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")

# ---- 认证中间件 ----
PUBLIC_API_ROUTES = {"/api/auth/login", "/api/auth/status", "/api/health"}


@app.before_request
def check_api_auth():
    if not request.path.startswith("/api/"):
        return None
    if request.path in PUBLIC_API_ROUTES:
        return None
    from auth import _load_auth
    auth_data = _load_auth()
    if not auth_data or not auth_data.get("password_hash"):
        return None
    token = request.headers.get("X-Auth-Token", "")
    if not token or not check_token(token):
        return jsonify({"error": "未认证，请先登录"}), 401
    return None


def serve_frontend(path="index.html"):
    file_path = os.path.join(DIST_DIR, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(DIST_DIR, path)
    index_path = os.path.join(DIST_DIR, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(DIST_DIR, "index.html")
    return jsonify({"error": "frontend not built"}), 404


# ---- AI 对话 ----
_query_engine = None
_conversations = defaultdict(list)
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

    with _conversation_lock:
        history = list(_conversations[session_id])

    engine = get_query_engine()
    answer = engine.answer(question, history=history)

    with _conversation_lock:
        _conversations[session_id].append({"role": "user", "content": question})
        _conversations[session_id].append({"role": "assistant", "content": answer})
        if len(_conversations[session_id]) > 20:
            _conversations[session_id] = _conversations[session_id][-20:]

    return jsonify({"answer": answer})


# ---- 账户列表 ----
@app.route("/api/accounts")
def api_list_accounts():
    from utils.transactions import DEFAULT_ACCOUNTS, _load_transactions
    txs = _load_transactions()
    used = list(set(t.get("account", "") for t in txs if t.get("account")))
    accounts = list(dict.fromkeys(DEFAULT_ACCOUNTS + used))
    return jsonify(accounts)


# ---- 记账 ----
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


# ---- 智能分类 ----
@app.route("/api/suggest-category")
def api_suggest_category():
    text = request.args.get("text", "")
    suggestions = suggest_category(text)
    return jsonify(suggestions)


# ---- 预算 ----
@app.route("/api/budget", methods=["GET", "PUT"])
def api_budget():
    if request.method == "PUT":
        data = request.get_json(force=True)
        update_budget(data)
        return jsonify({"status": "ok"})
    month = request.args.get("month")
    return jsonify(get_budget_status(month))


# ---- LLM 配置 ----
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


# ---- 数据管理 ----
@app.route("/api/db/status")
def api_db_status():
    return jsonify({
        "migrated": db.is_migrated(),
        "stats": db.get_table_stats() if db.is_migrated() else None,
    })


@app.route("/api/db/migrate", methods=["POST"])
def api_db_migrate():
    try:
        db.init_db()
        count = db.migrate_from_csv(V4_FILE)
        stats = db.get_table_stats()
        _invalidate_all_cache()
        return jsonify({"success": True, "records": count, "stats": stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/db/rollback", methods=["POST"])
def api_db_rollback():
    import os
    if DB_PATH and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        _invalidate_all_cache()
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "no database to rollback"}), 400


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "请选择文件"}), 400
    f = request.files["file"]
    if not f.filename.endswith(".csv"):
        return jsonify({"error": "仅支持 CSV 文件"}), 400
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    from datetime import datetime as dt
    ts = dt.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(UPLOAD_DIR, f"raw_{ts}.csv")
    f.save(path)
    import csv
    with open(path, "r", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    pipeline_result = run_full_pipeline(path)
    _invalidate_all_cache()
    return jsonify({
        "status": "ok",
        "filename": f.filename,
        "records": len(rows),
        "saved_as": f"raw_{ts}.csv",
        "pipeline": pipeline_result,
    })


@app.route("/api/assets/backfill", methods=["POST"])
def api_backfill_assets():
    result = backfill_asset_history()
    return jsonify(result)


# ---- AI 洞察 ----
@app.route("/api/insights")
def api_insights():
    from utils.ai_engine import get_unread_insights
    return jsonify(get_unread_insights())


@app.route("/api/insights/read", methods=["POST"])
def api_mark_insight_read():
    data = request.get_json(force=True)
    insight_id = data.get("id")
    if not insight_id:
        return jsonify({"error": "id required"}), 400
    from utils.ai_engine import mark_insight_read
    mark_insight_read(insight_id)
    return jsonify({"status": "ok"})


@app.route("/api/insights/generate", methods=["POST"])
def api_generate_insight():
    data = request.get_json(force=True) or {}
    insight_type = data.get("type", "daily")
    from utils.ai_engine import generate_daily_insight, generate_weekly_report
    if insight_type == "weekly":
        content = generate_weekly_report()
    else:
        content = generate_daily_insight()
    return jsonify({"content": content})


@app.route("/api/daily-digest")
def api_daily_digest():
    from utils.ai_engine import get_unread_insights
    insights = get_unread_insights()
    return jsonify({"insights": insights, "count": len(insights)})


# ---- 健康检查 ----
@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


@app.route("/api/health/detail")
def api_health_detail():
    return jsonify(get_financial_health())


@app.route("/api/portfolio")
def api_portfolio():
    from utils.data_loader import get_portfolio
    return jsonify(get_portfolio())


@app.route("/api/overview")
def api_overview():
    return jsonify(get_overview())


@app.route("/api/monthly")
def api_monthly():
    return jsonify(get_monthly_trend())


@app.route("/api/credit-card")
def api_credit_card():
    from utils.transactions import get_credit_card_status
    return jsonify(get_credit_card_status())


@app.route("/api/credit-card/pay", methods=["POST"])
def api_pay_credit_card():
    from utils.transactions import pay_credit_card
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


# ---- 认证 ----
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


# ---- 定时任务 ----
import time as _time


def _scheduled_task_runner():
    last_daily = None
    last_weekly = None
    while True:
        try:
            now = datetime.now()
            today = now.date()
            if now.hour == 23 and last_daily != today:
                print("[scheduler] Generating daily insight...")
                from utils.ai_engine import generate_daily_insight
                generate_daily_insight()
                last_daily = today
                print("[scheduler] Daily insight generated")
            if now.weekday() == 6 and now.hour == 23 and now.minute >= 5 and last_weekly != today:
                print("[scheduler] Generating weekly report...")
                from utils.ai_engine import generate_weekly_report
                generate_weekly_report()
                last_weekly = today
                print("[scheduler] Weekly report generated")
        except Exception as e:
            print(f"[scheduler] Error: {e}")
        _time.sleep(60)


_scheduler_thread = threading.Thread(target=_scheduled_task_runner, daemon=True)
_scheduler_thread.start()
print("[scheduler] Background task scheduler started")


# ---- 前端路由 ----
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
