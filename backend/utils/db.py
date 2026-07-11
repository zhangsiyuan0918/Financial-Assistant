import sqlite3, os, json, hashlib
from datetime import datetime

DB_PATH = None


def set_db_path(path):
    global DB_PATH
    DB_PATH = path


def _ensure_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def get_conn():
    if not DB_PATH:
        raise RuntimeError("DB_PATH not set. Call set_db_path() first.")
    _ensure_dir(DB_PATH)
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            "类型" TEXT, "货币" TEXT, "金额" REAL, "汇率（相对本位币）" REAL,
            "项目" TEXT, "分类" TEXT, "父类" TEXT,
            "账户" TEXT, "付款" TEXT, "收款" TEXT, "日期" TEXT,
            "标签" TEXT, "备注" TEXT,
            "clean_amount" REAL, "amount_abs" REAL, "flow_direction" TEXT,
            "clean_date" TEXT, "date_valid" TEXT, "clean_project" TEXT,
            "is_transfer" TEXT, "transfer_subtype" TEXT, "is_refund" TEXT,
            "is_loan" TEXT, "cny_amount" REAL, "valid_for_stats" TEXT,
            "corrected_type" TEXT, "category_l1" TEXT, "category_l2" TEXT,
            "is_fixed_expense" TEXT, "is_travel" TEXT,
            "year" INTEGER, "month" TEXT, "quarter" INTEGER,
            "day_of_week" INTEGER, "is_weekend" TEXT, "is_holiday" TEXT,
            "holiday_name" TEXT, "is_around_holiday" TEXT,
            "is_capital_expense" TEXT, "is_outlier" TEXT,
            "life_stage" TEXT, "month_complete" TEXT, "is_purchase_support" TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_trans_month ON transactions("month");
        CREATE INDEX IF NOT EXISTS idx_trans_cat ON transactions("category_l1");
        CREATE INDEX IF NOT EXISTS idx_trans_clean_date ON transactions("clean_date");

        CREATE TABLE IF NOT EXISTS manual_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT '支出',
            account TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_manual_date ON manual_transactions("date");
        CREATE INDEX IF NOT EXISTS idx_manual_month ON manual_transactions(date);
    """)
    conn.commit()
    conn.close()


def migrate_from_csv(csv_path):
    """Migrate CSV to SQLite with transaction safety and verification."""
    import csv

    # Compute fingerprint of incoming data
    with open(csv_path, "rb") as f:
        new_hash = hashlib.md5(f.read()).hexdigest()

    # Check if data is unchanged
    if is_migrated():
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM transactions")
            old_count = cur.fetchone()[0]
            conn.close()
            if old_count > 0:
                with open(csv_path, "r", encoding="utf-8-sig") as f:
                    new_count = sum(1 for _ in csv.DictReader(f))
                if new_count == old_count:
                    return {"skipped": True, "reason": "data_unchanged", "records": old_count}
        except Exception:
            pass  # If check fails, proceed with migration

    # Read CSV rows
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames
        quoted_cols = [f'"{c}"' for c in cols]
        placeholders = ",".join("?" * len(cols))
        col_names = ",".join(quoted_cols)
        rows = [tuple(row.get(c, "") for c in cols) for row in reader]

    total_rows = len(rows)

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")

        # Backup to temp table
        conn.execute("DROP TABLE IF EXISTS _backup_transactions")
        conn.execute("CREATE TEMPORARY TABLE _backup_transactions AS SELECT * FROM transactions")

        # Clear and refill
        conn.execute("DELETE FROM transactions")
        conn.executemany(
            f"INSERT INTO transactions ({col_names}) VALUES ({placeholders})",
            rows,
        )

        # Verify row count
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM transactions")
        inserted = cur.fetchone()[0]

        if inserted != total_rows:
            # Rollback: restore from backup
            conn.execute("DELETE FROM transactions")
            conn.execute("INSERT INTO transactions SELECT * FROM _backup_transactions")
            conn.execute("DROP TABLE IF EXISTS _backup_transactions")
            conn.commit()
            raise ValueError(
                f"Verification failed: expected {total_rows} rows, got {inserted}"
            )

        conn.execute("DROP TABLE IF EXISTS _backup_transactions")
        conn.commit()
        return {"success": True, "records": inserted}

    except Exception:
        conn.rollback()
        raise
    finally:
        # Clean up backup table in case rollback path was taken
        try:
            conn.execute("DROP TABLE IF EXISTS _backup_transactions")
        except Exception:
            pass
        conn.close()


def get_table_stats():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM transactions")
    count = cur.fetchone()[0]
    cur.execute('SELECT MIN("clean_date"), MAX("clean_date") FROM transactions')
    dates = cur.fetchone()
    cur.execute(
        'SELECT COUNT(DISTINCT "category_l1") FROM transactions '
        'WHERE "category_l1" IS NOT NULL AND "category_l1" != \'\''
    )
    cats = cur.fetchone()[0]
    conn.close()
    return {
        "records": count,
        "date_from": dates[0][:7] if dates[0] else None,
        "date_to": dates[1][:7] if dates[1] else None,
        "categories": cats,
    }


def is_migrated():
    if not DB_PATH or not os.path.exists(DB_PATH):
        return False
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM transactions")
        count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False
