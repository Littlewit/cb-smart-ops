/**
 * 认证状态 store：token + 用户信息（Pinia + localStorage 持久化）。
 * 401 时由 request.ts 调用 logout()。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Role } from '../types'

const TOKEN_KEY = 'cb_token'
const USER_KEY = 'cb_user'

interface StoredUser {
  username: string
  role: Role
}

export const useAuthStore = defineStore('auth', () => {
  // state：从 localStorage 恢复，刷新页面不丢登录态
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const user = ref<StoredUser | null>(JSON.parse(localStorage.getItem(USER_KEY) || 'null'))

  // getters
  const isLoggedIn = computed(() => !!token.value)
  const username = computed(() => user.value?.username || '')
  const role = computed<Role>(() => user.value?.role || 'viewer')

  /** 登录成功后调用：写入内存 + localStorage */
  function setSession(newToken: string, newUser: StoredUser) {
    token.value = newToken
    user.value = newUser
    localStorage.setItem(TOKEN_KEY, newToken)
    localStorage.setItem(USER_KEY, JSON.stringify(newUser))
  }

  /** 登出 / 401：清空内存与 localStorage */
  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  return { token, user, isLoggedIn, username, role, setSession, logout }
})
