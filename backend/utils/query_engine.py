"""
QueryEngine V2: LLM-driven intent recognition with SQL tool and multi-turn support.
Falls back to rule-based engine when LLM is not configured.
"""

import json, re
from datetime import datetime
from utils import llm, sql_tool


def _format_amount(v):
    if v is None:
        return "¥0"
    v = float(v)
    if abs(v) >= 10000:
        return f"¥{v/10000:.2f}万"
    return f"¥{v:,.0f}"


# ============================================================
# Time range resolver (supports ranges, not just single month)
# ============================================================

def _resolve_time_range(text):
    """
    Extract time range from question.
    Returns: {"type": "single", "month": "YYYY-MM"} or {"type": "range", "start": "YYYY-MM", "end": "YYYY-MM"}
    """
    now = datetime.now()
    cur_y, cur_m = now.year, now.month
    cur = f"{cur_y}-{cur_m:02d}"

    # Range patterns
    if re.search(r"(近|最近|过去)\s*(\d+)\s*个月?", text):
        m = re.search(r"(近|最近|过去)\s*(\d+)\s*个月?", text)
        n = int(m.group(2))
        sm = cur_m - n + 1
        sy = cur_y
        while sm <= 0:
            sm += 12
            sy -= 1
        return {"type": "range", "start": f"{sy}-{sm:02d}", "end": cur}

    if "今年" in text or "本年" in text:
        return {"type": "range", "start": f"{cur_y}-01", "end": cur}

    if "去年" in text:
        return {"type": "range", "start": f"{cur_y-1}-01", "end": f"{cur_y-1}-12"}

    if re.search(r"(上|上个?)(季度|Q)", text):
        q = (cur_m - 1) // 3  # previous quarter
        if q == 0:
            q = 4
            y = cur_y - 1
        else:
            y = cur_y
        sm = (q - 1) * 3 + 1
        em = q * 3
        return {"type": "range", "start": f"{y}-{sm:02d}", "end": f"{y}-{em:02d}"}

    if re.search(r"(这个?季度|本季度|这Q)", text):
        q = (cur_m - 1) // 3 + 1
        sm = (q - 1) * 3 + 1
        em = min(q * 3, cur_m)
        return {"type": "range", "start": f"{cur_y}-{sm:02d}", "end": f"{cur_y}-{em:02d}"}

    # Single month patterns
    for kw, val in [("本月", None), ("这个月", None), ("上月", "prev"), ("上个月", "prev"),
                     ("下月", "next"), ("下个月", "next")]:
        if kw in text:
            if val is None:
                return {"type": "single", "month": cur}
            elif val == "prev":
                pm, py = cur_m - 1, cur_y
                if pm == 0:
                    pm, py = 12, cur_y - 1
                return {"type": "single", "month": f"{py}-{pm:02d}"}
            elif val == "next":
                nm, ny = cur_m + 1, cur_y
                if nm == 13:
                    nm, ny = 1, cur_y + 1
                return {"type": "single", "month": f"{ny}-{nm:02d}"}

    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月?", text)
    if m:
        return {"type": "single", "month": f"{m.group(1)}-{int(m.group(2)):02d}"}
    m = re.search(r"(\d{4})-(\d{1,2})", text)
    if m:
        return {"type": "single", "month": f"{m.group(1)}-{int(m.group(2)):02d}"}

    return {"type": "single", "month": cur}


_CATEGORY_KEYWORDS = {
    "餐饮": ["吃饭", "餐饮", "外卖", "堂食", "饮食", "吃喝", "饭", "餐厅", "食堂"],
    "交通": ["交通", "打车", "加油", "地铁", "公交", "出行", "车费"],
    "购物": ["购物", "买东西", "网购", "淘宝", "京东", "消费"],
    "居住": ["房租", "居住", "水电", "物业", "住房", "水费", "电费"],
    "娱乐": ["娱乐", "电影", "游戏", "视频会员", "ktv"],
    "社交": ["社交", "聚餐", "请客", "送礼", "红包"],
    "旅游": ["旅游", "旅行", "机票", "酒店", "度假", "景点"],
    "车辆": ["车辆", "车贷", "养车", "修车", "停车", "洗车"],
    "医疗": ["医疗", "看病", "医院", "药", "体检", "医保"],
    "个护": ["理发", "个护", "美容", "护肤"],
    "学习": ["学习", "课程", "书", "培训", "教育"],
    "数字消费": ["话费", "流量", "数字", "会员", "订阅"],
}


def _resolve_category(text):
    for cat, kws in _CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                return cat
    return None


# ============================================================
# QueryEngine
# ============================================================

class QueryEngine:
    def __init__(self, data_loader):
        self.dl = data_loader

    def answer(self, question, history=None):
        """
        Main entry point. history is optional list of prior messages for multi-turn.
        """
        question = question.strip()
        if llm.is_configured():
            return self._llm_answer(question, history)
        return self._rule_answer(question)

    # --------------------------------------------------------
    # LLM-driven path
    # --------------------------------------------------------

    def _llm_answer(self, question, history=None):
        context = self._build_context()
        schema = sql_tool.get_schema_description()

        # Build conversation history string
        history_str = ""
        if history:
            recent = history[-10:]  # last 5 turns
            history_str = "\n\n对话历史：\n"
            for msg in recent:
                role = "用户" if msg["role"] == "user" else "助手"
                history_str += f"{role}: {msg['content']}\n"

        system_prompt = (
            "你是一个友善的个人财务助手，像朋友一样和用户聊天。\n\n"
            "## 风格\n"
            "- 用轻松自然的语气，像朋友间的对话\n"
            "- 可以用 emoji，但不要过度\n"
            "- 先说结论，再解释原因\n"
            "- 金额用中文（如 1.2万、500块）\n"
            "- 如果发现异常或有建议，主动提醒用户\n"
            "- 回答不要太长，3-5句话就够\n"
            "- 不确定就说不知道，不要编造数据\n"
            "- 可以给出具体的省钱建议和预算优化方案\n\n"
            "## 当前财务数据\n" + context + history_str + "\n\n"
            "## SQL 查询工具\n"
            "如果用户问的是具体的某笔消费、某个时间段的明细、或需要聚合计算，"
            "你可以通过输出 JSON 来调用 SQL 查询。格式：\n"
            '{"tool": "sql", "sql": "SELECT ... FROM transactions WHERE ..."}\n'
            "表结构：" + schema + "\n"
            "只能用 SELECT，不能修改数据。如果不需查数据库，直接回答即可。\n\n"
            "## 时间理解\n"
            "- 本月/这个月 = 当前月\n"
            "- 上月/上个月 = 上个月\n"
            "- 最近N月 = range\n"
            "- 今年 = 今年1月至今\n"
            "- 去年 = 去年全年\n"
            "- 月底 = 预测本月总额\n"
        )

        response = llm.ask(question, system_prompt)
        if not response:
            return self._rule_answer(question)

        # Check if LLM wants to use SQL tool
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[^{}]*"tool"\s*:\s*"sql"[^{}]*\}', response)
            if json_match:
                tool_call = json.loads(json_match.group())
                sql = tool_call.get("sql", "")
                if sql:
                    sql_result = sql_tool.query_sql(sql)
                    # Get a second LLM call with the SQL result
                    followup_prompt = (
                        f"用户问：{question}\n\n"
                        f"SQL 查询结果：\n{sql_result}\n\n"
                        "请根据查询结果简洁回答用户问题。金额用中文。"
                    )
                    followup = llm.ask(followup_prompt, "你是财务助手，根据查询结果简洁回答。")
                    if followup:
                        return followup
                    # Fallback: return raw result
                    return f"查询结果：{sql_result}"
        except (json.JSONDecodeError, AttributeError):
            pass

        return response

    # --------------------------------------------------------
    # Rule-based fallback (preserved for when LLM is off)
    # --------------------------------------------------------

    def _rule_answer(self, question):
        intent, entities = self._parse(question)
        handlers = {
            "total_expense": self._total_expense,
            "category_expense": self._category_expense,
            "total_income": self._total_income,
            "net_worth": self._net_worth,
            "budget_status": self._budget_status,
            "budget_remaining": self._budget_remaining,
            "top_category": self._top_category,
            "comparison": self._comparison,
            "portfolio": self._portfolio,
            "savings_rate": self._savings_rate,
            "liquidity": self._liquidity,
            "health": self._health,
            "monthly_report": self._monthly_report,
            "spending_trend": self._spending_trend,
            "prediction": self._prediction,
            "advice": self._advice,
            "help": self._help,
        }
        handler = handlers.get(intent, self._fallback)
        try:
            return handler(question, entities)
        except Exception as e:
            return f"查询出错：{str(e)}"

    def _parse(self, q):
        intent = "help"
        time_range = _resolve_time_range(q)
        entities = {"time_range": time_range, "category": _resolve_category(q)}

        if any(w in q for w in ["帮助", "能做什么", "怎么用", "功能", "你会什么"]):
            intent = "help"
        elif any(w in q for w in ["预测", "预计", "估计", "月底", "下个月会"]):
            intent = "prediction"
        elif any(w in q for w in ["建议", "怎么省", "省钱", "控制", "优化", "怎么花", "帮我"]):
            intent = "advice"
        elif any(w in q for w in ["趋势", "走势", "逐月", "变化趋势"]):
            intent = "spending_trend"
        elif any(w in q for w in ["净资产", "总资产", "我有多少钱", "身家"]):
            intent = "net_worth"
        elif any(w in q for w in ["流动性", "能撑", "能花多少", "可用资金"]):
            intent = "liquidity"
        elif any(w in q for w in ["健康评分", "财务健康", "评分"]):
            intent = "health"
        elif any(w in q for w in ["储蓄率", "存钱率"]):
            intent = "savings_rate"
        elif any(w in q for w in ["持仓", "盈亏", "基金赚", "股票赚", "投资赚", "亏了"]):
            intent = "portfolio"
        elif any(w in q for w in ["最多", "最大", "最高", "大头", "主要花"]):
            intent = "top_category"
        elif any(w in q for w in ["预算剩", "还剩", "还能花", "预算余"]):
            intent = "budget_remaining"
        elif any(w in q for w in ["预算", "超支"]):
            intent = "budget_status"
        elif any(w in q for w in ["同比", "环比", "比上月", "比去年", "变化"]):
            intent = "comparison"
        elif any(w in q for w in ["收入", "工资", "赚了", "发了"]):
            intent = "total_income"
        elif entities["category"] and any(w in q for w in ["花了", "支出", "用了", "多少", "费用"]):
            intent = "category_expense"
        elif any(w in q for w in ["花了多少钱", "支出多少", "总支出", "花了多少", "总花费"]):
            intent = "total_expense"
        elif any(w in q for w in ["花了", "支出", "用了"]):
            intent = "category_expense" if entities["category"] else "total_expense"
        elif any(w in q for w in ["报告", "月报", "月度"]):
            intent = "monthly_report"

        return intent, entities

    def _get_month_data(self, month):
        df = self.dl.load_v4()
        valid = df[df["valid_for_stats"] == "True"]
        exp = valid[(valid["corrected_type"] == "支出") & (valid["month"] == month)]
        inc = valid[(valid["corrected_type"] == "收入") & (valid["month"] == month)]
        return exp, inc

    def _get_range_data(self, time_range):
        """Get data for a time range."""
        df = self.dl.load_v4()
        valid = df[df["valid_for_stats"] == "True"]
        if time_range["type"] == "range":
            mask = (valid["month"] >= time_range["start"]) & (valid["month"] <= time_range["end"])
        else:
            mask = valid["month"] == time_range["month"]
        subset = valid[mask]
        exp = subset[subset["corrected_type"] == "支出"]
        inc = subset[subset["corrected_type"] == "收入"]
        return exp, inc

    # --- Rule-based handlers ---

    def _total_expense(self, q, e):
        tr = e["time_range"]
        exp, _ = self._get_range_data(tr)
        total = exp["cny_amount"].sum()
        if tr["type"] == "range":
            return f"{tr['start']} ~ {tr['end']} 总支出：{_format_amount(total)}（共 {len(exp)} 笔）"
        return f"{tr['month']} 总支出：{_format_amount(total)}（共 {len(exp)} 笔）"

    def _category_expense(self, q, e):
        tr = e["time_range"]
        cat = e["category"]
        if not cat:
            return "请告诉我具体类目，例如「这个月吃饭花了多少钱」"
        exp, _ = self._get_range_data(tr)
        sub = exp[exp["category_l1"] == cat]
        total = sub["cny_amount"].sum()
        label = f"{tr['start']}~{tr['end']}" if tr["type"] == "range" else tr["month"]
        return f"{label} {cat} 支出：{_format_amount(total)}（共 {len(sub)} 笔）"

    def _total_income(self, q, e):
        tr = e["time_range"]
        _, inc = self._get_range_data(tr)
        total = inc["cny_amount"].sum()
        items = inc.groupby("category_l1")["cny_amount"].sum()
        detail = "，".join(f"{k} {_format_amount(v)}" for k, v in items.items())
        label = f"{tr['start']}~{tr['end']}" if tr["type"] == "range" else tr["month"]
        return f"{label} 总收入：{_format_amount(total)}（{detail}）"

    def _net_worth(self, q, e):
        ov = self.dl.get_overview()
        return (
            f"净资产：{_format_amount(ov['net_worth'])}  "
            f"总资产：{_format_amount(ov['total_assets'])}  "
            f"可用资金：{_format_amount(ov['cash_and_liquid'])}  "
            f"投资：{_format_amount(ov['investment'])}  "
            f"受限：{_format_amount(ov['restricted'])}"
        )

    def _budget_status(self, q, e):
        tr = e["time_range"]
        month = tr["month"] if tr["type"] == "single" else tr["end"]
        bd = self.dl.get_budget_status(month)
        over = [i for i in bd["items"] if i["ratio"] >= 100]
        warn = [i for i in bd["items"] if 80 <= i["ratio"] < 100]
        parts = [f"总预算执行：{bd['total_ratio']}%（{_format_amount(bd['total_actual'])}/{_format_amount(bd['total_budget'])}）"]
        if over:
            parts.append(f"已超支：{'、'.join(i['category'] for i in over)}")
        if warn:
            parts.append(f"接近上限：{'、'.join(i['category'] for i in warn)}")
        return "；".join(parts)

    def _budget_remaining(self, q, e):
        tr = e["time_range"]
        month = tr["month"] if tr["type"] == "single" else tr["end"]
        bd = self.dl.get_budget_status(month)
        remaining = bd["total_budget"] - bd["total_actual"]
        return f"{month} 预算剩余：{_format_amount(max(remaining, 0))}（总预算 {_format_amount(bd['total_budget'])}，已用 {bd['total_ratio']}%）"

    def _top_category(self, q, e):
        tr = e["time_range"]
        exp, _ = self._get_range_data(tr)
        top = exp.groupby("category_l1")["cny_amount"].sum().sort_values(ascending=False).head(3)
        items = [f"{i+1}. {k} {_format_amount(v)}" for i, (k, v) in enumerate(top.items())]
        label = f"{tr['start']}~{tr['end']}" if tr["type"] == "range" else tr["month"]
        return f"{label} 支出 TOP3：{'，'.join(items)}"

    def _comparison(self, q, e):
        tr = e["time_range"]
        month = tr["month"] if tr["type"] == "single" else tr["end"]
        exp, _ = self._get_month_data(month)
        cur_total = exp["cny_amount"].sum()

        parts_ = month.split("-")
        py, pm = int(parts_[0]), int(parts_[1])
        prev = f"{py-1}-{pm:02d}" if pm == 1 else f"{py}-{pm-1:02d}"
        exp_p, _ = self._get_month_data(prev)
        prev_total = exp_p["cny_amount"].sum()
        mom_pct = f"{(cur_total - prev_total) / prev_total * 100:.1f}%" if prev_total else "N/A"

        yoy_m = f"{py-1}-{pm:02d}"
        exp_y, _ = self._get_month_data(yoy_m)
        yoy_total = exp_y["cny_amount"].sum()
        yoy_pct = f"{(cur_total - yoy_total) / yoy_total * 100:.1f}%" if yoy_total else "N/A"

        return f"{month} 支出 {_format_amount(cur_total)}，环比（vs {prev}）：{mom_pct}，同比（vs {yoy_m}）：{yoy_pct}"

    def _portfolio(self, q, e):
        port = self.dl.get_portfolio()
        total_pnl = port["total_pnl"]
        total_pct = port["total_pnl_pct"]
        items = port["items"]
        detail = "，".join(
            f"{i['account']} {'涨' if i['pnl'] >= 0 else '跌'}{abs(i['pnl_pct']):.1f}%（{_format_amount(i['pnl'])}）"
            for i in items
        )
        return f"投资组合 {'盈利' if total_pnl >= 0 else '亏损'} {_format_amount(abs(total_pnl))}（{total_pct:.1f}%），{detail}"

    def _savings_rate(self, q, e):
        ov = self.dl.get_overview()
        inc = ov["monthly_income"]
        exp = ov["avg_monthly_expense"]
        rate = (inc - exp) / inc * 100 if inc else 0
        return f"月均储蓄率：{rate:.1f}%（收入 {_format_amount(inc)}，支出 {_format_amount(exp)}，结余 {_format_amount(inc - exp)}）"

    def _liquidity(self, q, e):
        ov = self.dl.get_overview()
        cov = ov["liquidity_coverage"]
        cash = ov["cash_and_liquid"]
        return f"流动性覆盖率：{cov} 个月（可用资金 {_format_amount(cash)}，月均支出 {_format_amount(ov['avg_monthly_expense'])}）"

    def _health(self, q, e):
        h = self.dl.get_financial_health()
        items = "，".join(f"{i['name']} {i['score']}分" for i in h["items"])
        return f"财务健康评分：{h['total_score']}分（{h['level']}，{items}）"

    def _monthly_report(self, q, e):
        tr = e["time_range"]
        month = tr["month"] if tr["type"] == "single" else tr["end"]
        r = self.dl.get_monthly_report(month)
        return (
            f"{r['month']} 月度报告：收入 {_format_amount(r['income'])}，"
            f"支出 {_format_amount(r['expense'])}，"
            f"结余 {_format_amount(r['balance'])}，"
            f"储蓄率 {r['savings_rate']}%，"
            f"环比 {r['mom_change']}%，"
            f"同比 {r['yoy_change']}%"
        )

    def _spending_trend(self, q, e):
        tr = e["time_range"]
        trend = self.dl.get_monthly_trend()
        if tr["type"] == "range":
            trend = [t for t in trend if tr["start"] <= t["month"] <= tr["end"]]
        else:
            trend = trend[-12:]
        items = [f"{t['month']} {_format_amount(t['expense'])}" for t in trend]
        return f"支出趋势：{' → '.join(items)}"

    def _prediction(self, q, e):
        """预测本月支出"""
        from datetime import datetime
        now = datetime.now()
        day = now.day
        month = now.strftime("%Y-%m")

        exp, _ = self._get_month_data(month)
        current_total = exp["cny_amount"].sum()

        # 历史月均
        trend = self.dl.get_monthly_trend()
        if len(trend) > 1:
            avg = sum(t["expense"] for t in trend[:-1]) / max(len(trend) - 1, 1)
        else:
            avg = current_total

        if day > 0:
            projected = current_total / day * 30
            deviation = (projected - avg) / avg * 100 if avg > 0 else 0
            if deviation > 15:
                return f"按当前速度，{month} 月底预计支出 {_format_amount(projected)}，比历史月均高 {deviation:.0f}%，建议控制消费 📉"
            elif deviation < -15:
                return f"按当前速度，{month} 月底预计支出 {_format_amount(projected)}，比历史月均低 {abs(deviation):.0f}%，这个月控制得不错 👍"
            else:
                return f"按当前速度，{month} 月底预计支出 {_format_amount(projected)}，跟历史月均差不多，保持就好 😊"
        return f"本月已支出 {_format_amount(current_total)}"

    def _advice(self, q, e):
        """给出省钱/优化建议"""
        ov = self.dl.get_overview()
        bd = self.dl.get_budget_status()
        suggestions = []

        # 预算相关
        over = [i for i in bd["items"] if i["ratio"] >= 100]
        warn = [i for i in bd["items"] if 80 <= i["ratio"] < 100]
        if over:
            for i in over:
                suggestions.append(f"⚠️ {i['category']}已超支，建议暂停该类消费")
        if warn:
            for i in warn:
                remaining = i["budget"] - i["actual"]
                suggestions.append(f"⚡ {i['category']}快到预算上限了，只剩 {_format_amount(remaining)}")

        # 流动性
        if ov["liquidity_coverage"] < 3:
            suggestions.append("💧 流动性偏低，建议存一些应急资金")

        # 储蓄率
        if ov["monthly_income"] > 0:
            rate = (ov["monthly_income"] - ov["avg_monthly_expense"]) / ov["monthly_income"] * 100
            if rate < 20:
                suggestions.append(f"💰 储蓄率只有 {rate:.0f}%，建议每月至少存收入的 20%")

        if not suggestions:
            suggestions.append("目前财务状况看起来不错，继续保持！💪")

        return "根据你的财务状况，我有这些建议：\n" + "\n".join(f"  {s}" for s in suggestions[:5])

    def _help(self, q=None, e=None):
        return (
            "你可以问我：\n"
            "• 「我这个月花了多少钱」\n"
            "• 「上个月吃饭花了多少」\n"
            "• 「最近3个月支出趋势」\n"
            "• 「这个月预计花多少」\n"
            "• 「我的净资产有多少」\n"
            "• 「预算还剩多少」\n"
            "• 「我的基金赚了还是亏了」\n"
            "• 「帮我分析一下消费习惯」\n"
            "• 「怎么省钱」\n"
            "• 「帮我查一下上个月最大的3笔消费」（需要LLM）"
        )

    def _fallback(self, q, e):
        return f"不太理解「{q}」。试试说「帮助」查看我能回答的问题。"

    # --------------------------------------------------------
    # Context builder (shared by LLM path)
    # --------------------------------------------------------

    def _build_context(self):
        ov = self.dl.get_overview()
        budget = self.dl.get_budget_status()
        port = self.dl.get_portfolio()
        health = self.dl.get_financial_health()
        trend = self.dl.get_monthly_trend()
        recent = trend[-6:] if trend else []

        budget_items = {
            i["category"]: {"预算": i["budget"], "实际": i["actual"], "执行率": f"{i['ratio']}%"}
            for i in budget["items"]
        }
        port_items = {
            i["account"]: {"成本": i["cost"], "市值": i["current"], "盈亏": i["pnl"], "收益率": f"{i['pnl_pct']}%"}
            for i in port["items"]
        }

        # 本月数据
        from datetime import datetime
        now = datetime.now()
        month = now.strftime("%Y-%m")
        try:
            month_bd = self.dl.get_budget_status(month)
            month_expense = month_bd["total_actual"]
            month_budget = month_bd["total_budget"]
            month_ratio = month_bd["total_ratio"]
        except Exception:
            month_expense = ov["monthly_expense"]
            month_budget = 0
            month_ratio = 0

        # 预测
        day = now.day
        if day > 0 and ov["avg_monthly_expense"] > 0:
            projected = month_expense / day * 30
        else:
            projected = month_expense

        return json.dumps({
            "净资产": ov["net_worth"],
            "总资产": ov["total_assets"],
            "可用资金": ov["cash_and_liquid"],
            "投资资产": ov["investment"],
            "受限资产": ov["restricted"],
            "月均收入": ov["monthly_income"],
            "月均支出": ov["avg_monthly_expense"],
            "本月支出": month_expense,
            "本月预算": month_budget,
            "本月预算执行率": f"{month_ratio}%",
            "本月预测支出": round(projected, 2),
            "流动性覆盖率": f"{ov['liquidity_coverage']}个月",
            "预算执行": {
                "总预算": budget["total_budget"],
                "已花费": budget["total_actual"],
                "执行率": f"{budget['total_ratio']}%",
                "分类明细": budget_items,
            },
            "投资组合": {"总盈亏": f"{port['total_pnl_pct']}%", "明细": port_items},
            "健康评分": f"{health['total_score']}分（{health['level']}）",
            "近6月收支趋势": [
                {"月": t["month"], "支出": t["expense"], "收入": t["income"], "结余": t["balance"]}
                for t in recent
            ],
        }, ensure_ascii=False, indent=2)
