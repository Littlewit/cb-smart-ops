<template>
  <div class="page">
    <el-card shadow="hover">
      <!-- 工具栏：搜索 / 预警过滤 / 新增 -->
      <el-form inline>
        <el-form-item label="关键字">
          <el-input v-model="query.q" placeholder="SKU / 名称搜索" clearable style="width: 220px" autocomplete="off" @change="load">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item label="店铺">
          <el-select v-model="query.shop_id" placeholder="全部店铺" clearable style="width: 160px" @change="load">
            <el-option v-for="s in shops" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.alert" placeholder="全部状态" clearable style="width: 140px" @change="load">
            <el-option label="仅预警商品" :value="true" />
            <el-option label="仅正常商品" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="canWrite">
          <el-button type="primary" @click="openCreate">
            <el-icon><Plus /></el-icon>新增商品
          </el-button>
        </el-form-item>
      </el-form>
  
      <!-- 商品表格：预警行红色高亮；点击行打开 SKU 映射抽屉（与库存页交互一致） -->
      <el-table
        :data="items"
        v-loading="loading"
        :row-class-name="rowClass"
        @row-click="openMappings"
      >
        <el-table-column prop="sku" label="SKU" width="120" />
        <el-table-column prop="name" label="名称" min-width="100" />
        <!-- 金额/库存列等宽数字（Stripe 金融数字规范） -->
        <el-table-column prop="cost_price" label="成本价" width="90" align="center" class-name="num" />
        <el-table-column prop="sale_price" label="售价" width="90" align="center" class-name="num" />
        <el-table-column prop="stock" label="库存" width="80" align="center" class-name="num" />
        <el-table-column prop="safety_stock" label="安全库存" width="90" align="center" class-name="num" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.alert_status ? 'danger' : 'success'" effect="light">
              {{ row.alert_status ? '预警' : '正常' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <template v-if="canWrite">
              <!-- 编辑/删除用图标按钮；stop 避免触发行点击打开映射 -->
              <el-button size="small" type="primary" @click.stop="openEdit(row)">
                <el-icon><Edit /></el-icon>
              </el-button>
              <el-button size="small" type="danger" @click.stop="onDelete(row)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
  
      <!-- 分页：右对齐 -->
      <el-pagination
        v-model:current-page="query.page"
        :page-size="query.page_size"
        :total="total"
        layout="total, prev, pager, next"
        class="pager"
        @current-change="load"
      />
    </el-card>

    <!-- 新增/编辑 dialog -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑商品' : '新增商品'" width="480px">
      <el-form :model="form" label-width="90px" style="margin-top: 30px;">
        <el-form-item label="店铺" v-if="!editingId">
          <el-select v-model="form.shop_id" style="width: 100%">
            <el-option v-for="s in shops" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="SKU" v-if="!editingId">
          <el-input v-model="form.sku" autocomplete="off" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" autocomplete="off" />
        </el-form-item>
        <el-form-item label="成本价"><el-input-number v-model="form.cost_price" :min="0" :precision="2" /></el-form-item>
        <el-form-item label="售价"><el-input-number v-model="form.sale_price" :min="0" :precision="2" /></el-form-item>
        <el-form-item label="库存"><el-input-number v-model="form.stock" :min="0" /></el-form-item>
        <el-form-item label="安全库存"><el-input-number v-model="form.safety_stock" :min="0" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- SKU 映射抽屉 -->
    <el-drawer v-model="mappingVisible" title="多平台 SKU 映射" size="420px">
      <el-form inline>
        <el-select v-model="mappingForm.platform" style="width: 120px">
          <el-option label="SHEIN" value="shein" />
          <el-option label="Shopify" value="shopify" />
          <el-option label="Mock" value="mock" />
        </el-select>
        <el-input v-model="mappingForm.external_sku" placeholder="平台侧SKU" style="width: 150px" autocomplete="off" />
        <el-button type="primary" v-if="canWrite" @click="addMapping">添加</el-button>
      </el-form>
      <el-table :data="mappings">
        <el-table-column prop="platform" label="平台" width="90" />
        <el-table-column prop="external_sku" label="平台SKU" />
        <el-table-column v-if="canWrite" label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" type="danger" @click="removeMapping(row)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { productsApi, shopsApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { Product, Shop, SkuMapping } from '@/types'

const auth = useAuthStore()
// operator 及以上才显示写操作（安全边界在后端，这里只是隐藏入口）
const canWrite = computed(() => ['admin', 'operator'].includes(auth.role))

const items = ref<Product[]>([])
const shops = ref<Shop[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive<{ q: string; shop_id: string; alert: boolean | null; page: number; page_size: number }>({
  q: '',
  shop_id: '',
  alert: null,
  page: 1,
  page_size: 10,
})

const dialogVisible = ref(false)
const editingId = ref('')
// 表单字段：创建需要 shop_id/sku，编辑只更新其余字段
const form = reactive<{
  shop_id: string; sku: string; name: string;
  cost_price: number; sale_price: number; stock: number; safety_stock: number
}>({ shop_id: '', sku: '', name: '', cost_price: 0, sale_price: 0, stock: 0, safety_stock: 10 })

const mappingVisible = ref(false)
const mappingProductId = ref('')
const mappings = ref<SkuMapping[]>([])
const mappingForm = reactive({ platform: 'shein', external_sku: '' })

/** 预警商品整行标红 */
const rowClass = ({ row }: { row: Product }): string => (row.alert_status ? 'alert-row' : '')

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await productsApi.list({ ...query })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function loadShops(): Promise<void> {
  shops.value = await shopsApi.list()
}

function openCreate(): void {
  editingId.value = ''
  Object.assign(form, { shop_id: '', sku: '', name: '', cost_price: 0, sale_price: 0, stock: 0, safety_stock: 10 })
  dialogVisible.value = true
}

function openEdit(row: Product): void {
  editingId.value = row.id
  Object.assign(form, row)
  dialogVisible.value = true
}

async function onSubmit(): Promise<void> {
  if (editingId.value) {
    // 编辑：仅提交可更新字段（shop_id/sku 创建后不可改）
    await productsApi.update(editingId.value, {
      name: form.name, cost_price: form.cost_price, sale_price: form.sale_price,
      stock: form.stock, safety_stock: form.safety_stock,
    })
  } else {
    await productsApi.create({ ...form })
  }
  ElMessage.success('已保存')
  dialogVisible.value = false
  load()
}

async function onDelete(row: Product): Promise<void> {
  await ElMessageBox.confirm(`确认删除商品 ${row.sku}？关联的流水/映射将一并删除`, '删除确认', { type: 'warning' })
  await productsApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

// ---------- SKU 映射 ----------
async function openMappings(row: Product): Promise<void> {
  mappingProductId.value = row.id
  mappings.value = await productsApi.listSkuMappings(row.id)
  mappingVisible.value = true
}

async function addMapping(): Promise<void> {
  await productsApi.addSkuMapping(mappingProductId.value, { ...mappingForm })
  mappings.value = await productsApi.listSkuMappings(mappingProductId.value)
  ElMessage.success('已添加')
}

async function removeMapping(row: SkuMapping): Promise<void> {
  await productsApi.removeSkuMapping(mappingProductId.value, row.id)
  mappings.value = await productsApi.listSkuMappings(mappingProductId.value)
}

onMounted(() => {
  load()
  loadShops()
})
</script>
