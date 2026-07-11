<template>
  <div>
    <h2>情景模拟</h2>
    <el-tabs v-model="tab">
      <el-tab-pane label="正向模拟" name="forward">
        <el-row :gutter="16">
          <el-col :span="6">
            <el-card><template #header>参数设置</template>
              <el-form label-width="100px">
                <el-form-item label="月支出"><el-slider v-model="expense" :min="5000" :max="25000" :step="500" show-input /></el-form-item>
                <el-form-item label="年化收益"><el-slider v-model="rate" :min="0" :max="15" :step="0.5" show-input /></el-form-item>
                <el-form-item label="模拟年数"><el-slider v-model="years" :min="1" :max="30" :step="1" show-input /></el-form-item>
                <el-form-item><el-button type="primary" @click="runForward">开始模拟</el-button></el-form-item>
              </el-form>
            </el-card>
          </el-col>
          <el-col :span="18">
            <el-row :gutter="16">
              <el-col :span="8"><el-card><div style="text-align:center"><div style="color:#999;font-size:13px">起始终值</div><div style="font-size:22px;font-weight:bold;margin-top:8px">{{ fmt(fwd.initial_net_worth) }}</div></div></el-card></el-col>
              <el-col :span="8"><el-card><div style="text-align:center"><div style="color:#999;font-size:13px">月结余</div><div style="font-size:22px;font-weight:bold;color:#67c23a;margin-top:8px">{{ fmt(fwd.monthly_net) }}</div></div></el-card></el-col>
              <el-col :span="8"><el-card><div style="text-align:center"><div style="color:#999;font-size:13px">{{ years }}年后资产</div><div style="font-size:22px;font-weight:bold;color:#409eff;margin-top:8px">{{ fmt(fwd.final_net_worth) }}</div></div></el-card></el-col>
            </el-row>
            <el-card style="margin-top:16px">
              <div ref="simChart" style="height:350px"></div>
            </el-card>
          </el-col>
        </el-row>
        <el-card style="margin-top:16px"><template #header>逐年数据</template>
          <el-table :data="fwd.projection || []" stripe>
            <el-table-column prop="year" label="年份" width="100" />
            <el-table-column prop="net_worth" label="净资产"><template #default="{row}">{{ fmt(row.net_worth) }}</template></el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="反向计算" name="reverse">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-card><template #header>目标→月存</template>
              <el-form label-width="90px">
                <el-form-item label="目标金额"><el-input-number v-model="revTarget.target" :min="100000" :max="10000000" :step="100000" style="width:100%" /></el-form-item>
                <el-form-item label="年限"><el-input-number v-model="revTarget.years" :min="1" :max="50" :step="1" style="width:100%" /></el-form-item>
                <el-form-item label="年化收益"><el-input-number v-model="revTarget.rate" :min="0" :max="20" :step="0.5" style="width:100%" /></el-form-item>
                <el-form-item><el-button type="primary" @click="runTarget">计算</el-button></el-form-item>
              </el-form>
              <el-divider />
              <div v-if="revTargetRes.required_monthly_save">
                <div style="color:#999;font-size:13px">每月需存</div>
                <div style="font-size:22px;font-weight:bold;color:#e6a23c">{{ fmt(revTargetRes.required_monthly_save) }}</div>
                <div style="font-size:12px;color:#999;margin-top:8px">对应月支出: {{ fmt(revTargetRes.implied_monthly_expense) }}</div>
              </div>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card><template #header>目标→年限</template>
              <el-form label-width="90px">
                <el-form-item label="目标金额"><el-input-number v-model="revYears.target" :min="100000" :max="10000000" :step="100000" style="width:100%" /></el-form-item>
                <el-form-item label="月存"><el-input-number v-model="revYears.save" :min="1000" :max="50000" :step="1000" style="width:100%" /></el-form-item>
                <el-form-item label="年化收益"><el-input-number v-model="revYears.rate" :min="0" :max="20" :step="0.5" style="width:100%" /></el-form-item>
                <el-form-item><el-button type="primary" @click="runYears">计算</el-button></el-form-item>
              </el-form>
              <el-divider />
              <div v-if="revYearsRes.years">
                <div style="color:#999;font-size:13px">需要</div>
                <div style="font-size:22px;font-weight:bold;color:#409eff">{{ revYearsRes.years }} <span style="font-size:14px">年</span></div>
                <div style="font-size:12px;color:#999">({{ revYearsRes.months }} 个月)</div>
              </div>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card><template #header>目标→收益率</template>
              <el-form label-width="90px">
                <el-form-item label="目标金额"><el-input-number v-model="revRate.target" :min="100000" :max="10000000" :step="100000" style="width:100%" /></el-form-item>
                <el-form-item label="月存"><el-input-number v-model="revRate.save" :min="1000" :max="50000" :step="1000" style="width:100%" /></el-form-item>
                <el-form-item label="年限"><el-input-number v-model="revRate.years" :min="1" :max="50" :step="1" style="width:100%" /></el-form-item>
                <el-form-item><el-button type="primary" @click="runRate">计算</el-button></el-form-item>
              </el-form>
              <el-divider />
              <div v-if="revRateRes.annual_rate">
                <div style="color:#999;font-size:13px">需要年化收益</div>
                <div style="font-size:22px;font-weight:bold;color:#67c23a">{{ revRateRes.annual_rate }}<span style="font-size:14px">%</span></div>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>
    </el-tabs>

    <AiFloat />
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { fetchSimulation, fetchCalcTarget, fetchCalcYears, fetchCalcRate } from '../api/index.js'
import AiFloat from '../components/AiFloat.vue'
import { createChart } from '../utils/chart.js'

const tab = ref('forward')
const expense = ref(9622)
const rate = ref(5)
const years = ref(10)
const fwd = ref({ projection: [], monthly_net: 0, initial_net_worth: 0, final_net_worth: 0 })
const simChart = ref(null)

const revTarget = ref({ target: 500000, years: 10, rate: 5 })
const revTargetRes = ref({})
const revYears = ref({ target: 500000, save: 8000, rate: 5 })
const revYearsRes = ref({})
const revRate = ref({ target: 500000, save: 8000, years: 10 })
const revRateRes = ref({})

const fmt = v => '¥' + Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 0 })

async function runForward() {
  fwd.value = await fetchSimulation({ expense: expense.value, rate: rate.value, years: years.value })
  nextTick(() => {
    if (simChart.value) {
      const c = createChart(simChart.value, {
        tooltip: { trigger: 'axis' }, grid: { left: 80, bottom: 60 },
        xAxis: { type: 'category', data: fwd.value.projection.map(d => '第' + d.year + '年') },
        yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
        series: [{ type: 'line', data: fwd.value.projection.map(d => d.net_worth), smooth: true, areaStyle: { opacity: 0.2 }, lineStyle: { width: 3 } }],
      })
    }
  })
}

async function runTarget() {
  revTargetRes.value = await fetchCalcTarget(revTarget.value)
}
async function runYears() {
  revYearsRes.value = await fetchCalcYears(revYears.value)
}
async function runRate() {
  revRateRes.value = await fetchCalcRate(revRate.value)
}

onMounted(runForward)
</script>