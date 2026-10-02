/**
 * JWT 客户端解码工具：从 token payload 提取角色。
 * 客户端解码仅用于菜单显示（体验层），安全边界在后端 RBAC。
 */
import type { Role } from '@/types'

const VALID_ROLES: readonly Role[] = ['admin', 'operator', 'viewer']

/** 解出 role；任何解析失败兜底返回 'viewer'（最低权限展示）。 */
export function decodeRole(token: string): Role {
  try {
    // JWT payload 是 base64url 编码：-/_ 需还原为 +/ 才能被 atob 处理
    const b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const payload = JSON.parse(atob(b64))
    return VALID_ROLES.includes(payload.role) ? payload.role : 'viewer'
  } catch {
    return 'viewer'
  }
}
