# 后端镜像：FastAPI API 与 Celery worker/beat 共用（系统设计 §9.2）
FROM python:3.11-slim

WORKDIR /app

# 运行时优化：不写 pyc、日志直出（容器内必须无缓冲）
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 依赖层单独 COPY 以利用构建缓存（requirements 不变时不重装）
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --no-cache-dir --index-url $PIP_INDEX_URL --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url $PIP_INDEX_URL -r requirements.txt

# 拷贝应用代码（.dockerignore 已排除 .venv/dev.db/缓存）
COPY . .

EXPOSE 8000

# API 默认命令；worker/beat 由 docker-compose 覆盖 command 复用同一镜像
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
