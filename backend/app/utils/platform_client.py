"""平台适配层：与第三方平台（当前为 Mock，后续可接真实 SHEIN/Shopify）通信。

适配层模式：上层业务（Celery 同步任务、连通性测试）只依赖本模块的函数签名；
接入真实平台时仅需在这里替换实现（改 URL/鉴权/字段映射），业务代码零改动。

当前为同步实现（httpx.Client），供 Celery 任务在 asyncio.to_thread 中调用，
避免阻塞事件循环。
"""

import httpx

from app.core.config import get_settings


def fetch_products(platform: str) -> list[dict]:
    """拉取指定平台的商品列表。

    返回结构（Mock 平台约定）：
        [{"sku": str, "name": str, "stock": int, "cost_price": float, "sale_price": float}, ...]

    网络/响应异常向上抛出，由调用方（任务重试 or 连通性测试）处理。
    """
    settings = get_settings()
    resp = httpx.get(
        f"{settings.mock_platform_url}/api/{platform}/products",
        headers={"Authorization": "Bearer mock-token"},  # Mock 网关仅校验 Bearer 前缀
        timeout=10,
        trust_env=False,  # 内网服务间调用：忽略系统代理，避免代理劫持 127.0.0.1 请求
    )
    resp.raise_for_status()
    return resp.json()["products"]


async def fetch_platform_orders(platform: str, limit: int = 3) -> list[dict]:
    """拉取指定平台的新订单（async 版本：供订单拉取接口在事件循环内直接调用）。

    返回结构（Mock 平台约定）：
        [{"platform_order_no": str, "ordered_at": str, "receiver_name": str,
          "receiver_phone": str, "receiver_address": str,
          "items": [{"sku": str, "quantity": int, "price": float}]}, ...]

    幂等由 backend 的 (shop_id, platform_order_no) 唯一索引保证，
    Mock 平台单号跨调用递增，重复拉取已入库订单会被唯一约束拦截。
    """
    settings = get_settings()
    async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
        resp = await client.get(
            f"{settings.mock_platform_url}/api/{platform}/orders",
            headers={"Authorization": "Bearer mock-token"},
            params={"limit": limit},
        )
    resp.raise_for_status()
    return resp.json()["orders"]
