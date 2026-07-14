<template>
  <div>
    <h2>设置</h2>

    <!-- LLM Config -->
    <el-card>
      <template #header><span style="font-size:14px">AI 配置</span></template>
      <el-form :model="llmForm" label-width="100px" size="small">
        <el-form-item label="API Key">
          <el-input v-model="llmForm.api_key" placeholder="输入 API Key" show-password />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="llmForm.base_url" placeholder="https://api.deepseek.com" />
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="llmForm.model" placeholder="deepseek-v4-flash" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveLlmConfig" :loading="llmSaving">保存</el-button>
          <el-tag v-if="llmConfigured" type="success" size="small" style="margin-left:8px">已配置</el-tag>
          <el-tag v-else type="info" size="small" style="margin-left:8px">未配置</el-tag>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Budget Config -->
    <el-card style="margin-top:4px">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:14px">月度预算</span>
          <el-button size="small" type="primary" @click="saveBudget" :loading="budgetSaving">保存</el-button>
        </div>
      </template>
      <el-form label-width="80px" size="small">
        <el-form-item v-for="item in budgetForm" :key="item.category" :label="item.category">
          <el-input-number v-model="item.budget" :min="0" :step="500" style="width:180px" />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Data Management -->
    <el-card style="margin-top:4px">
      <template #header><span style="font-size:14px">数据管理</span></template>
      <el-space wrap>
        <el-button size="small" type="primary" plain @click="uploadVisible = true">导入 CSV</el-button>
        <el-button size="small" type="success" plain @click="doBackfill" :loading="backfilling">回填历史净值</el-button>
        <el-tag v-if="dbStatus.migrated" type="success" size="small">SQLite</el-tag>
        <el-tag v-else type="info" size="small">CSV</el-tag>
        <span v-if="dbStatus.stats" style="font-size:12px;color:#999">
          {{ dbStatus.stats.records }} 条（{{ dbStatus.stats.date_from }} ~ {{ dbStatus.stats.date_to }}）
        </span>
      </el-space>
    </el-card>

    <!-- Upload Dialog -->
    <el-dialog v-model="uploadVisible" title="导入数据" width="500px">
      <el-upload drag :auto-upload="false" :on-change="handleUpload" accept=".csv">
        <el-icon style="font-size:48px;color:#409eff"><Upload /></el-icon>
        <div style="margin-top:8px">将 CSV 文件拖到此处</div>
      </el-upload>
      <div v-if="uploadResult" style="margin-top:12px;padding:12px;background:#f0f9eb;border-radius:4px">
        已导入 {{ uploadResult.records }} 条记录
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchLlmConfig, saveLlmConfig as saveLlm, fetchBudget, updateBudget, fetchDbStatus,
  migrateDb, rollbackDb, uploadCsv, backfillAssets } from '../api/index.js'

const llmForm = ref({ api_key: '', base_url: 'https://api.deepseek.com', model: 'deepseek-v4-flash' })
const llmConfigured = ref(false)
const llmSaving = ref(false)

const budgetForm = ref([])
const budgetSaving = ref(false)

const dbStatus = ref({ migrated: false, stats: null })
const backfilling = ref(false)
const uploadVisible = ref(false)
const uploadResult = ref(null)

async function saveLlmConfig() {
  llmSaving.value = true
  try {
    await saveLlm(llmForm.value)
    llmConfigured.value = true
    ElMessage.success('配置已保存')
  } catch {
    ElMessage.error('保存失败')
  }
  llmSaving.value = false
}

async function saveBudget() {
  budgetSaving.value = true
  try {
    const obj = {}
    for (const item of budgetForm.value) obj[item.category] = item.budget
    await updateBudget(obj)
    ElMessage.success('预算已保存')
  } catch {
    ElMessage.error('保存失败')
  }
  budgetSaving.value = false
}

async function doBackfill() {
  backfilling.value = true
  try {
    await backfillAssets()
    ElMessage.success('历史净值已回填')
  } catch {
    ElMessage.error('回填失败')
  }
  backfilling.value = false
}

async function handleUpload(file) {
  uploadResult.value = null
  try {
    uploadResult.value = await uploadCsv(file.raw)
  } catch {}
}

onMounted(async () => {
  const [llm, bd, db] = await Promise.all([
    fetchLlmConfig(), fetchBudget(), fetchDbStatus(),
  ])
  if (llm.configured) {
    llmConfigured.value = true
    llmForm.value.base_url = llm.base_url || 'https://api.deepseek.com'
    llmForm.value.model = llm.model || 'deepseek-v4-flash'
  }
  budgetForm.value = (bd.items || []).map(i => ({ category: i.category, budget: i.budget }))
  dbStatus.value = db
})
</script>
