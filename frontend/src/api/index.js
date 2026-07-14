import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 30000 })

api.interceptors.request.use(config => {
  const token = localStorage.getItem('auth_token')
  if (token) config.headers['X-Auth-Token'] = token
  return config
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response && err.response.status === 401) {
      localStorage.removeItem('auth_token')
      window.location.hash = '#/login'
    }
    return Promise.reject(err)
  }
)

// Auth
export function loginApi(password) { return api.post('/auth/login', { password }).then(r => r.data) }
export function checkAuth() { return api.get('/auth/status').then(r => r.data) }

// AI Chat
export function askQuestion(question, sessionId) { return api.post('/query', { question, session_id: sessionId }).then(r => r.data) }

// AI Insights
export function fetchInsights() { return api.get('/insights').then(r => r.data) }
export function markInsightRead(id) { return api.post('/insights/read', { id }).then(r => r.data) }
export function generateInsight(type) { return api.post('/insights/generate', { type }).then(r => r.data) }
export function fetchDailyDigest() { return api.get('/daily-digest').then(r => r.data) }

// Transaction
export function addTransactionApi(data) { return api.post('/transaction', data).then(r => r.data) }

// Accounts
export function fetchAccountsApi() { return api.get('/accounts').then(r => r.data) }

// Overview
export function fetchOverview() { return api.get('/overview').then(r => r.data) }

// Smart Category
export function suggestCategory(text) { return api.get('/suggest-category', { params: { text } }).then(r => r.data) }

// Budget
export function fetchBudget(month) { return api.get('/budget', { params: { month } }).then(r => r.data) }
export function updateBudget(data) { return api.put('/budget', data).then(r => r.data) }

// LLM Config
export function fetchLlmConfig() { return api.get('/llm/config').then(r => r.data) }
export function saveLlmConfig(cfg) { return api.post('/llm/config', cfg).then(r => r.data) }

// Data Management
export function fetchDbStatus() { return api.get('/db/status').then(r => r.data) }
export function migrateDb() { return api.post('/db/migrate').then(r => r.data) }
export function rollbackDb() { return api.post('/db/rollback').then(r => r.data) }
export function uploadCsv(file) {
  const form = new FormData()
  form.append('file', file)
  return api.post('/upload', form).then(r => r.data)
}
export function backfillAssets() { return api.post('/assets/backfill').then(r => r.data) }

// Portfolio
export function fetchPortfolio() { return api.get('/portfolio').then(r => r.data) }

// Credit Card
export function fetchCreditCard() { return api.get('/credit-card').then(r => r.data) }
export function payCreditCard(data) { return api.post('/credit-card/pay', data).then(r => r.data) }

// Monthly Trend
export function fetchMonthly() { return api.get('/monthly').then(r => r.data) }

// Financial Health
export function fetchFinancialHealth() { return api.get('/health/detail').then(r => r.data) }
