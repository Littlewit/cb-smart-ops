# 跨境电商 AI 辅助运营系统 — 系统设计文档

> 版本：v1.1 ｜ 日期：2026-10-01 ｜ 上游文档：《需求文档-跨境电商AI辅助运营系统.md》
> 原则：演示级系统，结构清晰、易于讲解（面试场景），每个设计点都能讲出"为什么"。
> v1.1 变更：LLM 由千问改为 **DeepSeek**；后端统一使用 **.venv 虚拟环境**；**开发阶段数据库改为 SQLite**（部署阶段 PostgreSQL）。

---

## 1. 总体架构

```
                        ┌─────────────────────────────────────┐
                        │              Nginx (80/443)          │
                        │  /        → Vue3 静态资源            │
                        │  /api    → FastAPI:8000             │
                        │  /mock   → Mock平台:8001             │
                        └───────┬──────────────┬──────────────┘
                                ▼              ▼
                    ┌───────────────┐   ┌───────────────┐
                    │  FastAPI      │   │  Mock 平台 API │
                    │  (async)      │   │  (SHEIN/Shopify│
                    │               │   │   行为模拟)     │
                    └──┬─────────┬──┘   └───────────────┘
                       │         │
          publish      ▼         ▼
                    ┌───────┐ ┌──────────────┐
                    │ Redis │ │  数据库       │
                    │broker │ │ 开发: SQLite  │
                    └───┬───┘ │ 部署: PG16    │
                        │     │   + pgvector  │
                        │     └──────────────┘
                        │ consume
                        ▼
              ┌─────────────────────┐        ┌──────────────┐
              │ Celery Worker/Beat  │──────▶ │ DeepSeek API │
              │ 同步/预警/建议任务    │        │(OpenAI兼容)  │
              └─────────────────────┘        └──────────────┘
```

**关键设计决策（面试可讲点）：**
1. **异步框架**：FastAPI + SQLAlchemy 2.0 async + aiosqlite/asyncpg，IO 密集型场景（外部 API 调用、AI 请求）吞吐更好
2. **任务解耦**：同步/AI 生成走 Celery，HTTP 请求立即返回 task_id，避免长阻塞；开发阶段可设 `CELERY_TASK_ALWAYS_EAGER=true` 同步执行，无需 Redis
3. **Mock 平台独立服务**：模拟真实第三方 API 的延迟与响应格式，使同步代码路径与真实对接一致，后续替换真实 API 只改 client 适配层
4. **AI 兜底**：LLM 不可用时降级为规则引擎（补货公式直接计算），保证演示永不中断
5. **双数据库策略**：开发阶段 SQLite（零安装、克隆即跑），部署阶段切 PostgreSQL 16 + pgvector；仅通过 `DATABASE_URL` 切换，ORM 层不感知差异
6. **本地虚拟环境**：后端统一使用 `.venv`（`python -m venv`），依赖锁定在 requirements.txt，本地与 Docker 镜像复用同一份清单

---

## 2. 代码结构

```
cb-smart-ops/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口，路由注册、 lifespan
│   │   ├── core/
│   │   │   ├── config.py           # pydantic-settings，读 .env
│   │   │   ├── security.py         # JWT 签发/校验、bcrypt、AES-GCM 加解密
│   │   │   └── deps.py             # get_db / get_current_user / require_role
│   │   ├── models/                 # SQLAlchemy ORM（user, shop, product, ...）
│   │   ├── schemas/                # Pydantic 请求/响应模型
│   │   ├── routers/                # auth, shops, products, inventory, orders,
│   │   │                           # dashboard, ai
│   │   ├── services/               # 业务逻辑层（router 只做参数校验与转发）
│   │   ├── tasks/                  # celery_app.py + sync.py + suggestion.py
│   │   ├── ai/
│   │   │   ├── llm.py              # DeepSeek 客户端封装（OpenAI 兼容协议、
│   │   │   │                       #   超时、重试、降级开关）
│   │   │   ├── chains.py           # 补货 Chain / 定价 Chain
│   │   │   ├── rag.py              # 检索：PG 下 pgvector top-k；
│   │   │   │                       #   SQLite 下关键词匹配降级
│   │   │   └── prompts.py          # Prompt 模板（要求输出 JSON schema）
│   │   └── utils/
│   │       └── platform_client.py  # 平台适配层（Mock/真实 API 统一接口）
│   ├── alembic/                    # 迁移（每模块一个 revision）
│   ├── .venv/                      # 本地虚拟环境（gitignore，不入库）
│   ├── requirements.txt
│   └── Dockerfile
├── mock-platform/
│   └── main.py                     # FastAPI，模拟 SHEIN/Shopify 商品库存接口
├── frontend/
│   ├── src/
│   │   ├── api/                    # axios 封装 + 各模块 API
│   │   ├── stores/                 # Pinia（auth、全局状态）
│   │   ├── router/                 # 路由 + 登录守卫 + 角色守卫
│   │   └── views/                  # Login / Products / Inventory / Shops /
│   │                               # AiAdvice / Dashboard
│   └── Dockerfile
├── nginx/nginx.conf
├── docker-compose.yml
└── .env.example
```

**分层原则：** router（校验/鉴权）→ service（业务/事务）→ model（ORM）。Celery 任务直接调 service 层，不依赖 HTTP。

---

## 3. 数据库设计

> **双数据库策略：** 开发阶段 SQLite（`sqlite+aiosqlite:///./dev.db`，零安装）；部署阶段 PostgreSQL 16（镜像 `pgvector/pgvector:pg16`）。
> 字段类型以标准 SQL 书写，SQLite 下由 SQLAlchemy 自动适配（UUID→char(36)、JSONB→JSON、numeric→float）。
> 所有表含 `id (UUID)`, `created_at`, `updated_at`，下表省略。

| 表 | 字段（类型） | 索引/约束 |
|---|---|---|
| **users** | username(varchar64, unique), password_hash(varchar255), role(enum: admin/operator/viewer) | unique(username) |
| **shops** | platform(enum: shein/shopify/mock), name(varchar128), credentials_enc(blob) — AES-GCM 密文, status(enum: active/disconnected) | unique(platform, name) |
| **products** | shop_id(fk), sku(varchar64), name(varchar255), cost_price(numeric12,2), sale_price(numeric12,2), stock(int, default 0), safety_stock(int, default 10), alert_status(bool) | unique(shop_id, sku); idx(alert_status) |
| **product_sku_mappings** | product_id(fk), platform(enum), external_sku(varchar64) | unique(platform, external_sku) |
| **orders** | shop_id(fk), platform_order_no(varchar64), status(enum: pending/shipped/done), amount(numeric12,2) | unique(shop_id, platform_order_no); idx(created_at) |
| **inventory_logs** | product_id(fk), type(enum: in/out/check), quantity(int), stock_before(int), stock_after(int), reason(varchar255), operator_id(fk, nullable) | idx(product_id, created_at) |
| **ai_suggestions** | type(enum: restock/pricing/alert), product_id(fk, nullable), content(jsonb) — 结构化建议, rule_refs(jsonb) — 引用的规则 id, status(enum: pending/accepted/dismissed) | idx(status) |
| **rule_documents** | title(varchar255), content(text), embedding(vector(1024), 仅 PG) | PG: pgvector ivfflat 索引；SQLite: 不建 |

**设计要点：**
- 库存变动只通过 `inventory_logs` 记录并同事务更新 `products.stock`，保证流水与余额一致（"账实分离"是 JD 关键词）
- AI 建议存 jsonb，Schema 由 Prompt 约束（见 §6），前端按 type 渲染卡片
- 运营规则（滞销品定义、补货公式等）以 markdown 分条入库，启动时 seed 脚本写入；PG 下同时生成向量，SQLite 下跳过向量化
- 迁移管理用 Alembic，两种数据库各验证一遍 upgrade/downgrade

---

## 4. 核心流程设计

### 4.1 店铺商品同步（Celery 异步）

```
POST /api/shops/{id}/sync
  → service: 解密凭证 → 创建 SyncTask 记录(可选简化为内存) → celery send_task
  → 立即返回 {"task_id": "...", "message": "同步已提交"}
  → Worker: platform_client.fetch_products(shop)  # 模拟 1~3s 延迟
    → 逐 SKU upsert products（存在则更新库存/价格，不存在则新建）
    → 库存变化写 inventory_logs(type=out/in/check, reason="平台同步")
    → 更新 alert_status = stock < safety_stock
  → 失败重试 1 次（autoretry_for=RequestException）
```

**Celery Beat 周期任务：**

| 任务 | 频率 | 说明 |
|---|---|---|
| sync_all_active_shops | 每 5 分钟 | 遍历 active 店铺调 fetch，模拟平台库存变化 |
| scan_inventory_alerts | 每 5 分钟（同步后触发） | 扫描低于安全库存商品，刷新预警 + 生成 alert 型建议 |
| generate_restock_suggestions | 每小时 | 对预警商品批量生成 AI 补货建议 |

### 4.2 AI 补货建议（RAG + Chain）

```
POST /api/ai/advice {product_id, type: "restock"}
  → service:
    1. 取商品上下文：库存、安全库存、近7天销量(SUM inventory_logs out)
    2. rag.retrieve(query="补货 商品SKU...", top_k=3)
       → PG: pgvector 余弦相似度 top-k
       → SQLite(开发): 关键词匹配降级 / 直接使用内置规则文本兜底
    3. chain: Prompt(系统: 运营顾问角色 + JSON schema 约束)
       + 上下文数据 + 检索到的规则原文 → DeepSeek API (chat.completions)
    4. 解析输出 JSON（解析失败重试 1 次 → 仍失败走规则引擎）
    5. 写入 ai_suggestions(content, rule_refs)，返回给前端
  兜底规则引擎公式：建议补货量 = max(0, 未来7天预估销量×1.2 + 安全库存 − 当前库存)
```

**建议 JSON Schema（Prompt 中约束）：**

```json
{
  "suggestion_type": "restock",
  "quantity": 120,
  "priority": "high | medium | low",
  "reason": "近7天日均出库15件，当前库存18件低于安全库存...",
  "rule_refs": ["rule_id_1", "rule_id_2"]
}
```

### 4.3 AI 对话（SSE 流式）

```
POST /api/ai/chat  (Accept: text/event-stream)
  → StreamingResponse(generator):
    1. RAG 检索相关规则拼入 system prompt
    2. 调用 DeepSeek stream 模式（OpenAI 兼容，stream=True），
       逐 chunk yield "data: {text}\n\n"
    3. 结束 yield "data: [DONE]"
  → 前端 EventSource/fetch-stream 逐字渲染
```

---

## 5. API 设计

统一前缀 `/api`，统一响应包 `{code, message, data}`，错误码：400 参数 / 401 未认证 / 403 无权限 / 404 / 409 冲突 / 500。

| 模块 | 路由 | 方法 | 角色 |
|---|---|---|---|
| 认证 | /api/auth/register, /api/auth/login | POST | 公开 |
| 店铺 | /api/shops | GET/POST | admin 写 |
| | /api/shops/{id} | PUT/DELETE | admin |
| | /api/shops/{id}/sync | POST | admin, operator |
| | /api/shops/{id}/test | POST | admin |
| 商品 | /api/products（分页/搜索/shop_id 筛选） | GET | 全部 |
| | /api/products | POST/PUT/DELETE | operator+ |
| | /api/products/{id}/sku-mappings | GET/POST/DELETE | operator+ |
| 库存 | /api/inventory/summary（含预警列表） | GET | 全部 |
| | /api/inventory/logs?product_id= | GET | 全部 |
| | /api/inventory/logs | POST(入库/出库/盘点) | operator |
| 订单 | /api/orders（分页） | GET | 全部 |
| 看板 | /api/dashboard/stats | GET | 全部 |
| AI | /api/ai/advice | POST | 全部 |
| | /api/ai/suggestions?status= | GET | 全部 |
| | /api/ai/suggestions/{id}/action | POST(采纳/忽略) | operator+ |
| | /api/ai/chat | POST(SSE) | 全部 |

**鉴权实现：** `deps.get_current_user` 解 JWT；`require_role("operator")` 返回依赖工厂，router 声明式挂载。角色硬编码于枚举，无权限表。

---

## 6. 前端设计

| 页面 | 路由 | 组件要点 |
|---|---|---|
| 登录 | /login | 表单校验，token 存 Pinia + localStorage，路由守卫 |
| 商品列表 | /products | el-table + 分页 + SKU 搜索；行内"同步"按钮 |
| 库存看板 | /inventory | 顶部统计卡片；预警行红色高亮；流水抽屉（el-drawer） |
| 店铺管理 | /shops | 凭证输入框 type=password；同步按钮带 loading 轮询 task 状态 |
| AI 建议 | /ai | 左侧对话面板（SSE 渲染）+ 右侧建议卡片流（采纳/忽略） |
| 数据看板 | /dashboard | ECharts 折线图（7日销售额）+ 饼图（店铺分布） |

**请求层：** axios 拦截器统一注入 `Authorization: Bearer`，401 自动跳登录；SSE 用 fetch + ReadableStream（EventSource 不支持 POST）。

---

## 7. 安全设计

1. **密码**：bcrypt（cost=12）
2. **JWT**：HS256，有效期 24h，payload 含 user_id/role；secret 来自 .env
3. **平台凭证**：AES-256-GCM 加密入库，密钥 `CREDENTIAL_ENCRYPT_KEY` 环境变量；出库解密仅限服务层，接口永不回显明文
4. **RBAC**：3 角色接口级校验（见 §5），前端路由守卫做菜单隐藏（仅体验层，不作为安全边界）
5. **SQL 注入**：SQLAlchemy 参数化；**XSS**：Vue 默认转义，AI 输出渲染不加 v-html

---

## 8. 配置管理（pydantic-settings）

`.env` 示例：

```
# 数据库：开发用 SQLite，部署切 PostgreSQL（只改这一行）
DATABASE_URL=sqlite+aiosqlite:///./dev.db
# DATABASE_URL=postgresql+asyncpg://ops:ops@db:5432/cb_ops

# Redis / Celery：开发阶段可免装 Redis，用 eager 模式同步执行
REDIS_URL=redis://redis:6379/0
CELERY_TASK_ALWAYS_EAGER=true   # 仅开发阶段；部署置 false

JWT_SECRET=change-me
CREDENTIAL_ENCRYPT_KEY=change-me-32bytes
DEEPSEEK_API_KEY=sk-xxx
AI_ENABLED=true                 # false 时全部走规则引擎兜底
MOCK_PLATFORM_URL=http://127.0.0.1:8001
```

`Settings` 类集中校验，缺失关键配置时启动即报错（fail-fast）。

---

## 9. 部署设计

### 9.1 本地开发（.venv，无 Docker）

```powershell
# Windows PowerShell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head                 # SQLite 建表 + seed 规则数据
uvicorn app.main:app --reload        # http://127.0.0.1:8000/docs
```

开发阶段 SQLite + `CELERY_TASK_ALWAYS_EAGER=true`，无需安装 PostgreSQL/Redis，克隆即跑。

### 9.2 部署（docker-compose，阿里云 ECS）

| 服务 | 镜像/构建 | 端口 | 说明 |
|---|---|---|---|
| db | pgvector/pgvector:pg16 | 5432(内部) | volume 持久化 |
| redis | redis:7-alpine | 6379(内部) | broker + result backend |
| api | backend Dockerfile (uvicorn) | 8000(内部) | 2 worker |
| worker | 同 api 镜像 (celery worker) | — | 并发 2 |
| beat | 同 api 镜像 (celery beat) | — | 单实例 |
| mock | mock-platform | 8001(内部) | 平台模拟 |
| web | frontend 多阶段构建 → nginx:alpine | 80/443 | 静态资源 + 反代 |

**部署步骤：** docker compose up -d（`DATABASE_URL` 切 PG）→ alembic upgrade head + seed 脚本 → Nginx 证书配置（certbot）→ 云安全组放行 80/443。
**降级路径：** HTTPS 受阻时先开放 80 + IP 访问。
**切换 PG 注意点：** 部署前用 PG 跑一遍 alembic 迁移与 pytest，验证 SQLite 专属写法（如 PRAGMA、SQLite 方言函数）未泄漏到代码。

---

## 10. 测试与验收

| 层 | 策略 | 工具 |
|---|---|---|
| API | pytest + httpx AsyncClient，核心链路各 2~3 用例（登录、同步 upsert 幂等、库存流水一致性）；测试用内存 SQLite | pytest-asyncio |
| AI | LLM 输出 JSON Schema 校验；mock LLM 跑降级路径 | pydantic 校验 |
| 迁移 | SQLite 与 PG 双跑 alembic upgrade | alembic |
| 演示 | 按需求文档 §9 演示脚本走查一遍 | 手工 |

**关键幂等性验证：** 同一店铺连续同步两次，商品数不变、库存流水不重复记录（upsert + 仅变化时写流水）。

---

## 11. 面试技术难点备选（对应 README"3 个难点"）

1. **多平台 SKU 映射与同步幂等**：upsert 策略 + 仅差异写流水，讲数据一致性
2. **AI 输出不确定性工程化**：Prompt JSON 约束 → 解析校验 → 重试 → 规则引擎兜底，四级降级链
3. **双数据库开发/部署策略**：SQLite 开发提速 + PG/pgvector 生产检索，讲 SQLAlchemy 方言隔离与迁移双验证
