/**
 * 各模块 API 封装：与后端路由一一对应（backend/app/routers/）。
 * 返回值已被 request.ts 拦截器解包为 data 部分，泛型 T 标注业务类型。
 */
import request from '@/api/request'
import type {
  AiSuggestion,
  Batch,
  CeoDashboard,
  ChatMessageOut,
  Conversation,
  DashboardStats,
  FinanceReconciliation,
  InventoryLog,
  InventorySummary,
  PagedData,
  PerformanceStats,
  PlatformOrder,
  Product,
  Profile,
  PurchaseOrder,
  Shipment,
  Shop,
  SkuMapping,
  Stocktaking,
  Supplier,
  WarehouseLocation,
} from '@/types'

// ---------- 认证 ----------
export interface LoginResult {
  access_token: string
  token_type: string
}

export const authApi = {
  register: (payload: { username: string; password: string; email: string; role: string }) =>
    request.post('/auth/register', payload),
  login: (payload: {
    username: string
    password: string
    captcha_id: string
    captcha_code: string
  }) => request.post<LoginResult>('/auth/login', payload),
  /** 图形验证码：返回 captcha_id 与 base64 PNG（登录时一次性校验） */
  captcha: () =>
    request.get<{ captcha_id: string; image: string }>('/auth/captcha'),
  /** 忘记密码：用户名+注册邮箱 匹配后重置（公开接口，演示级无邮件验证码） */
  resetPassword: (payload: { username: string; email: string; new_password: string }) =>
    request.post('/auth/reset-password', payload),
  /** 已登录修改密码：需验证旧密码 */
  changePassword: (payload: { old_password: string; new_password: string }) =>
    request.post('/auth/change-password', payload),
  /** 当前登录用户信息（个人中心） */
  me: () => request.get<Profile>('/auth/me'),
  /** 更新个人信息（当前仅邮箱可改） */
  updateMe: (payload: { email: string }) =>
    request.put<Profile>('/auth/me', payload),
}

// ---------- 采购（ERP） ----------
export const procurementApi = {
  listSuppliers: () =>
    request.get<{ items: Supplier[]; total: number }>('/suppliers'),
  createSupplier: (payload: { name: string; contact?: string; phone?: string; email?: string }) =>
    request.post('/suppliers', payload),
  updateSupplier: (id: string, payload: Partial<Supplier>) =>
    request.put(`/suppliers/${id}`, payload),

  listPos: (params?: { status?: string; page?: number; page_size?: number }) =>
    request.get<PagedData<PurchaseOrder>>('/purchase-orders', { params }),
  getPo: (id: string) => request.get<PurchaseOrder>(`/purchase-orders/${id}`),
  createPo: (payload: {
    supplier_id: string
    expected_date?: string
    remark?: string
    items: { product_id: string; quantity: number; unit_price: number }[]
  }) => request.post<{ id: string; po_no: string; status: string }>('/purchase-orders', payload),
  updatePo: (id: string, payload: object) => request.put(`/purchase-orders/${id}`, payload),
  submitPo: (id: string) => request.post(`/purchase-orders/${id}/submit`),
  cancelPo: (id: string) => request.post(`/purchase-orders/${id}/cancel`),
  /** 分批收货：收货行 = 明细 ID + 实收量 + 上架库位（可空） */
  receive: (id: string, items: { item_id: string; quantity: number; location_id?: string }[]) =>
    request.post<{ id: string; po_no: string; status: string }>(`/purchase-orders/${id}/receive`, { items }),
}

// ---------- 仓库（ERP） ----------
export const warehouseApi = {
  listBatches: () => request.get<{ items: Batch[]; total: number }>('/warehouse/batches'),
  listLocations: () => request.get<{ items: WarehouseLocation[]; total: number }>('/warehouse/locations'),
  createLocation: (payload: { code: string; name?: string; remark?: string }) =>
    request.post('/warehouse/locations', payload),
  listStocktakings: () =>
    request.get<{ items: Stocktaking[]; total: number }>('/warehouse/stocktakings'),
  createStocktaking: () => request.post('/warehouse/stocktakings'),
  getStocktaking: (id: string) => request.get<Stocktaking>(`/warehouse/stocktakings/${id}`),
  /** 提交盘点：按差异写 check 流水（账实分离） */
  completeStocktaking: (id: string) => request.post(`/warehouse/stocktakings/${id}/complete`),
}

// ---------- 订单（ERP） ----------
export const orderApi = {
  list: (params?: { status?: string; page?: number; page_size?: number }) =>
    request.get<PagedData<PlatformOrder>>('/orders', { params }),
  fetch: (payload: { shop_id: string; limit?: number }) =>
    request.post<{ fetched: number; skipped: number; shop: string }>('/orders/fetch', payload),
  split: (payload: { order_id?: string }) =>
    request.post<{ split: number; skipped: number }>('/orders/split', payload),
  listShipments: (params?: { status?: string; page?: number; page_size?: number }) =>
    request.get<PagedData<Shipment>>('/shipments', { params }),
  ship: (id: string, payload: { tracking_no: string; carrier?: string }) =>
    request.post<{ id: string; status: string; tracking_no: string }>(`/shipments/${id}/ship`, payload),
}

// ---------- 报表（ERP） ----------
export const reportApi = {
  ceo: (params?: { days?: number }) => request.get<CeoDashboard>('/reports/ceo', { params }),
  performance: () => request.get<PerformanceStats>('/reports/performance'),
  finance: (params?: { days?: number }) =>
    request.get<FinanceReconciliation>('/reports/finance', { params }),
}

// ---------- Agent 工作流 + 知识库（ERP AI 进阶） ----------
export const agentApi = {
  listRules: () =>
    request.get<{ items: { id: string; title: string; content: string; created_at: string }[]; total: number }>(
      '/ai/rules'
    ),
  createRule: (payload: { title: string; content: string }) =>
    request.post('/ai/rules', payload),
  updateRule: (id: string, payload: { title: string; content: string }) =>
    request.put(`/ai/rules/${id}`, payload),
  deleteRule: (id: string) => request.delete(`/ai/rules/${id}`),
  /** 单条补货建议 → 采购单草稿 */
  suggestionToPo: (suggestionId: string, supplierId: string) =>
    request.post<{ id: string; po_no: string; status: string }>(
      `/ai/suggestions/${suggestionId}/to-purchase-order`,
      { supplier_id: supplierId }
    ),
}

// ---------- 店铺 ----------
export const shopsApi = {
  list: () => request.get<Shop[]>('/shops'),
  create: (payload: { platform: string; name: string; credentials: string }) =>
    request.post('/shops', payload),
  update: (id: string, payload: object) => request.put(`/shops/${id}`, payload),
  remove: (id: string) => request.delete(`/shops/${id}`),
  /** 触发同步（eager 模式下返回时任务已完成） */
  sync: (id: string) => request.post<{ task_id: string; message: string }>(`/shops/${id}/sync`),
  testConnection: (id: string) =>
    request.post<{ status: 'connected' | 'disconnected'; product_count?: number }>(
      `/shops/${id}/test`
    ),
}

// ---------- 商品 ----------
export const productsApi = {
  list: (params: object) => request.get<PagedData<Product>>('/products', { params }),
  get: (id: string) => request.get<Product>(`/products/${id}`),
  create: (payload: object) => request.post('/products', payload),
  update: (id: string, payload: object) => request.put(`/products/${id}`, payload),
  remove: (id: string) => request.delete(`/products/${id}`),
  listSkuMappings: (id: string) => request.get<SkuMapping[]>(`/products/${id}/sku-mappings`),
  addSkuMapping: (id: string, payload: { platform: string; external_sku: string }) =>
    request.post(`/products/${id}/sku-mappings`, payload),
  removeSkuMapping: (productId: string, mappingId: string) =>
    request.delete(`/products/${productId}/sku-mappings/${mappingId}`),
}

// ---------- 库存 ----------
export const inventoryApi = {
  summary: () => request.get<InventorySummary>('/inventory/summary'),
  listLogs: (params: object) => request.get<PagedData<InventoryLog>>('/inventory/logs', { params }),
  createLog: (payload: { product_id: string; type: 'in' | 'out' | 'check'; quantity: number; reason: string }) =>
    request.post('/inventory/logs', payload),
}

// ---------- 看板 ----------
export const dashboardApi = {
  stats: (params?: { days?: number }) =>
    request.get<DashboardStats>('/dashboard/stats', { params }),
}

// ---------- AI ----------
export const aiApi = {
  listSuggestions: (params: object) =>
    request.get<PagedData<AiSuggestion>>('/ai/suggestions', { params }),
  advice: (payload: { product_id: string; type: 'restock' | 'pricing' }) =>
    request.post('/ai/advice', payload),
  /** 会话列表（按更新时间倒序），用于侧栏 */
  conversations: () => request.get<{ items: Conversation[]; total: number }>('/ai/conversations'),
  /** 会话消息明细（正序），切换会话/刷新后恢复气泡 */
  messages: (id: string) =>
    request.get<{ conversation_id: string; items: ChatMessageOut[] }>(
      `/ai/conversations/${id}/messages`
    ),
  removeConversation: (id: string) => request.delete(`/ai/conversations/${id}`),
}
