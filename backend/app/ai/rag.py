"""RAG 检索：运营规则知识库。

双实现策略（系统设计 §3 / §4.2）：
- 部署（PG + pgvector）：embedding 余弦相似度 top-k（迁移补充 embedding 列后启用）
- 开发（SQLite）：关键词重合度打分降级实现，接口签名完全一致

两级兜底：库中无规则文档 → 使用内置规则（BUILTIN_RULES），保证 AI 建议链路
在全新环境也能跑通（演示不中断）。
"""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RuleDocument

# 内置规则：seed 脚本未执行 / 检索无结果时的最终兜底
BUILTIN_RULES = [
    {
        "id": "builtin-restock-formula",
        "title": "补货公式",
        "content": "建议补货量 = max(0, 近7天出库量 × 1.2 + 安全库存 − 当前库存)；库存为 0 时优先级 high。",
    },
    {
        "id": "builtin-slow-moving",
        "title": "滞销品定义",
        "content": "连续 14 天日出库量低于 1 件且库存高于安全库存 2 倍的商品判定为滞销品，建议打折清仓。",
    },
    {
        "id": "builtin-pricing",
        "title": "定价策略",
        "content": "建议售价 = max(成本 × 1.35, 竞品均价 × 0.95)，尾数取 .9；新品可上浮 10% 试价。",
    },
    {
        "id": "builtin-alert",
        "title": "预警阈值策略",
        "content": "库存 < 安全库存即触发预警；安全库存默认 10，可按商品调整；畅销品建议设为 7 天销量。",
    },
]


def _keywords(text: str) -> set[str]:
    """极简中文分词：2 字滑窗 + 英数单词。演示规模够用，无需 jieba 依赖。"""
    compact = re.sub(r"\s+", "", text)
    bigrams = {compact[i : i + 2] for i in range(len(compact) - 1)}
    return bigrams | set(re.findall(r"[A-Za-z0-9]+", text))


async def retrieve_rules(db: AsyncSession, query: str, top_k: int = 3) -> list[dict]:
    """检索与 query 相关的运营规则，返回 [{id, title, content}, ...]。

    SQLite：关键词重合度打分；PG 部署时切换为 pgvector 余弦相似度，
    调用方无感知（接口签名不变）。
    """
    docs = list((await db.execute(select(RuleDocument))).scalars().all())
    if not docs:
        # 库为空（未跑 seed）→ 内置规则兜底
        return BUILTIN_RULES[:top_k]

    query_kw = _keywords(query)
    scored = []
    for doc in docs:
        doc_kw = _keywords(doc.title + doc.content)
        score = len(query_kw & doc_kw)
        scored.append((score, doc))
    # 分数降序；0 分的文档也保留（按原顺序），避免检索为空
    scored.sort(key=lambda pair: -pair[0])
    top = scored[:top_k]

    results = [{"id": d.id, "title": d.title, "content": d.content} for _, d in top]
    if all(pair[0] == 0 for pair in top):
        # 全部 0 分说明检索不到相关内容 → 前置内置规则
        results = BUILTIN_RULES[:top_k] + results[: max(0, top_k - len(BUILTIN_RULES))]
    return results
