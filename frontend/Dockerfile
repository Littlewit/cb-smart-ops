# 多阶段构建：Node 编译 TS → Nginx 托管静态资源并反代 API（系统设计 §9.2）
# 注意：构建上下文为项目根目录（docker-compose 中 web 服务 context: .）

# ---------- 阶段一：编译 ----------
FROM node:20-alpine AS build
WORKDIR /app

# npmmirror 镜像加速（国内构建环境；可用 --build-arg 覆盖）
ARG NPM_REGISTRY=https://registry.npmmirror.com

# 先拷贝依赖清单利用缓存，再拷贝源码
COPY frontend/package.json frontend/package-lock.json ./
RUN npm config set registry $NPM_REGISTRY && npm ci

COPY frontend/ .
# npm run build 内含 vue-tsc 类型检查，类型错误会阻断构建
RUN npm run build

# ---------- 阶段二：运行 ----------
FROM nginx:alpine
# SPA 静态资源
COPY --from=build /app/dist /usr/share/nginx/html
# Nginx 配置：SPA 路由回退 + /api 反代 + SSE 关闭缓冲
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
