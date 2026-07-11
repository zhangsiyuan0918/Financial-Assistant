"""
Data pipeline: CSV upload → merge → DB sync → forecast refresh.
Called after /api/upload or /api/forecast/refresh.
"""

import csv, os, sys, subprocess, hashlib
from datetime import datetime

from config import V4_FILE, DB_PATH, DATA_DIR, FORECAST_FILE, MONTHLY_FILE
from utils import db

db.set_db_path(DB_PATH)

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "scripts")


def _file_fingerprint(path):
    """Compute MD5 of file contents for change detection."""
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def merge_csv(new_csv_path, v4_path=V4_FILE):
    """
    Append rows from new_csv_path into v4_path.
    Deduplication happens at load time in data_loader._deduplicate().
    Returns (total_rows, new_rows, skipped_duplicates).
    """
    # Read existing rows
    existing_rows = []
    existing_keys = set()
    if os.path.exists(v4_path):
        with open(v4_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for row in reader:
                key = (row.get("clean_date", ""), row.get("cny_amount", ""), row.get("clean_project", ""))
                existing_keys.add(key)
                existing_rows.append(row)
    else:
        fieldnames = None

    # Read new rows
    new_rows = []
    with open(new_csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if fieldnames is None:
            fieldnames = reader.fieldnames
        for row in reader:
            new_rows.append(row)

    if not fieldnames:
        return {"error": "No fieldnames found in CSV"}

    # Merge: append only truly new rows
    added = 0
    skipped = 0
    for row in new_rows:
        key = (row.get("clean_date", ""), row.get("cny_amount", ""), row.get("clean_project", ""))
        if key in existing_keys:
            skipped += 1
            continue
        existing_keys.add(key)
        existing_rows.append(row)
        added += 1

    # Write merged file
    with open(v4_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(existing_rows)

    return {
        "total": len(existing_rows),
        "added": added,
        "skipped": skipped,
        "source_file": os.path.basename(new_csv_path),
    }


def sync_to_db(csv_path=V4_FILE):
    """Migrate CSV to SQLite (with dedup safety from P0)."""
    if not os.path.exists(csv_path):
        return {"error": "CSV file not found"}
    db.init_db()
    return db.migrate_from_csv(csv_path)


def refresh_forecast(timeout=180):
    """Re-run Prophet forecast script with correct paths."""
    script = os.path.join(SCRIPTS_DIR, "prophet_forecast.py")
    if not os.path.exists(script):
        return {"status": "skipped", "reason": "prophet_forecast.py not found in scripts/"}

    # Patch the script's hardcoded BASE_DIR to use our data directory
    try:
        result = subprocess.run(
            [sys.executable, "-c", _patched_forecast_script()],
            capture_output=True, timeout=timeout,
            cwd=SCRIPTS_DIR,
        )
        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        if result.returncode == 0:
            return {"status": "ok", "output": stdout[-800:]}
        return {"status": "error", "error": stderr[-500:]}
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}


def _patched_forecast_script():
    """Generate a patched version of prophet_forecast.py with correct paths."""
    script = os.path.join(SCRIPTS_DIR, "prophet_forecast.py")
    output_dir = os.path.join(DATA_DIR, "预测结果")
    os.makedirs(output_dir, exist_ok=True)

    with open(script, "r", encoding="utf-8") as f:
        code = f.read()

    # Replace hardcoded BASE_DIR with our data directory
    code = code.replace(
        r'BASE_DIR = r"C:\Users\77432\.doubao\chats\2026-07-10\new-chat"',
        f'BASE_DIR = r"{DATA_DIR}"'
    )
    return code


def run_full_pipeline(uploaded_csv_path):
    """
    Full pipeline after CSV upload:
    1. Merge into v4 CSV
    2. Sync to SQLite
    3. Refresh forecast
    """
    steps = []

    # Step 1: Merge CSV
    merge_result = merge_csv(uploaded_csv_path)
    steps.append({"step": "CSV 合并", "result": merge_result})

    if "error" in merge_result:
        return {"success": False, "steps": steps}

    # Step 2: Sync to DB
    db_result = sync_to_db()
    steps.append({"step": "数据库同步", "result": db_result})

    # Step 3: Refresh forecast (best effort)
    forecast_result = refresh_forecast()
    steps.append({"step": "预测更新", "result": forecast_result})

    return {"success": True, "steps": steps}


def run_forecast_only():
    """Just refresh forecast without CSV processing."""
    return {"success": True, "steps": [{"step": "预测更新", "result": refresh_forecast()}]}
