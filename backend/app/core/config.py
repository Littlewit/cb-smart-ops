from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """集中配置管理：缺失关键配置时启动即报错（fail-fast）。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "cb-smart-ops"
    app_version: str = "0.1.0"

    # 数据库：开发 SQLite，部署切 PostgreSQL（只改 DATABASE_URL）
    database_url: str = "sqlite+aiosqlite:///./dev.db"

    redis_url: str = "redis://127.0.0.1:6379/0"
    # 开发阶段免装 Redis，Celery 同步执行；部署置 false
    celery_task_always_eager: bool = True

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 24 * 60

    # 平台凭证 AES-256-GCM 加密密钥（32 字节）
    credential_encrypt_key: str = "change-me-32bytes"

    deepseek_api_key: str = ""
    # false 时 AI 接口全部走规则引擎兜底
    ai_enabled: bool = True

    mock_platform_url: str = "http://127.0.0.1:8001"


@lru_cache
def get_settings() -> Settings:
    return Settings()
