import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

V4_FILE = os.path.join(DATA_DIR, "记账数据_清洗_v4.csv")
DB_PATH = os.path.join(DATA_DIR, "finance.db")
FORECAST_FILE = os.path.join(DATA_DIR, "预测结果", "月度支出预测.csv")
MONTHLY_FILE = os.path.join(DATA_DIR, "预测结果", "月度支出汇总.csv")

# 资产分层配置
# 现金/活期：即时可用，流动性 = 1
CASH_LIQUID = {
    "招行储蓄卡": 33699.91,
    "微信零钱": 16974.15,
    "现金": 1100.00,
}

# 投资资产：有波动，卖出才兑现
INVESTMENT = {
    "股票账户": 12702.15,
    "基金账户": 88983.01,
    "支付宝基金": 599.06,
}

# 受限资产：有提取门槛
RESTRICTED = {
    "公积金": 116966.20,
}

# 应收（不确定性）
RECEIVABLES = {
    "外债（未追回）": 7000.00,
}

# 层级汇总（用于遍历）
ASSET_LAYERS = {
    "现金/活期": CASH_LIQUID,
    "投资资产": INVESTMENT,
    "受限资产": RESTRICTED,
    "应收": RECEIVABLES,
}

# 负债拆分
DEBT = {}  # 无有息债务
BILLS_PAYABLE = {"信用卡（下月账单）": 1413.71}

# 信用卡账单文件
CREDIT_CARD_FILE = os.path.join(DATA_DIR, "信用卡账单.json")

# 周期性交易模板
TEMPLATES_FILE = os.path.join(DATA_DIR, "交易模板.json")

# 月收入
MONTHLY_SALARY = 16000
QUARTERLY_BONUS = 10610
CAR_LOAN_MONTHLY = 11742

# 资产快照文件
ASSET_HISTORY_FILE = os.path.join(DATA_DIR, "月度资产快照.csv")
ASSET_CONFIG_FILE = os.path.join(DATA_DIR, "资产设置.json")
BUDGET_CONFIG_FILE = os.path.join(DATA_DIR, "预算设置.json")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
ALERTS_FILE = os.path.join(DATA_DIR, "预警记录.json")
GOALS_FILE = os.path.join(DATA_DIR, "目标设置.json")

# 月度预算（按 category_l1 设置，0 表示不限制）
MONTHLY_BUDGET = {
    "餐饮": 2000,
    "居住": 5000,
    "交通": 500,
    "购物": 1500,
    "娱乐": 1000,
    "社交": 1000,
    "旅游": 2000,
    "车辆": 1500,
    "医疗": 500,
    "个护": 500,
    "学习": 500,
    "数字消费": 300,
    "其他": 500,
}

# 持仓盈亏明细（账户级，不含标的级明细）
PORTFOLIO = [
    {"account": "股票账户", "cost": 33500.00, "current": 12702.15, "type": "股票"},
    {"account": "基金账户", "cost": 50000.00, "current": 88983.01, "type": "基金"},
    {"account": "支付宝基金", "cost": 600.00, "current": 599.06, "type": "基金"},
]
