<template>
  <div class="page">
    <!-- admin 才显示新增按钮 -->
    <el-button type="primary" v-if="isAdmin" @click="dialogVisible = true">新增店铺</el-button>

    <el-table :data="shops" v-loading="loading" style="margin-top: 12px">
      <el-table-column prop="platform" label="平台" width="120">
        <template #default="{ row }">
          <el-tag>{{ platformLabel(row.platform) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="店铺名" />
      <el-table-column label="连接状态" width="120">
        <template #default="{ row }">
          <el-tag :type="row.status === 'connected' || row.status === 'active' ? 'success' : 'info'">
            {{ row.status === 'connected' ? '已连接' : row.status === 'active' ? '可用' : '断开' }}
          </el-tag>
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

    <!-- 新增店铺：凭证以密码框输入，仅创建时传一次 -->
    <el-dialog v-model="dialogVisible" title="新增店铺" width="440px">
      <el-form :model="form" label-width="90px">
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

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { shopsApi } from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isAdmin = computed(() => auth.role === 'admin')
const canWrite = computed(() => ['admin', 'operator'].includes(auth.role))

const shops = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const syncingId = ref('')
const form = reactive({ platform: 'mock', name: '', credentials: '' })

const platformLabel = (p) => ({ mock: 'Mock 演示', shein: 'SHEIN', shopify: 'Shopify' }[p] || p)

async function load() {
  loading.value = true
  try {
    shops.value = await shopsApi.list()
  } finally {
    loading.value = false
  }
}

async function onCreate() {
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
async function onSync(row) {
  syncingId.value = row.id
  try {
    await shopsApi.sync(row.id)
    ElMessage.success(`店铺「${row.name}」同步完成，商品列表已更新`)
  } finally {
    syncingId.value = ''
  }
}

/** 连通性测试：不抛错，返回 connected/disconnected */
async function onTest(row) {
  const result = await shopsApi.testConnection(row.id)
  if (result.status === 'connected') {
    ElMessage.success(`连接成功，拉到 ${result.product_count} 个商品`)
  } else {
    ElMessage.warning('连接失败：请检查凭证或平台状态')
  }
}

async function onDelete(row) {
  await ElMessageBox.confirm(`确认删除店铺「${row.name}」？`, '删除确认', { type: 'warning' })
  await shopsApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>
