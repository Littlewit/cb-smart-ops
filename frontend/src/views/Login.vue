<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 class="title">跨境电商 AI 辅助运营系统</h2>
      <el-tabs v-model="tab">
        <!-- 登录 Tab -->
        <el-tab-pane label="登录" name="login">
          <el-form :model="loginForm" @keyup.enter="onLogin">
            <el-form-item>
              <el-input v-model="loginForm.username" placeholder="用户名" />
            </el-form-item>
            <el-form-item>
              <el-input v-model="loginForm.password" type="password" placeholder="密码" show-password />
            </el-form-item>
            <el-button type="primary" style="width: 100%" :loading="loading" @click="onLogin">
              登 录
            </el-button>
          </el-form>
        </el-tab-pane>

        <!-- 注册 Tab（演示项目：注册时可选角色，生产应由管理员分配） -->
        <el-tab-pane label="注册" name="register">
          <el-form :model="regForm">
            <el-form-item>
              <el-input v-model="regForm.username" placeholder="用户名（≥3位）" />
            </el-form-item>
            <el-form-item>
              <el-input v-model="regForm.password" type="password" placeholder="密码（≥6位）" show-password />
            </el-form-item>
            <el-form-item>
              <el-select v-model="regForm.role" style="width: 100%">
                <el-option label="管理员 admin" value="admin" />
                <el-option label="运营 operator" value="operator" />
                <el-option label="查看 viewer" value="viewer" />
              </el-select>
            </el-form-item>
            <el-button type="success" style="width: 100%" :loading="loading" @click="onRegister">
              注 册
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '../api'
import { useAuthStore } from '../stores/auth'
import { decodeRole } from '../utils/jwt'
import type { Role } from '../types'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const tab = ref<'login' | 'register'>('login')
const loading = ref(false)
const loginForm = reactive({ username: '', password: '' })
const regForm = reactive<{ username: string; password: string; role: Role }>({
  username: '',
  password: '',
  role: 'operator',
})

async function onLogin(): Promise<void> {
  if (!loginForm.username || !loginForm.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const data = await authApi.login(loginForm)
    // 登录响应只有 token；用户名取输入值，role 从 JWT 解出
    auth.setSession(data.access_token, {
      username: loginForm.username,
      role: decodeRole(data.access_token),
    })
    ElMessage.success('登录成功')
    router.push((route.query.redirect as string) || '/')
  } finally {
    loading.value = false
  }
}

async function onRegister(): Promise<void> {
  if (regForm.username.length < 3 || regForm.password.length < 6) {
    ElMessage.warning('用户名 ≥3 位，密码 ≥6 位')
    return
  }
  loading.value = true
  try {
    await authApi.register(regForm)
    ElMessage.success('注册成功，请登录')
    loginForm.username = regForm.username
    tab.value = 'login'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2d3d 0%, #409eff 100%);
}
.login-card { width: 380px; padding: 8px 12px; }
.title { text-align: center; margin: 12px 0 20px; color: #303133; }
</style>
