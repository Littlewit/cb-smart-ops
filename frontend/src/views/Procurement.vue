<template>
  <div class="page">
    <!-- 上卡：供应商主数据 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>供应商</span>
          <el-button type="primary" size="small" @click="openSupplierDialog()">新增供应商</el-button>
        </div>
      </template>
      <el-table :data="suppliers" size="small">
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="contact" label="联系人" width="110" />
        <el-table-column prop="phone" label="电话" width="140" />
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }: { row: Supplier }">
            <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" align="center">
          <template #default="{ row }: { row: Supplier }">
            <el-button size="small" @click="openSupplierDialog(row)">编辑</el-button>
            <el-button
              v-if="row.status === 'active'"
              size="small" type="warning" plain
              @click="toggleSupplier(row, 'disabled')"
            >停用</el-button>
            <el-button v-else size="small" type="success" plain @click="toggleSupplier(row, 'active')">
              启用
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 下卡：采购单列表 -->
    <el-card shadow="never" style="margin-top: 16px">
      <template #header>
        <div class="card-header">
          <el-select v-model="statusFilter" size="small" style="width: 140px" @change="loadPos">
            <el-option label="全部状态" value="" />
            <el-option v-for="(label, key) in PO_STATUS_LABELS" :key="key" :label="label" :value="key" />
          </el-select>
          <el-button type="primary" size="small" @click="poDialogVisible = true">新建采购单</el-button>
        </div>
      </template>
      <el-table :data="pos" size="small" @row-click="openPoDetail">
        <el-table-column prop="po_no" label="采购单号" width="180" />
        <el-table-column label="供应商" min-width="140">
          <template #default="{ row }: { row: PurchaseOrder }">
            {{ supplierName(row.supplier_id) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }: { row: PurchaseOrder }">
            <el-tag size="small" :type="PO_STATUS_TAG[row.status]">{{ PO_STATUS_LABELS[row.status] }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_amount" label="总金额" width="110" align="right">
          <template #default="{ row }: { row: PurchaseOrder }">￥{{ row.total_amount.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }: { row: PurchaseOrder }">{{ row.created_at.replace('T', ' ').slice(0, 16) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 采购单详情抽屉：明细 + 分批收货 -->
    <el-drawer v-model="detailVisible" :title="detail?.po_no || '采购单详情'" size="620px">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="状态">
            <el-tag size="small" :type="PO_STATUS_TAG[detail.status]">{{ PO_STATUS_LABELS[detail.status] }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="总金额">￥{{ detail.total_amount.toFixed(2) }}</el-descriptions-item>
        </el-descriptions>
        <h4 class="drawer-title">采购明细（可分批收货）</h4>
        <el-table :data="detail.items" size="small">
          <el-table-column prop="product_id" label="商品" min-width="120">
            <template #default="{ row }: { row: PurchaseOrderItem }">
              {{ productName(row.product_id) }}
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="采购量" width="80" align="center" />
          <el-table-column prop="unit_price" label="单价" width="80" align="right" />
          <el-table-column prop="received_qty" label="已收" width="70" align="center" />
          <el-table-column label="本次收货" width="140" align="center">
            <template #default="{ row }: { row: PurchaseOrderItem }">
              <el-input-number
                v-if="canReceive"
                v-model="receiveQty[row.id]"
                size="small" :min="0" :max="row.quantity - row.received_qty"
                :disabled="row.quantity - row.received_qty <= 0"
                style="width: 120px"
              />
              <span v-else-if="row.quantity - row.received_qty <= 0">已收齐</span>
              <span v-else>待收 {{ row.quantity - row.received_qty }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div style="margin-top: 14px; text-align: right">
          <!-- 草稿：先提交锁定；已提交/收货中：收货入库 -->
          <el-button
            v-if="canWrite && detail.status === 'draft'"
            type="warning" :loading="submitting" @click="onSubmitPo"
          >提交采购单</el-button>
          <el-button
            v-if="canWrite && (detail.status === 'submitted' || detail.status === 'receiving')"
            type="primary" :loading="receiving" @click="onReceive"
          >确认收货入库</el-button>
        </div>
        <p v-if="detail.status === 'cancelled'" class="hint">该采购单已撤销。</p>
      </template>
    </el-drawer>

    <!-- 新建采购单弹窗 -->
    <el-dialog v-model="poDialogVisible" title="新建采购单" width="560px">
      <el-form label-width="90px">
        <el-form-item label="供应商">
          <el-select v-model="poForm.supplier_id" style="width: 100%" placeholder="选择启用中的供应商">
            <el-option v-for="s in activeSuppliers" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="poForm.remark" placeholder="可留空" />
        </el-form-item>
        <el-form-item v-for="(it, i) in poForm.items" :key="i" :label="`商品 ${i + 1}`">
          <div class="po-item-row">
            <el-select v-model="it.product_id" style="flex: 1" placeholder="选择商品">
              <el-option v-for="p in products" :key="p.id" :label="`${p.sku} ${p.name}`" :value="p.id" />
            </el-select>
            <el-input-number v-model="it.quantity" :min="1" placeholder="数量" style="width: 110px" />
            <el-input-number v-model="it.unit_price" :min="0" :precision="2" placeholder="单价" style="width: 120px" />
            <el-button text type="danger" @click="poForm.items.splice(i, 1)">删</el-button>
          </div>
        </el-form-item>
        <el-form-item>
          <el-button size="small" @click="poForm.items.push({ product_id: '', quantity: 1, unit_price: 0 })">
            + 添加商品行
          </el-button>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="poDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="onCreatePo">创建草稿</el-button>
      </template>
    </el-dialog>

    <!-- 供应商弹窗 -->
    <el-dialog v-model="supplierDialogVisible" :title="editingSupplier ? '编辑供应商' : '新增供应商'" width="440px">
      <el-form label-width="70px">
        <el-form-item label="名称"><el-input v-model="supplierForm.name" /></el-form-item>
        <el-form-item label="联系人"><el-input v-model="supplierForm.contact" /></el-form-item>
        <el-form-item label="电话"><el-input v-model="supplierForm.phone" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="supplierForm.email" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="supplierDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingSupplier" @click="onSaveSupplier">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { procurementApi, productsApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { PurchaseOrder, PurchaseOrderItem, Supplier } from '@/types'

const auth = useAuthStore()
const canWrite = computed(() => ['admin', 'operator'].includes(auth.role))
const canReceive = canWrite

// 状态 → 文案/Tag 颜色（与后端状态机一一对应）
const PO_STATUS_LABELS: Record<string, string> = {
  draft: '草稿', submitted: '已提交', receiving: '收货中', completed: '已完成', cancelled: '已撤销',
}
const PO_STATUS_TAG: Record<string, 'info' | 'primary' | 'warning' | 'success' | 'danger'> = {
  draft: 'info', submitted: 'primary', receiving: 'warning', completed: 'success', cancelled: 'danger',
}

// ---------- 数据 ----------
const suppliers = ref<Supplier[]>([])
const products = ref<{ id: string; sku: string; name: string }[]>([])
const pos = ref<PurchaseOrder[]>([])
const statusFilter = ref('')
const detail = ref<PurchaseOrder | null>(null)
const detailVisible = ref(false)
const receiveQty = reactive<Record<string, number>>({})

const activeSuppliers = computed(() => suppliers.value.filter((s) => s.status === 'active'))
const supplierName = (id: string) => suppliers.value.find((s) => s.id === id)?.name ?? id.slice(0, 8)
const productName = (id: string) => {
  const p = products.value.find((x) => x.id === id)
  return p ? `${p.sku} ${p.name}` : id.slice(0, 8)
}

async function loadAll(): Promise<void> {
  const [sup, prod] = await Promise.all([procurementApi.listSuppliers(), productsApiList()])
  suppliers.value = sup.items
  products.value = prod
  await loadPos()
}

/** 商品列表（供应商/采购单选择用）——复用商品分页接口 */
async function productsApiList() {
  const data = await productsApi.list({ page: 1, page_size: 100 })
  return data.items.map((p) => ({ id: p.id, sku: p.sku, name: p.name }))
}

async function loadPos(): Promise<void> {
  const data = await procurementApi.listPos({
    status: statusFilter.value || undefined, page: 1, page_size: 50,
  })
  pos.value = data.items
}

// ---------- 采购单详情与收货 ----------
async function openPoDetail(row: PurchaseOrder): Promise<void> {
  detail.value = await procurementApi.getPo(row.id)
  receiveQtyClear()
  detailVisible.value = true
}

function receiveQtyClear(): void {
  Object.keys(receiveQty).forEach((k) => delete receiveQty[k])
}

async function onReceive(): Promise<void> {
  if (!detail.value) return
  // 汇总本次收货行：只提交数量 > 0 的明细
  const items = (detail.value.items ?? [])
    .filter((it) => (receiveQty[it.id] ?? 0) > 0)
    .map((it) => ({ item_id: it.id, quantity: receiveQty[it.id] }))
  if (!items.length) {
    ElMessage.warning('请先填写本次收货数量')
    return
  }
  receiving.value = true
  try {
    const result = await procurementApi.receive(detail.value.id, items)
    ElMessage.success(`收货成功，采购单状态：${PO_STATUS_LABELS[result.status] ?? result.status}`)
    detail.value = await procurementApi.getPo(detail.value.id)
    receiveQtyClear()
    loadPos()
  } finally {
    receiving.value = false
  }
}
const receiving = ref(false)
const submitting = ref(false)

async function onSubmitPo(): Promise<void> {
  if (!detail.value) return
  submitting.value = true
  try {
    await procurementApi.submitPo(detail.value.id)
    ElMessage.success('采购单已提交，明细已锁定')
    detail.value = await procurementApi.getPo(detail.value.id)
    loadPos()
  } finally {
    submitting.value = false
  }
}

// ---------- 新建采购单 ----------
const poDialogVisible = ref(false)
const creating = ref(false)
const poForm = reactive({
  supplier_id: '',
  remark: '',
  items: [{ product_id: '', quantity: 1, unit_price: 0 }] as { product_id: string; quantity: number; unit_price: number }[],
})

async function onCreatePo(): Promise<void> {
  if (!poForm.supplier_id) {
    ElMessage.warning('请选择供应商')
    return
  }
  const items = poForm.items.filter((it) => it.product_id && it.quantity > 0)
  if (!items.length) {
    ElMessage.warning('请至少添加一行有效商品')
    return
  }
  creating.value = true
  try {
    const po = await procurementApi.createPo({ supplier_id: poForm.supplier_id, remark: poForm.remark, items })
    ElMessage.success(`采购单 ${po.po_no} 已创建（草稿）`)
    poDialogVisible.value = false
    poForm.items = [{ product_id: '', quantity: 1, unit_price: 0 }]
    loadPos()
  } finally {
    creating.value = false
  }
}

// ---------- 供应商弹窗 ----------
const supplierDialogVisible = ref(false)
const savingSupplier = ref(false)
const editingSupplier = ref<Supplier | null>(null)
const supplierForm = reactive({ name: '', contact: '', phone: '', email: '' })

function openSupplierDialog(row?: Supplier): void {
  editingSupplier.value = row ?? null
  Object.assign(supplierForm, {
    name: row?.name ?? '', contact: row?.contact ?? '',
    phone: row?.phone ?? '', email: row?.email ?? '',
  })
  supplierDialogVisible.value = true
}

async function onSaveSupplier(): Promise<void> {
  if (!supplierForm.name.trim()) {
    ElMessage.warning('请输入供应商名称')
    return
  }
  savingSupplier.value = true
  try {
    if (editingSupplier.value) {
      await procurementApi.updateSupplier(editingSupplier.value.id, { ...supplierForm })
    } else {
      await procurementApi.createSupplier({ ...supplierForm })
    }
    ElMessage.success('已保存')
    supplierDialogVisible.value = false
    loadAll()
  } finally {
    savingSupplier.value = false
  }
}

async function toggleSupplier(row: Supplier, status: 'active' | 'disabled'): Promise<void> {
  await procurementApi.updateSupplier(row.id, { status })
  ElMessage.success(status === 'active' ? '已启用' : '已停用')
  loadAll()
}

onMounted(loadAll)
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
.drawer-title { margin: 16px 0 8px; color: var(--s-ink); }
.po-item-row { display: flex; gap: 8px; width: 100%; }
.hint { color: #909399; font-size: 12px; margin-top: 10px; }
</style>
