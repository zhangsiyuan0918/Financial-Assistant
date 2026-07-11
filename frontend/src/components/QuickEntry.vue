<template>
  <el-card class="quick-entry">
    <template #header>
      <el-space>
        <span style="font-size:14px;font-weight:bold">记一笔</span>
        <el-tag size="small" type="success">实时分析</el-tag>
      </el-space>
    </template>

    <el-form :model="form" inline size="default">
      <el-form-item label="金额">
        <el-input-number v-model="form.amount" :min="0.01" :step="10" :precision="2" style="width:140px" placeholder="0.00" />
      </el-form-item>
      <el-form-item label="分类">
        <el-select v-model="form.category" style="width:120px" placeholder="选择分类">
          <el-option v-for="cat in categories" :key="cat" :label="cat" :value="cat" />
        </el-select>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.note" style="width:160px" placeholder="可选" clearable />
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

      <!-- 建议 -->
      <div v-if="analysis.suggestions.length" class="suggestions">
        <div v-for="(s, i) in analysis.suggestions" :key="i" style="font-size:12px;padding:2px 0;color:#e6a23c">
          {{ s }}
        </div>
      </div>

      <!-- 总支出进度 -->
      <div class="budget-bar">
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px">
          <span>本月支出 ¥{{ analysis.month_summary.total.toLocaleString() }}</span>
          <span>预算 ¥{{ analysis.budget.total_budget.toLocaleString() }} ({{ analysis.budget.total_ratio }}%)</span>
        </div>
        <el-progress :percentage="Math.min(analysis.budget.total_ratio, 100)" :stroke-width="10"
          :color="analysis.budget.total_ratio > 100 ? '#f56c6c' : analysis.budget.total_ratio > 80 ? '#e6a23c' : '#67c23a'" />
      </div>

      <!-- 分类明细（前3） -->
      <div class="category-list">
        <div v-for="(item, i) in analysis.budget.items.slice(0, 3)" :key="item.category" class="category-item">
          <span style="font-size:12px;color:#666">{{ item.category }}</span>
          <el-progress :percentage="Math.min(item.ratio, 100)" :stroke-width="6" style="flex:1;margin:0 8px"
            :color="item.ratio > 100 ? '#f56c6c' : item.ratio > 80 ? '#e6a23c' : '#409eff'" />
          <span style="font-size:11px;color:#999;width:80px;text-align:right">
            ¥{{ item.spent.toLocaleString() }}/{{ item.budget.toLocaleString() }}
          </span>
        </div>
      </div>

      <!-- 最近5笔 -->
      <div v-if="analysis.recent_5.length" class="recent-list">
        <div style="font-size:12px;color:#999;margin-bottom:4px">最近记录</div>
        <div v-for="tx in analysis.recent_5.slice().reverse()" :key="tx.date + tx.amount"
          style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0;border-bottom:1px solid #f5f5f5">
          <span>{{ tx.category }} {{ tx.note ? '- ' + tx.note : '' }}</span>
          <span style="color:#f56c6c">-¥{{ tx.amount.toLocaleString() }}</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const emit = defineEmits(['recorded'])

const categories = ['餐饮', '交通', '购物', '居住', '娱乐', '社交', '旅游', '车辆', '医疗', '个护', '学习', '数字消费', '其他']
const form = ref({ amount: null, category: '', note: '' })
const loading = ref(false)
const analysis = ref(null)

async function submit() {
  if (!form.value.amount || !form.value.category) return
  loading.value = true
  try {
    const res = await fetch('/api/transaction', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form.value),
    }).then(r => r.json())

    if (res.error) {
      ElMessage.error(res.error)
      return
    }

    analysis.value = res
    ElMessage.success('记账成功')
    emit('recorded', res)

    // 重置表单
    form.value.amount = null
    form.value.note = ''
  } catch (e) {
    ElMessage.error('记账失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.quick-entry { margin-bottom: 12px; }
.analysis-result { font-size: 13px; }
.analysis-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
.suggestions { margin-bottom: 8px; }
.budget-bar { margin-bottom: 8px; }
.category-list { margin-bottom: 8px; }
.category-item { display: flex; align-items: center; padding: 2px 0; }
.recent-list { margin-top: 8px; }
</style>
