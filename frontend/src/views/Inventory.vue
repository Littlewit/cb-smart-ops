<template>
  <div class="page">
    <!-- 顶部指标卡片（来自 /api/inventory/summary）：图标芯片 + 大数字；
         xs 单列 / sm 起三列，窄屏不挤压 -->
    <el-row :gutter="16">
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover">
          <div class="stat">
            <div class="stat-icon indigo"><el-icon><Goods /></el-icon></div>
            <div>
              <div class="stat-label">商品总数</div>
              <div class="stat-value">{{ summary.total_products }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover">
          <div class="stat">
            <div class="stat-icon ruby"><el-icon><Warning /></el-icon></div>
            <div>
              <div class="stat-label">预警商品</div>
              <div class="stat-value ruby">{{ summary.alert_count }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover">
          <div class="stat">
            <div class="stat-icon navy"><el-icon><Shop /></el-icon></div>
            <div>
              <div class="stat-label">店铺数量</div>
              <div class="stat-value">{{ summary.total_shops }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    <el-card shadow="hover" style="margin-top: 16px">
      <!-- 预警商品列表：红色高亮 + 操作入口 -->
      <h4 class="section-title">库存预警商品（点击行查看流水）</h4>
      <el-table :data="summary.alert_products" :row-class-name="() => 'alert-row'" @row-click="openLogs">
        <el-table-column prop="sku" label="SKU" width="140" />
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="stock" label="当前库存" width="100" align="center" />
        <el-table-column width="190" align="center">
          <template #header>
            安全库存
            <el-tooltip content="调整阈值后预警状态实时重算（需运营权限）" placement="top">
              <el-icon style="vertical-align: -2px"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <!-- @click.stop 防止触发行点击打开流水抽屉；改完即调 API 重算预警 -->
            <el-input-number
              v-if="canWrite"
              :model-value="row.safety_stock"
              size="small"
              :min="0"
              style="width: 110px"
              @click.stop
              @change="(v: number | undefined) => onSafetyChange(row, v)"
            />
            <span v-else>{{ row.safety_stock }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" v-if="canWrite" @click.stop="openOp(row)">入库/出库</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 库存流水抽屉：窄屏全宽，桌面固定 560px -->
    <el-drawer v-model="logsVisible" :title="`库存流水 - ${currentProduct?.sku || ''}`" :size="isMobile ? '100%' : '560px'">
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

    <!-- 入库/出库/盘点 dialog：窄屏 95% 宽防溢出 -->
    <el-dialog v-model="opVisible" :title="`库存操作 - ${currentProduct?.sku || ''}`" :width="isMobile ? '95%' : '420px'">
      <el-form :model="opForm" label-width="80px" style="margin-top: 30px;">
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
        <el-form-item label="原因"><el-input v-model="opForm.reason" placeholder="可留空自动生成" autocomplete="off" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="opVisible = false">取消</el-button>
        <el-button type="primary" @click="submitOp">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { inventoryApi, productsApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { InventoryLog, InventorySummary, Product } from '@/types'

const auth = useAuthStore()
const canWrite = computed(() => ['admin', 'operator'].includes(auth.role))

// 窄屏判定：驱动抽屉/弹窗宽度自适应（el-drawer 的 size 是 prop，CSS 难覆盖）
const isMobile = ref(window.innerWidth < 640)
const onWinResize = (): void => {
  isMobile.value = window.innerWidth < 640
}
onMounted(() => window.addEventListener('resize', onWinResize))
onUnmounted(() => window.removeEventListener('resize', onWinResize))

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

/**
 * 行内修改安全库存：更新后预警状态由后端同事务重算，
 * 重新拉取概览即可看到预警列表实时变化（规则闭环演示点）。
 */
async function onSafetyChange(row: Product, value: number | undefined): Promise<void> {
  if (value === undefined || value === row.safety_stock) return
  await productsApi.update(row.id, { safety_stock: value })
  ElMessage.success(`${row.sku} 安全库存已更新为 ${value}`)
  load()
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
