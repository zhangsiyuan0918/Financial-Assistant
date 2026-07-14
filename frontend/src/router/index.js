import { createRouter, createWebHistory } from 'vue-router'
import { checkAuth } from '../api/index.js'

const routes = [
  { path: '/login', name: '登录', component: () => import('../views/Login.vue') },
  { path: '/', name: 'AI 助手', component: () => import('../views/AiAssistant.vue'), meta: { requiresAuth: true } },
  { path: '/status', name: '状态', component: () => import('../views/Status.vue'), meta: { requiresAuth: true } },
  { path: '/settings', name: '设置', component: () => import('../views/Settings.vue'), meta: { requiresAuth: true } },
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
