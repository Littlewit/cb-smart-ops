/**
 * 路由与守卫。
 *
 * 两层守卫（系统设计 §6）：
 * 1. 登录守卫：未登录访问受保护页面 → 跳 /login（带 redirect）
 * 2. 角色守卫：页面 meta.role 要求最低角色 → 不满足跳首页
 * 注意：前端守卫仅做体验层菜单控制，安全边界在后端 RBAC（deps.require_role）。
 */
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { Role } from '@/types'

// 角色等级：与后端 ROLE_LEVELS 保持一致
const ROLE_LEVELS: Record<Role, number> = { viewer: 0, operator: 1, admin: 2 }

// 扩展 meta 类型：title 页面标题 / role 最低角色 / public 公开页
declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    role?: Role
    public?: boolean
  }
}

const routes: RouteRecordRaw[] = [
  { path: '/login', component: () => import('@/views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '数据看板' } },
      { path: 'products', component: () => import('@/views/Products.vue'), meta: { title: '商品管理', role: 'viewer' } },
      { path: 'inventory', component: () => import('@/views/Inventory.vue'), meta: { title: '库存看板', role: 'viewer' } },
      { path: 'shops', component: () => import('@/views/Shops.vue'), meta: { title: '店铺管理', role: 'viewer' } },
      { path: 'ai', component: () => import('@/views/AiAdvice.vue'), meta: { title: 'AI 助手', role: 'viewer' } },
      { path: 'procurement', component: () => import('@/views/Procurement.vue'), meta: { title: '采购管理', role: 'viewer' } },
      { path: 'warehouse', component: () => import('@/views/Warehouse.vue'), meta: { title: '仓库管理', role: 'viewer' } },
      { path: 'orders', component: () => import('@/views/Orders.vue'), meta: { title: '订单管理', role: 'viewer' } },
      { path: 'reports', component: () => import('@/views/Reports.vue'), meta: { title: '报表中心', role: 'viewer' } },
      { path: 'profile', component: () => import('@/views/Profile.vue'), meta: { title: '个人中心', role: 'viewer' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  // 1) 登录守卫
  if (!to.meta.public && !auth.isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  // 2) 角色守卫：页面要求的最低角色 > 当前角色 → 拦截
  if (to.meta.role && ROLE_LEVELS[auth.role] < ROLE_LEVELS[to.meta.role]) {
    return { path: '/' }
  }
})

export default router
