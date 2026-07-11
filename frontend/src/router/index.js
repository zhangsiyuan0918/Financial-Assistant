import { createRouter, createWebHistory } from 'vue-router'
import Overview from '../views/Overview.vue'
import Spending from '../views/Spending.vue'
import Forecast from '../views/Forecast.vue'
import Simulation from '../views/Simulation.vue'
import Income from '../views/Income.vue'
import Portfolio from '../views/Portfolio.vue'
import Report from '../views/Report.vue'
import Login from '../views/Login.vue'
import Alerts from '../views/Alerts.vue'
import Goals from '../views/Goals.vue'
import AIQuery from '../views/AIQuery.vue'
import Settings from '../views/Settings.vue'
import { checkAuth } from '../api/index.js'

const routes = [
  { path: '/login', name: '登录', component: Login },
  { path: '/', name: '总览', component: Overview, meta: { requiresAuth: true } },
  { path: '/spending', name: '支出分析', component: Spending, meta: { requiresAuth: true } },
  { path: '/income', name: '收入分析', component: Income, meta: { requiresAuth: true } },
  { path: '/forecast', name: '支出预测', component: Forecast, meta: { requiresAuth: true } },
  { path: '/simulation', name: '情景模拟', component: Simulation, meta: { requiresAuth: true } },
  { path: '/portfolio', name: '持仓盈亏', component: Portfolio, meta: { requiresAuth: true } },
  { path: '/report', name: '月度报告', component: Report, meta: { requiresAuth: true } },
  { path: '/alerts', name: '预警中心', component: Alerts, meta: { requiresAuth: true } },
  { path: '/goals', name: '目标管理', component: Goals, meta: { requiresAuth: true } },
  { path: '/ai', name: 'AI 助手', component: AIQuery, meta: { requiresAuth: true } },
  { path: '/settings', name: '设置', component: Settings, meta: { requiresAuth: true } },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to, from, next) => {
  if (to.meta.requiresAuth) {
    try {
      const res = await checkAuth()
      if (!res.authenticated) {
        next('/login')
        return
      }
    } catch {
      next('/login')
      return
    }
  }
  next()
})

export default router
