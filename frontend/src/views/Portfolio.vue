<template>
  <div>
    <h2>持仓盈亏</h2>
    <el-row :gutter="16">
      <el-col :span="6"><el-card><div style="text-align:center"><div style="color:#999;font-size:13px">持仓成本</div><div style="font-size:24px;font-weight:bold;margin-top:8px">{{ fmt(data.total_cost) }}</div></div></el-card></el-col>
      <el-col :span="6"><el-card><div style="text-align:center"><div style="color:#999;font-size:13px">当前市值</div><div style="font-size:24px;font-weight:bold;color:#409eff;margin-top:8px">{{ fmt(data.total_current) }}</div></div></el-card></el-col>
      <el-col :span="6"><el-card><div style="text-align:center"><div style="color:#999;font-size:13px">总盈亏</div><div style="font-size:24px;font-weight:bold;margin-top:8px;color:{{ data.total_pnl >= 0 ? '#67c23a' : '#f56c6c' }}">{{ data.total_pnl >= 0 ? '+' : '' }}{{ fmt(data.total_pnl) }}</div></div></el-card></el-col>
      <el-col :span="6"><el-card><div style="text-align:center"><div style="color:#999;font-size:13px">总收益率</div><div style="font-size:24px;font-weight:bold;margin-top:8px;color:{{ data.total_pnl >= 0 ? '#67c23a' : '#f56c6c' }}">{{ data.total_pnl_pct }}%</div></div></el-card></el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="8">
        <el-card><template #header>持仓分布</template>
          <div ref="pieChart" style="height: 300px"></div>
        </el-card>
      </el-col>
      <el-col :span="16">
        <el-card><template #header>账户盈亏</template>
          <div ref="barChart" style="height: 300px"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-card><template #header>持仓明细</template>
      <el-table :data="data.items" stripe>
        <el-table-column prop="account" label="账户" />
        <el-table-column prop="type" label="类型" width="80" />
        <el-table-column prop="cost" label="成本" width="120"><template #default="{row}">{{ fmt(row.cost) }}</template></el-table-column>
        <el-table-column prop="current" label="市值" width="120"><template #default="{row}">{{ fmt(row.current) }}</template></el-table-column>
        <el-table-column prop="pnl" label="盈亏" width="120"><template #default="{row}"><span :style="{color: row.pnl >= 0 ? '#67c23a' : '#f56c6c'}">{{ row.pnl >= 0 ? '+' : '' }}{{ fmt(row.pnl) }}</span></template></el-table-column>
        <el-table-column prop="pnl_pct" label="收益率" width="100"><template #default="{row}"><span :style="{color: row.pnl >= 0 ? '#67c23a' : '#f56c6c'}">{{ row.pnl_pct }}%</span></template></el-table-column>
      </el-table>
    </el-card>
    <el-alert type="info" show-icon style="margin-top:16px" :closable="false" title="当前仅展示账户级汇总，不含具体标的（个股/单只基金）明细。如需标的级跟踪，可扩展 config.py 中的 PORTFOLIO 配置。" />
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { fetchPortfolio } from '../api/index.js'
import { createChart } from '../utils/chart.js'

const data = ref({ items: [], total_cost: 0, total_current: 0, total_pnl: 0, total_pnl_pct: 0 })
const pieChart = ref(null)
const barChart = ref(null)
const fmt = v => '¥' + Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 0 })

onMounted(async () => {
  data.value = await fetchPortfolio()
  nextTick(() => {
    if (pieChart.value) {
      createChart(pieChart.value, {
        tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
        series: [{ type: 'pie', radius: ['30%', '60%'], data: data.value.items.map(i => ({ name: i.account, value: i.current })), label: { formatter: '{b}\n{d}%' } }],
      })
    }
    if (barChart.value) {
      createChart(barChart.value, {
        tooltip: { trigger: 'axis' }, grid: { left: 60, right: 20 },
        xAxis: { type: 'category', data: data.value.items.map(i => i.account) },
        yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
        series: [
          { name: '成本', type: 'bar', data: data.value.items.map(i => i.cost), itemStyle: { color: '#909399' } },
          { name: '市值', type: 'bar', data: data.value.items.map(i => i.current), itemStyle: { color: '#409eff' } },
        ],
        legend: { bottom: 0 },
      })
    }
  })
})
</script>