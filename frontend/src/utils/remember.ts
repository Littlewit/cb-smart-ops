/**
 * "记住密码"持久化（localStorage）。
 *
 * 安全取舍（面试可讲点）：
 * - localStorage 为明文存储，本方案仅适合作演示/个人工具场景；
 *   生产环境应交给浏览器密码管理器（凭证管理），或只记用户名 + token
 * - 验证码等一次性字段绝不持久化；存储内容仅 username/password
 */

const KEY = 'login_remember'

export interface RememberedAccount {
  username: string
  password: string
}

/** 读取记住的账号；无记录/解析失败返回 null（静默容错，不影响登录流程） */
export function loadRemembered(): RememberedAccount | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const data = JSON.parse(raw) as Partial<RememberedAccount>
    // 字段缺失视为无效记录，按未记住处理
    if (typeof data.username === 'string' && typeof data.password === 'string') {
      return { username: data.username, password: data.password }
    }
    return null
  } catch {
    return null
  }
}

/** 保存/覆盖记住的账号（勾选"记住密码"且登录成功时调用） */
export function saveRemembered(account: RememberedAccount): void {
  localStorage.setItem(KEY, JSON.stringify(account))
}

/** 清除记住的账号（取消勾选时调用） */
export function clearRemembered(): void {
  localStorage.removeItem(KEY)
}
