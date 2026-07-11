<template>
  <div>
    <h2>收入分析</h2>
    <el-row :gutter="16">
      <el-col :span="6"><el-card><div style="text-align:center"><div style="color:#999;font-size:13px">总收入</div><div style="font-size:24px;font-weight:bold;color:#67c23a;margin-top:8px">{{ fmt(data.total) }}</div></div></el-card></el-col>
      <el-col :span="6"><el-card><div style="text-align:center"><div style="color:#999;font-size:13px">月均收入</div><div style="font-size:24px;font-weight:bold;color:#409eff;margin-top:8px">{{ fmt(monthlyAvg) }}</div></div></el-card></el-col>
      <el-col :span="6"><el-card><div style="text-align:center"><div style="color:#999;font-size:13px">主要来源</div><div style="font-size:20px;font-weight:bold;color:#e6a23c;margin-top:8px">{{ topCat }}</div></div></el-card></el-col>
      <el-col :span="6"><el-card><div style="text-align:center"><div style="color:#999;font-size:13px">记录笔数</div><div style="font-size:24px;font-weight:bold;margin-top:8px">{{ totalCount }}</div></div></el-card></el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="10">
        <el-card><template #header>收入构成</template>
          <div ref="pieChart" style="height: 350px"></div>
        </el-card>
      </el-col>
      <el-col :span="14">
        <el-card><template #header>月度收入趋势</template>
          <div ref="trendChart" style="height: 350px"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-card><template #header>收入明细</template>
      <el-table :data="data.categories" stripe>
        <el-table-column prop="category" label="类别" />
        <el-table-column prop="amount" label="金额" width="150"><template #default="{row}">{{ fmt(row.amount) }}</template></el-table-column>
        <el-table-column prop="ratio" label="占比" width="100"><template #default="{row}">{{ row.ratio }}%</template></el-table-column>
        <el-table-column prop="count" label="笔数" width="80" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, computed } from 'vue'
import { fetchIncome } from '../api/index.js'
import { createChart } from '../utils/chart.js'

const data = ref({ categories: [], total: 0, trend: [] })
const pieChart = ref(null)
const trendChart = ref(null)
const fmt = v => '¥' + Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 0 })

const monthlyAvg = computed(() => data.value.trend.length ? Math.round(data.value.total / data.value.trend.length) : 0)
const totalCount = computed(() => data.value.categories.reduce((s, c) => s + c.count, 0))
const topCat = computed(() => {
  const cats = data.value.categories
  return cats.length ? cats[0].category : ''
})

onMounted(async () => {
  data.value = await fetchIncome()
  nextTick(() => {
    if (pieChart.value) {
      createChart(pieChart.value, {
        tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
        series: [{ type: 'pie', radius: ['30%', '60%'], data: data.value.categories.map(i => ({ name: i.category, value: i.amount })), label: { formatter: '{b}\n{d}%' } }],
      })
    }
    if (trendChart.value) {
      createChart(trendChart.value, {
        tooltip: { trigger: 'axis' }, grid: { left: 60, right: 20, bottom: 60 },
        xAxis: { type: 'category', data: data.value.trend.map(d => d.month), axisLabel: { rotate: 45 } },
        yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
        series: [{ type: 'bar', data: data.value.trend.map(d => d.amount), itemStyle: { color: '#67c23a' } }],
      })
    }
  })
})
</script>