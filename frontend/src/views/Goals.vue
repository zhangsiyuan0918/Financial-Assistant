<template>
  <div>
    <h2>目标管理</h2>
    <el-row :gutter="16">
      <el-col :span="6" v-for="g in goals" :key="g.id">
        <el-card>
          <template #header>
            <el-space>
              <span>{{ g.name }}</span>
              <el-tag size="small" :type="g.on_track ? 'success' : 'danger'">{{ g.on_track ? '正常' : '偏离' }}</el-tag>
            </el-space>
          </template>
          <div style="text-align:center;padding:8px 0">
            <el-progress type="dashboard" :percentage="g.progress_pct" :width="100" :stroke-width="8"
              :color="g.on_track ? '#67c23a' : '#f56c6c'" />
            <div style="margin-top:8px;font-size:13px;color:#999">{{ fmt(g.current) }} / {{ fmt(g.target) }}</div>
            <div style="margin-top:4px;font-size:12px;color:#999" v-if="g.deadline">截止 {{ g.deadline }}</div>
          </div>
          <el-button size="small" type="danger" plain @click="doDelete(g.id)" style="width:100%">删除</el-button>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div style="text-align:center;padding:20px 0;cursor:pointer" @click="showCreate = true">
            <div style="font-size:36px;color:#409eff">+</div>
            <div style="color:#999;margin-top:8px">新建目标</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="showCreate" title="新建目标" width="450px">
      <el-form label-width="100px">
        <el-form-item label="目标名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="目标类型">
          <el-select v-model="form.type" style="width:100%">
            <el-option label="攒钱目标" value="save" />
            <el-option label="资产目标" value="net_worth" />
            <el-option label="支出控制" value="expense_control" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标金额"><el-input-number v-model="form.target" :min="1000" :step="10000" style="width:100%" /></el-form-item>
        <el-form-item label="截止日期"><el-date-picker v-model="form.deadline" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        <el-form-item v-if="form.type === 'expense_control'" label="支出类目">
          <el-select v-model="form.category" style="width:100%">
            <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="doCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { fetchGoals, createGoal, deleteGoal } from '../api/index.js'

const goals = ref([])
const showCreate = ref(false)
const categories = ['餐饮', '居住', '交通', '购物', '娱乐', '社交', '旅游', '车辆', '医疗']
const form = ref({ name: '', type: 'save', target: 100000, deadline: '', category: '餐饮' })
const fmt = v => '¥' + Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 0 })

async function doCreate() {
  await createGoal(form.value)
  showCreate.value = false
  form.value = { name: '', type: 'save', target: 100000, deadline: '', category: '餐饮' }
  goals.value = await fetchGoals()
}

async function doDelete(id) {
  await deleteGoal(id)
  goals.value = await fetchGoals()
}

onMounted(async () => { goals.value = await fetchGoals() })
</script>