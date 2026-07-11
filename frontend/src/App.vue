<template>
  <el-container style="min-height: 100vh">
    <el-aside :width="isMobile ? '0px' : '220px'" :class="{ 'mobile-hidden': isMobile }">
      <div class="sidebar-logo">
        <span style="font-size:18px;font-weight:bold">FinFlow</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409eff"
        :collapse="isMobile"
        class="sidebar-menu"
      >
        <el-menu-item index="/">
          <el-icon><DataBoard /></el-icon><span>总览</span>
        </el-menu-item>

        <el-sub-menu index="analysis">
          <template #title>
            <el-icon><TrendCharts /></el-icon><span>分析</span>
          </template>
          <el-menu-item index="/spending">支出分析</el-menu-item>
          <el-menu-item index="/habits">消费习惯</el-menu-item>
          <el-menu-item index="/income">收入分析</el-menu-item>
          <el-menu-item index="/portfolio">持仓盈亏</el-menu-item>
          <el-menu-item index="/report">月度报告</el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="planning">
          <template #title>
            <el-icon><MagicStick /></el-icon><span>规划</span>
          </template>
          <el-menu-item index="/forecast">支出预测</el-menu-item>
          <el-menu-item index="/simulation">情景模拟</el-menu-item>
          <el-menu-item index="/goals">目标管理</el-menu-item>
        </el-sub-menu>

        <el-menu-item index="/alerts">
          <el-icon><WarningFilled /></el-icon>
          <span>预警</span>
          <el-badge v-if="alertCount" :value="alertCount" :max="99" class="alert-badge" />
        </el-menu-item>

        <el-menu-item index="/ai">
          <el-icon><ChatDotRound /></el-icon><span>AI 助手</span>
        </el-menu-item>

        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon><span>设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-main style="background: #f0f2f5; padding: 20px; padding-bottom: 80px">
        <router-view />
      </el-main>
    </el-container>

    <!-- Mobile bottom navigation -->
    <nav v-if="isMobile" class="mobile-nav">
      <router-link v-for="item in mobileNavItems" :key="item.path" :to="item.path"
        class="mobile-nav-item" :class="{ active: route.path === item.path }">
        <el-icon :size="20"><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </router-link>
    </nav>
  </el-container>

  <!-- Global loading overlay -->
  <div v-if="globalLoading" class="global-loading">
    <el-icon class="is-loading" :size="24"><Loading /></el-icon>
    <span>加载中...</span>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, provide } from 'vue'
import { useRoute } from 'vue-router'
import { pollAlerts } from './api/index.js'

const route = useRoute()
const isMobile = ref(false)
const globalLoading = ref(false)
const alertCount = ref(0)
let alertTimer = null

provide('globalLoading', globalLoading)

const mobileNavItems = [
  { path: '/', label: '总览', icon: 'DataBoard' },
  { path: '/spending', label: '分析', icon: 'TrendCharts' },
  { path: '/simulation', label: '规划', icon: 'MagicStick' },
  { path: '/ai', label: 'AI', icon: 'ChatDotRound' },
  { path: '/settings', label: '设置', icon: 'Setting' },
]

function checkMobile() {
  isMobile.value = window.innerWidth < 768
}

async function checkAlerts() {
  try {
    const res = await pollAlerts()
    alertCount.value = res.new_count || 0
  } catch {}
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  checkAlerts()
  alertTimer = setInterval(checkAlerts, 300000) // every 5 min
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
  if (alertTimer) clearInterval(alertTimer)
})
</script>

<style>
body { margin: 0; font-family: 'PingFang SC', 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
.el-card { margin-bottom: 8px; border-radius: 8px; }

/* Sidebar */
.el-aside {
  display: flex;
  flex-direction: column;
  background-color: #304156;
}
.sidebar-logo {
  padding: 8px;
  color: #fff;
  text-align: center;
  border-bottom: 1px solid rgba(255,255,255,.1);
}
.sidebar-menu {
  border-right: none !important;
  flex: 1;
  overflow-y: auto;
}

/* Alert badge in sidebar */
.alert-badge { margin-left: 8px; }

/* Mobile: hide sidebar */
.mobile-hidden { display: none; }

/* Mobile bottom navigation */
.mobile-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 60px;
  background: #304156;
  display: flex;
  z-index: 1000;
  box-shadow: 0 -2px 8px rgba(0,0,0,.15);
}
.mobile-nav-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #bfcbd9;
  text-decoration: none;
  font-size: 11px;
  gap: 2px;
  transition: color .2s;
}
.mobile-nav-item.active { color: #409eff; }

/* Global loading */
.global-loading {
  position: fixed;
  top: 12px;
  right: 24px;
  z-index: 9999;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: rgba(255,255,255,.95);
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0,0,0,.1);
  color: #409eff;
  font-size: 13px;
}

/* Responsive overrides */
@media (max-width: 768px) {
  .el-main { padding: 12px !important; padding-bottom: 80px !important; }
  .el-row { margin-left: 0 !important; margin-right: 0 !important; }
  .el-col-6, .el-col-12, .el-col-16, .el-col-8 { padding-left: 0 !important; padding-right: 0 !important; }
  .el-card { margin-bottom: 8px !important; }
  h2 { font-size: 18px !important; margin: 12px 0 !important; }
}
</style>
