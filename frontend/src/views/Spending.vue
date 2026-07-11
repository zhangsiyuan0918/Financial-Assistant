<template>
  <div>
    <h2>支出分析</h2>
    <el-card>
      <el-radio-group v-model="year" style="margin-bottom:16px">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button v-for="y in years" :key="y" :value="String(y)">{{ y }}</el-radio-button>
      </el-radio-group>
      <el-row :gutter="16">
        <el-col :span="8"><div ref="pieChart" style="height:350px"></div></el-col>
        <el-col :span="16"><div ref="barChart" style="height:350px"></div></el-col>
      </el-row>
    </el-card>
    <el-card>
      <template #header>分类明细（点击行查看子分类）</template>
      <el-table :data="categories" stripe @row-click="showDetail" highlight-current-row>
        <el-table-column prop="category" label="分类" />
        <el-table-column prop="amount" label="金额" width="150"><template #default="{row}">{{ fmt(row.amount) }}</template></el-table-column>
        <el-table-column prop="ratio" label="占比" width="100"><template #default="{row}">{{ row.ratio }}%</template></el-table-column>
        <el-table-column prop="count" label="笔数" width="80" />
      </el-table>
    </el-card>
    <el-dialog v-model="detailVisible" :title="detailTitle" width="700px">
      <div ref="detailChart" style="height:300px"></div>
      <el-table :data="detailData" stripe style="margin-top:16px">
        <el-table-column prop="sub_category" label="子分类" />
        <el-table-column prop="amount" label="金额" width="150"><template #default="{row}">{{ fmt(row.amount) }}</template></el-table-column>
        <el-table-column prop="ratio" label="占比" width="100"><template #default="{row}">{{ row.ratio }}%</template></el-table-column>
        <el-table-column prop="count" label="笔数" width="80" />
      </el-table>
    </el-dialog>

    <el-card style="margin-top:16px">
      <template #header>
        <el-space>
          <span>同比/环比</span>
          <el-select v-model="compMonth" size="small" style="width:130px" @change="loadComp">
            <el-option v-for="m in availableMonths" :key="m" :label="m" :value="m" />
          </el-select>
        </el-space>
      </template>
      <el-tabs v-model="compTab">
        <el-tab-pane label="环比（上月）" name="mom">
          <el-table :data="compData.mom?.items ?? []" stripe size="small" max-height="250">
            <el-table-column prop="category" label="分类" width="80" />
            <el-table-column prop="current" label="本月" width="100"><template #default="{row}">{{ fmt(row.current) }}</template></el-table-column>
            <el-table-column prop="previous" label="上月" width="100"><template #default="{row}">{{ fmt(row.previous) }}</template></el-table-column>
            <el-table-column prop="diff" label="差额" width="100"><template #default="{row}"><span :style="{color: row.diff > 0 ? '#f56c6c' : '#67c23a'}">{{ fmt(row.diff) }}</span></template></el-table-column>
            <el-table-column prop="pct" label="变化" width="80"><template #default="{row}"><el-tag v-if="row.pct !== null" :type="row.pct > 0 ? 'danger' : 'success'" size="small">{{ row.pct > 0 ? '+' : '' }}{{ row.pct }}%</el-tag></template></el-table-column>
          </el-table>
          <div style="margin-top:8px;font-size:12px;color:#999">对比月份：{{ compData.mom_month }}</div>
        </el-tab-pane>
        <el-tab-pane label="同比（去年同月）" name="yoy">
          <el-table :data="compData.yoy?.items ?? []" stripe size="small" max-height="250">
            <el-table-column prop="category" label="分类" width="80" />
            <el-table-column prop="current" label="本月" width="100"><template #default="{row}">{{ fmt(row.current) }}</template></el-table-column>
            <el-table-column prop="previous" label="去年" width="100"><template #default="{row}">{{ fmt(row.previous) }}</template></el-table-column>
            <el-table-column prop="diff" label="差额" width="100"><template #default="{row}"><span :style="{color: row.diff > 0 ? '#f56c6c' : '#67c23a'}">{{ fmt(row.diff) }}</span></template></el-table-column>
            <el-table-column prop="pct" label="变化" width="80"><template #default="{row}"><el-tag v-if="row.pct !== null" :type="row.pct > 0 ? 'danger' : 'success'" size="small">{{ row.pct > 0 ? '+' : '' }}{{ row.pct }}%</el-tag></template></el-table-column>
          </el-table>
          <div style="margin-top:8px;font-size:12px;color:#999">对比月份：{{ compData.yoy_month }}</div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-card style="margin-top:16px">
      <template #header>
        <el-space>
          <span>季节性分析</span>
          <el-tag type="warning" size="small">Beta</el-tag>
        </el-space>
      </template>
      <el-row :gutter="16">
        <el-col :span="12">
          <div ref="seasonalChart" style="height:250px"></div>
        </el-col>
        <el-col :span="12">
          <el-table :data="seasonalCats" stripe size="small" max-height="250">
            <el-table-column prop="category" label="类别" />
            <el-table-column prop="peak_month" label="峰值月" width="80"><template #default="{row}">{{ row.peak_month }}月</template></el-table-column>
            <el-table-column prop="avg" label="月均" width="100"><template #default="{row}">{{ fmt(row.avg) }}</template></el-table-column>
          </el-table>
        </el-col>
      </el-row>
    </el-card>

    <AiFloat />
  </div>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import { fetchSpending, fetchSpendingDetail, fetchSeasonal, fetchComparison } from '../api/index.js'
import AiFloat from '../components/AiFloat.vue'
import * as echarts from 'echarts'

const year = ref('all')
const years = ref([])
const categories = ref([])
const detailVisible = ref(false)
const detailTitle = ref('')
const detailData = ref([])
const seasonalCats = ref([])
const compTab = ref('mom')
const compMonth = ref('')
const compData = ref({ mom: { items: [] }, yoy: { items: [] } })
const availableMonths = ref([])
const pieChart = ref(null)
const barChart = ref(null)
const detailChart = ref(null)
const seasonalChart = ref(null)

let pieInstance = null
let barInstance = null
let detailInstance = null
let seasonalInstance = null

const fmt = v => '¥' + Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2 })

function renderCharts(data) {
  if (!pieChart.value || !barChart.value) return
  if (!pieInstance) pieInstance = echarts.init(pieChart.value)
  if (!barInstance) barInstance = echarts.init(barChart.value)
  pieInstance.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
    series: [{ type: 'pie', radius: ['30%', '60%'], data: data.categories.map(i => ({ name: i.category, value: i.amount })), label: { formatter: '{b}\n{d}%' } }],
  })
  barInstance.setOption({
    tooltip: { trigger: 'axis' }, grid: { left: 80, right: 20 },
    xAxis: { type: 'category', data: data.categories.map(i => i.category), axisLabel: { rotate: 30 } },
    yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
    series: [{ type: 'bar', data: data.categories.map(i => i.amount), itemStyle: { color: '#409eff' } }],
  })
}

async function load() {
  spendingData = await fetchSpending(year.value)
  categories.value = spendingData.categories
  years.value = spendingData.years
  await nextTick()
  renderCharts(spendingData)
}

async function showDetail(row) {
  detailTitle.value = row.category
  detailVisible.value = true
  const data = await fetchSpendingDetail(row.category, year.value)
  detailData.value = data.sub_categories
  await nextTick()
  if (detailChart.value) {
    if (!detailInstance) detailInstance = echarts.init(detailChart.value)
    detailInstance.setOption({
      tooltip: { trigger: 'axis' }, grid: { left: 80 },
      xAxis: { type: 'category', data: data.sub_categories.map(i => i.sub_category), axisLabel: { rotate: 30 } },
      yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
      series: [{ type: 'bar', data: data.sub_categories.map(i => i.amount) }],
    })
  }
}

async function loadSeasonal() {
  const data = await fetchSeasonal()
  seasonalCats.value = data.seasonal_categories
  nextTick(() => {
    if (seasonalChart.value) {
      if (!seasonalInstance) seasonalInstance = echarts.init(seasonalChart.value)
      const months = data.month_pattern
      const colors = months.map(m => m.diff_pct > 15 ? '#f56c6c' : m.diff_pct < -15 ? '#67c23a' : '#409eff')
      seasonalInstance.setOption({
        tooltip: { trigger: 'axis' }, grid: { left: 50, right: 20, bottom: 30 },
        xAxis: { type: 'category', data: months.map(m => m.month + '月') },
        yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
        series: [{ type: 'bar', data: months.map(m => m.avg), itemStyle: { color: params => colors[params.dataIndex] } }],
      })
    }
  })
}

async function loadComp() {
  if (!compMonth.value) return
  const [y, m] = compMonth.value.split('-')
  compData.value = await fetchComparison(y, m)
}

let spendingData = null
function buildMonths() {
  if (!spendingData) return
  const months = Object.keys(spendingData.monthly_trend || {}).sort()
  availableMonths.value = months
  if (months.length && !compMonth.value) {
    compMonth.value = months[months.length - 1]
    loadComp()
  }
}

watch(year, async () => {
  await load()
  buildMonths()
  loadComp()
})
onMounted(async () => {
  await load()
  loadSeasonal()
  buildMonths()
  loadComp()
})
</script>
