"""
data_loader.py — Facade（门面）
此文件仅做 re-export，保证 app.py 和 query_engine.py 的 import 不需要改动。
"""

# ---- 基础设施 + 数据加载 ----
from utils.data_core import (
    load_v4,
    load_unified,
    clear_request_cache,
    _invalidate_unified_cache,
    _invalidate_all_cache,
    _atomic_write,
    _file_locks,
)

# ---- 资产管理 ----
from utils.assets import (
    get_overview,
    get_asset_history,
    get_portfolio,
    update_assets,
    backfill_asset_history,
    flatten_assets,
    _load_asset_config,
    _save_asset_config,
)

# ---- 预算 ----
from utils.budget import (
    get_budget_status,
    update_budget,
    _load_budget_config,
    _save_budget_config,
)

# ---- 消费分析 ----
from utils.spending import (
    get_spending,
    get_monthly_trend,
    get_category_detail,
    get_income_analysis,
    get_seasonal_patterns,
)

# ---- 报告 ----
from utils.reports import (
    get_monthly_report,
    get_annual_report,
    get_financial_health,
    get_comparison,
)

# ---- 实时记账 + 信用卡 ----
from utils.transactions import (
    add_transaction,
    delete_transaction,
    get_quick_stats,
    add_credit_card_expense,
    pay_credit_card,
    get_credit_card_status,
    _load_transactions,
    _load_credit_card,
    _update_account_balance,
    _reverse_credit_card_expense,
    _analyze_after_transaction,
    _lightweight_overview,
    DEFAULT_ACCOUNTS,
)

# ---- 智能分类 ----
from utils.smart_category import (
    suggest_category,
    get_category_stats,
    _PRESET_CATEGORY_MAP,
    _build_keyword_category_map,
)
