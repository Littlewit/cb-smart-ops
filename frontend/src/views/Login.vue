<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 class="title">跨境电商 AI 辅助运营系统</h2>

      <!-- 登录主表单（注册/忘记密码均为弹窗入口；登录需图形验证码防暴力破解） -->
      <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" size="large" @keyup.enter="onLogin">
        <el-form-item prop="username">
          <el-input v-model="loginForm.username" placeholder="用户名" :prefix-icon="User" autocomplete="off" />
        </el-form-item>
        <!-- 密码框用 new-password：Chrome 会无视 off 强制填充已存密码 -->
        <el-form-item prop="password">
          <el-input v-model="loginForm.password" type="password" placeholder="密码" show-password :prefix-icon="Lock" autocomplete="new-password" />
        </el-form-item>
        <el-form-item prop="captcha_code">
          <div class="captcha-row">
            <el-input
              v-model="loginForm.captcha_code"
              placeholder="验证码"
              maxlength="4"
              :prefix-icon="Key"
              autocomplete="off"
              @keyup.enter="onLogin"
            />
            <!-- 点击图片刷新验证码；一次性校验，失败后也需刷新 -->
            <img :src="captchaImg" class="captcha-img" title="点击刷新" alt="验证码" @click="refreshCaptcha" />
          </div>
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="onLogin">
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
    <el-dialog v-model="regVisible" title="注册账号" width="480px" @closed="regFormRef?.resetFields()">
      <el-form ref="regFormRef" :model="regForm" :rules="regRules" size="large" label-width="80px" style="margin-top: 30px;">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="regForm.username" placeholder="≥3 位" :prefix-icon="User" autocomplete="off" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="regForm.password" type="password" placeholder="≥6 位" show-password :prefix-icon="Lock" autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="regForm.email" placeholder="用于忘记密码时身份匹配" :prefix-icon="Message" autocomplete="off" />
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
        <el-button size="large" @click="regVisible = false">取消</el-button>
        <el-button type="primary" size="large" :loading="loading" @click="onRegister">注 册</el-button>
      </template>
    </el-dialog>

    <!-- 忘记密码弹窗：用户名 + 注册邮箱 匹配后设置新密码 -->
    <el-dialog v-model="resetVisible" title="重置密码" width="480px" @closed="resetFormRef?.resetFields()">
      <el-alert
        type="info"
        :closable="false"
        title="验证用户名与注册邮箱后即可设置新密码"
        style="margin: 16px 0"
      />
      <el-form ref="resetFormRef" :model="resetForm" :rules="resetRules" size="large" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="resetForm.username" :prefix-icon="User" autocomplete="off" />
        </el-form-item>
        <el-form-item label="注册邮箱" prop="email">
          <el-input v-model="resetForm.email" :prefix-icon="Message" autocomplete="off" />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="resetForm.new_password" type="password" placeholder="≥6 位" show-password :prefix-icon="Lock" autocomplete="new-password" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="large" @click="resetVisible = false">取消</el-button>
        <el-button type="primary" size="large" :loading="loading" @click="onReset">重置密码</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
// 表单图标（main.ts 已全局注册，这里按需具名导入以传给 prefix-icon）
import { User, Lock, Key, Message } from '@element-plus/icons-vue'
import { authApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { decodeRole } from '@/utils/jwt'
import type { Role } from '@/types'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const loading = ref(false)
// 三个表单实例：用于 validate() 校验与弹窗关闭后 resetFields()
const loginFormRef = ref<FormInstance>()
const regFormRef = ref<FormInstance>()
const resetFormRef = ref<FormInstance>()
// captcha_id/captcha_code 随表单整体提交给登录接口（见 onLogin）
const loginForm = reactive({ username: '', password: '', captcha_id: '', captcha_code: '' })
const captchaImg = ref('')

/** 拉取新验证码（base64 PNG）；失败静默——登录时后端会拦截并提示 */
async function refreshCaptcha(): Promise<void> {
  try {
    const data = await authApi.captcha()
    loginForm.captcha_id = data.captcha_id
    captchaImg.value = data.image
    loginForm.captcha_code = ''
  } catch {
    /* 忽略：下次登录时后端会兜底校验 */
  }
}
const regVisible = ref(false)
const resetVisible = ref(false)
const regForm = reactive<{ username: string; password: string; email: string; role: Role }>({
  username: '',
  password: '',
  email: '',
  role: 'operator',
})
const resetForm = reactive({ username: '', email: '', new_password: '' })

/** 登录校验规则：必填项前置拦截，减少无效请求 */
const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  captcha_code: [{ required: true, message: '请输入验证码', trigger: 'blur' }],
}

/** 注册校验规则：与后端 UserCreate 约束保持一致（长度/邮箱格式） */
const EMAIL_PATTERN = /^[\w.+-]+@[\w-]+(\.[\w-]+)+$/
const regRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 64, message: '用户名长度 3-64 位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { pattern: EMAIL_PATTERN, message: '邮箱格式不正确', trigger: 'blur' },
  ],
}

/** 重置密码校验规则 */
const resetRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入注册邮箱', trigger: 'blur' },
    { pattern: EMAIL_PATTERN, message: '邮箱格式不正确', trigger: 'blur' },
  ],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
}

onMounted(refreshCaptcha)

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

/** 统一校验入口：通过返回 true，失败已由表单内联提示 */
async function check(formRef: FormInstance | undefined): Promise<boolean> {
  if (!formRef) return false
  return formRef.validate().then(() => true).catch(() => false)
}

async function onLogin(): Promise<void> {
  if (!(await check(loginFormRef.value))) return
  loading.value = true
  try {
    const data = await authApi.login(loginForm)
    finishLogin(data.access_token, loginForm.username)
  } catch {
    // 验证码为一次性消费：无论账密对错，失败后必须刷新验证码重输
    await refreshCaptcha()
  } finally {
    loading.value = false
  }
}

async function onRegister(): Promise<void> {
  if (!(await check(regFormRef.value))) return
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
  if (!(await check(resetFormRef.value))) return
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
/* 白色画布卡片浮于渐变之上：加宽容纳 large 表单 + 蓝调阴影 */
.login-card {
  width: 420px;
  padding: 16px 24px 20px;
  border: 1px solid var(--s-hairline);
  box-shadow: 0 12px 48px rgba(0, 55, 112, 0.18);
}
.title {
  text-align: center;
  margin: 14px 0 24px;
  color: var(--s-ink);
  font-weight: 300;
  font-size: 24px;      /* display-md */
  letter-spacing: -0.26px;
}
/* 辅助入口：两端分布 */
.aux-links {
  display: flex;
  justify-content: space-between;
  margin-top: 18px;
  font-size: 14px;
}
/* 验证码行：图片高度对齐 large 输入框（40px），可点击刷新 */
.captcha-row { display: flex; gap: 10px; align-items: center; width: 100%; }
.captcha-img {
  height: 40px;
  border-radius: 6px;
  border: 1px solid var(--s-hairline);
  cursor: pointer;
  flex-shrink: 0;
}
</style>
