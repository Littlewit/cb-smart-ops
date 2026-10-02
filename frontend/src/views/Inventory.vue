<template>
  <div class="page">
    <!-- 顶部指标卡片（来自 /api/inventory/summary） -->
    <el-row :gutter="12">
      <el-col :span="8">
        <el-card shadow="hover"><el-statistic title="商品总数" :value="summary.total_products" /></el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <el-statistic title="预警商品" :value="summary.alert_count" :value-style="{ color: '#f56c6c' }" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover"><el-statistic title="店铺数量" :value="summary.total_shops" /></el-card>
      </el-col>
    </el-row>

    <!-- 预警商品列表：红色高亮 + 操作入口 -->
    <h4 style="margin: 16px 0 8px">库存预警商品（点击行查看流水）</h4>
    <el-table :data="summary.alert_products" :row-class-name="() => 'alert-row'" @row-click="openLogs">
      <el-table-column prop="sku" label="SKU" width="140" />
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column prop="stock" label="当前库存" width="100" />
      <el-table-column prop="safety_stock" label="安全库存" width="100" />
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button size="small" type="primary" v-if="canWrite" @click.stop="openOp(row)">入库/出库</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 库存流水抽屉 -->
    <el-drawer v-model="logsVisible" :title="`库存流水 - ${currentProduct?.sku || ''}`" size="560px">
      <el-table :data="logs" size="small">
        <el-table-column prop="created_at" label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="70">
          <template #default="{ row }: { row: InventoryLog }">
            <el-tag size="small" :type="{ in: 'success', out: 'danger', check: 'info' }[row.type]">
              {{ { in: '入库', out: '出库', check: '盘点' }[row.type] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="quantity" label="数量" width="70" />
        <el-table-column label="变动" width="110">
          <template #default="{ row }">{{ row.stock_before }} → {{ row.stock_after }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" />
      </el-table>
    </el-drawer>

    <!-- 入库/出库/盘点 dialog -->
    <el-dialog v-model="opVisible" :title="`库存操作 - ${currentProduct?.sku || ''}`" width="420px">
      <el-form :model="opForm" label-width="80px">
        <el-form-item label="类型">
          <el-radio-group v-model="opForm.type">
            <el-radio-button value="in">入库</el-radio-button>
            <el-radio-button value="out">出库</el-radio-button>
            <el-radio-button value="check">盘点</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="opForm.quantity" :min="0" />
          <span v-if="opForm.type === 'check'" style="margin-left: 8px; color: #909399">实盘数量</span>
        </el-form-item>
        <el-form-item label="原因"><el-input v-model="opForm.reason" placeholder="可留空自动生成" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="opVisible = false">取消</el-button>
        <el-button type="primary" @click="submitOp">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { inventoryApi } from '../api'
import { useAuthStore } from '../stores/auth'
import type { InventoryLog, InventorySummary, Product } from '../types'

const auth = useAuthStore()
const canWrite = computed(() => ['admin', 'operator'].includes(auth.role))

const summary = ref<InventorySummary>({
  total_products: 0,
  alert_count: 0,
  total_shops: 0,
  alert_products: [],
})
const logsVisible = ref(false)
const logs = ref<InventoryLog[]>([])
const currentProduct = ref<Product | null>(null)
const opVisible = ref(false)
const opForm = reactive<{ type: 'in' | 'out' | 'check'; quantity: number; reason: string }>({
  type: 'in',
  quantity: 0,
  reason: '',
})

const formatTime = (iso: string): string => (iso ? iso.replace('T', ' ').slice(0, 19) : '')

async function load(): Promise<void> {
  summary.value = await inventoryApi.summary()
}

/** 点击预警行 → 打开该商品流水抽屉 */
async function openLogs(row: Product): Promise<void> {
  currentProduct.value = row
  const data = await inventoryApi.listLogs({ product_id: row.id, page: 1, page_size: 50 })
  logs.value = data.items
  logsVisible.value = true
}

function openOp(row: Product): void {
  currentProduct.value = row
  Object.assign(opForm, { type: 'in', quantity: 0, reason: '' })
  opVisible.value = true
}

/** 提交入库/出库/盘点：余额与流水由后端同事务保证 */
async function submitOp(): Promise<void> {
  if (!currentProduct.value) return
  await inventoryApi.createLog({ product_id: currentProduct.value.id, ...opForm })
  ElMessage.success('操作成功')
  opVisible.value = false
  logsVisible.value = false
  load() // 刷新概览与预警列表
}

onMounted(load)
</script>
