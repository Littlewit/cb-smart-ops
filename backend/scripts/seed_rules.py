"""运营规则种子数据：向 rule_documents 写入知识库文档（幂等：非空表跳过）。

执行（backend 目录下）：
    .venv\\Scripts\\python.exe scripts\\seed_rules.py
"""

import asyncio
import sys
from pathlib import Path

# 直接以脚本运行时 sys.path[0] 是 scripts/，需要把 backend 根加入导入路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.core.database import task_session  # noqa: E402
from app.models import RuleDocument  # noqa: E402

# 五条核心运营规则（对应需求 FR-2.3 提到的"滞销品定义""补货公式"等）
RULES = [
    (
        "补货公式",
        "建议补货量 = max(0, 近7天出库量 × 1.2 + 安全库存 − 当前库存)。"
        "当前库存为 0 时优先级 high，低于安全库存为 medium，其余为 low。",
    ),
    (
        "滞销品定义",
        "连续 14 天日出库量低于 1 件且库存高于安全库存 2 倍的商品判定为滞销品，"
        "建议打折清仓或平台下架，释放库存资金。",
    ),
    (
        "定价策略",
        "建议售价 = max(成本 × 1.35, 竞品均价 × 0.95)，尾数取 .9；"
        "新品上市可上浮 10% 试价，两周内根据转化率回调。",
    ),
    (
        "预警阈值策略",
        "库存 < 安全库存即触发预警；安全库存默认 10，可按商品调整；"
        "畅销品建议将安全库存设置为近 7 天日均销量的 1.5 倍。",
    ),
    (
        "补货优先级",
        "多商品同时缺货时：缺货且高销量 > 低库存高销量 > 仅低于安全库存；"
        "采购资金有限时优先保障 TOP 销量 SKU 不断货。",
    ),
]


async def main() -> None:
    async with task_session() as session:
        count = (await session.execute(select(func.count(RuleDocument.id)))).scalar_one()
        if count > 0:
            print(f"rule_documents 已有 {count} 条记录，跳过 seed")
            return
        for title, content in RULES:
            session.add(RuleDocument(title=title, content=content))
        await session.flush()
        print(f"已写入 {len(RULES)} 条运营规则")


if __name__ == "__main__":
    asyncio.run(main())
