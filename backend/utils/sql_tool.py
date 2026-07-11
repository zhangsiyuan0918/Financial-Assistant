"""
Safe read-only SQL execution tool for LLM query augmentation.
Only allows SELECT queries; blocks all mutation operations.
"""

import sqlite3, json
from config import DB_PATH
from utils import db

db.set_db_path(DB_PATH)

_TABLE_SCHEMA = """
transactions table columns:
- clean_date (TEXT, YYYY-MM-DD), cny_amount (REAL), category_l1 (TEXT, e.g. 餐饮/交通/购物)
- corrected_type (TEXT, '收入' or '支出'), clean_project (TEXT, description)
- month (TEXT, YYYY-MM), year (INTEGER), quarter (INTEGER)
- is_outlier (TEXT, 'True'/'False'), valid_for_stats (TEXT, 'True'/'False')
- category_l2 (TEXT, sub-category), is_fixed_expense (TEXT)
- life_stage (TEXT, 'pre_car'/'post_car')
"""

_FORBIDDEN_KEYWORDS = {"DELETE", "INSERT", "UPDATE", "DROP", "ALTER", "CREATE", "TRUNCATE", "EXEC", "EXECUTE"}


def get_schema_description():
    """Return table schema for LLM context."""
    return _TABLE_SCHEMA


def query_sql(sql):
    """
    Execute a read-only SQL query and return results as JSON.
    Returns error string if query is invalid or forbidden.
    """
    sql = sql.strip().rstrip(";")

    # Safety checks
    sql_upper = sql.upper()
    if not sql_upper.startswith("SELECT"):
        return json.dumps({"error": "只允许 SELECT 查询"}, ensure_ascii=False)

    for kw in _FORBIDDEN_KEYWORDS:
        if kw in sql_upper:
            return json.dumps({"error": f"不允许 {kw} 操作"}, ensure_ascii=False)

    # Limit result size
    if "LIMIT" not in sql_upper:
        sql += " LIMIT 100"

    try:
        conn = db.get_conn()
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        conn.close()

        result = [dict(zip(columns, row)) for row in rows]
        # Convert non-serializable types
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": f"SQL 执行失败: {str(e)}"}, ensure_ascii=False)
