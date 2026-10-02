<template>
  <!-- 主布局：深色渐变侧边栏 + 顶栏 + 内容区（设计稿：数据看板.html 侧边栏规范） -->
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <div class="logo-badge"><el-icon :size="18"><Lightning /></el-icon></div>
        <span>跨境电商 AI 运营</span>
      </div>
      <el-menu router :default-active="$route.path" class="menu">
        <el-menu-item-group title="主导航">
          <el-menu-item index="/dashboard">
            <el-icon><Odometer /></el-icon><span>数据看板</span>
          </el-menu-item>
          <el-menu-item index="/products">
            <el-icon><Goods /></el-icon><span>商品管理</span>
          </el-menu-item>
          <el-menu-item index="/inventory">
            <el-icon><Warning /></el-icon><span>库存看板</span>
            <!-- 预警数 badge：来自 /api/inventory/summary，>0 才显示 -->
            <span v-if="alertCount > 0" class="menu-badge">{{ alertCount }}</span>
          </el-menu-item>
          <el-menu-item index="/shops">
            <el-icon><Shop /></el-icon><span>店铺管理</span>
          </el-menu-item>
        </el-menu-item-group>
        <el-menu-item-group title="智能工具">
          <el-menu-item index="/ai">
            <el-icon><ChatDotRound /></el-icon><span>AI 助手</span>
          </el-menu-item>
        </el-menu-item-group>
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
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { inventoryApi } from '@/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

// 角色中文标签
const roleLabel = computed(
  () => ({ admin: '管理员', operator: '运营', viewer: '查看' })[auth.role] || auth.role
)

// 侧边栏"库存看板"badge：预警商品数（未登录时不请求）
const alertCount = ref(0)
onMounted(async () => {
  if (!auth.isLoggedIn) return
  try {
    const summary = await inventoryApi.summary()
    alertCount.value = summary.alert_count
  } catch {
    // 概览获取失败不影响菜单使用，badge 置 0 即可
    alertCount.value = 0
  }
})

function onLogout(): void {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout { height: 100%; }

/* ===== 侧边栏：#0f172a → #1e1b4b 纵向渐变（设计稿令牌） ===== */
.aside {
  background: linear-gradient(180deg, #0f172a 0%, #1e1b4b 100%);
}

/* Logo：渐变徽章（135deg indigo→violet）+ 白色标题 */
.logo {
  padding: 22px 22px 18px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.3px;
  color: #ffffff;
}
.logo-badge {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}

/* ===== 菜单（EP 变量整体翻转 + 设计稿 item 令牌） ===== */
.menu {
  --el-menu-bg-color: transparent;
  --el-menu-text-color: #94a3b8;
  --el-menu-hover-bg-color: rgba(255, 255, 255, 0.06);
  --el-menu-active-color: #ffffff;
  border-right: none;
  padding: 8px 12px;
}

/* 分组标题：小号大写字距（主导航 / 智能工具） */
.menu :deep(.el-menu-item-group__title) {
  padding: 12px 16px 6px;
  font-size: 11px;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 1px;
}

/* 菜单项：10px 圆角、#94a3b8 文字、悬浮提亮 */
.menu :deep(.el-menu-item) {
  height: 44px;
  border-radius: 10px;
  margin-bottom: 4px;
  color: #94a3b8;
  transition: all 0.2s ease;
}
.menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.06);
  color: #e2e8f0;
}

/* 选中态：横向 indigo→violet 渐变 + 光晕阴影 + 左缘白色指示条 */
.menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(90deg, #6366f1, #8b5cf6);
  color: #ffffff;
  font-weight: 400;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
}
.menu :deep(.el-menu-item.is-active)::before {
  content: '';
  position: absolute;
  left: -12px;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 60%;
  background: #ffffff;
  border-radius: 0 4px 4px 0;
}

/* 预警数 badge：红色 pill，右对齐 */
.menu-badge {
  margin-left: auto;
  background: #ef4444;
  color: #fff;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  line-height: 1.4;
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
