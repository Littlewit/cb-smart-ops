<template>
  <div class="page dashboard">
    <!-- 统计卡片：4 列 grid，图标渐变芯片 + 数值 + 趋势行（设计稿：数据看板.html） -->
    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-icon icon-purple"><el-icon :size="26"><Goods /></el-icon></div>
        <div class="stat-meta">
          <div class="stat-label">商品总数</div>
          <div class="stat-value">{{ stats.total_products }}</div>
          <div class="stat-trend trend-neutral">较昨日 +0</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon icon-red"><el-icon :size="26"><Warning /></el-icon></div>
        <div class="stat-meta">
          <div class="stat-label">预警商品</div>
          <div class="stat-value red">{{ stats.alert_count }}</div>
          <div class="stat-trend trend-down">{{ stats.alert_count > 0 ? '需立即处理' : '暂无预警' }}</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon icon-blue"><el-icon :size="26"><Shop /></el-icon></div>
        <div class="stat-meta">
          <div class="stat-label">店铺数量</div>
          <div class="stat-value">{{ stats.total_shops }}</div>
          <div class="stat-trend trend-neutral">已接入</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon icon-green"><el-icon :size="26"><TrendCharts /></el-icon></div>
        <div class="stat-meta">
          <div class="stat-label">近 7 天销售额</div>
          <div class="stat-value">¥ {{ totalSales.toFixed(2) }}</div>
          <div class="stat-trend trend-neutral">{{ totalSales > 0 ? '持续增长中' : '暂无交易' }}</div>
        </div>
      </div>
    </div>

    <!-- 图表区：左折线（销售趋势）右环形图（店铺分布） -->
    <div class="chart-row">
      <div class="chart-card">
        <div class="chart-header">
          <div>
            <div class="chart-title">近 7 天销售额趋势</div>
            <div class="chart-subtitle">单位：元 · 最近 7 天</div>
          </div>
          <div class="chart-filter">近 7 天 ▾</div>
        </div>
        <div ref="trendRef" class="chart-box"></div>
      </div>
      <div class="chart-card">
        <div class="chart-header">
          <div>
            <div class="chart-title">各店铺商品分布</div>
            <div class="chart-subtitle">按商品数量统计</div>
          </div>
        </div>
        <div ref="pieRef" class="chart-box"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { dashboardApi } from '@/api'
import type { DashboardStats } from '@/types'

const stats = ref<DashboardStats>({
  total_products: 0,
  alert_count: 0,
  total_shops: 0,
  sales_trend: [],
  shop_distribution: [],
})

// 近7天销售额合计（指标卡片）
const totalSales = computed<number>(() =>
  (stats.value.sales_trend || []).reduce((sum, d) => sum + Number(d.amount || 0), 0)
)

const trendRef = ref<HTMLElement | null>(null)
const pieRef = ref<HTMLElement | null>(null)
// echarts 实例类型：init 返回 ECharts | undefined
let trendChart: echarts.ECharts | null = null
let pieChart: echarts.ECharts | null = null

/** indigo→violet 品牌渐变（折线与环形图共用配色语言） */
const LINE_GRADIENT = new echarts.graphic.LinearGradient(0, 0, 1, 0, [
  { offset: 0, color: '#6366f1' },
  { offset: 1, color: '#8b5cf6' },
])

/** 环形图多店铺色板：[起始色, 结束色] 成对渐变 */
const PIE_PALETTE: [string, string][] = [
  ['#6366f1', '#8b5cf6'],
  ['#818cf8', '#a78bfa'],
  ['#4f46e5', '#7c3aed'],
  ['#38bdf8', '#818cf8'],
  ['#8b5cf6', '#d946ef'],
]

/** 渲染销售趋势折线图：渐变线条 + 渐变面积 + 白描圆点 */
function renderTrend(trend: DashboardStats['sales_trend']): void {
  if (!trendRef.value) return
  trendChart = echarts.init(trendRef.value)
  trendChart.setOption({
    grid: { left: 55, right: 30, top: 20, bottom: 40 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#fff',
      borderColor: '#e2e8f0',
      textStyle: { color: '#0f172a', fontSize: 13 },
      extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-radius: 8px;',
    },
    xAxis: {
      type: 'category',
      data: trend.map((d) => d.date),
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisTick: { show: false },
      axisLabel: { color: '#64748b', fontSize: 12 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f1f5f9' } },
      axisLabel: { color: '#64748b', fontSize: 12 },
    },
    series: [
      {
        data: trend.map((d) => d.amount),
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        lineStyle: { width: 3, color: LINE_GRADIENT },
        itemStyle: { color: '#6366f1', borderColor: '#fff', borderWidth: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(99,102,241,0.15)' },
            { offset: 1, color: 'rgba(99,102,241,0.01)' },
          ]),
        },
      },
    ],
  })
}

/** 渲染店铺商品分布环形图：圆角扇区 + 白描边 + 底部圆形图例 */
function renderPie(dist: DashboardStats['shop_distribution']): void {
  if (!pieRef.value) return
  pieChart = echarts.init(pieRef.value)
  pieChart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} 件 ({d}%)',
      backgroundColor: '#fff',
      borderColor: '#e2e8f0',
      textStyle: { color: '#0f172a', fontSize: 13 },
      extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-radius: 8px;',
    },
    legend: {
      bottom: 0,
      left: 'center',
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { color: '#64748b', fontSize: 12 },
    },
    series: [
      {
        type: 'pie',
        radius: ['50%', '72%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: false,
        label: { show: false },
        labelLine: { show: false },
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 3 },
        data: dist.map((d, i) => ({
          value: d.product_count,
          name: d.shop,
          // 按索引从 indigo→violet 色板取渐变，多店铺时颜色可区分
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 1, 1, [
              { offset: 0, color: PIE_PALETTE[i % PIE_PALETTE.length][0] },
              { offset: 1, color: PIE_PALETTE[i % PIE_PALETTE.length][1] },
            ]),
          },
        })),
      },
    ],
  })
}

// 窗口缩放时重算图表尺寸
const onResize = (): void => {
  trendChart?.resize()
  pieChart?.resize()
}

onMounted(async () => {
  stats.value = await dashboardApi.stats()
  renderTrend(stats.value.sales_trend || [])
  renderPie(stats.value.shop_distribution || [])
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  trendChart?.dispose()
  pieChart?.dispose()
})
</script>

<style scoped>
/* ===== 统计卡片（设计稿 .stat-card 令牌） ===== */
.stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-bottom: 24px;
}
.stat-card {
  background: var(--s-canvas);
  border-radius: 16px;
  padding: 22px 24px;
  display: flex;
  align-items: center;
  gap: 18px;
  border: 1px solid rgba(226, 232, 240, 0.6);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04), 0 4px 16px rgba(15, 23, 42, 0.04);
  transition: transform 0.2s, box-shadow 0.2s;
}
.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(15, 23, 42, 0.06), 0 12px 28px rgba(15, 23, 42, 0.08);
}

/* 图标芯片：52px 圆角 14px + 双色渐变底 */
.stat-icon {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.icon-purple { background: linear-gradient(135deg, #ede9fe, #ddd6fe); color: #7c3aed; }
.icon-red    { background: linear-gradient(135deg, #fee2e2, #fecaca); color: #dc2626; }
.icon-blue   { background: linear-gradient(135deg, #dbeafe, #bfdbfe); color: #2563eb; }
.icon-green  { background: linear-gradient(135deg, #d1fae5, #a7f3d0); color: #059669; }

.stat-meta { flex: 1; }
.stat-label { font-size: 13px; color: var(--s-ink-mute); margin-bottom: 6px; }
.stat-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.5px;
  color: var(--s-ink);
  font-variant-numeric: tabular-nums;
}
.stat-value.red { color: #dc2626; }

/* 趋势行：小字说明（up 绿 / down 红 / neutral 灰） */
.stat-trend { font-size: 12px; display: flex; align-items: center; gap: 2px; margin-top: 4px; }
.trend-down { color: #dc2626; }
.trend-neutral { color: var(--s-ink-mute); }

/* ===== 图表卡片（1.7fr : 1fr 双列） ===== */
.chart-row {
  display: grid;
  grid-template-columns: 1.7fr 1fr;
  gap: 20px;
}
.chart-card {
  background: var(--s-canvas);
  border-radius: 16px;
  padding: 24px;
  border: 1px solid rgba(226, 232, 240, 0.6);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04), 0 4px 16px rgba(15, 23, 42, 0.04);
}
.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.chart-title { font-size: 15px; font-weight: 600; color: var(--s-ink); }
.chart-subtitle { font-size: 12px; color: var(--s-ink-mute); margin-top: 2px; }
.chart-filter {
  font-size: 12px;
  color: var(--s-ink-secondary);
  background: var(--s-canvas-soft, #f1f5f9);
  padding: 4px 10px;
  border-radius: 6px;
}
.chart-box { width: 100%; height: 320px; }
</style>
