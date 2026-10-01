# 国庆冲刺计划（10.1-10.7）

## 核心目标
- 完成一个「跨境电商 AI 辅助运营系统」全栈项目（后端 FastAPI + 前端 Vue3 + AI 集成）
- 补齐 PostgreSQL + Celery 异步任务
- 简历重写，10.7 投出第一批

## 项目选择：跨境电商 AI 辅助运营系统

为什么选这个：
1. 精准匹配你收到的 JD（采购/仓库/发货/多店铺运营）
2. 复用你现有技术栈（Vue3 + FastAPI + LangChain）
3. 体现 AI 落地能力，这是 JD 加分项
4. 前端部分你用 Vue3 快速搞定，不用学 React

功能模块（做 3 个就够，不求全）：
- 多店铺商品同步（模拟 SHEIN/Shopify API 对接）
- 库存预警 + AI 补货建议（LangChain + 规则引擎）
- 运营数据看板（CEO 看板雏形）

---

## Day 1（10.1）：环境搭建 + 数据库设计

### 上午：环境搭建（3h）
- [ ] 本地安装 PostgreSQL 16 + Redis 7
- [ ] 创建 FastAPI 项目骨架（分层结构：routers / services / models / schemas）
- [ ] 配置 docker-compose.yml（FastAPI + PG + Redis + Celery）
- [ ] 安装依赖：fastapi、sqlalchemy[asyncio]、asyncpg、alembic、celery、redis、pydantic-settings

### 下午：数据库设计（3h）
设计以下表（用 Alembic 管理迁移）：
- users（用户 + 角色）
- shops（店铺：平台、店铺名、API凭证）
- products（商品：SKU、名称、成本、售价、库存）
- orders（订单：平台单号、状态、金额）
- inventory_logs（库存流水：入库/出库/盘点）
- ai_suggestions（AI建议：补货、定价、预警）

### 晚上：项目结构验证（2h）
- [ ] 跑通 docker-compose up，确认 PG + Redis + FastAPI 全部启动
- [ ] 写一个 /health 接口验证

产出：项目骨架 + 数据库迁移文件

---

## Day 2（10.2）：后端核心 API

### 上午：用户 + 店铺模块（4h）
- [ ] JWT 认证（复用你现有经验，改成 PostgreSQL）
- [ ] RBAC 权限（admin / operator / viewer）
- [ ] 店铺 CRUD + 第三方平台凭证加密存储

### 下午：商品 + 库存模块（4h）
- [ ] 商品 CRUD（支持多平台 SKU 映射）
- [ ] 库存查询 + 库存流水记录
- [ ] 库存预警逻辑（低于安全库存自动标记）

### 晚上：Celery 异步任务（2h）
- [ ] 配置 Celery + Redis broker
- [ ] 写一个模拟任务：定时同步店铺库存（每5分钟）
- [ ] 写一个模拟任务：生成补货建议

产出：可运行的 API + Celery worker

---

## Day 3（10.3）：AI 集成（核心差异化）

### 上午：LangChain 接入（4h）
- [ ] 接入千问 API（你已有经验）
- [ ] 写补货建议 Chain：输入库存+销量数据 → 输出补货建议
- [ ] 写定价建议 Chain：输入成本+竞品价格 → 输出定价策略

### 下午：RAG 知识库（4h）
- [ ] 用 pgvector 存运营规则文档（如“滞销品定义”“补货公式”）
- [ ] 检索增强：AI 建议时自动引用规则
- [ ] 写一个 /ai/advice 接口，返回结构化建议

### 晚上：前端 AI 对话界面（2h）
- [ ] Vue3 写一个简单的 AI 对话面板
- [ ] SSE 流式输出（你已有经验）
- [ ] 对接 /ai/advice 接口

产出：AI 建议功能 + 简单前端

---

## Day 4（10.4）：前端 Vue3 快速搭建

### 全天：核心页面（8h）
用 Vue3 + Element Plus 快速搭：
- [ ] 登录页
- [ ] 商品列表（表格 + 搜索 + 分页）
- [ ] 库存看板（卡片 + 预警高亮）
- [ ] 店铺管理页
- [ ] AI 建议页（对话 + 建议卡片）

技巧：用你 11 年的前端经验，不要追求完美，先跑通功能

产出：可操作的前端界面

---

## Day 5（10.5）：部署 + 文档

### 上午：Docker 化（3h）
- [ ] 写 Dockerfile（FastAPI + Celery 共用镜像）
- [ ] 完善 docker-compose（加 frontend 服务）
- [ ] Nginx 反向代理配置

### 下午：部署到阿里云（3h）
- [ ] 复用你之前的 ECS 部署经验
- [ ] 配置 HTTPS
- [ ] 测试线上可访问

### 晚上：写文档（2h）
- [ ] README：项目介绍、架构图、技术栈、启动方式
- [ ] 接口文档（FastAPI 自带 Swagger）
- [ ] 写 3 个“技术难点与解决方案”

产出：线上可访问的 Demo + 完整文档

---

## Day 6（10.6）：简历重写 + 项目包装

### 上午：简历重写（3h）
标题改为：**Python 后端 / 全栈开发工程师（Vue + FastAPI + AI 应用）**

技能栏重点：
- Python：FastAPI、SQLAlchemy 2.0 异步、Celery、Alembic
- 数据库：PostgreSQL、Redis、SQLite
- AI：LangChain、LangGraph、RAG、千问 API
- 前端：Vue2/Vue3、uniapp、微信小程序（11年经验）
- 工程化：Docker、Nginx、GitHub Actions、阿里云 ECS

项目经历（写 3 个）：
1. 跨境电商 AI 辅助运营系统（本次项目）
2. 企业知识库 RAG 问答（如果有）
3. 任务看板后端（升级为 PG + Redis）

### 下午：面试话术准备（3h）
准备好以下问题的回答：
- “你前端做了11年，为什么转后端/AI？”
  → “前端让我懂交付和用户体验，后端+AI让我能独立完成产品闭环。中小团队最缺能把AI落地成产品的人。”
- “你算法基础怎么样？”
  → “我不做模型训练，专注AI应用工程化：RAG、Agent、工具调用、工程部署。”
- “你怎么接手一个现有系统？”
  → 按 HR 问的答：通读代码 → 梳理架构 → 修线上bug → 吃透业务 → 按优先级迭代

### 晚上：项目描述打磨（2h）
用 STAR 法则重写项目，每个项目 3-5 句话：
- 背景：什么业务场景
- 任务：你负责什么
- 行动：用了什么技术，解决了什么问题
- 结果：量化成果（QPS、覆盖率、部署上线）

产出：简历定稿 + 面试话术

---

## Day 7（10.7）：投递 + 复盘

### 上午：投递（3h）
- [ ] BOSS 直聘：搜“Python 后端”“全栈”“AI 应用开发”“跨境电商”
- [ ] 优先投递：20-500人、跨境电商/SaaS/ERP 方向
- [ ] 附上项目 GitHub 链接和线上 Demo

### 下午：面试准备（3h）
- [ ] 准备 HR 那个30分钟笔试：基础 Python + SQL + FastAPI
- [ ] 复习高频题：async/await、SQLAlchemy 异步、JWT、Celery、RAG 流程

### 晚上：复盘 + 调整（2h）
- [ ] 记录投递反馈
- [ ] 根据反馈调整简历和项目描述

产出：第一批投递 + 面试准备

