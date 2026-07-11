<template>
  <div>
    <el-row :align="'middle'" style="margin-bottom:16px">
      <el-col :span="8">
        <h2 style="margin:0">月度报告</h2>
      </el-col>
      <el-col :span="8" style="text-align:center">
        <el-date-picker v-model="reportMonth" type="month" placeholder="选择月份" value-format="YYYY-MM" style="width:200px" @change="load" />
      </el-col>
      <el-col :span="8" style="text-align:right">
        <el-button type="primary" plain @click="exportPdf">导出 PDF</el-button>
      </el-col>
    </el-row>

    <div id="report-content">
      <!-- 月度概要 -->
      <el-card v-if="r.month" style="margin-bottom:16px">
        <template #header><strong>{{ r.month }} 月度财务报告</strong></template>
        <el-row :gutter="16">
          <el-col :span="6"><div style="text-align:center"><div style="color:#999;font-size:12px">收入</div><div style="font-size:22px;font-weight:bold;color:#67c23a">{{ fmt(r.income) }}</div></div></el-col>
          <el-col :span="6"><div style="text-align:center"><div style="color:#999;font-size:12px">支出</div><div style="font-size:22px;font-weight:bold;color:#f56c6c">{{ fmt(r.expense) }}</div></div></el-col>
          <el-col :span="6"><div style="text-align:center"><div style="color:#999;font-size:12px">结余</div><div style="font-size:22px;font-weight:bold" :style="{color: r.balance >= 0 ? '#67c23a' : '#f56c6c'}">{{ fmt(r.balance) }}</div></div></el-col>
          <el-col :span="6"><div style="text-align:center"><div style="color:#999;font-size:12px">储蓄率</div><div style="font-size:22px;font-weight:bold;color:#409eff">{{ r.savings_rate }}%</div></div></el-col>
        </el-row>
      </el-card>

      <!-- 变化对比 -->
      <el-row :gutter="16" v-if="r.month">
        <el-col :span="8">
          <el-card style="margin-bottom:16px">
            <template #header><strong>环比（vs {{ r.mom_month }}）</strong></template>
            <div v-if="r.mom_change != null" style="text-align:center;font-size:28px;font-weight:bold" :style="{color: r.mom_change >= 0 ? '#f56c6c' : '#67c23a'}">{{ r.mom_change >= 0 ? '+' : '' }}{{ r.mom_change }}%</div>
            <div style="text-align:center;color:#999;font-size:12px;margin-top:4px">上月支出 {{ fmt(r.expense / (1 + r.mom_change/100)) }}</div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card style="margin-bottom:16px">
            <template #header><strong>同比（vs {{ r.yoy_month }}）</strong></template>
            <div v-if="r.yoy_change != null" style="text-align:center;font-size:28px;font-weight:bold" :style="{color: r.yoy_change >= 0 ? '#f56c6c' : '#67c23a'}">{{ r.yoy_change >= 0 ? '+' : '' }}{{ r.yoy_change }}%</div>
            <div style="text-align:center;color:#999;font-size:12px;margin-top:4px">去年同月支出 {{ fmt(r.expense / (1 + r.yoy_change/100)) }}</div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card style="margin-bottom:16px">
            <template #header><strong>资产变化</strong></template>
            <div v-if="r.asset.change_pct != null" style="text-align:center;font-size:28px;font-weight:bold" :style="{color: r.asset.change_pct >= 0 ? '#67c23a' : '#f56c6c'}">{{ r.asset.change_pct >= 0 ? '+' : '' }}{{ r.asset.change_pct }}%</div>
            <div style="text-align:center;color:#999;font-size:12px;margin-top:4px">{{ fmt(r.asset.month_start) }} → {{ fmt(r.asset.month_end) }}</div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 支出分类明细 -->
      <el-row :gutter="16" v-if="r.month">
        <el-col :span="12">
          <el-card style="margin-bottom:16px">
            <template #header><strong>支出分类</strong></template>
            <div ref="pieChart" style="height:260px"></div>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card style="margin-bottom:16px">
            <template #header><strong>预算执行</strong></template>
            <el-table :data="r.budget.items ?? []" stripe size="small" max-height="260">
              <el-table-column prop="category" label="分类" width="80" />
              <el-table-column prop="actual" label="实际" width="80"><template #default="{row}">{{ fmt(row.actual) }}</template></el-table-column>
              <el-table-column prop="budget" label="预算" width="80"><template #default="{row}">{{ fmt(row.budget) }}</template></el-table-column>
              <el-table-column label="进度" width="90">
                <template #default="{row}">
                  <el-progress :percentage="Math.min(row.ratio, 100)" :width="60" :stroke-width="6"
                    :color="row.ratio > 100 ? '#f56c6c' : row.ratio > 80 ? '#e6a23c' : '#409eff'" />
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <!-- 环比明细 vs 同比明细 -->
      <el-row :gutter="16" v-if="r.month">
        <el-col :span="12">
          <el-card style="margin-bottom:16px">
            <template #header><strong>环比变化明细</strong></template>
            <el-table :data="r.mom_categories ?? []" stripe size="small" max-height="260">
              <el-table-column prop="category" label="分类" width="70" />
              <el-table-column prop="current" label="本月" width="80"><template #default="{row}">{{ fmt(row.current) }}</template></el-table-column>
              <el-table-column prop="previous" label="上月" width="80"><template #default="{row}">{{ fmt(row.previous) }}</template></el-table-column>
              <el-table-column label="变化" width="70">
                <template #default="{row}">
                  <el-tag v-if="row.pct !== null" :type="row.pct > 0 ? 'danger' : 'success'" size="small">{{ row.pct >= 0 ? '+' : '' }}{{ row.pct }}%</el-tag>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card style="margin-bottom:16px">
            <template #header><strong>同比变化明细</strong></template>
            <el-table :data="r.yoy_categories ?? []" stripe size="small" max-height="260">
              <el-table-column prop="category" label="分类" width="70" />
              <el-table-column prop="current" label="本月" width="80"><template #default="{row}">{{ fmt(row.current) }}</template></el-table-column>
              <el-table-column prop="previous" label="去年" width="80"><template #default="{row}">{{ fmt(row.previous) }}</template></el-table-column>
              <el-table-column label="变化" width="70">
                <template #default="{row}">
                  <el-tag v-if="row.pct !== null" :type="row.pct > 0 ? 'danger' : 'success'" size="small">{{ row.pct >= 0 ? '+' : '' }}{{ row.pct }}%</el-tag>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <!-- 底部指标 -->
      <el-row :gutter="16" v-if="r.month">
        <el-col :span="6">
          <el-card style="margin-bottom:16px"><div style="text-align:center">
            <div style="color:#999;font-size:12px">日均支出</div>
            <div style="font-size:18px;font-weight:bold;color:#f56c6c">{{ fmt(r.daily_avg_expense) }}</div>
          </div></el-card>
        </el-col>
        <el-col :span="6">
          <el-card style="margin-bottom:16px"><div style="text-align:center">
            <div style="color:#999;font-size:12px">交易笔数</div>
            <div style="font-size:18px;font-weight:bold;color:#409eff">{{ r.transaction_count }}</div>
          </div></el-card>
        </el-col>
        <el-col :span="6">
          <el-card style="margin-bottom:16px"><div style="text-align:center">
            <div style="color:#999;font-size:12px">收入构成</div>
            <div v-for="c in (r.income_breakdown ?? [])" :key="c.category" style="font-size:13px;margin-top:4px">{{ c.category }}: {{ fmt(c.amount) }} ({{ c.ratio }}%)</div>
          </div></el-card>
        </el-col>
        <el-col :span="6">
          <el-card style="margin-bottom:16px"><div style="text-align:center">
            <div style="color:#999;font-size:12px">流动资产变化</div>
            <div style="font-size:18px;font-weight:bold" :style="{color: (r.asset.cash_change ?? 0) >= 0 ? '#67c23a' : '#f56c6c'}">{{ r.asset.cash_change != null ? fmt(r.asset.cash_change) : '-' }}</div>
          </div></el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { fetchMonthlyReport } from '../api/index.js'
import * as echarts from 'echarts'

const r = ref({ budget: { items: [] }, mom_categories: [], yoy_categories: [], income_breakdown: [], asset: {} })
const reportMonth = ref('')
const pieChart = ref(null)
const fmt = v => '¥' + Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 0 })

async function load() {
  r.value = await fetchMonthlyReport(reportMonth.value)
  await nextTick()
  renderPie()
}

function renderPie() {
  if (!pieChart.value) return
  const c = echarts.init(pieChart.value)
  const cats = r.value.all_categories ?? []
  c.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
    series: [{
      type: 'pie', radius: ['30%', '60%'],
      data: cats.map(i => ({ name: i.category, value: i.amount })),
      label: { formatter: '{b}\n{d}%' },
    }],
  })
}

function exportPdf() {
  window.print()
}

function todayMonth() {
  const d = new Date()
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
}

watch(reportMonth, load)
onMounted(() => { reportMonth.value = todayMonth(); load() })
</script>

<style media="print">
#report-content { padding: 20px; }
.el-card { break-inside: avoid; page-break-inside: avoid; }
.el-button { display: none; }
h2, .el-row { margin-bottom: 8px !important; }
</style>