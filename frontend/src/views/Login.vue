<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 class="title">跨境电商 AI 辅助运营系统</h2>

      <!-- 登录主表单（注册/忘记密码均改为弹窗入口） -->
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

      <!-- 辅助入口：注册 / 忘记密码 -->
      <div class="aux-links">
        <el-link type="primary" @click="regVisible = true">注册账号</el-link>
        <el-link type="info" @click="resetVisible = true">忘记密码?</el-link>
      </div>
    </el-card>

    <!-- 注册弹窗（原 Tab 改弹窗；新增邮箱字段供忘记密码匹配） -->
    <el-dialog v-model="regVisible" title="注册账号" width="440px">
      <el-form :model="regForm" label-width="70px">
        <el-form-item label="用户名">
          <el-input v-model="regForm.username" placeholder="≥3 位" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="regForm.password" type="password" placeholder="≥6 位" show-password />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="regForm.email" placeholder="用于忘记密码时身份匹配" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="regForm.role" style="width: 100%">
            <el-option label="管理员 admin" value="admin" />
            <el-option label="运营 operator" value="operator" />
            <el-option label="查看 viewer" value="viewer" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="regVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="onRegister">注 册</el-button>
      </template>
    </el-dialog>

    <!-- 忘记密码弹窗：用户名 + 注册邮箱 匹配后设置新密码 -->
    <el-dialog v-model="resetVisible" title="重置密码" width="440px">
      <el-alert
        type="info"
        :closable="false"
        title="验证用户名与注册邮箱后即可设置新密码（演示级方案，未发邮件验证码）"
        style="margin-bottom: 16px"
      />
      <el-form :model="resetForm" label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="resetForm.username" />
        </el-form-item>
        <el-form-item label="注册邮箱">
          <el-input v-model="resetForm.email" />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="resetForm.new_password" type="password" placeholder="≥6 位" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="onReset">重置密码</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { decodeRole } from '@/utils/jwt'
import type { Role } from '@/types'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const loading = ref(false)
const loginForm = reactive({ username: '', password: '' })
const regVisible = ref(false)
const resetVisible = ref(false)
const regForm = reactive<{ username: string; password: string; email: string; role: Role }>({
  username: '',
  password: '',
  email: '',
  role: 'operator',
})
const resetForm = reactive({ username: '', email: '', new_password: '' })

/** 从 JWT payload 中解出 role（客户端解码仅用于菜单显示，安全边界在后端 RBAC） */
function roleFromToken(token: string): Role {
  return decodeRole(token)
}

/** 登录成功：写会话并跳转（redirect 做了 /login 嵌套净化） */
function finishLogin(token: string, username: string): void {
  auth.setSession(token, { username, role: roleFromToken(token) })
  ElMessage.success('登录成功')
  const redirect = (route.query.redirect as string) || '/'
  router.push(redirect.startsWith('/login') ? '/' : redirect)
}

async function onLogin(): Promise<void> {
  if (!loginForm.username || !loginForm.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const data = await authApi.login(loginForm)
    finishLogin(data.access_token, loginForm.username)
  } finally {
    loading.value = false
  }
}

async function onRegister(): Promise<void> {
  if (regForm.username.length < 3 || regForm.password.length < 6) {
    ElMessage.warning('用户名 ≥3 位，密码 ≥6 位')
    return
  }
  if (!/^[\w.+-]+@[\w-]+(\.[\w-]+)+$/.test(regForm.email)) {
    ElMessage.warning('请输入正确的邮箱格式')
    return
  }
  loading.value = true
  try {
    await authApi.register(regForm)
    ElMessage.success('注册成功，请登录')
    loginForm.username = regForm.username
    regVisible.value = false
  } finally {
    loading.value = false
  }
}

/** 重置成功：回填用户名到登录表单，引导用新密码登录 */
async function onReset(): Promise<void> {
  if (resetForm.new_password.length < 6) {
    ElMessage.warning('新密码 ≥6 位')
    return
  }
  loading.value = true
  try {
    await authApi.resetPassword(resetForm)
    ElMessage.success('密码已重置，请使用新密码登录')
    loginForm.username = resetForm.username
    loginForm.password = ''
    resetVisible.value = false
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* Stripe 渐变 mesh：cream → 橙 → lavender → indigo → ruby 的横向大气渐变带 */
.login-wrap {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(120% 90% at 15% 20%, rgba(245, 233, 212, 0.9) 0%, rgba(245, 233, 212, 0) 55%),
    radial-gradient(100% 80% at 85% 10%, rgba(234, 34, 97, 0.35) 0%, rgba(234, 34, 97, 0) 50%),
    linear-gradient(115deg, #f9c8b6 0%, #c8b8f5 35%, #533afd 70%, #4434d4 100%);
}
/* 白色画布卡片浮于渐变之上：12px 圆角 + 蓝调阴影 */
.login-card {
  width: 380px;
  padding: 8px 12px;
  border: 1px solid var(--s-hairline);
  box-shadow: 0 12px 48px rgba(0, 55, 112, 0.18);
}
.title {
  text-align: center;
  margin: 12px 0 20px;
  color: var(--s-ink);
  font-weight: 300;
  font-size: 22px;      /* heading-lg */
  letter-spacing: -0.22px;
}
/* 辅助入口：两端分布 */
.aux-links {
  display: flex;
  justify-content: space-between;
  margin-top: 14px;
}
</style>
