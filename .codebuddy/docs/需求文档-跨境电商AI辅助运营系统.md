# 跨境电商 AI 辅助运营系统 — 需求文档

> 版本：v1.0 ｜ 日期：2026-10-01 ｜ 周期：2026-10-01 ~ 2026-10-05（开发）+ 10.6~10.7（求职包装）
> 定位：求职演示级全栈项目，功能完整可演示、可线上访问，**不追求生产级完备性**。

---

## 1. 项目背景与目标

### 1.1 背景
跨境电商卖家通常在多个平台（SHEIN、Shopify 等）开设店铺，商品、库存、订单数据分散，运营人员缺乏统一的库存预警和补货决策工具。本项目构建一个 AI 辅助运营系统，将多店铺数据聚合后，由 LLM 结合运营规则知识库给出结构化的补货/定价建议。

### 1.2 项目目标
1. 完成可运行、可演示的全栈系统（后端 FastAPI + 前端 Vue3 + AI 集成）
2. 补齐 PostgreSQL + Celery 异步任务实践
3. 体现 AI 工程化落地能力（LangChain + RAG + 结构化建议输出）
4. 10.5 产出线上可访问 Demo + 完整文档，支撑 10.7 第一批投递

### 1.3 非目标（明确不做）
- ❌ 真实 SHEIN/Shopify API 对接（使用本地 Mock 服务模拟）
- ❌ 支付、物流对接、多语言国际化
- ❌ 细粒度权限管理（按钮级/数据行级）
- ❌ 多会话 AI 对话管理、对话历史持久化
- ❌ 高可用、监控告警体系

---

## 2. 用户角色

| 角色 | 说明 | 核心操作 |
|---|---|---|
| admin | 管理员 | 全部功能：店铺管理（含凭证配置）、商品、库存、AI 建议、看板 |
| operator | 运营人员 | 商品/库存管理、查看 AI 建议、确认补货 |
| viewer | 查看者 | 只读：商品、库存看板、AI 建议 |

权限实现方式：JWT 认证 + 3 个硬编码角色的接口级校验（依赖注入中间件），不做权限点配置化。

---

## 3. 功能需求

### 3.1 模块一：多店铺商品同步（P0）

**FR-1.1 店铺管理**
- 店铺 CRUD：平台类型（SHEIN/Shopify/Mock）、店铺名、API 凭证
- API 凭证加密存储（AES 对称加密，密钥来自环境变量）
- 店铺连接状态检测（手动触发"测试连接"）

**FR-1.2 商品同步**
- 商品 CRUD：SKU、名称、成本、售价、库存、所属店铺
- 多平台 SKU 映射：一个内部商品可关联多个平台店铺的 SKU（映射表）
- 触发同步：手动点击"同步"按钮 → Celery 任务 → 调用 Mock 平台 API → 更新/新建商品与库存
- 同步结果反馈：成功/失败条数、失败原因记录

**验收标准：** 创建 Mock 店铺 → 点击同步 → 商品列表出现模拟数据，重复同步不产生重复 SKU。

### 3.2 模块二：库存预警 + AI 补货建议（P0，核心差异化）

**FR-2.1 库存流水**
- 库存变动记录：入库/出库/盘点，字段含变动前后数量、原因、操作人
- 出库/入库后自动更新商品库存

**FR-2.2 库存预警**
- 每个商品可配置安全库存阈值（默认值按商品维度）
- 库存低于阈值自动标记预警状态
- Celery 定时任务（每 5 分钟）扫描并模拟各店铺库存同步 → 刷新预警状态

**FR-2.3 AI 补货建议**
- 输入：商品库存、近 N 天销量（由流水/模拟订单统计）、安全库存
- 处理：LangChain Chain + RAG 检索运营规则（如"滞销品定义""补货公式"）注入 Prompt
- 输出：结构化建议（JSON）：建议补货数量、优先级、理由、引用的规则条目
- 规则：建议生成后写入 `ai_suggestions` 表，前端以建议卡片展示，支持"采纳/忽略"

**FR-2.4 AI 定价建议**
- 输入：成本价 + 竞品价格（Mock 数据）
- 输出：建议售价区间 + 定价策略说明

**验收标准：** 对一个低库存商品调用 `/ai/advice`，返回含补货数量与规则引用的结构化建议；停用 LLM 时接口返回规则引擎兜底建议（不报错）。

### 3.3 模块三：运营数据看板（P1）

**FR-3.1 核心指标卡片**
- 总商品数、预警商品数、店铺数、近 7 天订单总额
- 数据来自聚合查询，不做复杂 OLAP

**FR-3.2 图表**
- 近 7 天销售额趋势（折线图）
- 各店铺商品/库存分布（柱状图或饼图）
- 库存预警商品列表（高亮置顶）

**验收标准：** 看板打开 3 秒内渲染完成，数据与商品/订单实际数据一致。

### 3.4 模块四：AI 对话面板（P1）

**FR-4.1 对话界面**
- Vue3 单会话对话面板，输入运营问题（如"SKU-A001 该补多少货？"）
- SSE 流式输出 AI 回答
- AI 回答可附带结构化建议卡片（复用 FR-2.3 的建议渲染）

### 3.5 基础模块（P0）

**FR-5.1 认证**
- 注册/登录，JWT（access token），密码 bcrypt 哈希
- `/health` 健康检查接口

**FR-5.2 订单（最小集）**
- 订单列表 + 状态（待发货/已发货/已完成）
- Mock 生成订单数据（供看板与销量统计使用），不做订单创建流程

---

## 4. 非功能需求

| 类别 | 要求 |
|---|---|
| 性能 | 列表接口分页（默认 20 条/页）；常规接口 P95 < 500ms |
| 安全 | JWT 认证；API 凭证 AES 加密存储；接口级 RBAC |
| 可靠性 | Celery 任务失败重试 1 次；AI 接口超时（30s）与兜底策略 |
| 可部署 | docker-compose 一键启动（FastAPI + Celery worker + PG + Redis + 前端 + Nginx） |
| 可观测 | Swagger 自动文档；关键操作日志（同步、AI 调用） |
| 兼容 | Chrome 最新版；数据量按演示规模（商品 < 1000）设计 |

---

## 5. 技术架构

```
┌─────────┐   HTTP/SSE   ┌──────────────┐
│  Vue3    │ ──────────▶ │   Nginx       │
│ Element+ │             └──────┬───────┘
└─────────┘                     ▼
                     ┌──────────────────┐    ┌────────┐
                     │  FastAPI (async) │───▶│ Redis  │◀───┐
                     │  routers/        │    └────────┘    │
                     │  services/       │───▶│   数据库    │    │
                     │  models/         │    │ 开发:SQLite │    │
                     │  schemas/        │    │ 部署:PG16   │    │
                     └──────────────────┘    │ +pgvector  │    │
                                              ┌──────────────┐
                          Mock 平台 API ◀────│ Celery Worker │
                          (SHEIN/Shopify模拟) └──────────────┘
                                   ▼
                          DeepSeek API (LangChain)
```

**技术栈：**
- 后端：Python 3.11+（.venv 虚拟环境管理依赖）/ FastAPI / SQLAlchemy 2.0 (async) / aiosqlite / asyncpg / Alembic / Celery / Redis / pydantic-settings
- 数据库：开发阶段 SQLite（零安装，克隆即跑）｜ 部署阶段 PostgreSQL 16 + pgvector（运营规则知识库向量存储），通过 DATABASE_URL 切换
- AI：LangChain + DeepSeek API（OpenAI 兼容协议，支持流式输出）
- 前端：Vue3 + Vite + Element Plus + ECharts
- 部署：Docker / docker-compose / Nginx / 阿里云 ECS

---

## 6. 数据模型

| 表 | 关键字段 | 说明 |
|---|---|---|
| users | id, username, password_hash, role(admin/operator/viewer) | 用户与角色 |
| shops | id, platform(shein/shopify/mock), name, encrypted_credentials, status | 店铺 |
| products | id, sku, name, cost_price, sale_price, stock, safety_stock, shop_id, alert_status | 商品 |
| product_sku_mappings | product_id, platform, external_sku | 多平台 SKU 映射 |
| orders | id, platform_order_no, shop_id, status, amount, created_at | 订单 |
| inventory_logs | id, product_id, type(in/out/check), quantity, before, after, reason, operator_id | 库存流水 |
| ai_suggestions | id, type(restock/pricing/alert), product_id, content(JSON), rule_refs, status(pending/accepted/dismissed) | AI 建议 |
| rule_documents | id, content, embedding(vector, 仅 PG) | RAG 运营规则（SQLite 下关键词检索降级） |

迁移管理：Alembic，每模块一个迁移文件。

---

## 7. 核心 API 一览

| 方法 | 路径 | 说明 | 角色 |
|---|---|---|---|
| POST | /api/auth/register, /login | 注册/登录 | 公开 |
| GET | /health | 健康检查 | 公开 |
| CRUD | /api/shops | 店铺管理（凭证加密） | admin |
| POST | /api/shops/{id}/sync | 触发店铺同步（Celery） | admin/operator |
| CRUD | /api/products | 商品管理 | viewer 只读 |
| GET | /api/inventory/summary | 库存概览 + 预警列表 | 全部 |
| POST | /api/inventory/logs | 入库/出库/盘点 | operator |
| GET | /api/orders | 订单列表 | 全部 |
| GET | /api/dashboard/stats | 看板指标 + 趋势 | 全部 |
| POST | /api/ai/advice | AI 建议（补货/定价） | 全部 |
| POST | /api/ai/chat | AI 对话（SSE 流式） | 全部 |

---

## 8. 里程碑计划

| 日期 | 交付物 | 对应模块 |
|---|---|---|
| Day1 10.1 | .venv 虚拟环境 + 项目骨架（开发期 SQLite，免装 PG/Redis）+ Alembic 迁移 + /health；docker-compose 用于部署验证 | 基础设施、数据模型 |
| Day2 10.2 | JWT/RBAC + 店铺/商品/库存 API + Celery 定时同步与预警任务 | 3.1、3.2(FR-2.1/2.2)、3.5 |
| Day3 10.3 | DeepSeek 接入 + 补货/定价 Chain + RAG（PG 下 pgvector，SQLite 下关键词降级）+ /ai/advice + AI 对话页(SSE) | 3.2(FR-2.3/2.4)、3.4 |
| Day4 10.4 | Vue3 全部页面（登录/商品/库存看板/店铺/AI 建议/数据看板） | 3.3 + 前端整合 |
| Day5 10.5 | Docker 化 + 阿里云部署(HTTPS) + README + 3 个技术难点文档 | 部署与文档 |

**风险预案：**
- pgvector 检索不稳 → 退化为纯 Prompt 模板注入规则原文
- HTTPS/域名受阻 → 先 HTTP + IP 访问，README 附截图
- 时间不足 → 砍 3.3 看板图表，仅保留指标卡片 + 预警列表
- 切换 PG 时迁移/方言问题 → 部署前用 PG 双跑 alembic + pytest（详见系统设计文档 §9.2/§10）

---

## 9. 演示脚本（求职场景）

1. 登录系统 → 展示 RBAC（viewer 无法编辑）
2. 添加 Mock 店铺 → 一键同步 → 商品列表出现数据
3. 将某商品库存调低 → 看板预警高亮
4. AI 对话面板提问"该商品怎么补货" → SSE 流式返回 → 建议卡片含补货数量与规则引用
5. 展示看板趋势图 → 打开 Swagger 展示接口文档
