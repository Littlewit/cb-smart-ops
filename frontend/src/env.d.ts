/// <reference types="vite/client" />

// 告诉 TS .vue 单文件组件是 Vue 组件模块（编辑器类型提示 + vue-tsc 检查）
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}
