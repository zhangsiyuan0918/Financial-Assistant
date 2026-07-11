# FinFlow 产品整体状况报告

> 更新时间：2026-07-11

---

## 一、项目概览

| 项目 | 信息 |
|------|------|
| 名称 | FinFlow（财务分析仪表盘） |
| 技术栈 | Flask + Vue 3 + Element Plus + SQLite + Prophet |
| 数据规模 | 7,198 条历史记录 + 实时记账 |
| 仓库 | https://github.com/zhangsiyuan0918/Financial-Assistant |
| 最新提交 | P0-P4 全阶段改进 + 功能增强 |

---

## 二、迭代记录

| 阶段 | 主题 | 核心改动 | 状态 |
|------|------|---------|------|
| **P0** | 安全与数据完整性 | bcrypt 认证、DB 迁移事务保护、CSV 去重 | ✅ |
| **P1** | 数据管道自动化 | CSV→合并→DB→预测全自动管道 | ✅ |
| **P2** | AI 能力重构 | LLM 意图识别、SQL 工具、多轮对话 | ✅ |
| **P3** | 前端体验升级 | 移动端适配、侧边栏分组、AI 浮动按钮 | ✅ |
| **P4** | 产品闭环与智能化 | 预警轮询、年度报告、预测回测、预算检测 | ✅ |
| **P5** | 功能增强 | 智能分类、模板、预算建议、消费习惯、AI 洞察 | ✅ |
| **P6** | 数据闭环 | 记账数据同步到分析模型 | ✅ |
| **P7** | 交互优化 | 预测回测图表、记账后实时更新图表、图表间距修复 | ✅ |

---

## 三、功能清单

### 已完成功能

| 模块 | 功能 | 文件 |
|------|------|------|
| **记账** | 实时记账（日期/金额/分类/账户/备注） | QuickEntry.vue |
| **记账** | 支出/收入切换 | QuickEntry.vue |
| **记账** | 智能分类推荐（200+ 关键词） | data_loader.py |
| **记账** | 周期性交易模板（创建/编辑/删除/应用） | QuickEntry.vue |
| **记账** | 历史记录查看/删除 | QuickEntry.vue |
| **记账** | 信用卡消费/还款/余额追踪 | data_loader.py |
| **资产** | 资产分层管理（现金/投资/受限/应收） | Overview.vue |
| **资产** | 净资产走势（43个月回填） | Overview.vue |
| **资产** | 活期资产走势（现金+投资） | Overview.vue |
| **预算** | 预算执行率（13分类） | Overview.vue |
| **预算** | 预算编辑 | Overview.vue |
| **预算** | 超支预警 + 智能建议 | data_loader.py |
| **分析** | 支出分类分析（饼图+柱状图+明细） | Spending.vue |
| **分析** | 同比/环比对比 | Spending.vue |
| **分析** | 季节性分析 | Spending.vue |
| **分析** | 收入分析 | Income.vue |
| **分析** | 持仓盈亏 | Portfolio.vue |
| **分析** | 消费习惯（6维度+AI洞察） | Habits.vue |
| **预测** | Prophet 月度支出预测 | Forecast.vue |
| **预测** | 预测回测（MAPE+对比图表） | Forecast.vue |
| **模拟** | 正向模拟（资产增长曲线） | Simulation.vue |
| **模拟** | 反向计算（目标→月存/年数/收益率） | Simulation.vue |
| **报告** | 月度财务报告 | Report.vue |
| **报告** | 年度报告 | /api/report/annual |
| **目标** | 攒钱目标设定/追踪 | Goals.vue |
| **预警** | 预算超支/流动性/异常检测 | Alerts.vue |
| **预警** | 轮询推送（5分钟） | App.vue |
| **AI** | 自然语言问答（LLM+规则引擎） | AIQuery.vue |
| **AI** | SQL 工具（LLM 可查历史明细） | sql_tool.py |
| **AI** | 多轮对话 | query_engine.py |
| **AI** | 智能分类推荐 | data_loader.py |
| **AI** | 消费习惯 AI 洞察（带缓存） | data_loader.py |
| **设置** | LLM API 配置（加密存储） | Settings.vue |
| **安全** | bcrypt 密码认证 | auth.py |
| **安全** | 登录限速（5次/IP/5分钟） | auth.py |
| **安全** | Token 持久化 | auth.py |
| **安全** | API 认证中间件 | app.py |
| **数据** | JSON 原子写入 + 文件锁 | data_loader.py |
| **数据** | SQLite 事务迁移 | db.py |
| **数据** | CSV 去重 | data_loader.py |
| **数据** | 记账数据同步到分析模型 | data_loader.py |

### 未完成功能（Todo）

| 优先级 | 功能 | 说明 |
|--------|------|------|
| P1 | 多币种支持 | 外币消费自动换算 |
| P1 | 推送通知 | 邮件/微信推送（需外部服务） |
| P1 | 数据云备份 | 防止本地数据丢失 |
| P2 | OCR 小票识别 | 拍照自动录入 |
| P2 | 家庭共享 | 多人共用账本 |
| P2 | AI 财务顾问 | 基于数据给出个性化理财建议 |
| P3 | 移动端 App | PWA 或小程序 |

---

## 四、问题列表（已修复）

| 编号 | 级别 | 问题 | 修复方案 |
|------|------|------|---------|
| C1 | CRITICAL | datetime 导入缺失 | 添加 import |
| C2 | CRITICAL | API 无认证 | before_request 中间件 |
| C3 | CRITICAL | 账户余额更新无检查 | 返回值检查 + 警告提示 |
| C4 | CRITICAL | JSON 并发不安全 | threading lock + 原子写入 |
| H1 | HIGH | 信用卡还款超额静默截断 | 返回 overpaid 标志 + warning |
| H2 | HIGH | DB写入和余额更新非原子 | balance_ok 检查 |
| H4 | HIGH | float() 无 try/except | API 端点添加异常处理 |
| H5 | HIGH | 无负数校验 | 金额必须大于0 |
| H6 | HIGH | created_at 毫秒冲突 | 改用数据库自增 ID |
| M1 | MEDIUM | 信用卡余额与配置不同步 | 净资产计算改用实时 JSON |
| M2 | MEDIUM | update_assets 忽略新账户 | 新账户自动添加 |
| M3 | MEDIUM | Goal ID 重复 | 改用时间戳 |
| M5 | MEDIUM | 每次记账调用重型 get_overview | 改用轻量级计算 |
| M8 | MEDIUM | debug=True 暴露调试器 | 环境变量控制 |
| M9 | MEDIUM | DB 错误静默 | 添加日志输出 |

### 待处理问题

| 编号 | 级别 | 问题 | 说明 |
|------|------|------|------|
| M10 | MEDIUM | 回填使用硬编码比例 | 资产分层比例可调整 |
| L22 | LOW | get_quick_stats 混合收支 | 收入/支出应分开统计 |
| L23 | LOW | _conversations 无上限增长 | 可添加 TTL 机制 |
| L24 | LOW | 路径遍历风险 | Flask 已有保护，风险低 |
| L25 | LOW | 限速状态不持久 | 重启后限速重置 |

---

## 五、代码统计

| 类型 | 文件数 | 说明 |
|------|--------|------|
| 后端 Python | 9 | app.py, auth.py, config.py, data_loader.py, db.py, llm.py, pipeline.py, query_engine.py, sql_tool.py |
| 前端 Vue | 14 | App.vue + 12 个视图 + AiFloat 组件 |
| 前端 JS | 2 | api/index.js, utils/chart.js |
| 脚本 | 2 | prophet_forecast.py, clean_round4.py |
| 文档 | 3 | PRD.md, IMPROVEMENT_PLAN.md, PRODUCT_STATUS.md |

---

## 六、下次会话建议

| 优先级 | 任务 |
|--------|------|
| **立即** | 推送代码到 GitHub（网络恢复后） |
| **本周** | 图表交互优化（缩放、拖拽、数据下钻） |
| **下周** | 多币种支持、推送通知 |
| **后续** | OCR 小票识别、数据云备份 |
