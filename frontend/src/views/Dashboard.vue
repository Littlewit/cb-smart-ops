<template>
  <div class="page">
    <!-- 顶部指标卡片：图标芯片 + 大数字 -->
    <el-row :gutter="16">
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat">
            <div class="stat-icon indigo"><el-icon><Goods /></el-icon></div>
            <div>
              <div class="stat-label">商品总数</div>
              <div class="stat-value">{{ stats.total_products }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat">
            <div class="stat-icon ruby"><el-icon><Warning /></el-icon></div>
            <div>
              <div class="stat-label">预警商品</div>
              <div class="stat-value ruby">{{ stats.alert_count }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat">
            <div class="stat-icon navy"><el-icon><Shop /></el-icon></div>
            <div>
              <div class="stat-label">店铺数量</div>
              <div class="stat-value">{{ stats.total_shops }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat">
            <div class="stat-icon green"><el-icon><TrendCharts /></el-icon></div>
            <div>
              <div class="stat-label">近 7 天销售额</div>
              <div class="stat-value">￥{{ totalSales.toFixed(2) }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区：左折线（销售趋势）右饼图（店铺分布） -->
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="14"><el-card shadow="hover"><div ref="trendRef" class="chart" /></el-card></el-col>
      <el-col :span="10"><el-card shadow="hover"><div ref="pieRef" class="chart" /></el-card></el-col>
    </el-row>
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

/** 渲染销售趋势折线图（窗口尺寸变化时自适应） */
function renderTrend(trend: DashboardStats['sales_trend']): void {
  if (!trendRef.value) return
  trendChart = echarts.init(trendRef.value)
  trendChart.setOption({
    title: { text: '近 7 天销售额趋势', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: trend.map((d) => d.date) },
    yAxis: { type: 'value' },
    series: [{ type: 'line', data: trend.map((d) => d.amount), smooth: true, areaStyle: { opacity: 0.15 } }],
  })
}

/** 渲染店铺商品分布饼图 */
function renderPie(dist: DashboardStats['shop_distribution']): void {
  if (!pieRef.value) return
  pieChart = echarts.init(pieRef.value)
  pieChart.setOption({
    title: { text: '各店铺商品分布', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'pie',
        radius: ['35%', '65%'],
        data: dist.map((d) => ({ name: d.shop, value: d.product_count })),
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
.chart { height: 320px; }
</style>
