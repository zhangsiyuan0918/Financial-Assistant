<template>
  <div v-if="!isMobile && route.path === '/'">
    <!-- Float button -->
    <el-button circle type="primary" size="large" @click="visible = true"
      class="ai-float-btn">
      <el-icon :size="20"><ChatDotRound /></el-icon>
    </el-button>

    <!-- Chat drawer -->
    <el-drawer v-model="visible" direction="btt" :size="drawerSize" :show-close="false"
      :with-header="false" class="ai-drawer">
      <div class="ai-drawer-inner">
        <div class="ai-drawer-header">
          <span style="font-weight:bold">AI 助手</span>
          <el-tag v-if="contextHint" size="small" type="info">{{ contextHint }}</el-tag>
          <el-button size="small" text @click="visible = false" style="margin-left:auto">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>

        <div ref="chatBox" class="ai-chat-box">
          <div v-for="(msg, i) in messages" :key="i"
            :class="msg.role === 'user' ? 'ai-msg-user' : 'ai-msg-assistant'">
            <div class="ai-msg-bubble" :class="msg.role">
              {{ msg.content }}
            </div>
          </div>
          <div v-if="loading" class="ai-loading">
            <el-icon class="is-loading"><Loading /></el-icon>
            思考中...
          </div>
        </div>

        <div class="ai-input-bar">
          <el-input v-model="question" :placeholder="`问关于${contextHint}的问题...`"
            @keyup.enter="send" clearable size="small" />
          <el-button type="primary" size="small" @click="send"
            :disabled="loading || !question.trim()">发送</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, inject, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { askQuestion } from '../api/index.js'

const route = useRoute()
const visible = ref(false)
const messages = ref([])
const question = ref('')
const loading = ref(false)
const chatBox = ref(null)
const globalLoading = inject('globalLoading', ref(false))
const isMobile = ref(false)

function checkMobile() {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

const contextHint = computed(() => {
  const map = {
    '/': '财务总览',
    '/book': '记账',
    '/analysis': '数据分析',
    '/assets': '资产',
    '/settings': '设置',
  }
  return map[route.path] || '财务数据'
})

const drawerSize = computed(() => {
  if (typeof window !== 'undefined' && window.innerWidth < 768) return '70%'
  return '45%'
})

async function send() {
  const q = question.value.trim()
  if (!q || loading.value) return

  messages.value.push({ role: 'user', content: q })
  question.value = ''
  loading.value = true
  scrollDown()

  try {
    const res = await askQuestion(q, 'ai_float_' + route.path)
    messages.value.push({ role: 'assistant', content: res.answer })
  } catch {
    messages.value.push({ role: 'assistant', content: '查询出错了' })
  }
  loading.value = false
  scrollDown()
}

function scrollDown() {
  nextTick(() => {
    if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
  })
}
</script>

<style scoped>
.ai-float-btn {
  position: fixed;
  bottom: 80px;
  right: 24px;
  z-index: 999;
  box-shadow: 0 4px 12px rgba(0,0,0,.15);
  width: 48px;
  height: 48px;
}

@media (max-width: 768px) {
  .ai-float-btn { bottom: 72px; right: 16px; width: 44px; height: 44px; }
}

.ai-drawer-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0;
}

.ai-drawer-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid #eee;
}

.ai-chat-box {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}

.ai-msg-user {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
.ai-msg-assistant {
  display: flex;
  justify-content: flex-start;
  margin-bottom: 8px;
}

.ai-msg-bubble {
  max-width: 80%;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.ai-msg-bubble.user { background: #ecf5ff; }
.ai-msg-bubble.assistant { background: #f0f9eb; }

.ai-loading {
  text-align: center;
  color: #999;
  padding: 12px;
  font-size: 13px;
}

.ai-input-bar {
  display: flex;
  gap: 8px;
  padding: 8px 16px;
  border-top: 1px solid #eee;
}
</style>
