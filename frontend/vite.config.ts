import { defineConfig } from 'vite'
// Vue 单文件组件支持
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // 开发代理：/api 请求转发到 FastAPI(8000)，避免跨域；
    // 生产环境由 Nginx 反代（见部署设计）
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  // Vitest：jsdom 环境跑组件测试
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
