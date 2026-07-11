<template>
  <div style="max-width: 800px; margin: 0 auto">
    <h2>
      AI 财务助手
      <el-button size="small" text @click="clearChat" style="float:right;margin-top:8px">
        <el-icon><Delete /></el-icon> 清空对话
      </el-button>
    </h2>
    <el-card style="min-height: 400px; display: flex; flex-direction: column">
      <div ref="chatBox" style="flex: 1; overflow-y: auto; padding: 8px; max-height: 500px">
        <div v-for="(msg, i) in messages" :key="i"
          style="margin-bottom: 12px; display: flex; justify-content: msg.role === 'user' ? 'flex-end' : 'flex-start'">
          <div :style="{
            maxWidth: '80%',
            padding: '8px 12px',
            borderRadius: '8px',
            whiteSpace: 'pre-wrap',
            lineHeight: '1.6',
            fontSize: '13px',
            background: msg.role === 'user' ? '#ecf5ff' : '#f0f9eb'
          }">
            <div v-if="msg.role === 'assistant' && msg.content.startsWith('(')"
              style="color:#999;font-size:11px;margin-bottom:4px">
              {{ msg.content }}
            </div>
            <div v-else>{{ msg.content }}</div>
          </div>
        </div>
        <div v-if="loading" style="text-align:center;color:#999;padding:20px">
          <el-icon class="is-loading"><Loading /></el-icon>
          思考中...
        </div>
      </div>
      <el-divider style="margin: 8px 0" />
      <el-row :gutter="8">
        <el-col :span="20">
          <el-input v-model="question" placeholder="用自然语言问财务问题..." @keyup.enter="send" clearable />
        </el-col>
        <el-col :span="4">
          <el-button type="primary" style="width:100%" @click="send" :disabled="loading || !question.trim()">
            发送
          </el-button>
        </el-col>
      </el-row>
    </el-card>
    <el-card style="margin-top: 12px">
      <template #header>试试这样问</template>
      <div style="font-size: 13px; line-height: 2">
        <el-tag v-for="ex in examples" :key="ex" style="margin:4px;cursor:pointer"
          @click="question = ex; send()">{{ ex }}</el-tag>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { askQuestion, clearConversation } from '../api/index.js'

const sessionId = ref('session_' + Date.now())
const messages = ref([
  { role: 'assistant', content: '你好！我是你的财务助手，可以问我关于收支、资产、预算、投资等方面的问题。支持多轮对话，试试看！' }
])
const question = ref('')
const loading = ref(false)
const chatBox = ref(null)

const examples = [
  '我这个月花了多少钱',
  '上个月吃饭花了多少',
  '最近3个月支出趋势',
  '我的净资产有多少',
  '预算还剩多少',
  '我的基金赚了还是亏了',
  '储蓄率多少',
  '今年一共花了多少',
  '财务健康评分',
  '帮我查一下上个月最大的3笔消费',
]

async function send() {
  const q = question.value.trim()
  if (!q || loading.value) return
  messages.value.push({ role: 'user', content: q })
  question.value = ''
  loading.value = true
  scrollDown()
  try {
    const res = await askQuestion(q, sessionId.value)
    messages.value.push({ role: 'assistant', content: res.answer })
  } catch {
    messages.value.push({ role: 'assistant', content: '查询出错了，请重试' })
  }
  loading.value = false
  scrollDown()
}

async function clearChat() {
  await clearConversation(sessionId.value)
  sessionId.value = 'session_' + Date.now()
  messages.value = [
    { role: 'assistant', content: '对话已清空。有什么财务问题可以继续问我！' }
  ]
}

function scrollDown() {
  nextTick(() => {
    if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
  })
}
</script>
