<template>
  <div>
    <h2>消费习惯分析</h2>

    <!-- 消费速度 -->
    <el-card v-if="habits.spending_velocity">
      <template #header><span style="font-size:14px">消费速度</span></template>
      <el-row :gutter="16">
        <el-col :span="8">
          <div style="text-align:center">
            <div style="color:#999;font-size:12px">本月已消费</div>
            <div style="font-size:20px;font-weight:bold;color:#f56c6c;margin-top:4px">¥{{ habits.spending_velocity.current_total.toLocaleString() }}</div>
          </div>
        </el-col>
        <el-col :span="8">
          <div style="text-align:center">
            <div style="color:#999;font-size:12px">历史月均</div>
            <div style="font-size:20px;font-weight:bold;color:#409eff;margin-top:4px">¥{{ habits.spending_velocity.avg_monthly.toLocaleString() }}</div>
          </div>
        </el-col>
        <el-col :span="8">
          <div style="text-align:center">
            <div style="color:#999;font-size:12px">预计本月</div>
            <div style="font-size:20px;font-weight:bold;margin-top:4px"
              :style="{color: habits.spending_velocity.deviation_pct > 20 ? '#f56c6c' : habits.spending_velocity.deviation_pct < -20 ? '#67c23a' : '#409eff'}">
              ¥{{ habits.spending_velocity.projected.toLocaleString() }}
            </div>
            <el-tag :type="habits.spending_velocity.status === '偏快' ? 'danger' : habits.spending_velocity.status === '偏慢' ? 'success' : 'info'" size="small">
              {{ habits.spending_velocity.status }}
            </el-tag>
          </div>
        </el-col>
      </el-row>
      <div style="margin-top:12px;padding:8px;background:#f5f7fa;border-radius:4px;font-size:13px;color:#666">
        💡 {{ habits.spending_velocity.insight }}
      </div>
    </el-card>

    <el-row :gutter="12">
      <!-- 星期消费模式 -->
      <el-col :xs="24" :sm="12">
        <el-card v-if="habits.weekday_pattern && habits.weekday_pattern.data.length">
          <template #header><span style="font-size:14px">星期消费模式</span></template>
          <div ref="weekdayChart" style="height:250px"></div>
          <div style="margin-top:8px;padding:8px;background:#f5f7fa;border-radius:4px;font-size:13px;color:#666">
            💡 {{ habits.weekday_pattern.insight }}
          </div>
        </el-card>
      </el-col>

      <!-- 月内消费节奏 -->
      <el-col :xs="24" :sm="12">
        <el-card v-if="habits.monthly_rhythm && habits.monthly_rhythm.data.length">
          <template #header><span style="font-size:14px">月内消费节奏</span></template>
          <div ref="rhythmChart" style="height:250px"></div>
          <div style="margin-top:8px;padding:8px;background:#f5f7fa;border-radius:4px;font-size:13px;color:#666">
            💡 {{ habits.monthly_rhythm.insight }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 消费频率 -->
    <el-card v-if="habits.spending_frequency" style="margin-top:12px">
      <template #header><span style="font-size:14px">消费频率</span></template>
      <el-row :gutter="16">
        <el-col :span="6">
          <div style="text-align:center">
            <div style="color:#999;font-size:12px">月均消费天数</div>
            <div style="font-size:20px;font-weight:bold;color:#409eff;margin-top:4px">{{ habits.spending_frequency.avg_spend_days_per_month }}天</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div style="text-align:center">
            <div style="color:#999;font-size:12px">日均笔数</div>
            <div style="font-size:20px;font-weight:bold;color:#e6a23c;margin-top:4px">{{ habits.spending_frequency.avg_tx_per_day }}笔</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div style="text-align:center">
            <div style="color:#999;font-size:12px">单笔均额</div>
            <div style="font-size:20px;font-weight:bold;color:#67c23a;margin-top:4px">¥{{ habits.spending_frequency.avg_per_transaction.toLocaleString() }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div style="text-align:center">
            <div style="color:#999;font-size:12px">大额消费占比</div>
            <div style="font-size:20px;font-weight:bold;color:#f56c6c;margin-top:4px">{{ habits.spending_frequency.big_tx_ratio }}%</div>
            <div style="font-size:11px;color:#999">单笔>¥500</div>
          </div>
        </el-col>
      </el-row>
      <div style="margin-top:12px;padding:8px;background:#f5f7fa;border-radius:4px;font-size:13px;color:#666">
        💡 {{ habits.spending_frequency.insight }}
      </div>
    </el-card>

    <!-- 分类趋势 -->
    <el-card v-if="habits.category_trends && habits.category_trends.length" style="margin-top:12px">
      <template #header><span style="font-size:14px">分类支出趋势（最近6个月）</span></template>
      <el-table :data="habits.category_trends" stripe size="small">
        <el-table-column prop="category" label="分类" width="100" />
        <el-table-column label="趋势" width="80">
          <template #default="{row}">
            <el-tag :type="row.trend === '上升' ? 'danger' : row.trend === '下降' ? 'success' : 'info'" size="small">
              {{ row.trend }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trend_pct" label="变化" width="80">
          <template #default="{row}">
            <span :style="{color: row.trend_pct > 0 ? '#f56c6c' : '#67c23a'}">
              {{ row.trend_pct > 0 ? '+' : '' }}{{ row.trend_pct }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="近6月数据" min-width="200">
          <template #default="{row}">
            <span v-for="(d, i) in row.data" :key="i" style="font-size:11px;margin-right:6px">
              {{ d.month.slice(5) }}月: ¥{{ d.amount.toLocaleString() }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 消费集中度 -->
    <el-card v-if="habits.concentration && habits.concentration.top3_categories.length" style="margin-top:12px">
      <template #header><span style="font-size:14px">消费集中度</span></template>
      <el-row :gutter="16">
        <el-col :span="8">
          <div style="text-align:center">
            <div style="color:#999;font-size:12px">TOP3占比</div>
            <div style="font-size:24px;font-weight:bold;color:#409eff;margin-top:4px">{{ habits.concentration.top3_ratio }}%</div>
            <div style="font-size:11px;color:#999">共{{ habits.concentration.total_categories }}个分类</div>
          </div>
        </el-col>
        <el-col :span="16">
          <div v-for="(cat, i) in habits.concentration.top3_categories" :key="i"
            style="display:flex;align-items:center;padding:6px 0;border-bottom:1px solid #f5f5f5">
            <span style="width:24px;font-weight:bold;color:#409eff">{{ i + 1 }}</span>
            <span style="flex:1">{{ cat.category }}</span>
            <span style="color:#999;margin-right:8px">¥{{ cat.amount.toLocaleString() }}</span>
            <el-progress :percentage="cat.ratio" :stroke-width="8" style="width:120px"
              :color="i === 0 ? '#409eff' : i === 1 ? '#67c23a' : '#e6a23c'" />
          </div>
        </el-col>
      </el-row>
      <div style="margin-top:12px;padding:8px;background:#f5f7fa;border-radius:4px;font-size:13px;color:#666">
        💡 {{ habits.concentration.insight }}
      </div>
    </el-card>

    <!-- AI 智能洞察 -->
    <el-card v-if="habits.ai_insights && habits.ai_insights.insights && habits.ai_insights.insights.length" style="margin-top:12px">
      <template #header>
        <el-space>
          <span style="font-size:14px">AI 智能洞察</span>
          <el-tag size="small" type="success">AI 分析</el-tag>
        </el-space>
      </template>
      <div v-for="(insight, i) in habits.ai_insights.insights" :key="i"
        style="padding:10px;margin-bottom:8px;border-radius:6px;font-size:13px"
        :style="{background: insight.severity === 'danger' ? '#fef0f0' : insight.severity === 'warning' ? '#fdf6ec' : '#f0f9eb', borderLeft: '3px solid ' + (insight.severity === 'danger' ? '#f56c6c' : insight.severity === 'warning' ? '#e6a23c' : '#67c23a')}">
        <div style="font-weight:bold;margin-bottom:4px">{{ insight.title }}</div>
        <div style="color:#666">{{ insight.detail }}</div>
      </div>
    </el-card>
    <el-card v-else-if="habits.ai_insights" style="margin-top:12px">
      <div style="text-align:center;color:#999;padding:20px">
        {{ habits.ai_insights.summary || 'AI 洞察生成中...' }}
      </div>
    </el-card>

    <AiFloat />
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { fetchSpendingHabits } from '../api/index.js'
import AiFloat from '../components/AiFloat.vue'
import { createChart } from '../utils/chart.js'

const habits = ref({})
const weekdayChart = ref(null)
const rhythmChart = ref(null)

onMounted(async () => {
  habits.value = await fetchSpendingHabits()

  await nextTick()

  // 渲染星期消费图表
  if (weekdayChart.value && habits.value.weekday_pattern?.data.length) {
    const data = habits.value.weekday_pattern.data
    createChart(weekdayChart.value, {
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 20, bottom: 30 },
      xAxis: { type: 'category', data: data.map(d => d.day) },
      yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
      series: [{ type: 'bar', data: data.map(d => d.total), itemStyle: { color: '#409eff' } }],
    })
  }

  // 渲染月内节奏图表
  if (rhythmChart.value && habits.value.monthly_rhythm?.data.length) {
    const data = habits.value.monthly_rhythm.data
    createChart(rhythmChart.value, {
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 20, bottom: 30 },
      xAxis: { type: 'category', data: data.map(d => d.period) },
      yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
      series: [{ type: 'bar', data: data.map(d => d.total), itemStyle: { color: '#67c23a' } }],
    })
  }
})
</script>
