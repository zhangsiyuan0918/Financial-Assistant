<template>
  <div>
    <h2>月度支出预测</h2>
    <el-row :gutter="16">
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover"><div class="metric-center">
          <div class="metric-label">年度预测总额</div>
          <div class="metric-value" style="color:#409eff">{{ fmt(annualTotal) }}</div>
        </div></el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover"><div class="metric-center">
          <div class="metric-label">月均预测</div>
          <div class="metric-value" style="color:#67c23a">{{ fmt(annualTotal / 12) }}</div>
        </div></el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover"><div class="metric-center">
          <div class="metric-label">最高月</div>
          <div class="metric-value" style="color:#e6a23c">{{ fmt(maxMonthVal) }}</div>
          <div class="metric-sub">{{ maxMonthLabel }}</div>
        </div></el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover"><div class="metric-center">
          <div class="metric-label">最低月</div>
          <div class="metric-value" style="color:#f56c6c">{{ fmt(minMonthVal) }}</div>
          <div class="metric-sub">{{ minMonthLabel }}</div>
        </div></el-card>
      </el-col>
    </el-row>

    <el-card>
      <div ref="forecastChart" style="height:400px"></div>
    </el-card>

    <el-card>
      <template #header>逐月预测明细</template>
      <el-table :data="forecastData" stripe size="small">
        <el-table-column prop="month" label="月份" width="120" />
        <el-table-column prop="prediction" label="预测值" width="130"><template #default="{row}">{{ fmt(row.prediction) }}</template></el-table-column>
        <el-table-column prop="lower" label="下限(80%)" width="130"><template #default="{row}">{{ fmt(row.lower) }}</template></el-table-column>
        <el-table-column prop="upper" label="上限(80%)" width="130"><template #default="{row}">{{ fmt(row.upper) }}</template></el-table-column>
      </el-table>
      <el-alert type="info" show-icon style="margin-top:12px" :closable="false" title="2026-07 含最后一期车贷 ¥11,742，2026-08 起月均减少约 ¥11,742" />
    </el-card>

    <!-- Backtest section -->
    <el-card v-if="backtestData.length" style="margin-top:12px">
      <template #header>
        <el-space>
          <span>预测回测</span>
          <el-tag size="small" :type="mape < 20 ? 'success' : mape < 40 ? 'warning' : 'danger'">
            MAPE: {{ mape }}%
          </el-tag>
        </el-space>
      </template>
      <div ref="backtestChart" style="height:280px"></div>
      <el-table :data="backtestData" stripe size="small" max-height="300" style="margin-top:12px">
        <el-table-column prop="month" label="月份" width="100" />
        <el-table-column prop="predicted" label="预测值" width="120"><template #default="{row}">{{ fmt(row.predicted) }}</template></el-table-column>
        <el-table-column prop="actual" label="实际值" width="120"><template #default="{row}">{{ fmt(row.actual) }}</template></el-table-column>
        <el-table-column prop="error_pct" label="误差%" width="90">
          <template #default="{row}">
            <el-tag :type="Math.abs(row.error_pct) < 10 ? 'success' : Math.abs(row.error_pct) < 30 ? 'warning' : 'danger'" size="small">
              {{ row.error_pct > 0 ? '+' : '' }}{{ row.error_pct }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error_amount" label="偏差金额" width="120">
          <template #default="{row}"><span :style="{color: row.error_amount > 0 ? '#f56c6c' : '#67c23a'}">{{ fmt(row.error_amount) }}</span></template>
        </el-table-column>
      </el-table>
    </el-card>

    <AiFloat />
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, computed } from 'vue'
import { fetchForecast, fetchForecastBacktest } from '../api/index.js'
import AiFloat from '../components/AiFloat.vue'
import { createChart } from '../utils/chart.js'

const forecastData = ref([])
const annualTotal = ref(0)
const forecastChart = ref(null)
const backtestChart = ref(null)
const backtestData = ref([])
const mape = ref(0)
const fmt = v => '¥' + Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 0 })

const maxMonth = computed(() => forecastData.value.reduce((a, b) => a.prediction > b.prediction ? a : b, { prediction: 0 }))
const minMonth = computed(() => forecastData.value.reduce((a, b) => a.prediction < b.prediction ? a : b, { prediction: Infinity }))
const maxMonthVal = computed(() => maxMonth.value.prediction || 0)
const maxMonthLabel = computed(() => maxMonth.value.month || '')
const minMonthVal = computed(() => minMonth.value.prediction || 0)
const minMonthLabel = computed(() => minMonth.value.month || '')

const CHINESE_FONT = "'PingFang SC', 'Microsoft YaHei', sans-serif"

onMounted(async () => {
  const data = await fetchForecast()
  forecastData.value = data.data
  annualTotal.value = data.annual_total

  // Load backtest
  try {
    const bt = await fetchForecastBacktest()
    backtestData.value = bt.backtest || []
    mape.value = bt.mape || 0
  } catch {}

  nextTick(() => {
    // Forecast chart
    if (forecastChart.value) {
      createChart(forecastChart.value, {
        tooltip: { trigger: 'axis' },
        grid: { left: 80, right: 20, top: 20, bottom: 80 },
        xAxis: { type: 'category', data: data.data.map(d => d.month), axisLabel: { rotate: 45, fontSize: 11 } },
        yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
        series: [
          { name: '预测值', type: 'line', data: data.data.map(d => d.prediction), smooth: true, symbol: 'circle', lineStyle: { width: 3 }, itemStyle: { color: '#409eff' } },
          { name: '上限', type: 'line', data: data.data.map(d => d.upper), lineStyle: { type: 'dashed', width: 1 }, symbol: 'none', itemStyle: { color: '#b3d8ff' } },
          { name: '下限', type: 'line', data: data.data.map(d => d.lower), lineStyle: { type: 'dashed', width: 1 }, symbol: 'none', itemStyle: { color: '#b3d8ff' } },
        ],
        legend: { bottom: 0, textStyle: { fontSize: 11 } },
      })
    }

    // Backtest chart
    if (backtestChart.value && backtestData.value.length) {
      const bt = backtestData.value
      createChart(backtestChart.value, {
        tooltip: { trigger: 'axis' },
        grid: { left: 80, right: 20, top: 20, bottom: 80 },
        legend: { bottom: 0, textStyle: { fontSize: 11 } },
        xAxis: { type: 'category', data: bt.map(d => d.month), axisLabel: { rotate: 45, fontSize: 11 } },
        yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
        series: [
          { name: '预测值', type: 'bar', data: bt.map(d => d.predicted), itemStyle: { color: '#409eff' } },
          { name: '实际值', type: 'bar', data: bt.map(d => d.actual), itemStyle: { color: '#67c23a' } },
          { name: '误差%', type: 'line', data: bt.map(d => d.error_pct), yAxisIndex: 0, lineStyle: { type: 'dashed' }, itemStyle: { color: '#f56c6c' } },
        ],
      })
    }
  })
})
</script>

<style scoped>
.metric-center { text-align: center; padding: 4px 0; }
.metric-label { color: #999; font-size: 13px; }
.metric-value { font-size: 24px; font-weight: bold; margin-top: 8px; }
.metric-sub { font-size: 12px; color: #999; margin-top: 4px; }
</style>
