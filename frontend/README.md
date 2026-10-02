# 跨境电商 AI 辅助运营系统 — 前端

> Vue3 + TypeScript + Element Plus + ECharts 管理端，对接 FastAPI 后端（见 `../backend`）。

## 项目简介

管理端 SPA，包含登录注册、商品管理（多平台 SKU 映射）、店铺管理（一键同步）、库存看板（预警高亮 + 流水）、AI 助手（DeepSeek 流式对话 + 建议卡片）、数据看板（ECharts）六个页面。

## 技术栈

| 类别 | 技术 |
|---|---|
| 框架 | Vue3（Composition API + `<script setup>`）/ **TypeScript（strict）** |
| 构建 | Vite 5（`build` 含 `vue-tsc --noEmit` 类型检查门禁） |
| UI | Element Plus（中文 locale）+ @element-plus/icons-vue |
| 图表 | ECharts 5（折线/饼图，窗口 resize 自适应） |
| 状态 / 路由 | Pinia（localStorage 持久化）/ Vue Router 4 |
| 请求 | axios（拦截器统一解包与 401 处理） |

## 目录结构

```
frontend/
├── src/
│   ├── main.ts            # 入口：装配 Pinia/Router/Element Plus
│   ├── api/
│   │   ├── request.ts     # axios 统一层：Token 注入 / 401 跳登录 / 解包 {code,data}
│   │   └── index.ts       # 各模块 API（泛型标注业务类型）
│   ├── stores/auth.ts     # 认证 store（token+user，localStorage 持久化）
│   ├── router/index.ts    # 登录守卫 + 角色守卫（meta.role 最低角色）
│   ├── layouts/MainLayout.vue  # 侧边菜单 + 用户栏
│   ├── views/             # 6 个页面（见下）
│   ├── types/index.ts     # 业务类型（与后端 schemas 一一对应）
│   └── utils/jwt.ts       # JWT payload 解码（角色显示用）
├── tests/smoke.test.ts    # Vitest 冒烟
├── tsconfig.json          # strict 模式
└── vite.config.ts         # /api 代理 → 127.0.0.1:8000
```

## 快速启动

```powershell
# 前置：Node 18+；先启动后端（../backend，端口 8000）
npm install
npm run dev        # http://localhost:5173（注意：Vite 默认绑定 localhost，非 127.0.0.1）
```

| 命令 | 说明 |
|---|---|
| `npm run dev` | 开发服务器（/api 代理到 8000，免跨域） |
| `npm run build` | **vue-tsc 类型检查 + Vite 生产构建** |
| `npm run typecheck` | 仅类型检查 |
| `npm test` | Vitest 单测（3 项冒烟） |

## 页面清单

| 页面 | 路由 | 功能要点 |
|---|---|---|
| 登录 | /login | 登录/注册双 Tab，JWT 解码角色，redirect 回跳 |
| 商品管理 | /products | 搜索/店铺/预警过滤 + 分页 CRUD + SKU 映射抽屉 + 预警行红色高亮 |
| 库存看板 | /inventory | 指标卡片 + 预警列表 + 流水抽屉 + 入库/出库/盘点 |
| 店铺管理 | /shops | admin CRUD + operator 一键同步 + 连通性测试 |
| AI 助手 | /ai | SSE 流式对话（打字机渲染）+ 建议卡片流（DeepSeek/规则引擎来源徽标）+ 一键生成补货/定价建议 |
| 数据看板 | /dashboard | 指标卡片 + ECharts 近 7 天销售折线 + 店铺分布饼图 |

## 技术要点

1. **SSE 流式对话**：`EventSource` 不支持 POST，因此用 `fetch + ReadableStream` 手动解析——按 `\n\n` 切分 SSE 帧（`data: {"delta": "..."}`，结束帧 `[DONE]`），`TextDecoder` 流式解码保证中文多字节不截断，逐字追加实现打字机效果
2. **axios 拦截器**：成功包 `{code:0, data}` 自动解包（调用方直接拿业务数据）；401 清登录态跳登录页（带 redirect）
3. **守卫分层**：前端路由守卫（登录 + 角色菜单）仅为体验层，**安全边界在后端 RBAC**（接口级 `require_role`），前端隐藏按钮不等于鉴权
4. **类型与后端同步**：`src/types/index.ts` 与 `backend/app/schemas/` 字段一一对应，接口变更两处同步；`npm run build` 强制 vue-tsc 全量检查
