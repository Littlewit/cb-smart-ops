/**
 * 各模块 API 封装：与后端路由一一对应（backend/app/routers/）。
 * 返回值已被 request.js 拦截器解包为 data 部分。
 */
import request from './request'

export const authApi = {
  register: (payload) => request.post('/auth/register', payload),
  login: (payload) => request.post('/auth/login', payload),
}

export const shopsApi = {
  list: () => request.get('/shops'),
  create: (payload) => request.post('/shops', payload),
  update: (id, payload) => request.put(`/shops/${id}`, payload),
  remove: (id) => request.delete(`/shops/${id}`),
  sync: (id) => request.post(`/shops/${id}/sync`),
  testConnection: (id) => request.post(`/shops/${id}/test`),
}

export const productsApi = {
  list: (params) => request.get('/products', { params }),
  get: (id) => request.get(`/products/${id}`),
  create: (payload) => request.post('/products', payload),
  update: (id, payload) => request.put(`/products/${id}`, payload),
  remove: (id) => request.delete(`/products/${id}`),
  listSkuMappings: (id) => request.get(`/products/${id}/sku-mappings`),
  addSkuMapping: (id, payload) => request.post(`/products/${id}/sku-mappings`, payload),
  removeSkuMapping: (productId, mappingId) =>
    request.delete(`/products/${productId}/sku-mappings/${mappingId}`),
}

export const inventoryApi = {
  summary: () => request.get('/inventory/summary'),
  listLogs: (params) => request.get('/inventory/logs', { params }),
  createLog: (payload) => request.post('/inventory/logs', payload),
}

export const dashboardApi = {
  stats: () => request.get('/dashboard/stats'),
}

export const aiApi = {
  listSuggestions: (params) => request.get('/ai/suggestions', { params }),
  advice: (payload) => request.post('/ai/advice', payload),
}
