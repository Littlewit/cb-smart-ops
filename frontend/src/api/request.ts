/**
 * axios 统一请求层。
 *
 * 职责（系统设计 §6 请求层）：
 * 1. 请求拦截：从 auth store 注入 Authorization: Bearer <token>
 * 2. 响应拦截：{code,message,data} 成功包直接解包返回 data；
 *    401 清除登录态并跳转登录页；其他错误统一 ElMessage 提示后 reject
 *
 * 说明：后端统一响应包拦截器直接解包返回 data，因此这里把响应类型
 * 断言为"解包后的数据"（Result<T>），调用方拿到的就是业务数据本身。
 */
import axios from 'axios'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'
import { useAuthStore } from '../stores/auth'

const request = axios.create({
  baseURL: '/api', // 开发走 Vite 代理，生产走 Nginx 反代
  timeout: 30000,
})

// ---------- 请求拦截：注入 Token ----------
request.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

// ---------- 响应拦截：解包 + 错误统一处理 ----------
request.interceptors.response.use(
  (response: AxiosResponse) => {
    const body = response.data
    // 成功包 {code:0, message, data} → 直接返回 data，业务代码零负担
    if (body && typeof body === 'object' && 'code' in body) {
      return body.data
    }
    return body
  },
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail || error.message

    if (status === 401) {
      // Token 缺失/过期：清登录态回登录页（带 redirect 以便登录后跳回）
      const auth = useAuthStore()
      auth.logout()
      ElMessage.warning('登录已过期，请重新登录')
      router.push({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } })
    } else {
      ElMessage.error(detail)
    }
    return Promise.reject(error)
  }
)

/** 解包后的请求函数：调用方拿到的是业务数据 T 本身 */
export default request as {
  get: <T = unknown>(url: string, config?: object) => Promise<T>
  post: <T = unknown>(url: string, data?: object, config?: object) => Promise<T>
  put: <T = unknown>(url: string, data?: object, config?: object) => Promise<T>
  delete: <T = unknown>(url: string, config?: object) => Promise<T>
}
