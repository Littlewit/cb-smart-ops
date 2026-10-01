"""Celery 应用：broker/backend 用 Redis；Beat 周期任务见 beat_schedule。

开发阶段免装 Redis：配置 celery_task_always_eager=true 时，
delay() 在调用方进程内同步执行任务（见 .env 示例），部署时置 false。
"""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "cb_smart_ops",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.sync", "app.tasks.suggestion"],
)

# eager 模式：任务在本地同步执行 + 异常直接抛出（便于测试发现问题）
if settings.celery_task_always_eager:
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

# 周期任务（Celery Beat 单实例运行）：需求 FR-1.2 / FR-2.2 / FR-2.3
celery_app.conf.beat_schedule = {
    # 每 5 分钟同步所有 active 店铺（模拟平台库存变化）
    "sync-all-active-shops": {
        "task": "app.tasks.sync.sync_all_shops_task",
        "schedule": 300.0,
    },
    # 每 5 分钟扫描库存预警（同步后刷新 alert_status）
    "scan-inventory-alerts": {
        "task": "app.tasks.sync.scan_alerts_task",
        "schedule": 300.0,
    },
    # 每小时为预警商品批量生成补货建议
    "generate-restock-suggestions": {
        "task": "app.tasks.suggestion.generate_restock_suggestions_task",
        "schedule": 3600.0,
    },
}
celery_app.conf.timezone = "Asia/Shanghai"
