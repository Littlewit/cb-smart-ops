/**
 * 各模块 API 封装：与后端路由一一对应（backend/app/routers/）。
 * 返回值已被 request.ts 拦截器解包为 data 部分，泛型 T 标注业务类型。
 */
import request from './request'
import type {
  AiSuggestion,
  InventoryLog,
  InventorySummary,
  PagedData,
  Product,
  Shop,
  SkuMapping,
} from '../types'

// ---------- 认证 ----------
export interface LoginResult {
  access_token: string
  token_type: string
}

export const authApi = {
  register: (payload: { username: string; password: string; role: string }) =>
    request.post('/auth/register', payload),
  login: (payload: { username: string; password: string }) =>
    request.post<LoginResult>('/auth/login', payload),
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
import type { DashboardStats } from '../types'

export const dashboardApi = {
  stats: () => request.get<DashboardStats>('/dashboard/stats'),
}

// ---------- AI ----------
export const aiApi = {
  listSuggestions: (params: object) =>
    request.get<PagedData<AiSuggestion>>('/ai/suggestions', { params }),
  advice: (payload: { product_id: string; type: 'restock' | 'pricing' }) =>
    request.post('/ai/advice', payload),
}
