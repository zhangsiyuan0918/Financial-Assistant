<template>
  <div>
    <h2>总览</h2>

    <!-- Quick Entry -->
    <QuickEntry @recorded="onRecorded" @deleted="onRecorded" />

    <!-- Core metrics: 3 cards -->
    <el-row :gutter="12">
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover" class="metric-card">
          <div class="metric-center">
            <div class="metric-label">净资产</div>
            <div class="metric-value" style="color:#67c23a">{{ fmt(o.net_worth) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover" class="metric-card">
          <div class="metric-center">
            <div class="metric-label">本月结余</div>
            <div class="metric-value" :style="{ color: o.monthly_balance >= 0 ? '#67c23a' : '#f56c6c' }">
              {{ fmt(o.monthly_balance) }}
            </div>
            <div class="metric-sub">收入 {{ fmt(o.monthly_income) }} - 支出 {{ fmt(o.monthly_expense) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover" class="metric-card">
          <div class="metric-center">
            <div class="metric-label">财务健康</div>
            <div class="metric-value" :style="{ color: h.total_score >= 70 ? '#67c23a' : h.total_score >= 50 ? '#e6a23c' : '#f56c6c' }">
              {{ h.total_score ?? '--' }}分
            </div>
            <div class="metric-sub">{{ h.level }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Charts + Alert summary in one row -->
    <el-row :gutter="8" style="margin-top:4px">
      <el-col :xs="24" :sm="14">
        <el-card>
          <template #header><span style="font-size:14px">资产分层</span></template>
          <div ref="layerChart" style="height:240px"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="10">
        <el-card v-if="alerts.length">
          <template #header>
            <el-space>
              <el-icon color="#e6a23c"><WarningFilled /></el-icon>
              <span style="font-size:14px">预警摘要</span>
            </el-space>
          </template>
          <div v-for="a in alerts.slice(0, 3)" :key="a.id" class="alert-row">
            <el-tag :type="a.severity === 'high' ? 'danger' : 'warning'" size="small" style="margin-right:6px">
              {{ a.type === 'budget_over' ? '预算' : a.type === 'liquidity' ? '流动性' : '异常' }}
            </el-tag>
            <span>{{ a.message }}</span>
          </div>
          <el-button size="small" text @click="$router.push('/alerts')" style="margin-top:8px">查看全部</el-button>
        </el-card>
        <el-card v-else>
          <template #header><span style="font-size:14px">快捷入口</span></template>
          <el-row :gutter="8">
            <el-col :span="12" v-for="item in quickActions" :key="item.path">
              <div class="quick-item" @click="$router.push(item.path)">
                <span style="font-size:20px">{{ item.icon }}</span>
                <span style="font-size:12px;color:#666">{{ item.label }}</span>
              </div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>
    </el-row>

    <!-- Net worth trend -->
    <el-card style="margin-top:4px">
      <template #header><span style="font-size:14px">净资产走势</span></template>
      <div ref="netWorthChart" style="height:180px"></div>
    </el-card>

    <!-- Liquid assets trend -->
    <el-card style="margin-top:4px">
      <template #header><span style="font-size:14px">活期资产走势（现金 + 投资）</span></template>
      <div ref="liquidChart" style="height:180px"></div>
    </el-card>

    <!-- Asset detail + Budget in one row -->
    <el-row :gutter="8" style="margin-top:4px">
      <el-col :xs="24" :sm="14">
        <el-card>
          <template #header>
            <el-space>
              <span style="font-size:14px">资产明细</span>
              <el-button size="small" type="primary" plain @click="editAssets">编辑</el-button>
            </el-space>
          </template>
          <el-table :data="o.assets" stripe size="small" style="width: 100%">
            <el-table-column prop="name" label="项目" min-width="100" />
            <el-table-column prop="amount" label="金额" width="120">
              <template #default="{row}">{{ fmt(row.amount) }}</template>
            </el-table-column>
            <el-table-column prop="ratio" label="占比" width="80">
              <template #default="{row}">{{ row.ratio }}%</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="10">
        <el-card v-if="budget.items && budget.items.length">
          <template #header>
            <el-space>
              <span style="font-size:14px">本月预算</span>
              <el-button size="small" text @click="editBudget">编辑</el-button>
            </el-space>
          </template>
          <div v-for="item in budget.items" :key="item.category" class="budget-row">
            <span class="budget-cat">{{ item.category }}</span>
            <el-progress :percentage="Math.min(item.ratio, 100)" :stroke-width="8" style="flex:1;margin:0 6px"
              :color="item.ratio > 100 ? '#f56c6c' : item.ratio > 80 ? '#e6a23c' : '#409eff'" />
            <span class="budget-num">{{ fmt(item.actual) }}/{{ fmt(item.budget) }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Data management -->
    <el-card style="margin-top:4px">
      <template #header><span style="font-size:14px">数据管理</span></template>
      <el-space wrap>
        <el-button size="small" type="primary" plain @click="uploadVisible = true">导入 CSV</el-button>
        <el-button size="small" type="success" plain @click="doBackfill" :loading="backfilling">回填历史净值</el-button>
        <el-tag v-if="dbStatus.migrated" type="success" size="small">SQLite</el-tag>
        <el-tag v-else type="info" size="small">CSV</el-tag>
        <span v-if="dbStatus.stats" style="font-size:12px;color:#999">
          {{ dbStatus.stats.records }} 条（{{ dbStatus.stats.date_from }} ~ {{ dbStatus.stats.date_to }}）
        </span>
        <el-button v-if="!dbStatus.migrated" size="small" type="warning" plain :loading="migrating" @click="doMigrate">迁移</el-button>
        <el-button v-if="dbStatus.migrated" size="small" type="danger" plain @click="doRollback">回滚</el-button>
      </el-space>
    </el-card>

    <!-- Dialogs -->
    <el-dialog v-model="editVisible" title="编辑资产" width="500px">
      <el-form label-width="120px" v-if="editForm.length">
        <template v-for="layer in layers" :key="layer">
          <el-divider content-position="left" style="margin:8px 0">{{ layer }}</el-divider>
          <el-form-item v-for="item in editForm.filter(i => i.layer === layer)" :key="item.name" :label="item.name">
            <el-input-number v-model="item.amount" :min="0" :step="1000" style="width:200px" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="saveAssets">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="uploadVisible" title="导入数据" width="550px">
      <el-upload drag :auto-upload="false" :on-change="handleUpload" accept=".csv" :disabled="uploading">
        <el-icon style="font-size:48px;color:#409eff"><Upload /></el-icon>
        <div style="margin-top:8px">将 CSV 文件拖到此处，或点击选择</div>
      </el-upload>
      <div v-if="uploading" style="margin-top:12px;text-align:center;color:#409eff">
        <el-icon class="is-loading" :size="16"><Loading /></el-icon> 处理中...
      </div>
      <div v-if="uploadResult" style="margin-top:12px;padding:12px;background:#f0f9eb;border-radius:4px">
        <div style="font-weight:bold;margin-bottom:8px">已导入 {{ uploadResult.records }} 条记录</div>
        <div v-if="uploadResult.pipeline?.steps">
          <div v-for="step in uploadResult.pipeline.steps" :key="step.step" style="font-size:12px;padding:2px 0;color:#666">
            <span v-if="step.result?.success !== false && step.result?.status !== 'error'">✓</span>
            <span v-else-if="step.result?.error">✗</span>
            <span v-else>○</span>
            {{ step.step }}
          </div>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-model="budgetEditVisible" title="编辑预算" width="400px">
      <el-form label-width="100px">
        <el-form-item v-for="item in budgetEditForm" :key="item.category" :label="item.category">
          <el-input-number v-model="item.budget" :min="0" :step="500" style="width:180px" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="budgetEditVisible = false">取消</el-button>
        <el-button type="primary" @click="saveBudget">保存</el-button>
      </template>
    </el-dialog>

    <AiFloat />
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchOverview, fetchAssetHistory, fetchBudget, updateAssets, updateBudget, uploadCsv, fetchHealth, fetchDbStatus, migrateDb, rollbackDb, fetchAlerts, backfillAssets } from '../api/index.js'
import AiFloat from '../components/AiFloat.vue'
import QuickEntry from '../components/QuickEntry.vue'
import { createChart } from '../utils/chart.js'

const o = ref({ assets: [], layers: [], net_worth: 0, cash_and_liquid: 0, investment: 0, restricted: 0, receivables: 0, bills_payable: 0, liquidity_coverage: 0, investment_ratio: 0, total_assets: 0, monthly_income: 0, monthly_balance: 0, monthly_expense: 0, avg_monthly_expense: 0 })
const h = ref({ items: [], total_score: 0, level: '' })
const dbStatus = ref({ migrated: false, stats: null })
const migrating = ref(false)
const assetHistory = ref([])
const budget = ref({ items: [] })
const alerts = ref([])
const layerChart = ref(null)
const netWorthChart = ref(null)
const liquidChart = ref(null)
const editVisible = ref(false)
const editForm = ref([])
const budgetEditVisible = ref(false)
const budgetEditForm = ref([])
const uploadVisible = ref(false)
const uploadResult = ref(null)
const uploading = ref(false)
const backfilling = ref(false)
const layers = ['现金/活期', '投资资产', '受限资产', '应收']
const fmt = v => '¥' + Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })

const quickActions = [
  { path: '/spending', icon: '📊', label: '支出分析' },
  { path: '/forecast', icon: '🔮', label: '支出预测' },
  { path: '/simulation', icon: '🧮', label: '情景模拟' },
  { path: '/ai', icon: '🤖', label: 'AI 助手' },
]

async function editAssets() {
  editForm.value = o.value.assets.map(a => ({ name: a.name, amount: a.amount, layer: a.layer }))
  editVisible.value = true
}

async function saveAssets() {
  const grouped = {}
  for (const item of editForm.value) {
    if (!grouped[item.layer]) grouped[item.layer] = {}
    grouped[item.layer][item.name] = item.amount
  }
  await updateAssets(grouped)
  editVisible.value = false
  o.value = await fetchOverview()
  assetHistory.value = await fetchAssetHistory()
}

async function doMigrate() {
  migrating.value = true
  try {
    const res = await migrateDb()
    if (res.success) {
      dbStatus.value = { migrated: true, stats: res.stats }
      o.value = await fetchOverview()
    }
  } finally { migrating.value = false }
}

async function doRollback() {
  await rollbackDb()
  dbStatus.value = { migrated: false, stats: null }
  o.value = await fetchOverview()
}

async function handleUpload(file) {
  uploadResult.value = null
  uploading.value = true
  try {
    uploadResult.value = await uploadCsv(file.raw)
    o.value = await fetchOverview()
    budget.value = await fetchBudget()
    h.value = await fetchHealth()
  } catch (e) {
    uploadResult.value = null
  } finally {
    uploading.value = false
  }
}

async function doBackfill() {
  backfilling.value = true
  try {
    await backfillAssets()
    assetHistory.value = await fetchAssetHistory()
    ElMessage.success('历史净值已回填')
  } catch {
    ElMessage.error('回填失败')
  } finally {
    backfilling.value = false
  }
}

async function onRecorded(result) {
  // 刷新所有相关数据
  o.value = await fetchOverview()
  assetHistory.value = await fetchAssetHistory()
  budget.value = await fetchBudget()

  // 重新渲染图表
  nextTick(() => renderCharts())
}

function renderCharts() {
  // Layer pie chart
  if (layerChart.value) {
    const layersData = o.value.layers.filter(l => l.total > 0)
    createChart(layerChart.value, {
      tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
      series: [{
        type: 'pie', radius: ['35%', '65%'],
        data: layersData.map(l => ({ name: l.layer, value: l.total })),
        label: { formatter: '{b}\n{d}%' },
        color: ['#409eff', '#e6a23c', '#909399', '#67c23a'],
      }],
    })
  }
  // Net worth trend
  if (netWorthChart.value && assetHistory.value.length) {
    const data = assetHistory.value
    createChart(netWorthChart.value, {
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 20, bottom: 40 },
      xAxis: { type: 'category', data: data.map(d => d.month), axisLabel: { rotate: 45 } },
      yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
      series: [{
        name: '净资产', type: 'line', data: data.map(d => d.total),
        smooth: true, areaStyle: { opacity: 0.15 }, lineStyle: { width: 2 },
      }],
    })
  }
  // Liquid assets trend
  if (liquidChart.value && assetHistory.value.length) {
    const data = assetHistory.value
    createChart(liquidChart.value, {
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0 },
      grid: { left: 60, right: 20, bottom: 40 },
      xAxis: { type: 'category', data: data.map(d => d.month), axisLabel: { rotate: 45 } },
      yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
      series: [
        { name: '现金/活期', type: 'bar', stack: 'liquid', data: data.map(d => d.cash_and_liquid), itemStyle: { color: '#409eff' } },
        { name: '投资资产', type: 'bar', stack: 'liquid', data: data.map(d => d.investment), itemStyle: { color: '#e6a23c' } },
        { name: '合计', type: 'line', data: data.map(d => d.cash_and_liquid + d.investment), lineStyle: { width: 2 }, itemStyle: { color: '#67c23a' } },
      ],
    })
  }
}

async function editBudget() {
  budgetEditForm.value = budget.value.items.map(i => ({ category: i.category, budget: i.budget }))
  budgetEditVisible.value = true
}

async function saveBudget() {
  const obj = {}
  for (const item of budgetEditForm.value) obj[item.category] = item.budget
  await updateBudget(obj)
  budgetEditVisible.value = false
  budget.value = await fetchBudget()
  o.value = await fetchOverview()
}

const CHINESE_FONT = "'PingFang SC', 'Microsoft YaHei', sans-serif"

onMounted(async () => {
  o.value = await fetchOverview()
  assetHistory.value = await fetchAssetHistory()
  budget.value = await fetchBudget()
  h.value = await fetchHealth()
  dbStatus.value = await fetchDbStatus()
  try { alerts.value = await fetchAlerts() } catch {}

  nextTick(() => {
    // Layer pie chart
    if (layerChart.value) {
      const layersData = o.value.layers.filter(l => l.total > 0)
      createChart(layerChart.value, {
        tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
        series: [{
          type: 'pie', radius: ['35%', '65%'],
          data: layersData.map(l => ({ name: l.layer, value: l.total })),
          label: { formatter: '{b}\n{d}%' },
          color: ['#409eff', '#e6a23c', '#909399', '#67c23a'],
        }],
      })
    }
    // Net worth trend
    if (netWorthChart.value && assetHistory.value.length) {
      const data = assetHistory.value
      createChart(netWorthChart.value, {
        tooltip: { trigger: 'axis' },
        grid: { left: 60, right: 20, bottom: 40 },
        xAxis: { type: 'category', data: data.map(d => d.month), axisLabel: { rotate: 45 } },
        yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
        series: [{
          name: '净资产', type: 'line', data: data.map(d => d.total),
          smooth: true, areaStyle: { opacity: 0.15 }, lineStyle: { width: 2 },
        }],
      })
    }
    // Liquid assets trend (cash + investment)
    if (liquidChart.value && assetHistory.value.length) {
      const data = assetHistory.value
      createChart(liquidChart.value, {
        tooltip: { trigger: 'axis', formatter: params => {
          let s = params[0].axisValue + '<br/>'
          params.forEach(p => { s += `${p.marker} ${p.seriesName}: ¥${Number(p.value).toLocaleString()}<br/>` })
          return s
        }},
        legend: { bottom: 0 },
        grid: { left: 60, right: 20, bottom: 40 },
        xAxis: { type: 'category', data: data.map(d => d.month), axisLabel: { rotate: 45 } },
        yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
        series: [
          { name: '现金/活期', type: 'bar', stack: 'liquid', data: data.map(d => d.cash_and_liquid), itemStyle: { color: '#409eff' } },
          { name: '投资资产', type: 'bar', stack: 'liquid', data: data.map(d => d.investment), itemStyle: { color: '#e6a23c' } },
          { name: '合计', type: 'line', data: data.map(d => d.cash_and_liquid + d.investment), lineStyle: { width: 2 }, itemStyle: { color: '#67c23a' } },
        ],
      })
    }
  })
})
</script>

<style scoped>
.metric-card { text-align: center; }
.metric-center { text-align: center; padding: 2px 0; }
.metric-label { color: #999; font-size: 13px; }
.metric-value { font-size: 24px; font-weight: bold; margin-top: 6px; }
.metric-sub { font-size: 12px; color: #999; margin-top: 4px; }

.quick-item {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 12px 0; cursor: pointer; border-radius: 6px; transition: background .2s;
}
.quick-item:hover { background: #f5f7fa; }

.alert-row { padding: 6px 0; border-bottom: 1px solid #f5f5f5; font-size: 13px; }
.alert-row:last-child { border-bottom: none; }

.budget-row { display: flex; align-items: center; padding: 3px 0; font-size: 12px; }
.budget-cat { width: 42px; color: #999; flex-shrink: 0; }
.budget-num { width: 90px; text-align: right; color: #666; flex-shrink: 0; }
</style>
