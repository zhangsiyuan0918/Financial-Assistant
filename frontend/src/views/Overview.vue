<template>
  <div>
    <h2>总览</h2>

    <!-- Core metrics: 3 cards -->
    <el-row :gutter="16">
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

    <!-- Quick actions -->
    <el-row :gutter="16" style="margin-top:4px">
      <el-col :xs="12" :sm="6" v-for="item in quickActions" :key="item.path">
        <el-card shadow="hover" class="quick-card" @click="$router.push(item.path)">
          <div class="metric-center">
            <div style="font-size:28px">{{ item.icon }}</div>
            <div style="margin-top:6px;font-size:13px;color:#666">{{ item.label }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Alert summary (if any) -->
    <el-card v-if="alerts.length" style="margin-top:12px">
      <template #header>
        <el-space>
          <el-icon color="#e6a23c"><WarningFilled /></el-icon>
          <span>预警摘要</span>
          <el-button size="small" text @click="$router.push('/alerts')">查看全部</el-button>
        </el-space>
      </template>
      <div v-for="a in alerts.slice(0, 3)" :key="a.id" class="alert-row">
        <el-tag :type="a.severity === 'high' ? 'danger' : 'warning'" size="small" style="margin-right:8px">
          {{ a.type === 'budget_over' ? '预算' : a.type === 'liquidity' ? '流动性' : '异常' }}
        </el-tag>
        <span>{{ a.message }}</span>
      </div>
    </el-card>

    <!-- Charts (collapsible) -->
    <el-collapse v-model="activeCollapse" style="margin-top:12px">
      <el-collapse-item title="资产分层" name="assets">
        <div ref="layerChart" style="height: 300px"></div>
      </el-collapse-item>
      <el-collapse-item title="净资产走势" name="trend">
        <div ref="netWorthChart" style="height: 300px"></div>
      </el-collapse-item>
    </el-collapse>

    <!-- Asset detail -->
    <el-card style="margin-top:12px">
      <template #header>
        <el-space>
          <span>资产明细</span>
          <el-button size="small" type="primary" plain @click="editAssets">编辑</el-button>
        </el-space>
      </template>
      <el-table :data="o.assets" stripe size="small" style="width: 100%">
        <el-table-column prop="name" label="项目" min-width="100" />
        <el-table-column prop="layer" label="层级" width="90" />
        <el-table-column prop="amount" label="金额" width="120">
          <template #default="{row}">{{ fmt(row.amount) }}</template>
        </el-table-column>
        <el-table-column prop="ratio" label="占比" width="80">
          <template #default="{row}">{{ row.ratio }}%</template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Budget -->
    <el-card v-if="budget.items && budget.items.length" style="margin-top:12px">
      <template #header>
        <el-space>
          <span>本月预算（{{ budget.month }}）</span>
          <el-button size="small" text @click="editBudget">编辑</el-button>
        </el-space>
      </template>
      <el-row :gutter="8">
        <el-col :xs="8" :sm="4" v-for="item in budget.items" :key="item.category">
          <div style="text-align:center;padding:4px 0">
            <div style="font-size:12px;color:#999">{{ item.category }}</div>
            <el-progress type="dashboard" :percentage="Math.min(item.ratio, 100)" :width="56" :stroke-width="6"
              :color="item.ratio > 100 ? '#f56c6c' : item.ratio > 80 ? '#e6a23c' : '#409eff'" />
            <div style="font-size:11px;margin-top:2px">{{ fmt(item.actual) }}/{{ fmt(item.budget) }}</div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- Data management (collapsed) -->
    <el-collapse style="margin-top:12px">
      <el-collapse-item title="数据管理">
        <el-space wrap>
          <el-button size="small" type="primary" plain @click="uploadVisible = true">导入 CSV</el-button>
          <el-tag v-if="dbStatus.migrated" type="success" size="small">SQLite</el-tag>
          <el-tag v-else type="info" size="small">CSV</el-tag>
          <span v-if="dbStatus.stats" style="font-size:12px;color:#999">
            {{ dbStatus.stats.records }} 条（{{ dbStatus.stats.date_from }} ~ {{ dbStatus.stats.date_to }}）
          </span>
          <el-button v-if="!dbStatus.migrated" size="small" type="warning" plain :loading="migrating" @click="doMigrate">迁移</el-button>
          <el-button v-if="dbStatus.migrated" size="small" type="danger" plain @click="doRollback">回滚</el-button>
        </el-space>
      </el-collapse-item>
    </el-collapse>

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
import { fetchOverview, fetchAssetHistory, fetchBudget, updateAssets, updateBudget, uploadCsv, fetchHealth, fetchDbStatus, migrateDb, rollbackDb, fetchAlerts } from '../api/index.js'
import AiFloat from '../components/AiFloat.vue'
import * as echarts from 'echarts'

const o = ref({ assets: [], layers: [], net_worth: 0, cash_and_liquid: 0, investment: 0, restricted: 0, receivables: 0, bills_payable: 0, liquidity_coverage: 0, investment_ratio: 0, total_assets: 0, monthly_income: 0, monthly_balance: 0, monthly_expense: 0, avg_monthly_expense: 0 })
const h = ref({ items: [], total_score: 0, level: '' })
const dbStatus = ref({ migrated: false, stats: null })
const migrating = ref(false)
const assetHistory = ref([])
const budget = ref({ items: [] })
const alerts = ref([])
const layerChart = ref(null)
const netWorthChart = ref(null)
const editVisible = ref(false)
const editForm = ref([])
const budgetEditVisible = ref(false)
const budgetEditForm = ref([])
const uploadVisible = ref(false)
const uploadResult = ref(null)
const uploading = ref(false)
const activeCollapse = ref([])
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
    if (layerChart.value) {
      const c = echarts.init(layerChart.value)
      const layersData = o.value.layers.filter(l => l.total > 0)
      c.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
        textStyle: { fontFamily: CHINESE_FONT },
        series: [{
          type: 'pie', radius: ['30%', '60%'],
          data: layersData.map(l => ({ name: l.layer, value: l.total })),
          label: { formatter: '{b}\n{d}%', fontFamily: CHINESE_FONT },
          color: ['#409eff', '#e6a23c', '#909399', '#67c23a'],
        }],
      })
    }
    if (netWorthChart.value && assetHistory.value.length) {
      const c = echarts.init(netWorthChart.value)
      const data = assetHistory.value
      c.setOption({
        tooltip: { trigger: 'axis' },
        textStyle: { fontFamily: CHINESE_FONT },
        grid: { left: 60, right: 20, bottom: 40 },
        xAxis: { type: 'category', data: data.map(d => d.month), axisLabel: { rotate: 45, fontFamily: CHINESE_FONT } },
        yAxis: { type: 'value', axisLabel: { formatter: '¥{value}', fontFamily: CHINESE_FONT } },
        series: [{
          name: '总资产', type: 'line', data: data.map(d => d.total),
          smooth: true, areaStyle: { opacity: 0.15 }, lineStyle: { width: 2 },
        }],
      })
    }
  })
})
</script>

<style scoped>
.metric-card { text-align: center; }
.metric-center { text-align: center; padding: 4px 0; }
.metric-label { color: #999; font-size: 13px; }
.metric-value { font-size: 24px; font-weight: bold; margin-top: 8px; }
.metric-sub { font-size: 12px; color: #999; margin-top: 4px; }

.quick-card { cursor: pointer; transition: transform .2s; }
.quick-card:hover { transform: translateY(-2px); }

.alert-row { padding: 8px 0; border-bottom: 1px solid #f5f5f5; font-size: 13px; }
.alert-row:last-child { border-bottom: none; }
</style>
