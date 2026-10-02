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
      // 区分两种 401：登录接口的"密码错误" ≠ 会话过期
      // （否则登录页会触发 logout+跳转，redirect 查询参数层层嵌套）
      const isLoginRequest = error.config?.url?.includes('/auth/login')
      if (isLoginRequest) {
        ElMessage.error(detail)
        return Promise.reject(error)
      }

      // 会话过期：清登录态回登录页；已在登录页时不重复跳转（避免 redirect 嵌套）
      const auth = useAuthStore()
      const current = router.currentRoute.value
      auth.logout()
      if (current.path !== '/login') {
        ElMessage.warning('登录已过期，请重新登录')
        router.push({ path: '/login', query: { redirect: current.fullPath } })
      }
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
