<template>
  <!-- 主布局：左侧角色菜单 + 顶部用户栏 + 内容区 -->
  <el-container class="layout">
    <el-aside width="200px" class="aside">
      <div class="logo">跨境电商 AI 运营</div>
      <el-menu router :default-active="$route.path" class="menu dark-menu">
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon><span>数据看板</span>
        </el-menu-item>
        <el-menu-item index="/products">
          <el-icon><Goods /></el-icon><span>商品管理</span>
        </el-menu-item>
        <el-menu-item index="/inventory">
          <el-icon><Warning /></el-icon><span>库存看板</span>
        </el-menu-item>
        <el-menu-item index="/shops">
          <el-icon><Shop /></el-icon><span>店铺管理</span>
        </el-menu-item>
        <el-menu-item index="/ai">
          <el-icon><ChatDotRound /></el-icon><span>AI 助手</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <span class="title">{{ $route.meta.title || '' }}</span>
        <el-dropdown>
          <span class="user">
            {{ auth.username }}（{{ roleLabel }}）
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="onLogout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

// 角色中文标签
const roleLabel = computed(
  () => ({ admin: '管理员', operator: '运营', viewer: '查看' })[auth.role] || auth.role
)

function onLogout(): void {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout { height: 100%; }

/* 深色侧边栏：Stripe brand-dark-900 深海军蓝面板（card-pricing-featured 同源色） */
.aside {
  background: var(--s-dark-900);
}
.logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 400;
  font-size: 18px;
  letter-spacing: -0.22px;
  color: #ffffff;
}

/* 深色菜单：EP 菜单变量整体翻转 */
.menu {
  --el-menu-bg-color: transparent;
  --el-menu-text-color: rgba(255, 255, 255, 0.72);
  --el-menu-hover-bg-color: rgba(255, 255, 255, 0.08);
  --el-menu-active-color: #ffffff;
  border-right: none;
  padding: 0 8px;
}
.menu :deep(.el-menu-item) {
  border-radius: 9999px;
  margin: 2px 0;
  height: 44px;
}
.menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.08);
}
/* 选中态：indigo 填充 + 白字（深色底上的品牌强调） */
.menu :deep(.el-menu-item.is-active) {
  background: var(--s-primary);
  color: #ffffff;
  font-weight: 400;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--s-canvas);
  border-bottom: 1px solid var(--s-hairline);
}
.title {
  font-weight: 300;
  font-size: 18px;      /* heading-sm */
  letter-spacing: -0.18px;
  color: var(--s-ink);
}
.user { cursor: pointer; display: flex; align-items: center; gap: 4px; color: var(--s-ink-secondary); }
</style>
