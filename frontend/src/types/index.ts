/**
 * 与后端 schemas/ 对应的前端类型定义（backend/app/schemas/）。
 * 保持字段一致，接口变更时两处同步。
 */

// ---------- 用户 / 认证 ----------
export type Role = 'admin' | 'operator' | 'viewer'

/** 个人中心信息（GET/PUT /api/auth/me） */
export interface Profile {
  id: string
  username: string
  role: Role
  email: string | null
  created_at: string
}

// ---------- 店铺 ----------
export interface Shop {
  id: string
  platform: 'shein' | 'shopify' | 'mock'
  name: string
  status: 'active' | 'disconnected' | 'connected'
}

// ---------- 商品 ----------
export interface Product {
  id: string
  shop_id: string
  sku: string
  name: string
  cost_price: number
  sale_price: number
  stock: number
  safety_stock: number
  alert_status: boolean
}

export interface SkuMapping {
  id: string
  product_id: string
  platform: string
  external_sku: string
}

export interface PagedData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// ---------- 库存 ----------
export interface InventoryLog {
  id: string
  product_id: string
  type: 'in' | 'out' | 'check'
  quantity: number
  stock_before: number
  stock_after: number
  reason: string
  created_at: string
}

export interface InventorySummary {
  total_products: number
  alert_count: number
  total_shops: number
  alert_products: Product[]
}

// ---------- AI ----------
export interface RestockContent {
  quantity: number
  priority: 'high' | 'medium' | 'low'
  reason: string
}

export interface PricingContent {
  suggested_price: number
  price_range: [number, number]
  strategy: string
  competitor_prices?: number[]
}

export type SuggestionContent = RestockContent | PricingContent

export interface AiSuggestion {
  id: string
  type: 'restock' | 'pricing' | 'alert'
  product_id: string | null
  content: SuggestionContent
  rule_refs: string[]
  /** 规则标题（后端随建议返回，展示用；旧数据无此字段） */
  rule_titles?: string[]
  status: 'pending' | 'accepted' | 'dismissed'
  created_at: string
}

// ---------- AI 会话（方案 B：对话历史后端持久化） ----------
export interface Conversation {
  id: string
  title: string
  updated_at: string
}

export interface ChatMessageOut {
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

// ---------- 看板 ----------
export interface DashboardStats {
  total_products: number
  alert_count: number
  total_shops: number
  sales_trend: { date: string; amount: number }[]
  shop_distribution: { shop: string; product_count: number }[]
}
