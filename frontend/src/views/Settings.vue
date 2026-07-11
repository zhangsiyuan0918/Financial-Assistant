<template>
  <div style="max-width: 600px; margin: 0 auto">
    <h2>设置</h2>
    <el-card>
      <template #header><strong>AI 模型配置</strong></template>
      <el-form label-width="120px">
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" type="password" show-password placeholder="sk-..." />
        </el-form-item>
        <el-form-item label="接口地址">
          <el-input v-model="form.base_url" placeholder="https://api.deepseek.com" />
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="form.model" placeholder="deepseek-v4-flash" />
        </el-form-item>
        <el-form-item>
          <div style="display:flex;gap:8px">
            <button @click="save" :disabled="saving"
              style="padding:8px 20px;background:#409eff;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:13px">
              {{ saving ? '保存中...' : '保存' }}
            </button>
            <button @click="test" :disabled="testing"
              style="padding:8px 16px;background:#fff;color:#606266;border:1px solid #dcdfe6;border-radius:4px;cursor:pointer;font-size:13px">
              {{ testing ? '测试中...' : '测试连接' }}
            </button>
          </div>
        </el-form-item>
        <el-form-item v-if="testResult">
          <el-alert :type="testResult.success ? 'success' : 'error'" show-icon :closable="false"
            :title="testResult.success ? '连接成功' : testResult.error" />
        </el-form-item>
        <el-form-item label="状态">
          <el-tag v-if="configured" type="success" size="small">已配置</el-tag>
          <el-tag v-else type="info" size="small">未配置（使用规则引擎）</el-tag>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { fetchLlmConfig, saveLlmConfig, askQuestion } from '../api/index.js'

const form = ref({ api_key: '', base_url: 'https://api.deepseek.com', model: 'deepseek-v4-flash' })
const configured = ref(false)
const saving = ref(false)
const testing = ref(false)
const testResult = ref(null)

onMounted(async () => {
  const cfg = await fetchLlmConfig()
  configured.value = cfg.configured
  if (cfg.base_url) form.value.base_url = cfg.base_url
  if (cfg.model) form.value.model = cfg.model
})

async function save() {
  saving.value = true
  await saveLlmConfig(form.value)
  configured.value = true
  saving.value = false
}

async function test() {
  testing.value = true
  testResult.value = null
  await saveLlmConfig(form.value)
  try {
    const res = await askQuestion('用一句话回答：1+1等于几？')
    testResult.value = { success: true }
  } catch (e) {
    testResult.value = { success: false, error: e.message || '连接失败' }
  }
  testing.value = false
}
</script>