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

// ---------- 采购（ERP） ----------
export interface Supplier {
  id: string
  name: string
  contact: string | null
  phone: string | null
  email: string | null
  status: 'active' | 'disabled'
}

export type PoStatus = 'draft' | 'submitted' | 'receiving' | 'completed' | 'cancelled'

export interface PurchaseOrderItem {
  id: string
  product_id: string
  quantity: number
  unit_price: number
  received_qty: number
}

export interface PurchaseOrder {
  id: string
  po_no: string
  supplier_id: string
  status: PoStatus
  total_amount: number
  expected_date: string | null
  remark: string | null
  created_at: string
  items?: PurchaseOrderItem[]
}

// ---------- 仓库（ERP） ----------
export interface WarehouseLocation {
  id: string
  code: string
  name: string | null
  remark: string | null
}

export interface Batch {
  id: string
  batch_no: string
  product_id: string
  po_item_id: string | null
  location_id: string | null
  qty_initial: number
  qty_remaining: number
  location?: WarehouseLocation | null
  product?: Product | null
}

export interface StocktakingItemOut {
  id: string
  product_id: string
  system_qty: number
  counted_qty: number | null
  product?: Product | null
}

export interface Stocktaking {
  id: string
  status: 'processing' | 'completed'
  remark: string | null
  created_at: string
  items?: StocktakingItemOut[]
}

// ---------- 订单（ERP） ----------
export type OrderStatus = 'pending' | 'partial' | 'shipped' | 'legacy'

export interface OrderItemOut {
  id: string
  product_id: string
  platform_sku: string
  quantity: number
  price: number
}

export interface PlatformOrder {
  id: string
  platform_order_no: string
  platform: string | null
  status: OrderStatus
  amount: number
  receiver_name: string | null
  receiver_phone: string | null
  receiver_address: string | null
  shipped_at: string | null
  created_at: string
  items: OrderItemOut[]
}

export interface Shipment {
  id: string
  order_id: string
  platform_order_no: string
  status: 'waiting' | 'shipped'
  tracking_no: string | null
  carrier: string | null
  shipped_at: string | null
  created_at: string
  items: { id: string; product_id: string; quantity: number }[]
}

// ---------- 报表（ERP） ----------
export interface CeoDashboard {
  days: number
  gmv: number
  gross_profit: number
  gross_margin: number
  total_stock: number
  stock_turnover: number
  alert_count: number
  sales_trend: { date: string; amount: number }[]
}

export interface PerformanceStats {
  total_orders: number
  shipped_orders: number
  pending_orders: number
  ship_rate: number
  total_shipments: number
  shipped_shipments: number
  avg_ship_hours: number | null
  alert_products: number
}

export interface FinanceReconciliation {
  days: number
  payable: { name: string; amount: number }[]
  receivable: { name: string; amount: number }[]
  total_payable: number
  total_receivable: number
  net_cash_gap: number
}

// ---------- 看板 ----------
export interface DashboardStats {
  total_products: number
  alert_count: number
  total_shops: number
  sales_trend: { date: string; amount: number }[]
  shop_distribution: { shop: string; product_count: number }[]
}
