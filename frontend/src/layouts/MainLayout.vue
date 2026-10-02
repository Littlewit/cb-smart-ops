<template>
  <!-- 主布局：左侧角色菜单 + 顶部用户栏 + 内容区 -->
  <el-container class="layout">
    <el-aside width="200px">
      <div class="logo">跨境电商 AI 运营</div>
      <el-menu router :default-active="$route.path" class="menu">
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

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

// 角色中文标签
const roleLabel = computed(
  () => ({ admin: '管理员', operator: '运营', viewer: '查看' }[auth.role] || auth.role)
)

function onLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout { height: 100%; }
.logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  color: #409eff;
}
.menu { border-right: none; }
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e6e6e6;
}
.user { cursor: pointer; display: flex; align-items: center; gap: 4px; }
</style>
