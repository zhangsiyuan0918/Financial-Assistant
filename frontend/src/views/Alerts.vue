<template>
  <div>
    <h2>
      预警中心
      <el-button size="small" text @click="refresh" style="float:right;margin-top:8px">
        <el-icon><Refresh /></el-icon> 刷新
      </el-button>
    </h2>
    <el-alert v-if="!alerts.length" type="info" show-icon :closable="false" title="暂无预警" description="所有指标正常" />
    <el-card v-for="a in alerts" :key="a.id" style="margin-bottom:8px" :class="a.resolved ? 'resolved' : ''">
      <el-row :align="'middle'" :gutter="8">
        <el-col :xs="24" :sm="20">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
            <el-tag :type="severityTag(a.severity)" size="small" effect="dark">{{ severityLabel(a.severity) }}</el-tag>
            <el-tag v-if="a.type === 'budget_over' || a.type === 'budget_warn'" type="warning" size="small">预算</el-tag>
            <el-tag v-else-if="a.type === 'liquidity'" type="danger" size="small">流动性</el-tag>
            <el-tag v-else-if="a.type === 'abnormal'" type="info" size="small">异常</el-tag>
            <el-tag v-else-if="a.type === 'goal_deviation'" type="warning" size="small">目标</el-tag>
            <el-tag v-else size="small">其他</el-tag>
            <span :style="{textDecoration: a.resolved ? 'line-through' : 'none', color: a.resolved ? '#999' : '#333', fontSize: '13px'}">
              {{ a.message }}
            </span>
          </div>
        </el-col>
        <el-col :xs="12" :sm="2" style="text-align:right;color:#999;font-size:12px">{{ a.created_at }}</el-col>
        <el-col :xs="12" :sm="2" style="text-align:right">
          <el-button v-if="!a.resolved" size="small" type="primary" plain @click="doResolve(a.id)">已读</el-button>
          <el-tag v-else type="success" size="small">已处理</el-tag>
        </el-col>
      </el-row>
    </el-card>

    <AiFloat />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { fetchAlerts, resolveAlert } from '../api/index.js'
import AiFloat from '../components/AiFloat.vue'

const alerts = ref([])

function severityTag(s) { return s === 'high' ? 'danger' : s === 'medium' ? 'warning' : 'info' }
function severityLabel(s) { return s === 'high' ? '高' : s === 'medium' ? '中' : '低' }

async function doResolve(id) {
  await resolveAlert(id)
  alerts.value = await fetchAlerts()
}

async function refresh() {
  alerts.value = await fetchAlerts()
}

onMounted(refresh)
</script>

<style scoped>
.resolved { opacity: 0.6; }
</style>
