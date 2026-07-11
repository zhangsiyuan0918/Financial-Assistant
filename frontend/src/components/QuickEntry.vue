<template>
  <el-card style="margin-bottom:12px">
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:14px;font-weight:bold">记一笔</span>
        <el-button size="small" text @click="showTemplateForm = !showTemplateForm">
          {{ showTemplateForm ? '关闭' : '+ 添加模板' }}
        </el-button>
      </div>
    </template>

    <!-- 常用模板快捷按钮 -->
    <div v-if="templates.length" style="margin-bottom:10px;display:flex;gap:6px;flex-wrap:wrap">
      <button v-for="t in templates" :key="t.id" @click="applyTpl(t)"
        style="padding:4px 10px;background:#f0f9eb;color:#67c23a;border:1px solid #b3e19d;border-radius:4px;cursor:pointer;font-size:12px">
        {{ t.name }} ¥{{ t.amount.toLocaleString() }}
      </button>
    </div>

    <!-- 创建模板表单 -->
    <div v-if="showTemplateForm" style="margin-bottom:10px;padding:10px;background:#f5f7fa;border-radius:4px">
      <div style="font-size:12px;color:#999;margin-bottom:6px">创建常用模板</div>
      <el-row :gutter="6" align="middle">
        <el-col :span="5"><el-input v-model="tplForm.name" size="small" placeholder="模板名称" /></el-col>
        <el-col :span="4"><el-input-number v-model="tplForm.amount" size="small" :min="0.01" :step="10" :precision="2" style="width:100%" /></el-col>
        <el-col :span="4">
          <el-select v-model="tplForm.category" size="small" style="width:100%" placeholder="分类">
            <el-option v-for="cat in currentCategories" :key="cat" :label="cat" :value="cat" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="tplForm.type" size="small" style="width:100%">
            <el-option label="支出" value="支出" />
            <el-option label="收入" value="收入" />
          </el-select>
        </el-col>
        <el-col :span="3">
          <el-button size="small" type="primary" @click="saveTpl" :disabled="!tplForm.name || !tplForm.amount || !tplForm.category">
            保存
          </el-button>
        </el-col>
      </el-row>
    </div>

    <!-- 输入字段 -->
    <el-row :gutter="8" align="middle">
      <el-col :span="3">
        <el-radio-group v-model="form.type" size="small" @change="form.category = ''">
          <el-radio-button value="支出">支出</el-radio-button>
          <el-radio-button value="收入">收入</el-radio-button>
        </el-radio-group>
      </el-col>
      <el-col :span="4">
        <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" :shortcuts="dateShortcuts" />
      </el-col>
      <el-col :span="4">
        <el-input-number v-model="form.amount" :min="0.01" :step="10" :precision="2" size="small" style="width:100%" placeholder="金额" />
      </el-col>
      <el-col :span="4">
        <el-select v-model="form.category" size="small" style="width:100%" placeholder="分类">
          <el-option v-for="cat in currentCategories" :key="cat" :label="cat" :value="cat" />
        </el-select>
      </el-col>
      <el-col :span="4">
        <el-select v-model="form.account" size="small" style="width:100%" placeholder="账户">
          <el-option v-for="acc in accounts" :key="acc" :label="acc" :value="acc" />
        </el-select>
      </el-col>
      <el-col :span="5">
        <el-input v-model="form.note" size="small" placeholder="备注（输入后自动推荐分类）" clearable
          @input="onNoteInput" />
      </el-col>
    </el-row>

    <!-- 智能分类推荐 -->
    <div v-if="suggestions.length && !form.category" style="margin-top:6px;display:flex;gap:6px;align-items:center">
      <span style="font-size:11px;color:#999">推荐：</span>
      <button v-for="s in suggestions" :key="s.category" @click="form.category = s.category"
        style="padding:2px 8px;background:#f0f9eb;color:#67c23a;border:1px solid #b3e19d;border-radius:3px;cursor:pointer;font-size:11px">
        {{ s.category }}
        <span style="color:#999;font-size:10px">({{ Math.round(s.confidence * 100) }}%)</span>
      </button>
    </div>

    <!-- 按钮行 -->
    <div style="margin-top:10px;display:flex;gap:8px;align-items:center">
      <button @click="submit" :disabled="!form.amount || !form.category"
        style="padding:8px 20px;background:#409eff;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:13px">
        {{ loading ? '记账中...' : '记账' }}
      </button>
      <button @click="showHistory = !showHistory"
        style="padding:8px 16px;background:#fff;color:#606266;border:1px solid #dcdfe6;border-radius:4px;cursor:pointer;font-size:13px">
        {{ showHistory ? '收起历史' : '查看历史记录' }}
      </button>
    </div>

    <!-- 分析结果 -->
    <div v-if="analysis" style="margin-top:12px;font-size:13px">
      <el-divider style="margin:8px 0" />
      <div style="display:flex;justify-content:space-between;margin-bottom:8px">
        <span style="font-weight:bold">本月分析</span>
        <span style="color:#999">{{ analysis.month_summary.month }} · {{ analysis.month_summary.count }}笔</span>
      </div>

      <div v-if="analysis.suggestions.length" style="margin-bottom:8px">
        <div v-for="(s, i) in analysis.suggestions" :key="i" style="padding:2px 0;color:#e6a23c;font-size:12px">
          {{ s }}
        </div>
      </div>

      <div style="margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px">
          <span>本月支出 ¥{{ analysis.month_summary.total_expense.toLocaleString() }}</span>
          <span>预算 ¥{{ analysis.budget.total_budget.toLocaleString() }} ({{ analysis.budget.total_ratio }}%)</span>
        </div>
        <el-progress :percentage="Math.min(analysis.budget.total_ratio, 100)" :stroke-width="10"
          :color="analysis.budget.total_ratio > 100 ? '#f56c6c' : analysis.budget.total_ratio > 80 ? '#e6a23c' : '#67c23a'" />
      </div>

      <div>
        <div v-for="item in analysis.budget.items.slice(0, 3)" :key="item.category"
          style="display:flex;align-items:center;padding:2px 0;font-size:12px">
          <span style="color:#666;width:48px">{{ item.category }}</span>
          <el-progress :percentage="Math.min(item.ratio, 100)" :stroke-width="6" style="flex:1;margin:0 6px"
            :color="item.ratio > 100 ? '#f56c6c' : item.ratio > 80 ? '#e6a23c' : '#409eff'" />
          <span style="color:#999;width:80px;text-align:right">
            ¥{{ item.spent.toLocaleString() }}/{{ item.budget.toLocaleString() }}
          </span>
        </div>
      </div>
    </div>

    <!-- 历史记录 -->
    <div v-if="showHistory" style="margin-top:12px">
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
      <div v-else style="max-height:300px;overflow-y:auto">
        <div v-for="(tx, i) in historyList" :key="i"
          style="display:flex;align-items:center;padding:6px 0;border-bottom:1px solid #f5f5f5;font-size:13px">
          <div style="flex:1">
            <span>{{ tx.category }}</span>
            <span v-if="tx.note" style="color:#999;margin-left:6px;font-size:12px">{{ tx.note }}</span>
          </div>
          <span style="color:#999;margin-right:8px;font-size:12px">{{ tx.date }}</span>
          <span :style="{fontWeight:500,marginRight:'8px',color: tx.type === '收入' ? '#67c23a' : '#f56c6c'}">
            {{ tx.type === '收入' ? '+' : '-' }}¥{{ Number(tx.amount).toLocaleString() }}
          </span>
          <button @click="deleteTx(tx)"
            style="padding:2px 8px;background:none;color:#f56c6c;border:1px solid #f56c6c;border-radius:3px;cursor:pointer;font-size:11px">
            删除
          </button>
        </div>
      </div>
    </div>

    <!-- 信用卡状态 -->
    <div v-if="creditCard.balance > 0" style="margin-top:12px;padding:12px;background:#fef0f0;border-radius:4px;border:1px solid #fbc4c4">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <div>
          <span style="font-weight:bold;font-size:13px;color:#f56c6c">信用卡待还</span>
          <span style="font-size:20px;font-weight:bold;color:#f56c6c;margin-left:8px">¥{{ creditCard.balance.toLocaleString() }}</span>
        </div>
        <button @click="showPayCC = !showPayCC"
          style="padding:6px 12px;background:#f56c6c;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px">
          {{ showPayCC ? '取消' : '还款' }}
        </button>
      </div>
      <!-- 还款表单 -->
      <div v-if="showPayCC" style="margin-top:8px;display:flex;gap:8px;align-items:center">
        <el-input-number v-model="payAmount" :min="0" :max="creditCard.balance" :step="100" size="small" style="width:140px" />
        <el-select v-model="payAccount" size="small" style="width:120px" placeholder="还款账户">
          <el-option v-for="acc in accounts" :key="acc" :label="acc" :value="acc" />
        </el-select>
        <button @click="doPayCC" :disabled="!payAmount || payAmount > creditCard.balance"
          style="padding:6px 16px;background:#67c23a;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px">
          确认还款
        </button>
      </div>
      <!-- 最近信用卡记录 -->
      <div v-if="creditCard.history.length" style="margin-top:8px">
        <div v-for="(tx, i) in creditCard.history.slice().reverse().slice(0, 3)" :key="i"
          style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0;border-top:1px solid #fde2e2">
          <span>{{ tx.date }} {{ tx.note }}</span>
          <span :style="{color: tx.type === '消费' ? '#f56c6c' : '#67c23a'}">
            {{ tx.type === '消费' ? '+' : '-' }}¥{{ tx.amount.toLocaleString() }}
          </span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchTransactions, fetchCreditCard, payCreditCard, addTransactionApi, deleteTransactionApi, fetchCurrentAnalysis, fetchAccountsApi, suggestCategory, fetchTemplates, createTemplate, applyTemplate as applyTemplateApi } from '../api/index.js'

const emit = defineEmits(['recorded', 'deleted'])

const categories = ['餐饮', '交通', '购物', '居住', '娱乐', '社交', '旅游', '车辆', '医疗', '个护', '学习', '数字消费', '其他']
const incomeCategories = ['工资', '奖金', '理财收益', '兼职', '退款', '红包', '其他收入']
const currentCategories = computed(() => form.value.type === '收入' ? incomeCategories : categories)

function today() { return new Date().toISOString().slice(0, 10) }
function daysAgo(n) { const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10) }

const dateShortcuts = [
  { text: '今天', value: today() },
  { text: '昨天', value: daysAgo(1) },
  { text: '前天', value: daysAgo(2) },
]

const form = ref({ date: today(), amount: null, category: '', account: '', note: '' })
const loading = ref(false)
const analysis = ref(null)
const showHistory = ref(false)
const historyList = ref([])
const historyMonths = ref([])
const historyMonth = ref('')
const historyLoading = ref(false)
const accounts = ref([])
const creditCard = ref({ balance: 0, history: [] })
const showPayCC = ref(false)
const payAmount = ref(0)
const payAccount = ref('招行储蓄卡')
const suggestions = ref([])
let suggestTimer = null
const templates = ref([])
const showTemplateForm = ref(false)
const tplForm = ref({ name: '', amount: null, category: '', type: '支出' })

async function submit() {
  if (!form.value.amount || !form.value.category) return
  loading.value = true
  try {
    const res = await addTransactionApi({ ...form.value, date: form.value.date })

    if (res.error) {
      ElMessage.error(res.error)
      return
    }

    analysis.value = res
    ElMessage.success('记账成功')
    emit('recorded', res)

    form.value = { date: today(), amount: null, note: '', category: '', account: '' }

    if (showHistory.value) loadHistory()
    loadCreditCard()
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
    await deleteTransactionApi(tx.id)
    ElMessage.success('已删除')
    loadHistory()
    loadCreditCard()
    refreshAnalysis()
    emit('deleted')
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

async function refreshAnalysis() {
  try {
    analysis.value = await fetchCurrentAnalysis()
  } catch (e) {
    analysis.value = null
  }
}

onMounted(async () => {
  loadHistory()
  loadCreditCard()
  loadTemplates()
  try {
    accounts.value = await fetchAccountsApi()
  } catch {}
})

async function loadTemplates() {
  try {
    templates.value = await fetchTemplates()
  } catch {}
}

async function saveTpl() {
  try {
    await createTemplate(tplForm.value)
    ElMessage.success('模板已保存')
    tplForm.value = { name: '', amount: null, category: '', type: '支出' }
    showTemplateForm.value = false
    loadTemplates()
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

async function applyTpl(t) {
  try {
    const res = await applyTemplateApi(t.id)
    if (res.error) {
      ElMessage.error(res.error)
      return
    }
    analysis.value = res
    ElMessage.success(`已记录「${t.name}」`)
    emit('recorded', res)
    loadHistory()
    loadCreditCard()
  } catch (e) {
    ElMessage.error('记账失败')
  }
}

async function loadCreditCard() {
  try {
    creditCard.value = await fetchCreditCard()
  } catch {}
}

function onNoteInput() {
  clearTimeout(suggestTimer)
  const text = form.value.note
  if (!text || text.length < 2) {
    suggestions.value = []
    return
  }
  suggestTimer = setTimeout(async () => {
    try {
      suggestions.value = await suggestCategory(text)
    } catch {
      suggestions.value = []
    }
  }, 300)
}

async function doPayCC() {
  if (!payAmount.value || payAmount.value > creditCard.value.balance) return
  try {
    await payCreditCard({ amount: payAmount.value, account: payAccount.value })
    ElMessage.success('还款成功')
    payAmount.value = 0
    showPayCC.value = false
    loadCreditCard()
    emit('deleted')  // 触发父组件刷新
  } catch (e) {
    ElMessage.error('还款失败')
  }
}
</script>
