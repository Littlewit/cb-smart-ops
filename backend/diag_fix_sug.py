r"""临时脚本（修正版）：更新旧格式建议。

坑（面试可讲）：SQLAlchemy JSON 列不做原地变异追踪——直接改 content 字典
后 flush 不会发 UPDATE，且同事务回读（identity map 同一对象）呈现"已生效"假象。
必须整体重新赋值 content 字段触发变更检测。
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select  # noqa: E402

from app.core.database import task_session  # noqa: E402
from app.models import AiSuggestion  # noqa: E402

NEW_REASON = (
    "依据《补货公式》，建议补货量 = max(0, 近7天出库量0×1.2 + 安全库存10 - 当前库存39) = 0；"
    "当前库存39件高于安全库存10件，不触发预警（依据《预警阈值策略》），"
    "且非缺货或低库存高销量情形（依据《补货优先级》），无需补货。"
)


async def main() -> None:
    async with task_session() as db:
        rows = list((await db.execute(select(AiSuggestion))).scalars())
        updated = 0
        for r in rows:
            c = r.content
            if c.get("quantity") == 0 and c.get("priority") == "low":
                # 关键：整体重建字典并重新赋值，触发 SQLAlchemy 变更检测
                r.content = {**c, "priority": "none", "reason": NEW_REASON}
                db.add(r)
                updated += 1
        await db.flush()
        await db.commit()  # 显式提交，不依赖上下文退出

        # 独立验证：新开原生 sqlite3 连接读库（绕过 ORM identity map）
        import sqlite3

        conn = sqlite3.connect("dev.db")
        check = [
            (row[0][:8], json.loads(row[1]).get("priority"), json.loads(row[1]).get("reason", "")[:40])
            for row in conn.execute("select id, content from ai_suggestions")
        ]
        conn.close()
        Path("../diag_out.txt").write_text(
            f"updated={updated}\n"
            + "\n".join(f"{cid} | {pri} | {reason}" for cid, pri, reason in check),
            encoding="utf-8",
        )


asyncio.run(main())
