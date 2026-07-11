<template>
  <div style="display:flex;height:100vh;align-items:center;justify-content:center;background:#f0f2f5">
    <el-card style="width:380px">
      <template #header><div style="text-align:center;font-size:18px">FinFlow 财务助手</div></template>
      <el-form @submit.prevent="doLogin">
        <el-form-item label="密码">
          <el-input v-model="password" type="password" show-password @keyup.enter="doLogin" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="doLogin" style="width:100%">登录</el-button>
        </el-form-item>
        <div v-if="error" style="color:#f56c6c;text-align:center">{{ error }}</div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { loginApi } from '../api/index.js'

const password = ref('')
const error = ref('')
const router = useRouter()

async function doLogin() {
  error.value = ''
  try {
    const r = await loginApi(password.value)
    localStorage.setItem('auth_token', r.token)
    router.push('/')
  } catch {
    error.value = '密码错误'
  }
}
</script>