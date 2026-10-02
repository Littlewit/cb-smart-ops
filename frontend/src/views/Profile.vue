<template>
  <div class="profile-page">
    <!-- 左卡：身份信息（只读部分：用户名/角色不可自行修改，为 RBAC 身份锚点） -->
    <el-card class="id-card" shadow="never">
      <div class="id-head">
        <div class="big-avatar">{{ profile?.username.charAt(0).toUpperCase() }}</div>
        <div>
          <div class="username">{{ profile?.username }}</div>
          <el-tag :type="roleTagType" size="small">{{ roleLabel }}</el-tag>
        </div>
      </div>
      <el-descriptions :column="1" border style="margin-top: 20px">
        <el-descriptions-item label="用户 ID">{{ profile?.id }}</el-descriptions-item>
        <el-descriptions-item label="角色">{{ roleLabel }}</el-descriptions-item>
        <el-descriptions-item label="注册时间">{{ formatDate(profile?.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="当前邮箱">{{ profile?.email || '—' }}</el-descriptions-item>
      </el-descriptions>
      <p class="hint">用户名与角色由系统分配，如需变更请联系管理员。</p>
    </el-card>

    <!-- 右列：邮箱编辑 + 修改密码 -->
    <div class="edit-col">
      <el-card shadow="never">
        <template #header>修改邮箱</template>
        <el-form ref="emailFormRef" :model="emailForm" :rules="emailRules" label-width="80px">
          <el-form-item label="新邮箱" prop="email">
            <el-input v-model="emailForm.email" placeholder="用于忘记密码时身份匹配" :prefix-icon="Message" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="emailLoading" @click="onSaveEmail">保存邮箱</el-button>
          </el-form-item>
        </el-form>
        <p class="hint">邮箱是"忘记密码"的身份匹配依据，修改后立即生效。</p>
      </el-card>

      <el-card shadow="never">
        <template #header>修改密码</template>
        <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="80px">
          <el-form-item label="旧密码" prop="old_password">
            <el-input v-model="pwdForm.old_password" type="password" show-password :prefix-icon="Lock" autocomplete="new-password" />
          </el-form-item>
          <el-form-item label="新密码" prop="new_password">
            <el-input v-model="pwdForm.new_password" type="password" placeholder="≥6 位" show-password :prefix-icon="Lock" autocomplete="new-password" />
          </el-form-item>
          <el-form-item label="确认密码" prop="confirm_password">
            <el-input v-model="pwdForm.confirm_password" type="password" placeholder="再次输入新密码" show-password :prefix-icon="Lock" autocomplete="new-password" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="pwdLoading" @click="onChangePwd">修改密码</el-button>
          </el-form-item>
        </el-form>
        <p class="hint">修改成功后将退出登录，请使用新密码重新登录。</p>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormItemRule } from 'element-plus'
import { Message, Lock } from '@element-plus/icons-vue'
import { authApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { Profile, Role } from '@/types'

const auth = useAuthStore()
const router = useRouter()

// ---------- 个人信息 ----------
const profile = ref<Profile | null>(null)

const roleLabel = computed(
  () => ({ admin: '管理员', operator: '运营', viewer: '查看' })[profile.value?.role as Role] ?? '—'
)
const roleTagType = computed(() =>
  profile.value?.role === 'admin' ? 'danger' : profile.value?.role === 'operator' ? 'warning' : 'info'
)

/** ISO 时间 → 本地可读格式（仅日期部分，注册时间无需精确到秒） */
function formatDate(iso?: string): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

async function loadProfile(): Promise<void> {
  profile.value = await authApi.me()
}

// ---------- 修改邮箱 ----------
const emailFormRef = ref<FormInstance>()
const emailLoading = ref(false)
const emailForm = reactive({ email: '' })
const emailRules: Record<string, FormItemRule[]> = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { pattern: /^[\w.+-]+@[\w-]+(\.[\w-]+)+$/, message: '邮箱格式不正确', trigger: 'blur' },
  ],
}

async function onSaveEmail(): Promise<void> {
  const valid = await emailFormRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  emailLoading.value = true
  try {
    profile.value = await authApi.updateMe({ email: emailForm.email })
    ElMessage.success('邮箱已更新')
  } finally {
    emailLoading.value = false
  }
}

// ---------- 修改密码（与 MainLayout 弹窗同款校验；成功后强制重新登录） ----------
const pwdFormRef = ref<FormInstance>()
const pwdLoading = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '', confirm_password: '' })

const validateConfirm = (_rule: unknown, value: string, callback: (err?: Error) => void) => {
  if (value !== pwdForm.new_password) callback(new Error('两次输入的新密码不一致'))
  else callback()
}
const pwdRules: Record<string, FormItemRule[]> = {
  old_password: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}

async function onChangePwd(): Promise<void> {
  const valid = await pwdFormRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  pwdLoading.value = true
  try {
    // confirm_password 为纯前端校验字段，不随请求提交
    await authApi.changePassword({
      old_password: pwdForm.old_password,
      new_password: pwdForm.new_password,
    })
    ElMessage.success('密码修改成功，请重新登录')
    auth.logout()
    router.push('/login')
  } finally {
    pwdLoading.value = false
  }
}

onMounted(loadProfile)
</script>

<style scoped>
.profile-page { display: flex; gap: 16px; align-items: flex-start; }
.id-card { width: 340px; flex-shrink: 0; }
.edit-col { flex: 1; display: flex; flex-direction: column; gap: 16px; }

/* 身份卡头部：大号渐变头像 + 用户名/角色 */
.id-head { display: flex; align-items: center; gap: 16px; }
.big-avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  font-weight: 600;
  flex-shrink: 0;
}
.username { font-size: 18px; font-weight: 600; color: var(--s-ink); margin-bottom: 6px; }

/* 操作说明：弱化灰字 */
.hint { color: #909399; font-size: 12px; margin-top: 12px; }
</style>
