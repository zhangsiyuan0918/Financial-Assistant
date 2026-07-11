# FinFlow 改进方案

> 基于代码审查 + PRD 对照 + 四视角分析产出。按优先级分 5 个阶段，每阶段包含技术实现细节。

---

## 阶段划分总览

| 阶段 | 主题 | 预计周期 | 核心目标 |
|------|------|---------|---------|
| P0 | 安全与数据完整性 | 3-5天 | 堵住数据丢失和认证漏洞 |
| P1 | 数据管道自动化 | 1-2周 | 导入→清洗→入库→预测全链路自动 |
| P2 | AI 能力重构 | 1-2周 | LLM 驱动的意图识别 + 多轮对话 |
| P3 | 前端体验升级 | 1-2周 | 移动端适配 + 交互优化 + 信息架构重整 |
| P4 | 产品闭环与智能化 | 2-3周 | 主动推送 + 报告自动化 + 高级分析 |

---

## P0：安全与数据完整性（最高优先级）

### P0-1. 认证系统加固

**问题**：SHA256 无盐哈希，无暴力破解防护，Token 存内存重启失效，LLM Key 明文存储。

**方案**：

```python
# auth.py 重写
import bcrypt, secrets, os, json, time

# 密码哈希：使用 bcrypt（自带盐）
def init_password(password: str):
    h = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    _save_auth({"password_hash": h.decode()})

def verify_password(password: str) -> bool:
    data = _load_auth()
    if not data:
        return True  # 未配置密码时放行（首次使用）
    stored = data.get("password_hash", "").encode()
    return bcrypt.checkpw(password.encode(), stored)
```

**Token 持久化**（解决重启失效问题）：

```python
# 内存 + 文件双写
TOKENS_FILE = os.path.join(DATA_DIR, "auth_tokens.json")

def _save_tokens():
    serializable = {t: exp.isoformat() for t, exp in _tokens.items()}
    with open(TOKENS_FILE, "w") as f:
        json.dump(serializable, f)

def _load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE) as f:
            data = json.load(f)
        for t, exp_str in data.items():
            exp = datetime.fromisoformat(exp_str)
            if exp > datetime.now():
                _tokens[t] = exp
```

**暴力破解防护**：

```python
_login_attempts = {}  # ip -> (count, first_attempt_time)

def _check_rate_limit(ip, max_attempts=5, window=300):
    now = time.time()
    if ip in _login_attempts:
        count, first = _login_attempts[ip]
        if now - first > window:
            del _login_attempts[ip]
        elif count >= max_attempts:
            return False
    return True

def login(password, ip="unknown"):
    if not _check_rate_limit(ip):
        return None, "登录过于频繁，请5分钟后重试"
    if not verify_password(password):
        _login_attempts[ip] = (_login_attempts.get(ip, (0, now))[0] + 1, now)
        return None, "密码错误"
    # ... 生成 token
```

**LLM Key 加密存储**：

```python
# llm_config.json → 加密存储
from cryptography.fernet import Fernet
import base64

_KEY_FILE = os.path.join(DATA_DIR, ".llm_key")

def _get_fernet():
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, "rb") as f:
            return Fernet(f.read())
    key = Fernet.generate_key()
    with open(_KEY_FILE, "wb") as f:
        f.write(key)
    return Fernet(key)

def save_config(data):
    f = _get_fernet()
    encrypted = f.encrypt(json.dumps(data).encode())
    with open(CONFIG_FILE, "wb") as fh:
        fh.write(encrypted)

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    f = _get_fernet()
    with open(CONFIG_FILE, "rb") as fh:
        return json.loads(f.decrypt(fh.read()))
```

**依赖变更**：

```
# requirements.txt 新增
bcrypt>=4.0.0
cryptography>=41.0.0
```

---

### P0-2. SQLite 迁移安全性

**问题**：`DELETE FROM transactions` 全量重插无事务保护，无校验。

**方案**：

```python
# db.py 改进
def migrate_from_csv(csv_path):
    import csv, hashlib

    # 1. 计算新数据的指纹
    with open(csv_path, "rb") as f:
        new_hash = hashlib.md5(f.read()).hexdigest()

    # 2. 检查是否已迁移且数据未变化
    if is_migrated():
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM transactions")
        old_count = cur.fetchone()[0]
        cur.execute('SELECT MIN("clean_date"), MAX("clean_date") FROM transactions')
        old_range = cur.fetchone()
        conn.close()

        if old_count > 0:
            # 对比记录数和日期范围
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                new_count = sum(1 for _ in csv.DictReader(f))
            if new_count == old_count:
                return {"skipped": True, "reason": "数据未变化"}

    # 3. 在事务中执行迁移
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")

        # 先备份到临时表
        conn.execute("CREATE TEMPORARY TABLE IF NOT EXISTS transactions_backup AS SELECT * FROM transactions")

        # 清空并重建
        conn.execute("DELETE FROM transactions")

        # 插入新数据
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames
            quoted_cols = [f'"{c}"' for c in cols]
            placeholders = ",".join("?" * len(cols))
            col_names = ",".join(quoted_cols)
            rows = [tuple(row.get(c, "") for c in cols) for row in reader]
            conn.executemany(f"INSERT INTO transactions ({col_names}) VALUES ({placeholders})", rows)

        # 校验：行数一致
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM transactions")
        inserted = cur.fetchone()[0]

        if inserted != len(rows):
            # 回滚到备份
            conn.execute("DELETE FROM transactions")
            conn.execute("INSERT INTO transactions SELECT * FROM transactions_backup")
            conn.commit()
            raise ValueError(f"校验失败：预期 {len(rows)} 行，实际 {inserted} 行")

        conn.execute("DROP TABLE IF EXISTS transactions_backup")
        conn.commit()
        return {"success": True, "records": inserted}

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

---

### P0-3. CSV 去重机制

**方案**：

```python
# data_loader.py 新增
def deduplicate(df):
    """按日期+金额+项目去重，保留首次出现"""
    before = len(df)
    df = df.drop_duplicates(
        subset=["clean_date", "cny_amount", "clean_project"],
        keep="first"
    )
    removed = before - len(df)
    return df, removed
```

在 `load_v4()` 中调用：

```python
def load_v4(force_csv=False):
    # ... 现有加载逻辑 ...
    df, removed = deduplicate(df)
    if removed > 0:
        print(f"去重：移除 {removed} 条重复记录")
    return df
```

---

## P1：数据管道自动化

### P1-1. CSV 上传后自动触发清洗

**问题**：当前上传只存文件，不触发清洗流程。

**方案**：

```python
# app.py 修改 /api/upload
@app.route("/api/upload", methods=["POST"])
def api_upload():
    # ... 现有文件保存逻辑 ...

    # 新增：自动触发清洗
    from utils.pipeline import run_cleaning_pipeline
    result = run_cleaning_pipeline(path)

    return jsonify({
        "status": "ok",
        "filename": f.filename,
        "records": len(rows),
        "saved_as": f"raw_{ts}.csv",
        "cleaning": result  # 清洗结果摘要
    })
```

新建 `utils/pipeline.py`：

```python
"""数据清洗流水线"""
import subprocess, os, sys
from datetime import datetime

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")

def run_cleaning_pipeline(raw_path):
    """执行 R1-R4 清洗流水线"""
    steps = [
        ("R1: 格式标准化", "clean_round1.py"),
        ("R2: 转账过滤", "clean_round2.py"),
        ("R3: 分类归一化", "clean_round3.py"),
        ("R4: 异常值标记", "clean_round4.py"),
    ]

    results = []
    current_input = raw_path

    for name, script in steps:
        script_path = os.path.join(SCRIPTS_DIR, script)
        if not os.path.exists(script_path):
            results.append({"step": name, "status": "skipped", "reason": "脚本不存在"})
            continue

        try:
            proc = subprocess.run(
                [sys.executable, script_path, current_input],
                capture_output=True, text=True, timeout=60
            )
            if proc.returncode == 0:
                results.append({"step": name, "status": "ok"})
                # 下一步的输入 = 这一步的输出
                # 由各脚本约定输出路径
            else:
                results.append({"step": name, "status": "error", "error": proc.stderr[:500]})
                break
        except subprocess.TimeoutExpired:
            results.append({"step": name, "status": "timeout"})
            break

    # 清洗完成后自动迁移数据库
    from utils import db
    from config import V4_FILE
    if db.is_migrated():
        db.migrate_from_csv(V4_FILE)
        results.append({"step": "DB同步", "status": "ok"})

    # 自动重跑预测
    forecast_script = os.path.join(SCRIPTS_DIR, "prophet_forecast.py")
    if os.path.exists(forecast_script):
        try:
            subprocess.run(
                [sys.executable, forecast_script],
                capture_output=True, text=True, timeout=120
            )
            results.append({"step": "预测更新", "status": "ok"})
        except Exception:
            results.append({"step": "预测更新", "status": "error"})

    return results
```

---

### P1-2. 资产编辑自动生成月度快照

**问题**：编辑资产后不会记录历史，无法追踪变化。

**方案**：

```python
# data_loader.py 修改 update_assets
def update_assets(data):
    """更新资产配置并自动生成月度快照"""
    # 1. 保存当前配置
    _save_asset_config(data)

    # 2. 自动生成月度快照
    _write_asset_snapshot()

def _write_asset_snapshot():
    """将当前资产状态写入月度快照 CSV"""
    from datetime import datetime
    now = datetime.now()
    month = f"{now.year}-{now.month:02d}"

    config = _load_asset_config()
    flat = flatten_assets(config)
    total = sum(item["amount"] for item in flat)

    snapshot = {
        "month": month,
        "total": round(total, 2),
        "cash": sum(item["amount"] for layer_items in config.get("现金/活期", {}).values() for item in [layer_items]),
        "investment": sum(item["amount"] for layer_items in config.get("投资资产", {}).values() for item in [layer_items]),
        "restricted": sum(item["amount"] for layer_items in config.get("受限资产", {}).values() for item in [layer_items]),
        "updated_at": now.isoformat(),
    }

    # 读取现有快照，更新当月
    history = []
    if os.path.exists(ASSET_HISTORY_FILE):
        with open(ASSET_HISTORY_FILE, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            history = [row for row in reader]

    # 替换或追加当月
    history = [h for h in history if h["month"] != month]
    history.append(snapshot)
    history.sort(key=lambda x: x["month"])

    with open(ASSET_HISTORY_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=snapshot.keys())
        writer.writeheader()
        writer.writerows(history)
```

---

### P1-3. 预测自动重跑

**方案**：在 pipeline 完成后触发，同时支持手动重跑：

```python
# app.py 新增
@app.route("/api/forecast/refresh", methods=["POST"])
def api_refresh_forecast():
    from utils.pipeline import refresh_forecast
    result = refresh_forecast()
    return jsonify(result)
```

```python
# utils/pipeline.py 补充
def refresh_forecast():
    """重跑 Prophet 预测"""
    script = os.path.join(SCRIPTS_DIR, "prophet_forecast.py")
    if not os.path.exists(script):
        return {"status": "error", "error": "预测脚本不存在"}

    try:
        proc = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=180
        )
        if proc.returncode == 0:
            return {"status": "ok", "output": proc.stdout[-500:]}
        return {"status": "error", "error": proc.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
```

---

### P1-4. 上传 UI 增强

**前端**：上传后显示清洗进度和结果：

```vue
<!-- Overview.vue 上传对话框改进 -->
<el-dialog v-model="uploadVisible" title="导入数据" width="600px">
  <el-upload drag :auto-upload="false" :on-change="handleUpload" accept=".csv">
    <el-icon style="font-size:48px;color:#409eff"><Upload /></el-icon>
    <div style="margin-top:8px">将 CSV 文件拖到此处，或点击选择</div>
  </el-upload>

  <!-- 清洗进度 -->
  <div v-if="cleaning" style="margin-top:16px">
    <el-steps :active="cleaningStep" direction="vertical" finish-status="success">
      <el-step v-for="step in cleaningSteps" :key="step.name" :title="step.name"
        :status="step.status" :description="step.desc" />
    </el-steps>
  </div>

  <!-- 清洗结果 -->
  <div v-if="uploadResult" style="margin-top:12px;padding:12px;background:#f0f9eb;border-radius:4px">
    <div>已导入 {{ uploadResult.records }} 条记录</div>
    <div v-if="uploadResult.cleaning">
      <div v-for="r in uploadResult.cleaning" :key="r.step"
        style="font-size:12px;color:#666;margin-top:4px">
        {{ r.status === 'ok' ? '✓' : r.status === 'error' ? '✗' : '○' }}
        {{ r.step }} {{ r.error ? '- ' + r.error : '' }}
      </div>
    </div>
  </div>
</el-dialog>
```

---

## P2：AI 能力重构

### P2-1. QueryEngine 重写 — LLM 驱动意图识别

**问题**：硬编码关键词匹配无法处理语义变体。

**方案**：用 LLM 做意图识别 + SQL 生成，替代规则引擎：

```python
# utils/query_engine_v2.py
import json, re
from datetime import datetime

class QueryEngineV2:
    def __init__(self, data_loader):
        self.dl = data_loader

    def answer(self, question):
        from utils import llm
        if not llm.is_configured():
            return self._fallback_answer(question)

        # Step 1: 让 LLM 解析意图和参数
        intent_prompt = self._build_intent_prompt(question)
        intent_response = llm.ask(intent_prompt, self._intent_system_prompt())

        # Step 2: 解析 LLM 返回的 JSON
        try:
            intent_data = json.loads(intent_response)
        except json.JSONDecodeError:
            intent_data = {"intent": "unknown", "params": {}}

        # Step 3: 执行查询
        return self._execute_intent(intent_data, question)

    def _intent_system_prompt(self):
        return """你是一个财务数据查询解析器。根据用户问题，输出 JSON 格式的查询意图。

可用的意图：
- total_expense: 总支出查询 (params: month: "YYYY-MM" 或 range: ["start", "end"])
- category_expense: 分类支出 (params: month, category)
- total_income: 总收入 (params: month 或 range)
- net_worth: 净资产
- budget_status: 预算状态 (params: month)
- portfolio: 持仓盈亏
- savings_rate: 储蓄率
- liquidity: 流动性覆盖率
- health: 财务健康评分
- spending_trend: 支出趋势 (params: months: int, end_month: "YYYY-MM")
- comparison: 同比环比 (params: month)
- monthly_report: 月度报告 (params: month)
- top_category: 支出排行 (params: month, top_n: int)

时间词规则：
- "本月"/"这个月" → 当前月份
- "上月"/"上个月" → 上月
- "上个季度"/"这个季度" → 自动计算季度范围
- "最近N月"/"近N个月" → range 从 (当前月-N+1) 到 当前月
- "今年" → range 从 "YYYY-01" 到当前月
- "去年" → range 从 "YYYY-01" 到 "YYYY-12"
- "YYYY年MM月" → 直接提取

输出格式（只输出 JSON，不要其他内容）：
{"intent": "...", "params": {...}}"""

    def _build_intent_prompt(self, question):
        now = datetime.now()
        return f"当前时间：{now.year}年{now.month}月\n用户问题：{question}"

    def _execute_intent(self, intent_data, original_question):
        intent = intent_data.get("intent", "unknown")
        params = intent_data.get("params", {})

        handlers = {
            "total_expense": self._handle_total_expense,
            "category_expense": self._handle_category_expense,
            "total_income": self._handle_total_income,
            "net_worth": self._handle_net_worth,
            "budget_status": self._handle_budget_status,
            "portfolio": self._handle_portfolio,
            "savings_rate": self._handle_savings_rate,
            "liquidity": self._handle_liquidity,
            "health": self._handle_health,
            "spending_trend": self._handle_spending_trend,
            "comparison": self._handle_comparison,
            "monthly_report": self._handle_monthly_report,
            "top_category": self._handle_top_category,
        }

        handler = handlers.get(intent)
        if not handler:
            return self._llm_general_answer(original_question)

        try:
            return handler(params)
        except Exception as e:
            return f"查询出错：{str(e)}"

    def _handle_spending_trend(self, params):
        months = params.get("months", 12)
        end_month = params.get("end_month")
        trend = self.dl.get_monthly_trend()
        if end_month:
            trend = [t for t in trend if t["month"] <= end_month]
        recent = trend[-months:]
        items = [f"{t['month']}: ¥{t['expense']:,.0f}" for t in recent]
        return f"近 {months} 月支出趋势：\n" + " → ".join(items)

    # ... 其他 handler 类似，支持 params 中的灵活参数
```

---

### P2-2. 多轮对话支持

**方案**：在前端维护对话上下文，后端支持上下文注入：

```python
# app.py 新增会话管理
from collections import defaultdict
import threading

_conversations = defaultdict(list)  # session_id -> [{"role": ..., "content": ...}]
_lock = threading.Lock()

@app.route("/api/query", methods=["POST"])
def api_query():
    data = request.get_json(force=True)
    question = data.get("question", "")
    session_id = data.get("session_id", "default")

    with _lock:
        history = _conversations[session_id]

    engine = get_query_engine()
    answer = engine.answer(question, context=history)

    with _lock:
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        # 保留最近 10 轮
        if len(history) > 20:
            _conversations[session_id] = history[-20:]

    return jsonify({"answer": answer})
```

**前端**（`AIQuery.vue` 改进）：

```javascript
// 生成 session_id
const sessionId = ref('session_' + Date.now())

async function send() {
  const q = question.value.trim()
  if (!q || loading.value) return
  messages.value.push({ role: 'user', content: q })
  question.value = ''
  loading.value = true

  try {
    const res = await api.post('/query', {
      question: q,
      session_id: sessionId.value
    }).then(r => r.data)
    messages.value.push({ role: 'assistant', content: res.answer })
  } catch {
    messages.value.push({ role: 'assistant', content: '查询出错了，请重试' })
  }
  loading.value = false
}
```

---

### P2-3. RAG 检索增强（支持历史细粒度查询）

**问题**：用户问"2023年3月餐饮花了多少"，上下文没有历史月度明细。

**方案**：为 LLM 提供 SQL 查询工具，让它自己查数据库：

```python
# utils/sql_tool.py
import sqlite3, json
from config import DB_PATH

def query_sql(sql: str) -> str:
    """安全执行只读 SQL"""
    # 只允许 SELECT
    sql = sql.strip()
    if not sql.upper().startswith("SELECT"):
        return "错误：只允许查询操作"

    # 禁止危险操作
    forbidden = ["DELETE", "INSERT", "UPDATE", "DROP", "ALTER", "CREATE"]
    for word in forbidden:
        if word in sql.upper():
            return f"错误：不允许 {word} 操作"

    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        result = [dict(zip(columns, row)) for row in rows[:50]]  # 最多50行
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        return f"SQL 错误：{str(e)}"
    finally:
        conn.close()
```

在 QueryEngine 中让 LLM 先判断是否需要查历史明细，如需要则调用 SQL 工具：

```python
def _llm_answer_with_tools(self, question, history):
    # 先让 LLM 判断是否需要查历史数据
    tool_prompt = f"""根据用户问题判断是否需要查询历史交易明细数据库。

数据库表结构：
transactions 表，字段包括：
- clean_date (日期), cny_amount (金额), category_l1 (分类)
- corrected_type (收入/支出), clean_project (项目描述)
- month (月份 YYYY-MM), year (年份)

如果需要查询，输出：{{"need_sql": true, "sql": "SELECT ..."}}
如果不需要，输出：{{"need_sql": false}}

用户问题：{question}"""

    tool_response = llm.ask(tool_prompt)
    tool_data = json.loads(tool_response)

    if tool_data.get("need_sql"):
        sql_result = query_sql(tool_data["sql"])
        # 将查询结果注入上下文
        context = self._build_context()
        context += f"\n\n历史查询结果：\n{sql_result}"
    else:
        context = self._build_context()

    # ... 正常 LLM 回答
```

---

## P3：前端体验升级

### P3-1. 移动端响应式适配

**问题**：侧边栏写死 220px，四列布局无适配。

**方案**：

```css
/* App.vue style 改进 */
<style>
/* 移动端：侧边栏变底部导航 */
@media (max-width: 768px) {
  .el-aside {
    position: fixed !important;
    bottom: 0;
    left: 0;
    right: 0;
    width: 100% !important;
    height: 60px !important;
    z-index: 1000;
    display: flex;
    overflow-x: auto;
    overflow-y: hidden;
  }

  .el-aside > div:first-child {  /* 隐藏 logo 区域 */
    display: none;
  }

  .el-menu {
    display: flex !important;
    flex-direction: row !important;
    width: 100%;
  }

  .el-menu-item {
    flex: 1;
    min-width: auto !important;
  }

  .el-menu-item span {
    display: none;  /* 只显示图标 */
  }

  .el-main {
    padding-bottom: 80px !important;
  }
}

/* 平板适配 */
@media (min-width: 769px) and (max-width: 1024px) {
  .el-aside { width: 180px !important; }
}
</style>
```

**表格列自适应**：

```vue
<!-- 使用 Element Plus 的 responsive 属性 -->
<el-table :data="o.assets" stripe style="width: 100%">
  <el-table-column prop="name" label="项目" min-width="120" />
  <el-table-column prop="layer" label="层级" width="100" :responsive="['md']" />
  <el-table-column prop="amount" label="金额" width="150">
    <template #default="{row}">{{ fmt(row.amount) }}</template>
  </el-table-column>
</el-table>
```

**图表自适应**：

```javascript
// ECharts 响应式处理
function initChart(el, option) {
  const chart = echarts.init(el)

  // 监听窗口大小变化
  const resizeObserver = new ResizeObserver(() => chart.resize())
  resizeObserver.observe(el)

  chart.setOption(option)
  return chart
}
```

---

### P3-2. 信息架构重整

**问题**：12个菜单项平铺无分组，总览页信息过载。

**方案**：侧边栏分组 + 总览页精简。

**侧边栏分组**：

```vue
<!-- App.vue 侧边栏改用 el-menu 分组 -->
<el-menu :default-active="route.path" router
  background-color="#304156" text-color="#bfcbd9" active-text-color="#409eff">

  <el-menu-item index="/">
    <el-icon><DataBoard /></el-icon><span>总览</span>
  </el-menu-item>

  <el-sub-menu index="analysis">
    <template #title><el-icon><TrendCharts /></el-icon><span>分析</span></template>
    <el-menu-item index="/spending">支出分析</el-menu-item>
    <el-menu-item index="/income">收入分析</el-menu-item>
    <el-menu-item index="/portfolio">持仓盈亏</el-menu-item>
    <el-menu-item index="/report">月度报告</el-menu-item>
  </el-sub-menu>

  <el-sub-menu index="planning">
    <template #title><el-icon><MagicStick /></el-icon><span>规划</span></template>
    <el-menu-item index="/forecast">支出预测</el-menu-item>
    <el-menu-item index="/simulation">情景模拟</el-menu-item>
    <el-menu-item index="/goals">目标管理</el-menu-item>
  </el-sub-menu>

  <el-menu-item index="/alerts">
    <el-icon><WarningFilled /></el-icon><span>预警</span>
    <el-badge v-if="alertCount" :value="alertCount" :max="99"
      style="margin-left:8px" />
  </el-menu-item>

  <el-menu-item index="/ai">
    <el-icon><ChatDotRound /></el-icon><span>AI 助手</span>
  </el-menu-item>

  <el-menu-item index="/settings">
    <el-icon><Setting /></el-icon><span>设置</span>
  </el-menu-item>
</el-menu>
```

**总览页精简**：

```vue
<!-- Overview.vue 重构 -->
<template>
  <div>
    <!-- 第一屏：核心指标（3个大数字） -->
    <el-row :gutter="16">
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover">
          <div style="text-align:center">
            <div style="color:#999;font-size:13px">净资产</div>
            <div style="font-size:28px;font-weight:bold;color:#67c23a;margin-top:8px">
              {{ fmt(o.net_worth) }}
            </div>
            <!-- 新增：环比变化 -->
            <div v-if="o.net_worth_change" :style="{color: o.net_worth_change > 0 ? '#67c23a' : '#f56c6c', fontSize:'12px'}">
              {{ o.net_worth_change > 0 ? '↑' : '↓' }} {{ Math.abs(o.net_worth_change) }}%
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover">
          <div style="text-align:center">
            <div style="color:#999;font-size:13px">本月结余</div>
            <div style="font-size:28px;font-weight:bold;color:#409eff;margin-top:8px">
              {{ fmt(o.monthly_balance) }}
            </div>
            <div style="font-size:12px;color:#999">收入 {{ fmt(o.monthly_income) }} - 支出 {{ fmt(o.monthly_expense) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover">
          <div style="text-align:center">
            <div style="color:#999;font-size:13px">财务健康</div>
            <div :style="{fontSize:'28px',fontWeight:'bold',marginTop:'8px',color: h.total_score >= 70 ? '#67c23a' : h.total_score >= 50 ? '#e6a23c' : '#f56c6c'}">
              {{ h.total_score ?? '--' }}分
            </div>
            <div style="font-size:12px;color:#999">{{ h.level }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 第二屏：预警摘要（只显示未处理的） -->
    <el-card v-if="alerts.length" style="margin-top:16px">
      <template #header>
        <el-space>
          <el-icon color="#e6a23c"><WarningFilled /></el-icon>
          <span>预警摘要</span>
          <el-button size="small" text @click="$router.push('/alerts')">查看全部</el-button>
        </el-space>
      </template>
      <div v-for="a in alerts.slice(0, 3)" :key="a.id" style="padding:8px 0;border-bottom:1px solid #f0f0f0">
        <el-tag :type="a.severity === 'high' ? 'danger' : 'warning'" size="small" style="margin-right:8px">
          {{ a.type === 'budget_over' ? '预算' : a.type === 'liquidity' ? '流动性' : '异常' }}
        </el-tag>
        <span>{{ a.message }}</span>
      </div>
    </el-card>

    <!-- 第三屏：快捷入口 -->
    <el-row :gutter="16" style="margin-top:16px">
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" style="cursor:pointer" @click="$router.push('/spending')">
          <div style="text-align:center;padding:12px 0">
            <div style="font-size:32px">📊</div>
            <div style="margin-top:8px">支出分析</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" style="cursor:pointer" @click="$router.push('/forecast')">
          <div style="text-align:center;padding:12px 0">
            <div style="font-size:32px">🔮</div>
            <div style="margin-top:8px">支出预测</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" style="cursor:pointer" @click="$router.push('/simulation')">
          <div style="text-align:center;padding:12px 0">
            <div style="font-size:32px">🧮</div>
            <div style="margin-top:8px">情景模拟</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" style="cursor:pointer" @click="$router.push('/ai')">
          <div style="text-align:center;padding:12px 0">
            <div style="font-size:32px">🤖</div>
            <div style="margin-top:8px">AI 助手</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表下沉到子页面，或折叠展示 -->
    <el-collapse v-model="activeCollapse" style="margin-top:16px">
      <el-collapse-item title="资产分层" name="assets">
        <div ref="layerChart" style="height: 300px"></div>
      </el-collapse-item>
      <el-collapse-item title="净资产走势" name="trend">
        <div ref="netWorthChart" style="height: 300px"></div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>
```

---

### P3-3. AI 助手内嵌到每个页面

**方案**：在分析页面增加"问 AI"浮动按钮：

```vue
<!-- 新组件 components/AiFloat.vue -->
<template>
  <div>
    <el-button circle type="primary" size="large" @click="visible = true"
      style="position:fixed;bottom:80px;right:24px;z-index:999;box-shadow:0 4px 12px rgba(0,0,0,.15)">
      <el-icon size="20"><ChatDotRound /></el-icon>
    </el-button>

    <el-drawer v-model="visible" direction="btt" size="60%" :show-close="false">
      <template #header>
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-weight:bold">AI 助手</span>
          <el-tag v-if="contextHint" size="small" type="info">{{ contextHint }}</el-tag>
        </div>
      </template>

      <div ref="chatBox" style="height:calc(100% - 60px);overflow-y:auto;padding:8px">
        <div v-for="(msg, i) in messages" :key="i"
          :style="{marginBottom:'12px',display:'flex',justifyContent:msg.role==='user'?'flex-end':'flex-start'}">
          <div :style="{maxWidth:'80%',padding:'8px 12px',borderRadius:'8px',
            background:msg.role==='user'?'#ecf5ff':'#f0f9eb',whiteSpace:'pre-wrap',lineHeight:'1.6',fontSize:'13px'}">
            {{ msg.content }}
          </div>
        </div>
      </div>

      <div style="display:flex;gap:8px;padding-top:8px;border-top:1px solid #eee">
        <el-input v-model="question" :placeholder="`问关于${contextHint}的问题...`"
          @keyup.enter="send" clearable />
        <el-button type="primary" @click="send" :disabled="loading || !question.trim()">发送</el-button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, inject } from 'vue'
import { useRoute } from 'vue-router'
import { askQuestion } from '../api/index.js'

const route = useRoute()
const visible = ref(false)
const messages = ref([])
const question = ref('')
const loading = ref(false)

// 自动注入当前页面上下文
const contextHint = computed(() => {
  const map = {
    '/spending': '支出分析',
    '/income': '收入分析',
    '/forecast': '支出预测',
    '/portfolio': '持仓盈亏',
    '/simulation': '情景模拟',
    '/goals': '目标管理',
    '/report': '月度报告',
  }
  return map[route.path] || '财务数据'
})

async function send() {
  const q = question.value.trim()
  if (!q || loading.value) return

  // 注入上下文前缀
  const contextPrefix = `（当前页面：${contextHint.value}）`
  messages.value.push({ role: 'user', content: q })
  question.value = ''
  loading.value = true

  try {
    const res = await askQuestion(contextPrefix + ' ' + q)
    messages.value.push({ role: 'assistant', content: res.answer })
  } catch {
    messages.value.push({ role: 'assistant', content: '查询出错了' })
  }
  loading.value = false
}
</script>
```

在每个分析页面引入：

```vue
<!-- Spending.vue 底部 -->
<AiFloat />
```

---

### P3-4. 图表空数据与中文处理

```javascript
// utils/chart.js 统一图表配置
export function safeChartOption(option) {
  // 空数据处理
  if (!option.series || option.series.every(s => !s.data?.length)) {
    return {
      graphic: {
        type: 'text',
        left: 'center',
        top: 'center',
        style: { text: '暂无数据', fontSize: 14, fill: '#999' }
      }
    }
  }

  // 中文字体
  return {
    ...option,
    textStyle: { fontFamily: "'PingFang SC', 'Microsoft YaHei', sans-serif" },
    xAxis: {
      ...option.xAxis,
      axisLabel: {
        ...option.xAxis?.axisLabel,
        fontFamily: "'PingFang SC', 'Microsoft YaHei', sans-serif"
      }
    },
    yAxis: {
      ...option.yAxis,
      axisLabel: {
        ...option.yAxis?.axisLabel,
        fontFamily: "'PingFang SC', 'Microsoft YaHei', sans-serif"
      }
    }
  }
}
```

---

### P3-5. 全局错误处理与加载状态

```javascript
// App.vue 新增全局 loading 和错误提示
<template>
  <el-container>
    <!-- ... 侧边栏 ... -->
    <el-main>
      <!-- 全局 loading 覆盖层 -->
      <div v-if="globalLoading" class="global-loading">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <span style="margin-left:8px">加载中...</span>
      </div>
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, provide } from 'vue'

const globalLoading = ref(false)
provide('globalLoading', globalLoading)

// 全局 axios 拦截器
api.interceptors.request.use(config => {
  globalLoading.value = true
  return config
})
api.interceptors.response.use(
  r => { globalLoading.value = false; return r },
  err => {
    globalLoading.value = false
    ElMessage.error(err.response?.data?.error || '请求失败')
    return Promise.reject(err)
  }
)
</script>
```

---

## P4：产品闭环与智能化

### P4-1. 主动预警推送

**问题**：预警需要用户主动打开查看，无推送能力。

**方案**：服务端定时检查 + 前端轮询 + WebSocket 推送。

**后端**：

```python
# utils/alert_engine.py
from datetime import datetime

def check_alerts():
    """检查所有预警条件，生成新预警"""
    from utils import data_loader as dl
    new_alerts = []

    # 1. 预算超支预警
    budget = dl.get_budget_status()
    for item in budget["items"]:
        if item["ratio"] >= 100:
            new_alerts.append({
                "id": f"budget_over_{item['category']}_{budget['month']}",
                "type": "budget_over",
                "severity": "high",
                "message": f"{item['category']} 已超支（{item['ratio']}%），已花 ¥{item['actual']:,.0f} / 预算 ¥{item['budget']:,.0f}",
                "created_at": datetime.now().isoformat(),
            })
        elif item["ratio"] >= 80:
            new_alerts.append({
                "id": f"budget_warn_{item['category']}_{budget['month']}",
                "type": "budget_warn",
                "severity": "medium",
                "message": f"{item['category']} 接近预算上限（{item['ratio']}%）",
                "created_at": datetime.now().isoformat(),
            })

    # 2. 流动性不足预警
    overview = dl.get_overview()
    if overview["liquidity_coverage"] < 3:
        new_alerts.append({
            "id": f"liquidity_{budget['month']}",
            "type": "liquidity",
            "severity": "high",
            "message": f"流动性覆盖率仅 {overview['liquidity_coverage']} 个月（低于3个月警戒线）",
            "created_at": datetime.now().isoformat(),
        })

    # 3. 异常支出预警（单笔超过月均支出 50%）
    df = dl.load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    current_month = datetime.now().strftime("%Y-%m")
    month_expenses = valid[(valid["corrected_type"] == "支出") & (valid["month"] == current_month)]
    avg_expense = overview["avg_monthly_expense"]
    for _, row in month_expenses.iterrows():
        if row["cny_amount"] > avg_expense * 0.5:
            new_alerts.append({
                "id": f"abnormal_{row.name}",
                "type": "abnormal",
                "severity": "medium",
                "message": f"异常支出：{row.get('clean_project', '未知')} ¥{row['cny_amount']:,.0f}（超过月均支出50%）",
                "created_at": datetime.now().isoformat(),
            })

    # 4. 目标偏离预警
    from utils.data_loader import get_goals
    goals = get_goals()
    for g in goals:
        if not g.get("on_track"):
            new_alerts.append({
                "id": f"goal偏离_{g['id']}",
                "type": "goal_deviation",
                "severity": "medium",
                "message": f"目标「{g['name']}」进度偏离预期，当前 {g.get('progress_pct', 0):.0f}%",
                "created_at": datetime.now().isoformat(),
            })

    # 保存预警（去重）
    _save_alerts(new_alerts)
    return new_alerts
```

**API 轮询端点**：

```python
@app.route("/api/alerts/poll")
def api_poll_alerts():
    """前端定期轮询，返回新预警"""
    from utils.alert_engine import check_alerts
    new_alerts = check_alerts()
    return jsonify({
        "new_count": len(new_alerts),
        "alerts": new_alerts
    })
```

**前端轮询**（`App.vue`）：

```javascript
// 定时检查预警（每5分钟）
let alertTimer = null

onMounted(() => {
  alertTimer = setInterval(async () => {
    try {
      const res = await api.get('/alerts/poll').then(r => r.data)
      if (res.new_count > 0) {
        ElNotification({
          title: `新预警 (${res.new_count})`,
          message: res.alerts[0].message,
          type: 'warning',
          duration: 5000
        })
        alertCount.value = res.new_count
      }
    } catch {}
  }, 300000) // 5分钟
})

onUnmounted(() => clearInterval(alertTimer))
```

---

### P4-2. 月度报告自动生成

**方案**：后端生成结构化报告数据，前端渲染：

```python
@app.route("/api/report/auto")
def api_auto_report():
    """自动生成当月报告"""
    from datetime import datetime
    month = datetime.now().strftime("%Y-%m")
    report = dl.get_monthly_report(month)
    overview = dl.get_overview()
    budget = dl.get_budget_status(month)

    # 增强：添加趋势对比
    prev_month = _prev_month(month)
    prev_report = dl.get_monthly_report(prev_month)

    return jsonify({
        **report,
        "comparison": {
            "prev_month": prev_month,
            "expense_change": round((report["expense"] - prev_report["expense"]) / prev_report["expense"] * 100, 1) if prev_report["expense"] else None,
            "income_change": round((report["income"] - prev_report["income"]) / prev_report["income"] * 100, 1) if prev_report["income"] else None,
        },
        "top_expenses": _get_top_expenses(month, n=5),
        "budget_highlights": _get_budget_highlights(budget),
        "savings_rate": report.get("savings_rate"),
    })
```

**年度报告**：

```python
@app.route("/api/report/annual")
def api_annual_report():
    year = request.args.get("year", str(datetime.now().year))
    # 汇总 12 个月数据
    months = [f"{year}-{m:02d}" for m in range(1, 13)]
    monthly_data = [dl.get_monthly_report(m) for m in months]

    total_income = sum(d.get("income", 0) for d in monthly_data)
    total_expense = sum(d.get("expense", 0) for d in monthly_data)
    avg_savings_rate = sum(d.get("savings_rate", 0) for d in monthly_data) / len(monthly_data)

    return jsonify({
        "year": year,
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "total_balance": round(total_income - total_expense, 2),
        "avg_savings_rate": round(avg_savings_rate, 1),
        "monthly_detail": monthly_data,
    })
```

---

### P4-3. 预测回测（验证准确性）

```python
@app.route("/api/forecast/backtest")
def api_forecast_backtest():
    """对比历史预测 vs 实际值"""
    from config import FORECAST_FILE

    # 加载预测结果
    predictions = []
    with open(FORECAST_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            predictions.append({
                "month": row["月份"],
                "predicted": float(row["预测值"]),
            })

    # 加载实际值
    df = dl.load_v4()
    valid = df[df["valid_for_stats"] == "True"]
    actual = valid[valid["corrected_type"] == "支出"].groupby("month")["cny_amount"].sum()

    # 对比
    backtest = []
    for p in predictions:
        m = p["month"]
        if m in actual.index:
            actual_val = actual[m]
            error_pct = (p["predicted"] - actual_val) / actual_val * 100
            backtest.append({
                "month": m,
                "predicted": round(p["predicted"], 2),
                "actual": round(actual_val, 2),
                "error_pct": round(error_pct, 1),
                "error_amount": round(p["predicted"] - actual_val, 2),
            })

    # 汇总指标
    if backtest:
        mape = sum(abs(b["error_pct"]) for b in backtest) / len(backtest)
    else:
        mape = 0

    return jsonify({
        "backtest": backtest,
        "mape": round(mape, 1),  # 平均绝对百分比误差
        "summary": f"历史 {len(backtest)} 个月预测，平均误差 {mape:.1f}%",
    })
```

---

### P4-4. 预算超支实时检测（前端拦截）

```javascript
// 在提交交易或刷新数据时主动检查
async function checkBudgetWarning(category, amount) {
  const budget = await fetchBudget()
  const item = budget.items.find(i => i.category === category)
  if (!item) return

  const newRatio = ((item.actual + amount) / item.budget * 100).toFixed(0)

  if (newRatio >= 100) {
    ElMessageBox.confirm(
      `${category} 将超支！预计执行率 ${newRatio}%`,
      '预算警告',
      { type: 'warning', confirmButtonText: '知道了' }
    )
  } else if (newRatio >= 80) {
    ElMessage.warning(`${category} 接近预算上限（${newRatio}%）`)
  }
}
```

---

## 实施路线图

```
Week 1:  P0-1 认证加固 + P0-2 DB迁移安全 + P0-3 去重
Week 2:  P1-1 自动清洗管道 + P1-2 资产快照 + P1-3 预测自动重跑
Week 3:  P2-1 QueryEngine V2 + P2-2 多轮对话
Week 4:  P3-1 移动端适配 + P3-2 信息架构重整
Week 5:  P3-3 AI浮动按钮 + P3-4 图表优化 + P3-5 错误处理
Week 6:  P4-1 预警引擎 + P4-2 报告自动化 + P4-3 预测回测
```

## 依赖变更汇总

```diff
# requirements.txt
+ bcrypt>=4.0.0
+ cryptography>=41.0.0

# package.json 无需新增依赖（Element Plus 和 ECharts 已满足）
```

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| LLM 意图识别不稳定 | AI 问答功能不可用 | 保留规则引擎作为降级方案 |
| 认证加固后用户首次需重设密码 | 用户体验 | 提供密码重置入口 |
| 移动端适配工作量大 | P3 延期 | 优先保证核心页面（总览+AI） |
| SQLite 迁移脚本破坏现有数据 | 数据丢失 | 迁移前自动备份 DB 文件 |
