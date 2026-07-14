<template>
  <div class="status-page">
    <!-- Player card -->
    <div class="player-card">
      <div class="player-avatar">
        <span style="font-size:40px">{{ levelEmoji }}</span>
      </div>
      <div class="player-info">
        <div class="player-name">财务达人</div>
        <div class="player-level">
          <span class="level-badge">Lv.{{ level }}</span>
          <span class="level-title">{{ levelTitle }}</span>
        </div>
      </div>
    </div>

    <!-- Core stats -->
    <div class="stats-section">
      <div class="section-title">核心属性</div>
      
      <div class="stat-row">
        <div class="stat-icon">💰</div>
        <div class="stat-info">
          <div class="stat-label">净资产</div>
          <div class="stat-bar">
            <div class="stat-fill" :style="{ width: netWorthPercent + '%', background: 'linear-gradient(90deg, #67c23a, #85ce61)' }"></div>
          </div>
        </div>
        <div class="stat-value">{{ formatMoney(ov.net_worth) }}</div>
      </div>

      <div class="stat-row">
        <div class="stat-icon">❤️</div>
        <div class="stat-info">
          <div class="stat-label">流动性</div>
          <div class="stat-bar">
            <div class="stat-fill" :style="{ width: liquidityPercent + '%', background: liquidityColor }"></div>
          </div>
          <div class="stat-desc">{{ ov.liquidity_coverage }} 个月（{{ liquidityStatus }}）</div>
        </div>
        <div class="stat-value" :style="{ color: liquidityColor }">{{ ov.liquidity_coverage }}</div>
      </div>

      <div class="stat-row">
        <div class="stat-icon">📊</div>
        <div class="stat-info">
          <div class="stat-label">预算使用</div>
          <div class="stat-bar">
            <div class="stat-fill" :style="{ width: Math.min(budgetRatio, 100) + '%', background: budgetColor }"></div>
          </div>
          <div class="stat-desc">{{ formatMoney(bd.total_actual) }} / {{ formatMoney(bd.total_budget) }}</div>
        </div>
        <div class="stat-value" :style="{ color: budgetColor }">{{ bd.total_ratio }}%</div>
      </div>

      <div class="stat-row">
        <div class="stat-icon">💹</div>
        <div class="stat-info">
          <div class="stat-label">投资收益</div>
          <div class="stat-bar">
            <div class="stat-fill" :style="{ width: investReturnPercent + '%', background: investColor }"></div>
          </div>
          <div class="stat-desc">持仓 {{ formatMoney(port.total_current) }}</div>
        </div>
        <div class="stat-value" :style="{ color: investColor }">{{ port.total_pnl_pct }}%</div>
      </div>
    </div>

    <!-- Key accounts -->
    <div class="stats-section">
      <div class="section-title">账户状态</div>
      <div class="account-list">
        <div class="account-item" v-for="acc in keyAccounts" :key="acc.name">
          <div class="account-icon">{{ acc.icon }}</div>
          <div class="account-info">
            <div class="account-name">{{ acc.name }}</div>
            <div class="account-bar">
              <div class="account-fill" :style="{ width: acc.percent + '%', background: acc.color }"></div>
            </div>
          </div>
          <div class="account-amount">{{ formatMoney(acc.amount) }}</div>
        </div>
      </div>
    </div>

    <!-- Credit card status -->
    <div class="stats-section" v-if="cc.balance > 0">
      <div class="section-title">💳 信用卡</div>
      <div class="cc-status">
        <div class="cc-balance">
          <span class="cc-label">待还</span>
          <span class="cc-amount">¥{{ cc.balance.toLocaleString() }}</span>
        </div>
        <div class="cc-bar">
          <div class="cc-fill" :style="{ width: ccPercent + '%' }"></div>
        </div>

        <!-- Repayment -->
        <div class="cc-repay">
          <button v-if="!showRepay" @click="showRepay = true" class="repay-btn">还款</button>
          <div v-else class="repay-form">
            <span style="font-size:12px;color:#909399">从招行储蓄卡还款</span>
            <div class="repay-row">
              <input v-model="repayAmount" type="number" placeholder="金额" class="repay-input" />
              <button @click="doRepay" :disabled="repayLoading" class="repay-confirm">
                {{ repayLoading ? '还款中...' : '确认还款' }}
              </button>
              <button @click="showRepay = false; repayAmount = null" class="repay-cancel">取消</button>
            </div>
          </div>
        </div>

        <div class="cc-history">
          <div v-for="h in cc.history.slice(0, 3)" :key="h.created_at" class="cc-item">
            <span>{{ h.date.slice(0, 10) }} {{ h.note }}</span>
            <span :style="{ color: h.type === '消费' ? '#f56c6c' : '#67c23a' }">
              {{ h.type === '消费' ? '+' : '-' }}¥{{ h.amount }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Monthly Trend -->
    <div class="stats-section">
      <div class="section-title">📈 月度趋势</div>
      <div ref="trendChart" style="height:180px"></div>
      <div v-if="!monthlyData.length" style="text-align:center;color:#999;padding:20px;font-size:13px">
        暂无月度数据
      </div>
    </div>

    <!-- Status Analysis -->
    <div class="stats-section ai-section">
      <div class="section-title">📋 状态评估</div>
      <div v-if="aiLoading" class="ai-loading">分析中...</div>
      <div v-else-if="aiAnalysis" class="ai-text">{{ aiAnalysis }}</div>
      <button @click="generateAiAnalysis" class="refresh-btn">刷新分析</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { fetchOverview, fetchBudget, fetchPortfolio, fetchFinancialHealth, fetchCreditCard, fetchMonthly, payCreditCard } from '../api/index.js'
import { createChart } from '../utils/chart.js'

const ov = ref({ net_worth: 0, liquidity_coverage: 0, monthly_income: 0, monthly_expense: 0, layers: [], cash_and_liquid: 0 })
const bd = ref({ total_ratio: 0, total_actual: 0, total_budget: 0 })
const port = ref({ total_pnl_pct: 0, total_current: 0, total_cost: 0 })
const health = ref({ total_score: 0, level: '' })
const cc = ref({ balance: 0, history: [] })
const showRepay = ref(false)
const repayAmount = ref(null)
const repayLoading = ref(false)
const monthlyData = ref([])
const trendChart = ref(null)
const aiAnalysis = ref('')
const aiLoading = ref(false)

const formatMoney = v => {
  if (v === null || v === undefined) return '¥0'
  return '¥' + Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// Level system
const level = computed(() => {
  const score = health.value.total_score || 0
  if (score >= 90) return 10
  if (score >= 80) return 8
  if (score >= 70) return 6
  if (score >= 60) return 4
  if (score >= 50) return 3
  return 1
})

const levelTitle = computed(() => {
  const l = level.value
  if (l >= 8) return '财务大师'
  if (l >= 6) return '理财达人'
  if (l >= 4) return '记账新手'
  return '财务小白'
})

const levelEmoji = computed(() => {
  const l = level.value
  if (l >= 8) return '👑'
  if (l >= 6) return '🏆'
  if (l >= 4) return '⭐'
  return '🌱'
})

// Stats calculations
const netWorthPercent = computed(() => Math.min(ov.value.net_worth / 500000 * 100, 100))
const liquidityPercent = computed(() => Math.min(ov.value.liquidity_coverage / 6 * 100, 100))
const budgetRatio = computed(() => bd.value.total_ratio || 0)
const investReturnPercent = computed(() => {
  const pct = port.value.total_pnl_pct || 0
  return Math.min(Math.max(pct, 0), 100)
})

// Key accounts
const keyAccounts = computed(() => {
  const assets = ov.value.assets || []
  const find = name => assets.find(a => a.name === name)
  const wechat = find('微信零钱')
  const cmb = find('招行储蓄卡')
  const total = ov.value.net_worth || 1

  return [
    { name: '微信零钱', icon: '💚', amount: wechat?.amount || 0, percent: (wechat?.amount || 0) / total * 100, color: '#67c23a' },
    { name: '招行储蓄卡', icon: '🏦', amount: cmb?.amount || 0, percent: (cmb?.amount || 0) / total * 100, color: '#409eff' },
    { name: '信用卡', icon: '💳', amount: -cc.value.balance, percent: cc.value.balance / total * 100, color: '#f56c6c' },
  ]
})

const ccPercent = computed(() => {
  const max = ov.value.net_worth || 1
  return Math.min(cc.value.balance / max * 100, 100)
})

async function doRepay() {
  if (!repayAmount.value || repayAmount.value <= 0) {
    return
  }
  repayLoading.value = true
  try {
    const res = await payCreditCard({ amount: repayAmount.value, account: '招行储蓄卡' })
    if (res.error) {
      alert(res.error)
      return
    }
    // Refresh credit card data
    cc.value = await fetchCreditCard()
    showRepay.value = false
    repayAmount.value = null
    // Refresh overview (asset balance changed)
    ov.value = await fetchOverview()
  } catch {}
  repayLoading.value = false
}

// Colors
const liquidityColor = computed(() => {
  const cov = ov.value.liquidity_coverage
  if (cov >= 6) return '#67c23a'
  if (cov >= 3) return '#e6a23c'
  return '#f56c6c'
})

const liquidityStatus = computed(() => {
  const cov = ov.value.liquidity_coverage
  if (cov >= 6) return '充足'
  if (cov >= 3) return '一般'
  return '偏低'
})

const budgetColor = computed(() => {
  const r = bd.value.total_ratio
  if (r >= 100) return '#f56c6c'
  if (r >= 80) return '#e6a23c'
  return '#409eff'
})

const investColor = computed(() => {
  const pct = port.value.total_pnl_pct || 0
  return pct >= 0 ? '#67c23a' : '#f56c6c'
})

const layerEmoji = layer => {
  const map = { '现金/活期': '💵', '投资资产': '📈', '受限资产': '🔒', '应收': '📝' }
  return map[layer] || '💰'
}

async function generateAiAnalysis() {
  aiLoading.value = true
  aiAnalysis.value = ''
  try {
    const parts = []
    const level_val = level.value

    // 1. 流动性分析
    const cov = ov.value.liquidity_coverage
    if (cov < 1) {
      parts.push('🔴 流动性极度危险！仅能覆盖 ' + cov + ' 个月，建议立即增加储蓄')
    } else if (cov < 3) {
      parts.push('🟡 流动性偏低（' + cov + ' 个月），建议存 3-6 个月的应急资金')
    } else if (cov < 6) {
      parts.push('🟢 流动性一般（' + cov + ' 个月），可以适当增加储蓄')
    } else {
      parts.push('✅ 流动性充足（' + cov + ' 个月），财务缓冲良好')
    }

    // 2. 预算分析
    const ratio = bd.value.total_ratio
    if (ratio >= 100) {
      parts.push('🔴 预算已超支！已用 ' + ratio + '%，本月支出需严格控制')
    } else if (ratio >= 80) {
      parts.push('🟡 预算使用 ' + ratio + '%，接近上限，剩余预算有限')
    } else if (ratio >= 50) {
      parts.push('🟢 预算使用 ' + ratio + '%，进度正常')
    } else {
      parts.push('✅ 预算使用仅 ' + ratio + '%，本月消费控制得很好')
    }

    // 3. 信用卡分析
    const ccBal = cc.value.balance
    if (ccBal > 5000) {
      parts.push('🔴 信用卡待还 ¥' + ccBal.toLocaleString() + '，金额较高，建议优先还款')
    } else if (ccBal > 0) {
      parts.push('💳 信用卡待还 ¥' + ccBal.toLocaleString() + '，记得按时还款')
    } else {
      parts.push('✅ 信用卡无欠款')
    }

    // 4. 投资分析
    const pnl = port.value.total_pnl_pct || 0
    if (pnl > 20) {
      parts.push('📈 投资收益 +' + pnl + '%，表现优秀，继续保持')
    } else if (pnl > 0) {
      parts.push('📈 投资收益 +' + pnl + '%，小幅盈利')
    } else if (pnl > -10) {
      parts.push('📉 投资亏损 ' + pnl + '%，可继续观察')
    } else {
      parts.push('📉 投资亏损 ' + pnl + '%，建议审视投资策略')
    }

    // 5. 综合建议
    const issues = parts.filter(p => p.startsWith('🔴')).length
    const warnings = parts.filter(p => p.startsWith('🟡')).length
    if (issues === 0 && warnings === 0) {
      parts.push('💪 综合状态良好，继续保持！')
    } else if (issues > 0) {
      parts.push('⚠️ 有 ' + issues + ' 个问题需要关注，建议优先处理红色标记项')
    }

    aiAnalysis.value = `Lv.${level_val} ${levelTitle.value}（综合评分 ${health.value.total_score} 分）\n\n` + parts.join('\n')
  } catch {}
  aiLoading.value = false
}

onMounted(async () => {
  const [ovData, bdData, portData, healthData, ccData, monthly] = await Promise.all([
    fetchOverview(), fetchBudget(), fetchPortfolio(), fetchFinancialHealth(), fetchCreditCard(), fetchMonthly()
  ])
  ov.value = ovData
  bd.value = bdData
  port.value = portData
  health.value = healthData
  cc.value = ccData
  monthlyData.value = monthly
  generateAiAnalysis()

  // Render trend chart (delay to ensure DOM is ready)
  setTimeout(() => {
    if (trendChart.value && monthlyData.value.length) {
      const data = monthlyData.value.slice(-6) // last 6 months
      createChart(trendChart.value, {
        tooltip: { trigger: 'axis', formatter: params => {
          let s = params[0].axisValue + '<br/>'
          params.forEach(p => { s += p.marker + ' ' + p.seriesName + ': ¥' + Number(p.value).toLocaleString() + '<br/>' })
          return s
        }},
        legend: { bottom: 0, textStyle: { fontSize: 11 } },
        grid: { left: 50, right: 15, top: 15, bottom: 35 },
        xAxis: { type: 'category', data: data.map(d => d.month), axisLabel: { fontSize: 10 } },
        yAxis: { type: 'value', axisLabel: { fontSize: 10, formatter: v => v >= 10000 ? (v/10000).toFixed(0) + '万' : v } },
        series: [
          { name: '支出', type: 'bar', data: data.map(d => d.expense), itemStyle: { color: '#f56c6c' }, barWidth: '40%' },
          { name: '收入', type: 'bar', data: data.map(d => d.income), itemStyle: { color: '#67c23a' }, barWidth: '40%' },
          { name: '结余', type: 'line', data: data.map(d => d.balance), lineStyle: { width: 2 }, itemStyle: { color: '#409eff' } },
        ],
      })
    }
  }, 300)
})
</script>

<style scoped>
.status-page {
  max-width: 500px;
  margin: 0 auto;
  padding: 16px;
}

.player-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: linear-gradient(135deg, #304156 0%, #3a4a5c 100%);
  border-radius: 12px;
  color: #fff;
  margin-bottom: 16px;
}

.player-avatar {
  width: 60px;
  height: 60px;
  background: rgba(255,255,255,0.1);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.player-name {
  font-size: 18px;
  font-weight: bold;
  margin-bottom: 4px;
}

.player-level {
  display: flex;
  align-items: center;
  gap: 8px;
}

.level-badge {
  background: #e6a23c;
  color: #fff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
}

.level-title {
  font-size: 13px;
  color: #bfcbd9;
}

.stats-section {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.section-title {
  font-size: 14px;
  font-weight: bold;
  color: #303133;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f5f5f5;
}

.stat-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid #f5f5f5;
}
.stat-row:last-child { border-bottom: none; }

.stat-icon {
  font-size: 20px;
  width: 28px;
  text-align: center;
}

.stat-info {
  flex: 1;
  min-width: 0;
}

.stat-label {
  font-size: 13px;
  color: #606266;
  margin-bottom: 4px;
}

.stat-bar {
  height: 8px;
  background: #f5f5f5;
  border-radius: 4px;
  overflow: hidden;
}

.stat-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.8s ease;
}

.stat-desc {
  font-size: 11px;
  color: #909399;
  margin-top: 2px;
}

.stat-value {
  font-size: 16px;
  font-weight: bold;
  min-width: 50px;
  text-align: right;
}

.attr-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.attr-item {
  text-align: center;
  padding: 8px;
  background: #f9f9f9;
  border-radius: 8px;
}

.attr-icon {
  font-size: 20px;
  margin-bottom: 4px;
}

.attr-name {
  font-size: 11px;
  color: #909399;
  margin-bottom: 2px;
}

.attr-value {
  font-size: 13px;
  font-weight: bold;
  color: #303133;
}

.attr-ratio {
  font-size: 10px;
  color: #909399;
}

/* Account list */
.account-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.account-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  background: #f9f9f9;
  border-radius: 8px;
}

.account-icon {
  font-size: 24px;
  width: 32px;
  text-align: center;
}

.account-info {
  flex: 1;
  min-width: 0;
}

.account-name {
  font-size: 13px;
  color: #606266;
  margin-bottom: 4px;
}

.account-bar {
  height: 6px;
  background: #ebeef5;
  border-radius: 3px;
  overflow: hidden;
}

.account-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s ease;
}

.account-amount {
  font-size: 15px;
  font-weight: bold;
  color: #303133;
  min-width: 60px;
  text-align: right;
}

/* Credit card */
.cc-status {
  padding: 4px 0;
}

.cc-balance {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
}

.cc-label {
  font-size: 13px;
  color: #909399;
}

.cc-amount {
  font-size: 22px;
  font-weight: bold;
  color: #f56c6c;
}

.cc-bar {
  height: 6px;
  background: #fef0f0;
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 10px;
}

.cc-fill {
  height: 100%;
  background: #f56c6c;
  border-radius: 3px;
  transition: width 0.6s ease;
}

.cc-history {
  border-top: 1px solid #f5f5f5;
  padding-top: 8px;
}

.cc-item {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 12px;
  color: #606266;
}

.cc-repay {
  margin: 10px 0;
}

.repay-btn {
  padding: 6px 16px;
  background: #f56c6c;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
}
.repay-btn:hover { background: #f78989; }

.repay-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.repay-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.repay-input {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 13px;
}
.repay-input:focus { border-color: #409eff; outline: none; }

.repay-confirm {
  padding: 6px 12px;
  background: #67c23a;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.repay-confirm:disabled { opacity: 0.6; cursor: not-allowed; }

.repay-cancel {
  padding: 6px 12px;
  background: none;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  cursor: pointer;
}

.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.badge {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: #f5f5f5;
  border-radius: 20px;
  font-size: 12px;
  color: #909399;
  opacity: 0.5;
}

.badge.unlocked {
  background: #f0f9eb;
  color: #67c23a;
  opacity: 1;
}

.badge-icon {
  font-size: 14px;
}

.ai-section {
  position: relative;
}

.ai-loading {
  text-align: center;
  color: #909399;
  padding: 12px;
}

.ai-text {
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
  padding: 8px;
  background: #f9f9f9;
  border-radius: 8px;
}

.refresh-btn {
  margin-top: 8px;
  padding: 6px 12px;
  background: none;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  cursor: pointer;
}
.refresh-btn:hover { border-color: #409eff; color: #409eff; }

@media (max-width: 768px) {
  .attr-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
