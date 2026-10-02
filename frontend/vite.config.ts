import { fileURLToPath, URL } from 'node:url'
// 从 vitest/config 导入：其 UserConfig 含 test 字段（vite 的类型不含，会报未知属性）
// 该包装完全兼容 Vite 原有能力，dev/build 行为不变
import { defineConfig } from 'vitest/config'
// Vue 单文件组件支持
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    // @ 别名指向 src：与 tsconfig.json 的 paths 对应，导入统一用 @/xxx
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
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
