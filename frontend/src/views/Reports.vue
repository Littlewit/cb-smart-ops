<template>
  <div class="page">
    <el-card shadow="never">
      <el-tabs v-model="tab">
        <!-- CEO 看板 -->
        <el-tab-pane label="CEO 看板" name="ceo">
          <div class="stat-row">
            <div v-for="card in ceoCards" :key="card.label" class="stat-card">
              <div class="stat-label">{{ card.label }}</div>
              <div class="stat-value">{{ card.value }}</div>
              <div class="stat-sub">{{ card.sub }}</div>
            </div>
          </div>
          <div ref="trendRef" class="chart-box"></div>
        </el-tab-pane>

        <!-- 运营绩效 -->
        <el-tab-pane label="运营绩效" name="performance">
          <el-descriptions :column="3" border style="margin-top: 8px">
            <el-descriptions-item label="总订单（ERP）">{{ perf?.total_orders ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="已发货">{{ perf?.shipped_orders ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="待拆单">{{ perf?.pending_orders ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="发货率">{{ perf?.ship_rate ?? 0 }}%</el-descriptions-item>
            <el-descriptions-item label="发货单">{{ perf?.shipped_shipments ?? 0 }} / {{ perf?.total_shipments ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="平均发货时长">
              {{ perf?.avg_ship_hours !== null && perf?.avg_ship_hours !== undefined ? `${perf.avg_ship_hours} 小时` : '暂无' }}
            </el-descriptions-item>
          </el-descriptions>
          <p class="hint">发货时效 = 订单创建 → 全部发货完成（仅统计已发货订单）。</p>
        </el-tab-pane>

        <!-- 财务对账 -->
        <el-tab-pane label="财务对账" name="finance">
          <div class="fin-cards">
            <div class="fin-card">
              <div class="fin-title">采购应付（{{ fin?.days ?? 30 }} 天）</div>
              <div class="fin-amount red">￥{{ fin?.total_payable.toFixed(2) ?? '0.00' }}</div>
              <div v-for="p in fin?.payable ?? []" :key="p.name" class="fin-line">
                {{ p.name }}：￥{{ p.amount.toFixed(2) }}
              </div>
            </div>
            <div class="fin-card">
              <div class="fin-title">销售应收（{{ fin?.days ?? 30 }} 天）</div>
              <div class="fin-amount green">￥{{ fin?.total_receivable.toFixed(2) ?? '0.00' }}</div>
              <div v-for="r in fin?.receivable ?? []" :key="r.name" class="fin-line">
                {{ r.name }}：￥{{ r.amount.toFixed(2) }}
              </div>
            </div>
            <div class="fin-card">
              <div class="fin-title">净现金缺口（应收 − 应付）</div>
              <div class="fin-amount" :class="(fin?.net_cash_gap ?? 0) >= 0 ? 'green' : 'red'">
                ￥{{ fin?.net_cash_gap.toFixed(2) ?? '0.00' }}
              </div>
              <div class="fin-line">正 = 现金流入，负 = 需关注资金占用</div>
            </div>
          </div>
          <p class="hint">口径：应付 = 采购单明细（已提交/收货中/已完成）；应收 = 已发货与历史订单（待拆单不计入）。</p>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import { reportApi } from '@/api'
import type { CeoDashboard, FinanceReconciliation, PerformanceStats } from '@/types'

const tab = ref('ceo')
const ceo = ref<CeoDashboard | null>(null)
const perf = ref<PerformanceStats | null>(null)
const fin = ref<FinanceReconciliation | null>(null)

const trendRef = ref<HTMLElement | null>(null)
let trendChart: echarts.ECharts | null = null

// CEO 指标卡（数值与副标题）
const ceoCards = computed(() => [
  { label: 'GMV', value: `￥${(ceo.value?.gmv ?? 0).toFixed(2)}`, sub: `近 ${ceo.value?.days ?? 30} 天` },
  { label: '毛利', value: `￥${(ceo.value?.gross_profit ?? 0).toFixed(2)}`, sub: `毛利率 ${ceo.value?.gross_margin ?? 0}%` },
  { label: '库存周转', value: `${ceo.value?.stock_turnover ?? 0}`, sub: `当前库存 ${ceo.value?.total_stock ?? 0} 件` },
  { label: '预警商品', value: `${ceo.value?.alert_count ?? 0}`, sub: '低于安全库存' },
])

/** 渲染销售趋势折线（切 Tab 回到 CEO 页时需重算尺寸） */
function renderTrend(): void {
  if (tab.value !== 'ceo' || !trendRef.value || !ceo.value) return
  if (!trendChart) trendChart = echarts.init(trendRef.value)
  trendChart.setOption({
    grid: { left: 60, right: 30, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: ceo.value.sales_trend.map((d) => d.date.slice(5)),
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisLabel: { color: '#64748b', fontSize: 12 },
    },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#f1f5f9' } }, axisLabel: { color: '#64748b' } },
    series: [
      {
        data: ceo.value.sales_trend.map((d) => d.amount),
        type: 'line', smooth: true, symbol: 'circle', symbolSize: 6,
        lineStyle: { width: 3, color: '#6366f1' },
        areaStyle: { color: 'rgba(99,102,241,0.12)' },
      },
    ],
  })
}

// Tab 切换：回 CEO 页重渲染（echarts 容器 display:none 时 init 尺寸为 0）
watch(tab, async (t) => {
  if (t === 'ceo') {
    await nextTick()
    renderTrend()
    trendChart?.resize()
  }
})

const onResize = (): void => trendChart?.resize()

onMounted(async () => {
  window.addEventListener('resize', onResize)
  const [c, p, f] = await Promise.all([
    reportApi.ceo({ days: 30 }),
    reportApi.performance(),
    reportApi.finance({ days: 30 }),
  ])
  ceo.value = c
  perf.value = p
  fin.value = f
  await nextTick()
  renderTrend()
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  trendChart?.dispose()
})
</script>

<style scoped>
/* CEO 指标卡：4 列 grid，窄屏自动降列（复用全站断点规范） */
.stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin: 8px 0 16px;
}
.stat-card {
  background: var(--s-canvas);
  border-radius: 14px;
  padding: 16px 18px;
  border: 1px solid rgba(226, 232, 240, 0.6);
}
.stat-label { font-size: 13px; color: var(--s-ink-mute); margin-bottom: 6px; }
.stat-value { font-size: 24px; font-weight: 700; color: var(--s-ink); }
.stat-sub { font-size: 12px; color: #94a3b8; margin-top: 4px; }
.chart-box { width: 100%; height: 300px; }

/* 财务对账：三列对比卡 */
.fin-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 8px 0; }
.fin-card {
  border: 1px solid rgba(226, 232, 240, 0.6);
  border-radius: 14px;
  padding: 16px 18px;
  background: var(--s-canvas);
}
.fin-title { font-size: 13px; color: var(--s-ink-mute); margin-bottom: 8px; }
.fin-amount { font-size: 22px; font-weight: 700; margin-bottom: 8px; }
.fin-amount.red { color: #dc2626; }
.fin-amount.green { color: #059669; }
.fin-line { font-size: 12px; color: #64748b; line-height: 1.8; }
.hint { color: #909399; font-size: 12px; margin-top: 12px; }

/* 响应式：窄屏降列 */
@media (max-width: 992px) {
  .stat-row, .fin-cards { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 600px) {
  .stat-row, .fin-cards { grid-template-columns: 1fr; }
  .chart-box { height: 240px; }
}
</style>
