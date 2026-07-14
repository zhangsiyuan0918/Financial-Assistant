<template>
  <div class="ai-assistant">
    <!-- Header -->
    <div class="chat-header">
      <span style="font-size:16px;font-weight:bold"> FinFlow AI</span>
      <div style="display:flex;gap:8px">
        <el-button text size="small" @click="$router.push('/status')">状态</el-button>
        <el-button v-if="messages.length" text size="small" @click="clearChatHistory">
          <el-icon><Delete /></el-icon> 清空
        </el-button>
      </div>
    </div>

    <!-- Insight banner -->
    <div v-if="latestInsight" class="insight-banner">
      <el-icon color="#409eff"><InfoFilled /></el-icon>
      <span style="flex:1;margin-left:8px">{{ latestInsight.title }}</span>
      <el-button text size="small" @click="dismissInsight">知道了</el-button>
    </div>

    <!-- Chat area -->
    <div class="chat-area" ref="chatArea">
      <!-- Welcome message - always visible -->
      <div class="welcome">
        <div style="font-size:32px;margin-bottom:12px"> FinFlow</div>
        <div style="font-size:16px;font-weight:500;margin-bottom:8px">你好，我是你的 AI 财务助手</div>
        <div style="color:#999;font-size:13px">我可以帮你分析消费、追踪预算、管理资产。试试问我：</div>
        <div class="quick-questions">
          <el-button v-for="q in quickQuestions" :key="q" size="small" plain @click="askQuestion(q)">
            {{ q }}
          </el-button>
        </div>
      </div>

      <!-- Messages (appear below welcome) -->
      <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.role]">
        <div class="message-avatar">
          <el-icon v-if="msg.role === 'assistant'" :size="18"><ChatDotRound /></el-icon>
          <el-icon v-else :size="18"><User /></el-icon>
        </div>
        <div class="message-content">
          <div v-html="formatMessage(msg.content)"></div>
          <div v-if="msg.time" class="message-time">{{ msg.time }}</div>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="message assistant">
        <div class="message-avatar">
          <el-icon :size="18"><ChatDotRound /></el-icon>
        </div>
        <div class="message-content">
          <el-icon class="is-loading"><Loading /></el-icon> 思考中...
        </div>
      </div>
    </div>

    <!-- Quick bookkeeping -->
    <div class="quick-book">
      <div class="book-row">
        <el-radio-group v-model="quickType" size="small">
          <el-radio-button value="支出">支出</el-radio-button>
          <el-radio-button value="收入">收入</el-radio-button>
        </el-radio-group>
        <el-date-picker v-model="quickDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:120px" />
      </div>
      <div class="book-row">
        <el-input v-model="quickAmount" placeholder="金额" type="number" style="width:80px" size="small" />
        <el-select v-model="quickCategory" placeholder="分类" size="small" style="width:80px" filterable>
          <el-option v-for="c in currentCategories" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="quickAccount" placeholder="账户" size="small" style="width:80px" filterable>
          <el-option v-for="a in accounts" :key="a" :label="a" :value="a" />
        </el-select>
        <el-input v-model="quickNote" placeholder="备注" size="small" style="flex:1" @input="onNoteInput" />
        <button @click="submitQuickBook" :disabled="bookLoading" class="book-btn">记账</button>
      </div>
    </div>

    <!-- Category suggestions -->
    <div v-if="suggestions.length" class="suggestions">
      <el-tag v-for="s in suggestions" :key="s.category" size="small" style="margin-right:4px;cursor:pointer"
        @click="quickCategory = s.category">
        {{ s.category }} ({{ Math.round(s.confidence * 100) }}%)
      </el-tag>
    </div>

    <!-- Input area -->
    <div class="input-area">
      <div class="input-row">
        <input v-model="inputText" placeholder="问我任何关于财务的问题..."
          @keyup.enter="sendMessage" :disabled="loading" class="chat-input" />
        <button @click="sendMessage" :disabled="loading || !inputText.trim()" class="send-btn">
          <span v-if="!loading">发送</span>
          <span v-else>...</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { askQuestion as apiAsk, fetchInsights, markInsightRead, addTransactionApi, suggestCategory, fetchAccountsApi } from '../api/index.js'

const messages = ref([])
const inputText = ref('')
const loading = ref(false)
const chatArea = ref(null)
const insights = ref([])

const quickAmount = ref(null)
const quickType = ref('支出')
const quickDate = ref(new Date().toISOString().slice(0, 10))
const quickCategory = ref('')
const quickAccount = ref('')
const quickNote = ref('')
const bookLoading = ref(false)
const suggestions = ref([])
const accounts = ref([])

const expenseCategories = ['餐饮', '交通', '购物', '居住', '娱乐', '社交', '旅游', '车辆', '医疗', '个护', '学习', '数字消费', '其他']
const incomeCategories = ['工资', '奖金', '理财收益', '兼职', '退款', '红包', '其他收入']
const currentCategories = computed(() => quickType.value === '收入' ? incomeCategories : expenseCategories)

const quickQuestions = [
  '我这个月花了多少钱？',
  '哪个分类支出最多？',
  '跟上个月比怎么样？',
  '我的预算还剩多少？',
  '帮我分析一下消费习惯',
  '我的净资产有多少？',
  '怎么省钱？',
  '这个月预计花多少？',
]

const latestInsight = computed(() => insights.value[0] || null)

function formatMessage(content) {
  if (!content) return ''
  return content.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || loading.value) return

  const now = new Date()
  const time = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0')

  messages.value.push({ role: 'user', content: text, time })
  inputText.value = ''
  loading.value = true
  scrollToBottom()

  try {
    const res = await apiAsk(text, 'default')
    messages.value.push({ role: 'assistant', content: res.answer || '抱歉，我暂时无法回答这个问题。', time })
  } catch {
    messages.value.push({ role: 'assistant', content: '请求失败，请稍后重试。', time })
  }

  loading.value = false
  scrollToBottom()
}

function askQuestion(q) {
  inputText.value = q
  sendMessage()
}

async function submitQuickBook() {
  if (!quickAmount.value || !quickCategory.value) {
    ElMessage.warning('金额和分类必填')
    return
  }
  bookLoading.value = true
  try {
    const res = await addTransactionApi({
      amount: quickAmount.value,
      category: quickCategory.value,
      note: quickNote.value,
      type: quickType.value,
      date: quickDate.value,
      account: quickAccount.value,
    })
    if (res.error) { ElMessage.error(res.error); return }

    const now = new Date()
    const time = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0')

    // 保存当前值（清空前）
    const amount = quickAmount.value
    const category = quickCategory.value
    const account = quickAccount.value
    const note = quickNote.value
    const txType = quickType.value
    const txDate = quickDate.value

    // Add user message (what was recorded)
    const userMsg = `记一笔${txType}：${category} ¥${amount}` + (note ? `（${note}）` : '') + (account ? ` [${account}]` : '') + ` ${txDate}`
    messages.value.push({ role: 'user', content: userMsg, time })

    // Reset form immediately
    quickAmount.value = null
    quickType.value = '支出'
    quickDate.value = new Date().toISOString().slice(0, 10)
    quickCategory.value = ''
    quickAccount.value = ''
    quickNote.value = ''
    suggestions.value = []
    scrollToBottom()

    // Show AI insights from backend (instant)
    if (res.ai_insights && res.ai_insights.length) {
      res.ai_insights.forEach(ins => {
        messages.value.push({ role: 'assistant', content: `💡 ${ins.title}\n${ins.content}`, time })
      })
      scrollToBottom()
    }

    // Auto ask AI for analysis
    loading.value = true
    try {
      const analysisPrompt = `我刚刚记了一笔${txType}：${category} ¥${amount}` + (note ? `，备注是${note}` : '') + `，日期是${txDate}。帮我分析一下这笔${txType}。`
      const aiRes = await apiAsk(analysisPrompt, 'default')
      if (aiRes.answer) {
        messages.value.push({ role: 'assistant', content: aiRes.answer, time })
      }
    } catch {}
    loading.value = false
    scrollToBottom()
  } catch {
    ElMessage.error('记账失败')
  }
  bookLoading.value = false
}

let noteTimer = null
function onNoteInput() {
  clearTimeout(noteTimer)
  if (quickNote.value.length < 2) { suggestions.value = []; return }
  noteTimer = setTimeout(async () => {
    try { suggestions.value = await suggestCategory(quickNote.value) } catch {}
  }, 300)
}

async function dismissInsight() {
  if (latestInsight.value) {
    await markInsightRead(latestInsight.value.id)
    insights.value = insights.value.filter(i => i.id !== latestInsight.value.id)
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (chatArea.value) chatArea.value.scrollTop = chatArea.value.scrollHeight
  })
}

onMounted(async () => {
  // Load accounts
  try { accounts.value = await fetchAccountsApi() } catch {}

  // Load unread insights
  try { insights.value = await fetchInsights() } catch {}
})

function clearChatHistory() {
  messages.value = []
  messages.value.push({
    role: 'assistant',
    content: '对话已清空。有什么可以帮你的？',
  })
}
</script>

<style scoped>
.ai-assistant {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 120px);
  max-width: 800px;
  margin: 0 auto;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #ebeef5;
  margin-bottom: 8px;
}

.insight-banner {
  display: flex;
  align-items: center;
  padding: 10px 16px;
  background: #ecf5ff;
  border-radius: 8px;
  margin-bottom: 8px;
  font-size: 13px;
}

.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
}

.welcome {
  text-align: center;
  padding: 40px 20px;
}

.quick-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 16px;
}

.message {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  padding: 0 16px;
}

.message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.message.assistant .message-avatar { background: #ecf5ff; color: #409eff; }
.message.user .message-avatar { background: #f0f9eb; color: #67c23a; }

.message-content {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
}

.message.assistant .message-content { background: #f5f7fa; }
.message.user .message-content { background: #ecf5ff; }

.message-time {
  font-size: 10px;
  color: #c0c4cc;
  margin-top: 4px;
}

.quick-book {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 12px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  margin-bottom: 8px;
}

.book-row {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}

.book-btn {
  padding: 4px 12px;
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  white-space: nowrap;
}
.book-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.suggestions {
  padding: 0 12px 8px;
}

.input-area {
  padding: 0 0 8px;
}

.input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.chat-input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  transition: border-color .2s;
}
.chat-input:focus { border-color: #409eff; }
.chat-input:disabled { background: #f5f7fa; }

.send-btn {
  padding: 10px 20px;
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}
.send-btn:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
