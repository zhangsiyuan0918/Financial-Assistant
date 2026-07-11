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

export function fetchOverview() { return api.get('/overview').then(r => r.data) }
export function fetchSpending(year = 'all') {
  return api.get(`/spending`, { params: { year } }).then(r => r.data)
}
export function fetchSpendingDetail(category, year = 'all') {
  return api.get(`/spending/${category}`, { params: { year } }).then(r => r.data)
}
export function fetchMonthly() { return api.get('/monthly').then(r => r.data) }
export function fetchIncome() { return api.get('/income').then(r => r.data) }
export function fetchForecast() { return api.get('/forecast').then(r => r.data) }
export function fetchHistory() { return api.get('/history').then(r => r.data) }
export function fetchAssetHistory() { return api.get('/assets/history').then(r => r.data) }
export function backfillAssets() { return api.post('/assets/backfill').then(r => r.data) }
export function fetchSimulation(params) {
  return api.get('/simulation', { params }).then(r => r.data)
}
export function fetchCalcTarget(params) {
  return api.get('/calculate/target', { params }).then(r => r.data)
}
export function fetchCalcYears(params) {
  return api.get('/calculate/years', { params }).then(r => r.data)
}
export function fetchCalcRate(params) {
  return api.get('/calculate/rate', { params }).then(r => r.data)
}
export function fetchPortfolio() { return api.get('/portfolio').then(r => r.data) }
export function fetchSeasonal() { return api.get('/spending/seasonal').then(r => r.data) }
export function fetchBudget(month) {
  return api.get('/budget', { params: { month } }).then(r => r.data)
}
export function fetchMonthlyReport(month) {
  return api.get('/report/monthly', { params: { month } }).then(r => r.data)
}
export function updateAssets(data) {
  return api.put('/assets', data).then(r => r.data)
}
export function updateBudget(data) {
  return api.put('/budget', data).then(r => r.data)
}
export function uploadCsv(file) {
  const form = new FormData()
  form.append('file', file)
  return api.post('/upload', form).then(r => r.data)
}
export function loginApi(password) {
  return api.post('/auth/login', { password }).then(r => r.data)
}
export function askQuestion(question, sessionId) {
  return api.post('/query', { question, session_id: sessionId }).then(r => r.data)
}
export function clearConversation(sessionId) {
  return api.post('/query/clear', { session_id: sessionId }).then(r => r.data)
}
export function fetchLlmConfig() { return api.get('/llm/config').then(r => r.data) }
export function saveLlmConfig(cfg) { return api.post('/llm/config', cfg).then(r => r.data) }
export function checkAuth() {
  return api.get('/auth/status').then(r => r.data)
}
export function fetchHealth() { return api.get('/health').then(r => r.data) }
export function fetchDbStatus() { return api.get('/db/status').then(r => r.data) }
export function migrateDb() { return api.post('/db/migrate').then(r => r.data) }
export function rollbackDb() { return api.post('/db/rollback').then(r => r.data) }
export function fetchComparison(year, month) { return api.get(`/comparison?year=${year}&month=${month}`).then(r => r.data) }
export function fetchAlerts() { return api.get('/alerts').then(r => r.data) }
export function resolveAlert(id) { return api.post(`/alerts/${id}/resolve`).then(r => r.data) }
export function fetchGoals() { return api.get('/goals').then(r => r.data) }
export function createGoal(data) { return api.post('/goals', data).then(r => r.data) }
export function updateGoal(id, data) { return api.put(`/goals/${id}`, data).then(r => r.data) }
export function deleteGoal(id) { return api.delete(`/goals/${id}`).then(r => r.data) }
export function refreshForecast() { return api.post('/forecast/refresh').then(r => r.data) }
export function pollAlerts() { return api.get('/alerts/poll').then(r => r.data) }
export function fetchAnnualReport(year) { return api.get('/report/annual', { params: { year } }).then(r => r.data) }
export function fetchForecastBacktest() { return api.get('/forecast/backtest').then(r => r.data) }
export function checkBudget(data) { return api.post('/budget/check', data).then(r => r.data) }
export function fetchTransactions(month) { return api.get('/transactions', { params: { month } }).then(r => r.data) }
export function fetchCreditCard() { return api.get('/credit-card').then(r => r.data) }
export function payCreditCard(data) { return api.post('/credit-card/pay', data).then(r => r.data) }
export function addTransactionApi(data) { return api.post('/transaction', data).then(r => r.data) }
export function deleteTransactionApi(created_at) { return api.delete(`/transaction/${encodeURIComponent(created_at)}`).then(r => r.data) }
export function fetchCurrentAnalysis() { return api.get('/analysis/current').then(r => r.data) }
export function fetchAccountsApi() { return api.get('/accounts').then(r => r.data) }
