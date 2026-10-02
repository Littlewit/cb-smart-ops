# 跨境电商 AI 辅助运营系统 — 后端

> FastAPI + SQLAlchemy 2.0 (async) + Celery + DeepSeek（LangChain 风格 Chain + RAG）
> 求职演示级全栈项目的后端工程，功能完整可演示，结构清晰可讲解。

## 项目简介

面向跨境电商多店铺运营场景的 AI 辅助系统后端，包含三大核心模块：

1. **多店铺商品同步**：对接 Mock 平台 API（适配层设计，可替换真实 SHEIN/Shopify），Celery 异步同步、幂等 upsert
2. **库存预警 + AI 补货/定价建议**：库存流水账实分离，低库存自动预警，DeepSeek + RAG 运营规则知识库生成结构化建议（LLM 不可用时规则引擎兜底，永不报错）
3. **运营数据看板**：核心指标、近 7 天销售趋势、店铺商品分布聚合接口

## 技术栈

| 类别 | 技术 |
|---|---|
| 框架 | Python 3.11 / FastAPI (async) / pydantic-settings |
| ORM / 迁移 | SQLAlchemy 2.0 (async) / Alembic |
| 异步任务 | Celery（开发 eager 模式免 Redis）+ Redis broker |
| 数据库 | SQLite（开发，零安装）→ PostgreSQL 16 + pgvector（部署），`DATABASE_URL` 一行切换 |
| AI | DeepSeek API（OpenAI 兼容协议，模型 `deepseek-flash`）+ RAG |
| 安全 | JWT (HS256) / bcrypt / AES-256-GCM 凭证加密 / RBAC 三级角色 |

## 目录结构

```
backend/
├── app/
│   ├── main.py            # 入口：create_app + 路由注册
│   ├── core/              # config(配置) / database(引擎) / security(JWT+bcrypt+AES) / deps(RBAC) / response
│   ├── models/            # 8 张表 ORM：users/shops/products/product_sku_mappings/
│   │                      #   orders/inventory_logs/ai_suggestions/rule_documents
│   ├── schemas/           # Pydantic 请求/响应模型（与前端 types 对应）
│   ├── routers/           # auth/shops/products/inventory/ai/dashboard/health（只做校验与转发）
│   ├── services/          # 业务逻辑层：auth/shop/product/inventory/dashboard
│   ├── tasks/             # celery_app(Beat调度) / sync(同步+预警) / suggestion(补货建议)
│   ├── ai/                # llm(DeepSeek封装) / prompts / rag(检索) / chains(补货/定价Chain)
│   └── utils/             # platform_client：平台适配层（Mock→真实平台只改这里）
├── alembic/               # 迁移（env.py 从配置读取 URL，SQLite/PG 双跑验证）
├── scripts/seed_rules.py  # RAG 运营规则种子数据（幂等）
├── tests/                 # pytest：31 项（API/RBAC/任务幂等/AI降级链/SSE）
└── requirements.txt
```

**分层原则**：router（校验/鉴权）→ service（业务/事务）→ model（ORM）。Celery 任务直接调 service，不依赖 HTTP；任务内用 `task_session()` 独立引擎，规避 asyncio.run 跨事件循环复用连接。

## 快速启动

```powershell
# 1. 创建虚拟环境并安装依赖（Python 3.11+）
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. 数据库迁移（开发默认 SQLite，零安装）
.venv\Scripts\alembic.exe upgrade head

# 3. 写入 RAG 运营规则种子数据（幂等，非空表跳过）
.venv\Scripts\python.exe scripts\seed_rules.py

# 4. 启动 API（端口 8000）
.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# 5.（可选）启动 Mock 平台服务（端口 8001，同步功能依赖）
#    在项目根目录执行：
..\.venv\Scripts\python.exe -m uvicorn mock_platform.main:app --port 8001
```

**验证**：访问 http://127.0.0.1:8000/docs（Swagger）与 /health；前端见 `../frontend`。

> 提示：Windows 下 alembic.ini 需保持 ASCII（GBK 控制台编码问题）；包目录名不能含连字符。

## 环境变量（.env，均可缺省走默认值）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./dev.db` | 部署切 PG：`postgresql+asyncpg://...` |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Celery broker/backend，eager 模式下不连接 |
| `CELERY_TASK_ALWAYS_EAGER` | `true` | 开发阶段任务同步执行免装 Redis；**部署必须置 false** |
| `JWT_SECRET` | dev 兜底值 | 部署必须覆盖为随机长密钥（≥32 字节） |
| `CREDENTIAL_ENCRYPT_KEY` | dev 兜底值 | 平台凭证 AES-256-GCM 密钥 |
| `DEEPSEEK_API_KEY` | 空 | 未配置时 AI 接口自动走规则引擎兜底 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容端点 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | DeepSeek-V4.1-Flash 的 API 模型名 |
| `AI_ENABLED` | `true` | false 时全部走规则引擎 |
| `MOCK_PLATFORM_URL` | `http://127.0.0.1:8001` | Mock 平台地址 |

## 技术亮点

1. **AI 四级降级链**：Prompt JSON Schema 约束 → 解析校验失败重试 → 规则引擎公式兜底 → RAG 空结果内置规则兜底。任何一级失败都返回 200（`source: "ai" | "rule"` 标识来源），演示永不中断
2. **账实分离**：库存流水（inventory_logs）与余额（products.stock）同事务更新，出库不足 400 回滚，任何时刻流水推演余额 = 实际余额
3. **同步幂等**：平台同步按 (shop_id, sku) upsert，仅库存变化写盘点流水——重复同步商品数不变、流水不重复
4. **平台适配层**：业务只依赖 `platform_client.fetch_products(platform)`，Mock→真实平台仅改适配层实现
5. **双数据库策略**：SQLite 开发零依赖克隆即跑，`DATABASE_URL` 一行切 PG + pgvector；alembic 双跑验证
6. **凭证安全**：AES-256-GCM 加密落库（随机 nonce），接口永不回显；JWT + bcrypt + RBAC（admin/operator/viewer）

## 测试

```powershell
.venv\Scripts\python.exe -m pytest -v   # 31 项
```

覆盖：认证与 RBAC 权限矩阵、同步幂等（重复同步不重复建/写）、账实一致性（出库不足回滚）、AI 三路径（正常/LLM 宕机/输出不合法，全部 mock 不依赖外部 API）、SSE 帧格式、看板统计。
