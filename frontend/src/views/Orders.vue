<template>
  <div class="page">
    <!-- 操作条：拉单 / 拆单 / 状态过滤 -->
    <el-card shadow="never">
      <div class="toolbar">
        <el-select v-model="fetchShopId" size="small" style="width: 200px" placeholder="选择店铺">
          <el-option v-for="s in shops" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
        <el-button type="primary" size="small" :loading="fetching" @click="onFetch">
          拉取平台订单
        </el-button>
        <el-button type="warning" size="small" :loading="splitting" @click="onSplit">
          一键拆单（全部待拆）
        </el-button>
        <el-select v-model="statusFilter" size="small" style="width: 130px" @change="loadAll">
          <el-option label="全部状态" value="" />
          <el-option label="待拆单" value="pending" />
          <el-option label="待发货" value="partial" />
          <el-option label="已发货" value="shipped" />
        </el-select>
      </div>
    </el-card>

    <!-- 订单列表 -->
    <el-card shadow="never" style="margin-top: 16px">
      <template #header><span>平台订单（{{ total }}）</span></template>
      <el-table :data="orders" size="small">
        <el-table-column prop="platform_order_no" label="平台单号" width="190" />
        <el-table-column label="平台" width="90" align="center">
          <template #default="{ row }: { row: PlatformOrder }">
            <el-tag size="small" effect="plain">{{ row.platform }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }: { row: PlatformOrder }">
            <el-tag size="small" :type="ORDER_TAG[row.status] ?? 'info'">
              {{ ORDER_LABEL[row.status] ?? row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="商品明细" min-width="200">
          <template #default="{ row }: { row: PlatformOrder }">
            <span v-for="(it, i) in row.items" :key="it.id">
              {{ i > 0 ? '、' : '' }}{{ it.platform_sku }}×{{ it.quantity }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="100" align="right">
          <template #default="{ row }: { row: PlatformOrder }">￥{{ row.amount.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="收货人" min-width="160">
          <template #default="{ row }: { row: PlatformOrder }">
            {{ row.receiver_name }} {{ row.receiver_phone }}
            <div class="addr">{{ row.receiver_address }}</div>
          </template>
        </el-table-column>
        <el-table-column label="下单时间" width="160">
          <template #default="{ row }: { row: PlatformOrder }">
            {{ row.created_at.replace('T', ' ').slice(0, 16) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 发货单列表 -->
    <el-card shadow="never" style="margin-top: 16px">
      <template #header><span>发货单（{{ shipments.length }}）</span></template>
      <el-table :data="shipments" size="small">
        <el-table-column prop="platform_order_no" label="平台单号" width="190" />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }: { row: Shipment }">
            <el-tag size="small" :type="row.status === 'shipped' ? 'success' : 'warning'">
              {{ row.status === 'shipped' ? '已发货' : '待发货' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="商品" min-width="160">
          <template #default="{ row }: { row: Shipment }">
            {{ row.items.map((it) => `${productName(it.product_id)}×${it.quantity}`).join('、') }}
          </template>
        </el-table-column>
        <el-table-column label="物流" min-width="170">
          <template #default="{ row }: { row: Shipment }">
            {{ row.tracking_no ? `${row.carrier ?? ''} ${row.tracking_no}` : '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="shipped_at" label="发货时间" width="160">
          <template #default="{ row }: { row: Shipment }">
            {{ row.shipped_at?.replace('T', ' ').slice(0, 16) || '—' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }: { row: Shipment }">
            <el-button
              v-if="row.status === 'waiting' && canWrite"
              size="small" type="primary" @click="openShipDialog(row)"
            >发货</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 发货弹窗 -->
    <el-dialog v-model="shipVisible" title="发货确认" width="420px">
      <el-form label-width="90px">
        <el-form-item label="物流单号">
          <el-input v-model="shipForm.tracking_no" placeholder="如 SF1234567890" />
        </el-form-item>
        <el-form-item label="承运商">
          <el-input v-model="shipForm.carrier" placeholder="如 顺丰（可空）" />
        </el-form-item>
      </el-form>
      <p class="hint">发货将按明细扣减库存并写入流水（账实分离），库存不足会整体拒绝。</p>
      <template #footer>
        <el-button @click="shipVisible = false">取消</el-button>
        <el-button type="primary" :loading="shipping" @click="onShip">确认发货</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { orderApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { PlatformOrder, Shipment, Shop } from '@/types'

const auth = useAuthStore()
const canWrite = computed(() => ['admin', 'operator'].includes(auth.role))

const ORDER_LABEL: Record<string, string> = {
  pending: '待拆单', partial: '待发货', shipped: '已发货', legacy: '历史',
}
const ORDER_TAG: Record<string, 'primary' | 'success' | 'warning' | 'info'> = {
  pending: 'warning', partial: 'primary', shipped: 'success', legacy: 'info',
}

const shops = ref<Shop[]>([])
const orders = ref<PlatformOrder[]>([])
const total = ref(0)
const shipments = ref<Shipment[]>([])
const statusFilter = ref('')
const fetchShopId = ref('')

const products = ref<{ id: string; sku: string; name: string }[]>([])
const productName = (id: string) => {
  const p = products.value.find((x) => x.id === id)
  return p ? p.sku : id.slice(0, 8)
}

async function loadAll(): Promise<void> {
  const [o, s, shopsData, prod] = await Promise.all([
    orderApi.list({ status: statusFilter.value || undefined, page: 1, page_size: 50 }),
    orderApi.listShipments({ page: 1, page_size: 50 }),
    shopsApiList(),
    productsApiList(),
  ])
  orders.value = o.items
  total.value = o.total
  shipments.value = s.items
  shops.value = shopsData
  products.value = prod
}

/** 店铺列表（拉单选择用） */
async function shopsApiList(): Promise<Shop[]> {
  const { shopsApi } = await import('@/api')
  return (await shopsApi.list()) as unknown as Shop[]
}

/** 商品列表（发货单商品名展示用） */
async function productsApiList() {
  const { productsApi } = await import('@/api')
  const data = await productsApi.list({ page: 1, page_size: 200 })
  return data.items.map((p) => ({ id: p.id, sku: p.sku, name: p.name }))
}

// ---------- 拉单 / 拆单 ----------
const fetching = ref(false)
const splitting = ref(false)

async function onFetch(): Promise<void> {
  if (!fetchShopId.value) {
    ElMessage.warning('请先选择店铺')
    return
  }
  fetching.value = true
  try {
    const r = await orderApi.fetch({ shop_id: fetchShopId.value })
    ElMessage.success(`拉取完成：新增 ${r.fetched} 单，跳过 ${r.skipped} 单（幂等去重）`)
    loadAll()
  } finally {
    fetching.value = false
  }
}

async function onSplit(): Promise<void> {
  splitting.value = true
  try {
    const r = await orderApi.split({})
    ElMessage.success(`拆单完成：生成 ${r.split} 张发货单，${r.skipped} 单库存不足待补货`)
    loadAll()
  } finally {
    splitting.value = false
  }
}

// ---------- 发货 ----------
const shipVisible = ref(false)
const shipping = ref(false)
const shipTarget = ref<Shipment | null>(null)
const shipForm = ref({ tracking_no: '', carrier: '' })

function openShipDialog(row: Shipment): void {
  shipTarget.value = row
  shipForm.value = { tracking_no: '', carrier: '' }
  shipVisible.value = true
}

async function onShip(): Promise<void> {
  if (!shipTarget.value) return
  if (!shipForm.value.tracking_no.trim()) {
    ElMessage.warning('请填写物流单号')
    return
  }
  shipping.value = true
  try {
    await orderApi.ship(shipTarget.value.id, { ...shipForm.value })
    ElMessage.success('发货成功，库存已扣减')
    shipVisible.value = false
    loadAll()
  } finally {
    shipping.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.addr { color: #909399; font-size: 12px; }
.hint { color: #909399; font-size: 12px; margin-top: 10px; }
</style>
