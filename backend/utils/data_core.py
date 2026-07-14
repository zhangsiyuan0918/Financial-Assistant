"""基础设施 + 数据加载：缓存、锁、原子写入、CSV/SQLite 加载"""
import csv
import json
import os
import threading

import pandas as pd

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import V4_FILE, DB_PATH
from utils import db

db.set_db_path(DB_PATH)

# ---- 共享 DataFrame 缓存 ----
_df_v4_cache = None
_df_unified_cache = None


def clear_request_cache():
    global _df_v4_cache, _df_unified_cache
    _df_v4_cache = None
    _df_unified_cache = None


def _invalidate_unified_cache():
    global _df_unified_cache
    _df_unified_cache = None


def _invalidate_all_cache():
    global _df_v4_cache, _df_unified_cache
    _df_v4_cache = None
    _df_unified_cache = None


# ---- 文件锁 ----
_file_locks = {
    "asset": threading.Lock(),
    "credit_card": threading.Lock(),
    "budget": threading.Lock(),
    "goals": threading.Lock(),
    "alerts": threading.Lock(),
}


def _atomic_write(filepath, data):
    """原子写入：先写临时文件，再重命名"""
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if os.path.exists(filepath):
        os.replace(tmp, filepath)
    else:
        os.rename(tmp, filepath)


# ---- 数据加载 ----

def _deduplicate(df):
    before = len(df)
    dedup_cols = ["clean_date", "cny_amount", "clean_project"]
    existing = [c for c in dedup_cols if c in df.columns]
    if existing:
        df = df.drop_duplicates(subset=existing, keep="first")
    removed = before - len(df)
    return df, removed


def load_v4(force_csv=False):
    """加载 CSV 历史数据（共享缓存，无锁）"""
    global _df_v4_cache
    if not force_csv and _df_v4_cache is not None:
        return _df_v4_cache

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
        _df_v4_cache = df
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
    _df_v4_cache = df
    return df


def load_unified():
    """加载统一数据（现在 CSV + 手动记账在同一张表，直接复用 load_v4）"""
    return load_v4()
