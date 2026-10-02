<template>
  <div class="page">
    <el-card shadow="hover" style="margin-top: 16px">
      <!-- 工具栏：admin 才显示新增按钮（右对齐） -->
      <div class="toolbar">
        <div class="toolbar-spacer"></div>
        <el-button type="primary" v-if="isAdmin" @click="dialogVisible = true">
          <el-icon><Plus /></el-icon>新增店铺
        </el-button>
      </div>
  
      <el-table :data="shops" v-loading="loading">
        <el-table-column prop="platform" label="平台" width="120">
          <template #default="{ row }">
            <el-tag :type="platformTagType(row.platform)" effect="plain">{{ platformLabel(row.platform) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="店铺名" />
        <el-table-column label="连接状态" width="140">
          <template #default="{ row }">
            <span class="status-cell">
              <span class="status-dot" :class="row.status"></span>
              {{ statusLabel(row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280">
          <template #default="{ row }">
            <el-button size="small" type="primary" :loading="syncingId === row.id" v-if="canWrite" @click="onSync(row)">
              同步商品
            </el-button>
            <el-button size="small" v-if="isAdmin" @click="onTest(row)">测试连接</el-button>
            <el-button size="small" type="danger" v-if="isAdmin" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增店铺：凭证以密码框输入，仅创建时传一次 -->
    <el-dialog v-model="dialogVisible" title="新增店铺" width="440px">
      <el-form :model="form" label-width="90px" style="margin-top: 30px">
        <el-form-item label="平台">
          <el-select v-model="form.platform" style="width: 100%">
            <el-option label="Mock（演示）" value="mock" />
            <el-option label="SHEIN" value="shein" />
            <el-option label="Shopify" value="shopify" />
          </el-select>
        </el-form-item>
        <el-form-item label="店铺名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="API 凭证">
          <el-input v-model="form.credentials" type="password" show-password placeholder="仅创建时传入，落库即加密" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onCreate">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { shopsApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { Shop } from '@/types'

const auth = useAuthStore()
const isAdmin = computed(() => auth.role === 'admin')
const canWrite = computed(() => ['admin', 'operator'].includes(auth.role))

const shops = ref<Shop[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const syncingId = ref('')
const form = reactive({ platform: 'mock', name: '', credentials: '' })

const platformLabel = (p: string): string =>
  ({ mock: 'Mock 演示', shein: 'SHEIN', shopify: 'Shopify' })[p] || p

/** 平台 tag 颜色区分：mock=info / shein=primary / shopify=success */
const PLATFORM_TAG_TYPES = {
  mock: 'info',
  shein: 'primary',
  shopify: 'success',
} as const
const platformTagType = (p: string): 'info' | 'primary' | 'success' =>
  PLATFORM_TAG_TYPES[p as keyof typeof PLATFORM_TAG_TYPES] ?? 'info'

/** 状态点文字 */
const statusLabel = (s: string): string =>
  (s === 'connected' ? '已连接' : s === 'active' ? '可用' : '断开')

async function load(): Promise<void> {
  loading.value = true
  try {
    shops.value = await shopsApi.list()
  } finally {
    loading.value = false
  }
}

async function onCreate(): Promise<void> {
  await shopsApi.create({ ...form })
  ElMessage.success('店铺已创建，凭证已加密存储')
  dialogVisible.value = false
  Object.assign(form, { platform: 'mock', name: '', credentials: '' })
  load()
}

/**
 * 一键同步：后端 Celery 任务（开发 eager 模式同步执行完才返回），
 * 完成后提示并让用户去商品页查看结果。
 */
async function onSync(row: Shop): Promise<void> {
  syncingId.value = row.id
  try {
    await shopsApi.sync(row.id)
    ElMessage.success(`店铺「${row.name}」同步完成，商品列表已更新`)
  } finally {
    syncingId.value = ''
  }
}

/** 连通性测试：不抛错，返回 connected/disconnected */
async function onTest(row: Shop): Promise<void> {
  const result = await shopsApi.testConnection(row.id)
  if (result.status === 'connected') {
    ElMessage.success(`连接成功，拉到 ${result.product_count} 个商品`)
  } else {
    ElMessage.warning('连接失败：请检查凭证或平台状态')
  }
}

async function onDelete(row: Shop): Promise<void> {
  await ElMessageBox.confirm(`确认删除店铺「${row.name}」？`, '删除确认', { type: 'warning' })
  await shopsApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
/* 连接状态：小圆点 + 文字（比 tag 更轻量） */
.status-cell { display: inline-flex; align-items: center; gap: 6px; color: var(--s-ink-secondary); }
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-dot.connected { background: #0e9f6e; box-shadow: 0 0 0 3px rgba(14, 159, 110, 0.15); }
.status-dot.active    { background: var(--s-primary); box-shadow: 0 0 0 3px rgba(83, 58, 255, 0.15); }
.status-dot.disconnected { background: var(--s-ruby); box-shadow: 0 0 0 3px rgba(234, 34, 97, 0.15); }
</style>
