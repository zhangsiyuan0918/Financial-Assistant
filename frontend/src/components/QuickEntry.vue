<template>
  <el-card class="quick-entry">
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <el-space>
          <span style="font-size:14px;font-weight:bold">记一笔</span>
          <el-tag size="small" type="success">实时分析</el-tag>
        </el-space>
        <el-button size="small" text @click="showHistory = !showHistory">
          {{ showHistory ? '收起' : '历史记录' }}
        </el-button>
      </div>
    </template>

    <el-form :model="form" inline size="default">
      <el-form-item label="日期">
        <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" style="width:130px" :shortcuts="dateShortcuts" />
      </el-form-item>
      <el-form-item label="金额">
        <el-input-number v-model="form.amount" :min="0.01" :step="10" :precision="2" style="width:120px" placeholder="0.00" />
      </el-form-item>
      <el-form-item label="分类">
        <el-select v-model="form.category" style="width:100px" placeholder="分类">
          <el-option v-for="cat in categories" :key="cat" :label="cat" :value="cat" />
        </el-select>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.note" style="width:120px" placeholder="可选" clearable />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="submit" :loading="loading" :disabled="!form.amount || !form.category">
          记账
        </el-button>
      </el-form-item>
    </el-form>

    <!-- 分析结果 -->
    <div v-if="analysis" class="analysis-result">
      <el-divider style="margin:8px 0" />
      <div class="analysis-header">
        <span style="font-weight:bold;font-size:13px">本月分析</span>
        <span style="font-size:12px;color:#999">{{ analysis.month_summary.month }} · {{ analysis.month_summary.count }}笔</span>
      </div>

      <div v-if="analysis.suggestions.length" class="suggestions">
        <div v-for="(s, i) in analysis.suggestions" :key="i" style="font-size:12px;padding:2px 0;color:#e6a23c">
          {{ s }}
        </div>
      </div>

      <div class="budget-bar">
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px">
          <span>本月支出 ¥{{ analysis.month_summary.total.toLocaleString() }}</span>
          <span>预算 ¥{{ analysis.budget.total_budget.toLocaleString() }} ({{ analysis.budget.total_ratio }}%)</span>
        </div>
        <el-progress :percentage="Math.min(analysis.budget.total_ratio, 100)" :stroke-width="10"
          :color="analysis.budget.total_ratio > 100 ? '#f56c6c' : analysis.budget.total_ratio > 80 ? '#e6a23c' : '#67c23a'" />
      </div>

      <div class="category-list">
        <div v-for="item in analysis.budget.items.slice(0, 3)" :key="item.category" class="category-item">
          <span style="font-size:12px;color:#666;width:48px">{{ item.category }}</span>
          <el-progress :percentage="Math.min(item.ratio, 100)" :stroke-width="6" style="flex:1;margin:0 6px"
            :color="item.ratio > 100 ? '#f56c6c' : item.ratio > 80 ? '#e6a23c' : '#409eff'" />
          <span style="font-size:11px;color:#999;width:80px;text-align:right">
            ¥{{ item.spent.toLocaleString() }}/{{ item.budget.toLocaleString() }}
          </span>
        </div>
      </div>
    </div>

    <!-- 历史记录 -->
    <div v-if="showHistory" class="history-section">
      <el-divider style="margin:8px 0" />
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <span style="font-weight:bold;font-size:13px">历史记录</span>
        <el-select v-model="historyMonth" size="small" style="width:120px" @change="loadHistory">
          <el-option label="全部" value="" />
          <el-option v-for="m in historyMonths" :key="m" :label="m" :value="m" />
        </el-select>
      </div>
      <div v-if="historyLoading" style="text-align:center;color:#999;padding:12px">加载中...</div>
      <div v-else-if="!historyList.length" style="text-align:center;color:#999;padding:12px">暂无记录</div>
      <div v-else class="history-list">
        <div v-for="(tx, i) in historyList" :key="i" class="history-item">
          <div style="flex:1">
            <span style="font-size:13px">{{ tx.category }}</span>
            <span v-if="tx.note" style="font-size:12px;color:#999;margin-left:6px">{{ tx.note }}</span>
          </div>
          <span style="font-size:12px;color:#999;margin-right:8px">{{ tx.date }}</span>
          <span style="font-size:13px;color:#f56c6c;font-weight:500;margin-right:8px">-¥{{ Number(tx.amount).toLocaleString() }}</span>
          <el-button size="small" type="danger" text @click="deleteTx(tx)">删除</el-button>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchTransactions } from '../api/index.js'

const emit = defineEmits(['recorded'])

const categories = ['餐饮', '交通', '购物', '居住', '娱乐', '社交', '旅游', '车辆', '医疗', '个护', '学习', '数字消费', '其他']

function today() { return new Date().toISOString().slice(0, 10) }
function daysAgo(n) { const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10) }

const dateShortcuts = [
  { text: '今天', value: today() },
  { text: '昨天', value: daysAgo(1) },
  { text: '前天', value: daysAgo(2) },
]

const form = ref({ date: today(), amount: null, category: '', note: '' })
const loading = ref(false)
const analysis = ref(null)
const showHistory = ref(false)
const historyList = ref([])
const historyMonths = ref([])
const historyMonth = ref('')
const historyLoading = ref(false)

async function submit() {
  if (!form.value.amount || !form.value.category) return
  loading.value = true
  try {
    const res = await fetch('/api/transaction', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...form.value, date: form.value.date }),
    }).then(r => r.json())

    if (res.error) {
      ElMessage.error(res.error)
      return
    }

    analysis.value = res
    ElMessage.success('记账成功')
    emit('recorded', res)

    form.value = { date: today(), amount: null, note: '', category: '' }

    if (showHistory.value) loadHistory()
  } catch (e) {
    ElMessage.error('记账失败')
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const txs = await fetchTransactions(historyMonth.value || undefined)
    historyList.value = txs
    // 提取可用月份
    if (!historyMonths.value.length) {
      const allTxs = await fetchTransactions()
      const months = [...new Set(allTxs.map(t => t.date.slice(0, 7)))].sort().reverse()
      historyMonths.value = months
    }
  } catch (e) {
    historyList.value = []
  } finally {
    historyLoading.value = false
  }
}

async function deleteTx(tx) {
  try {
    await fetch(`/api/transaction/${encodeURIComponent(tx.created_at)}`, { method: 'DELETE' })
    ElMessage.success('已删除')
    loadHistory()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

onMounted(() => { loadHistory() })
</script>

<style scoped>
.quick-entry { margin-bottom: 12px; }
.analysis-result { font-size: 13px; }
.analysis-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
.suggestions { margin-bottom: 8px; }
.budget-bar { margin-bottom: 8px; }
.category-list { margin-bottom: 8px; }
.category-item { display: flex; align-items: center; padding: 2px 0; }
.history-list { max-height: 300px; overflow-y: auto; }
.history-item { display: flex; align-items: center; padding: 6px 0; border-bottom: 1px solid #f5f5f5; }
.history-item:last-child { border-bottom: none; }
</style>
