r"""Mock 平台 API：模拟 SHEIN/Shopify 第三方接口行为（独立 FastAPI 服务）。

为什么独立服务（系统设计 §1 决策 3）：
让同步代码路径与真实第三方对接完全一致（HTTP 调用/延迟/异常），
后续接真实平台时只改 backend 的 platform_client 适配层。

启动（项目根目录）：
    backend\.venv\Scripts\uvicorn mock_platform.main:app --port 8001
"""

import random
import time

from fastapi import FastAPI, HTTPException, Header

app = FastAPI(title="Mock 平台 API", description="模拟第三方电商平台商品/库存接口")

# 内存商品数据：每个平台一份，库存随调用随机波动，模拟平台侧销售/补货
_PRODUCTS: dict[str, list[dict]] = {
    "mock": [
        {"sku": "MOCK-001", "name": "无线蓝牙耳机", "stock": 42, "cost_price": 35.0, "sale_price": 89.0},
        {"sku": "MOCK-002", "name": "手机支架", "stock": 8, "cost_price": 5.5, "sale_price": 19.9},
        {"sku": "MOCK-003", "name": "USB-C 数据线", "stock": 120, "cost_price": 3.2, "sale_price": 12.0},
    ],
    "shein": [
        {"sku": "SH-1001", "name": "夏季连衣裙", "stock": 66, "cost_price": 22.0, "sale_price": 59.0},
        {"sku": "SH-1002", "name": "凉鞋", "stock": 5, "cost_price": 15.0, "sale_price": 45.0},
    ],
    "shopify": [
        {"sku": "SP-2001", "name": "瑜伽垫", "stock": 30, "cost_price": 28.0, "sale_price": 79.0},
    ],
}


@app.get("/api/{platform}/products")
def list_products(
    platform: str,
    authorization: str = Header(default=""),
):
    """拉取平台商品列表；每次调用库存随机波动，模拟真实平台的库存变化。"""
    # 模拟平台鉴权：校验 Bearer 前缀（真实平台会校验签名/有效期）
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if platform not in _PRODUCTS:
        raise HTTPException(status_code=404, detail=f"unknown platform: {platform}")

    # 模拟网络延迟 0.1~0.5s，让同步任务的真实耗时可观测
    time.sleep(random.uniform(0.1, 0.5))

    products = _PRODUCTS[platform]
    for p in products:
        # 随机出库/补货：偏向出库，制造库存下降 → 触发预警 → 驱动补货建议
        p["stock"] = max(0, p["stock"] + random.choice([-3, -2, -1, 0, 0, 1]))
    return {"products": products}
