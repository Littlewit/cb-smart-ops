"""图形验证码：登录防暴力破解。

实现要点：
- 字符集剔除易混淆字符（0/O、1/l/I），4 位随机
- 存储为进程内存 dict（TTL 5 分钟、一次性消费、惰性清理过期项）：
  开发/演示（uvicorn 单 worker）足够；生产多 worker/多实例应改存 Redis
  （键 captcha:{id}，SETEX 300），接口无需变化
- 不区分大小写；verify 为一次性消费（防重放）
"""

import base64
import io
import random
import secrets
import time

from PIL import Image, ImageDraw, ImageFont

# 验证码字符集：剔除易混淆的 0/O 与 1/l/I
_CHARS = "23456789abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ"
_TTL_SECONDS = 300  # 5 分钟有效期

# captcha_id -> (明文小写答案, 过期时间戳)；仅单进程有效（见模块 docstring）
_store: dict[str, tuple[str, float]] = {}


def _cleanup() -> None:
    """惰性清理过期条目：每次签发时顺带执行，防止内存无限膨胀。"""
    now = time.time()
    for key in [k for k, (_, exp) in _store.items() if exp < now]:
        _store.pop(key, None)


def issue() -> tuple[str, str, str]:
    """生成一枚验证码。

    返回 (captcha_id, 明文小写答案, PNG 图片的 base64 编码)。
    明文答案仅用于测试注入与内部比对，路由只对外暴露图片。
    """
    _cleanup()
    code = "".join(random.choice(_CHARS) for _ in range(4))
    captcha_id = secrets.token_hex(16)
    _store[captcha_id] = (code.lower(), time.time() + _TTL_SECONDS)

    # 绘制：浅底 + 逐字符随机配色 + 干扰线；字体缺失时回退默认位图字体
    img = Image.new("RGB", (140, 44), (245, 247, 250))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 28)  # Windows 常见字体
    except OSError:
        font = ImageFont.load_default()             # Linux 容器内回退
    for i, ch in enumerate(code):
        color = random.choice([(83, 58, 255), (108, 94, 253), (28, 30, 84), (234, 34, 97)])
        draw.text((18 + i * 28, random.randint(4, 10)), ch, fill=color, font=font)
    for _ in range(4):  # 干扰线增加机器识别难度
        draw.line(
            (random.randint(0, 60), random.randint(0, 44), random.randint(80, 140), random.randint(0, 44)),
            fill=(200, 205, 215),
            width=1,
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return captcha_id, code, base64.b64encode(buf.getvalue()).decode("ascii")


def verify(captcha_id: str, code: str) -> bool:
    """一次性校验：不区分大小写；无论成败都消费掉该验证码（防重放）。"""
    entry = _store.pop(captcha_id, None)
    if entry is None:
        return False
    answer, expires_at = entry
    if time.time() > expires_at:
        return False
    return (code or "").strip().lower() == answer
