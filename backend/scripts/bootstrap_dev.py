r"""开发库数据引导：重建演示账号 + 运营规则种子（幂等，可重复执行）。

背景：dev.db 表结构完好（迁移最新）但业务数据被清空（时间在 10-03 之后，
与代码无关，疑似本地清理/重置所致）。本脚本恢复最小可演示数据：
- smoke_admin（admin / Passw0rd!）——E2E 与日常登录账号
- 运营规则 5 条（RAG 知识库，AI 建议/对话依赖）
- 演示店铺 1 家（凭证指向 Mock 平台）——商品数据需在 Mock 服务运行时
  通过"店铺管理→同步"或 POST /api/shops/{id}/sync 拉取

执行（backend 目录下）：.venv\\Scripts\\python.exe scripts\\bootstrap_dev.py
"""

import asyncio
import sys
from pathlib import Path

# 直接以脚本运行时 sys.path[0] 是 scripts/，需要把 backend 根加入导入路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.core import security  # noqa: E402
from app.core.database import task_session  # noqa: E402
from app.models import RuleDocument, Shop, User  # noqa: E402
from scripts.seed_rules import RULES as SEED_RULES  # noqa: E402


async def ensure_user(db, username: str, password: str, role: str, email: str) -> None:
    """幂等创建用户：已存在则跳过（不重置密码，避免覆盖用户改过的密码）。"""
    exists = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if exists is not None:
        print(f"用户已存在，跳过: {username} ({exists.role})")
        return
    db.add(
        User(
            username=username,
            password_hash=security.hash_password(password),
            email=email,
            role=role,
        )
    )
    print(f"已创建用户: {username} ({role})")


async def ensure_shop(db, name: str, platform: str, credentials: str) -> None:
    """幂等创建演示店铺（凭证经 AES-256-GCM 加密落库，与接口行为一致）。"""
    exists = (
        await db.execute(select(Shop).where(Shop.name == name))
    ).scalar_one_or_none()
    if exists is not None:
        print(f"店铺已存在，跳过: {name}")
        return
    db.add(
        Shop(
            platform=platform,
            name=name,
            credentials_enc=security.encrypt_credentials(credentials),
            status="active",
        )
    )
    print(f"已创建店铺: {name}（需在 Mock 服务运行时执行同步拉取商品）")


async def ensure_rules(db) -> None:
    """幂等写入运营规则种子（与 scripts/seed_rules.py 同源数据）。"""
    count = (await db.execute(select(func.count(RuleDocument.id)))).scalar_one()
    if count > 0:
        print(f"规则已存在（{count} 条），跳过")
        return
    for title, content in SEED_RULES:
        db.add(RuleDocument(title=title, content=content))
    print(f"已写入规则 {len(SEED_RULES)} 条")


async def main() -> None:
    async with task_session() as db:
        await ensure_user(db, "smoke_admin", "Passw0rd!", "admin", "admin@demo.com")
        await ensure_shop(db, "冒烟店铺", "mock", "mock-token-shein-001")
        await ensure_rules(db)


asyncio.run(main())
