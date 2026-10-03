<template>
  <div class="page">
    <el-card shadow="never">
      <el-tabs v-model="tab">
        <!-- 页签 1：批次（采购溯源） -->
        <el-tab-pane label="库存批次" name="batches">
          <el-table :data="batches" size="small">
            <el-table-column prop="batch_no" label="批次号" width="170" />
            <el-table-column prop="product_sku" label="商品 SKU" width="140" />
            <el-table-column label="库位" width="110" align="center">
              <template #default="{ row }: { row: Batch }">{{ row.location_code || '—' }}</template>
            </el-table-column>
            <el-table-column prop="qty_initial" label="初始量" width="90" align="center" />
            <el-table-column prop="qty_remaining" label="剩余量" width="90" align="center" />
            <el-table-column label="来源" width="150">
              <template #default="{ row }: { row: Batch }">
                <el-tag v-if="row.po_item_id" size="small" type="primary" effect="plain">采购入库</el-tag>
                <el-tag v-else size="small" type="info" effect="plain">期初</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 页签 2：库位 -->
        <el-tab-pane label="库位管理" name="locations">
          <div style="margin-bottom: 10px; display: flex; gap: 8px">
            <el-input v-model="locForm.code" placeholder="编码 如 A-01-01" style="width: 160px" size="small" />
            <el-input v-model="locForm.name" placeholder="名称（可选）" style="width: 160px" size="small" />
            <el-button type="primary" size="small" @click="onCreateLocation">新增库位</el-button>
          </div>
          <el-table :data="locations" size="small">
            <el-table-column prop="code" label="编码" width="140" />
            <el-table-column prop="name" label="名称" min-width="160" />
            <el-table-column prop="remark" label="备注" min-width="160" />
          </el-table>
        </el-tab-pane>

        <!-- 页签 3：盘点 -->
        <el-tab-pane label="库存盘点" name="stocktaking">
          <div style="margin-bottom: 10px">
            <el-button type="primary" size="small" :loading="creating" @click="onCreateStocktaking">
              创建盘点单（全量商品快照）
            </el-button>
          </div>
          <el-table :data="stocktakings" size="small" @row-click="openStocktaking">
            <el-table-column prop="created_at" label="创建时间" width="180">
              <template #default="{ row }: { row: Stocktaking }">
                {{ row.created_at.replace('T', ' ').slice(0, 16) }}
              </template>
            </el-table-column>
            <el-table-column prop="item_count" label="明细数" width="90" align="center" />
            <el-table-column label="状态" width="110" align="center">
              <template #default="{ row }: { row: Stocktaking }">
                <el-tag size="small" :type="row.status === 'processing' ? 'warning' : 'success'">
                  {{ row.status === 'processing' ? '盘点中' : '已完成' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 盘点单详情抽屉：录入实盘数 -->
    <el-drawer v-model="stVisible" title="盘点单" size="620px">
      <template v-if="stDetail">
        <el-tag size="small" :type="stDetail.status === 'processing' ? 'warning' : 'success'">
          {{ stDetail.status === 'processing' ? '盘点中' : '已完成' }}
        </el-tag>
        <el-table :data="stDetail.items" size="small" style="margin-top: 12px">
          <el-table-column label="商品" min-width="140">
            <template #default="{ row }: { row: StocktakingItemOut }">
              {{ productLabel(row.product_id) }}
            </template>
          </el-table-column>
          <el-table-column prop="system_qty" label="账面" width="80" align="center" />
          <el-table-column label="实盘" width="130" align="center">
            <template #default="{ row }: { row: StocktakingItemOut }">
              <el-input-number
                v-if="stDetail!.status === 'processing' && canWrite"
                :model-value="row.counted_qty ?? undefined"
                size="small" :min="0"
                @change="(v: number | undefined) => onCount(row, v)"
              />
              <span v-else>{{ row.counted_qty ?? '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异" width="90" align="center">
            <template #default="{ row }: { row: StocktakingItemOut }">
              <span v-if="row.counted_qty === null">—</span>
              <span v-else :style="{ color: row.counted_qty - row.system_qty === 0 ? '' : row.counted_qty > row.system_qty ? '#059669' : '#dc2626' }">
                {{ (row.counted_qty - row.system_qty > 0 ? '+' : '') + (row.counted_qty - row.system_qty) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="stDetail.status === 'processing' && canWrite" style="margin-top: 14px; text-align: right">
          <el-button type="primary" :loading="completing" @click="onComplete">提交盘点（差异入账）</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { warehouseApi, productsApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { Batch, Stocktaking, StocktakingItemOut, WarehouseLocation } from '@/types'

const auth = useAuthStore()
const canWrite = computed(() => ['admin', 'operator'].includes(auth.role))

const tab = ref('batches')
const batches = ref<Batch[]>([])
const locations = ref<WarehouseLocation[]>([])
const stocktakings = ref<Stocktaking[]>([])
const products = ref<{ id: string; sku: string; name: string }[]>([])

const productLabel = (id: string) => {
  const p = products.value.find((x) => x.id === id)
  return p ? `${p.sku} ${p.name}` : id.slice(0, 8)
}

async function loadAll(): Promise<void> {
  const [b, l, s, prod] = await Promise.all([
    warehouseApi.listBatches(),
    warehouseApi.listLocations(),
    warehouseApi.listStocktakings(),
    productsApi.list({ page: 1, page_size: 200 }),
  ])
  batches.value = b.items
  locations.value = l.items
  stocktakings.value = s.items
  products.value = prod.items.map((p) => ({ id: p.id, sku: p.sku, name: p.name }))
}

// ---------- 库位 ----------
const locForm = reactive({ code: '', name: '' })

async function onCreateLocation(): Promise<void> {
  if (!locForm.code.trim()) {
    ElMessage.warning('请输入库位编码')
    return
  }
  await warehouseApi.createLocation({ code: locForm.code, name: locForm.name || undefined })
  ElMessage.success('库位已创建')
  locForm.code = ''
  locForm.name = ''
  const l = await warehouseApi.listLocations()
  locations.value = l.items
}

// ---------- 盘点 ----------
const creating = ref(false)
const completing = ref(false)
const stVisible = ref(false)
const stDetail = ref<Stocktaking | null>(null)

async function onCreateStocktaking(): Promise<void> {
  creating.value = true
  try {
    const st = await warehouseApi.createStocktaking()
    ElMessage.success(`盘点单已创建（${st.item_count} 项商品快照）`)
    await loadAll()
  } finally {
    creating.value = false
  }
}

async function openStocktaking(row: Stocktaking): Promise<void> {
  stDetail.value = await warehouseApi.getStocktaking(row.id)
  stVisible.value = true
}

async function onCount(row: StocktakingItemOut, value: number | undefined): Promise<void> {
  if (value === undefined || !stDetail.value) return
  await warehouseApiUpdateCounted(stDetail.value.id, row.id, value)
  row.counted_qty = value
}

/** 录入实盘数（局部更新，避免整单重拉打断录入节奏） */
async function warehouseApiUpdateCounted(stId: string, itemId: string, qty: number): Promise<void> {
  await warehouseApi.updateCounted(stId, itemId, qty)
}

async function onComplete(): Promise<void> {
  if (!stDetail.value) return
  completing.value = true
  try {
    const r = await warehouseApi.completeStocktaking(stDetail.value.id)
    ElMessage.success(`盘点已提交，${r.adjusted_count} 项差异已入账`)
    stDetail.value = await warehouseApi.getStocktaking(stDetail.value.id)
    loadAll()
  } finally {
    completing.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
/* 三页签布局：表格密度 small，靠 EP 默认样式 + 设计令牌 */
</style>
