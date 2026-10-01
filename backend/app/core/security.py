"""安全工具集：密码哈希 / JWT 签发校验 / 平台凭证 AES 加解密。

- 密码：bcrypt（cost=12），只存哈希，永不存明文
- JWT：HS256，payload 含 user_id(sub) 与 role，有效期从配置读取
- 凭证：AES-256-GCM 对称加密（随机 nonce 拼接在密文前），密钥来自环境变量
"""

import hashlib
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


# ---------- 密码哈希 ----------

def hash_password(plain: str) -> str:
    """生成 bcrypt 哈希（cost=12），返回可直接入库的字符串。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与哈希是否匹配。"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # 哈希格式损坏时按"不匹配"处理，避免抛出未捕获异常
        return False


# ---------- JWT ----------

def create_access_token(user_id: str, role: str) -> str:
    """签发 JWT：sub=用户ID，role=角色（RBAC 快照），exp=过期时间。"""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """校验并解码 JWT；签名错误/过期时抛出 PyJWTError，由上层转为 401。"""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


# ---------- 平台凭证加密（AES-256-GCM） ----------

def _credential_key() -> bytes:
    """将配置中的密钥字符串统一派生为 32 字节 AES 密钥（SHA-256）。"""
    return hashlib.sha256(get_settings().credential_encrypt_key.encode("utf-8")).digest()


def encrypt_credentials(plain: str) -> bytes:
    """AES-256-GCM 加密平台 API 凭证。

    布局：12 字节随机 nonce + 密文（GCM 自带认证标签），解密时前 12 字节即为 nonce。
    """
    nonce = os.urandom(12)
    ciphertext = AESGCM(_credential_key()).encrypt(nonce, plain.encode("utf-8"), None)
    return nonce + ciphertext


def decrypt_credentials(blob: bytes) -> str:
    """解密平台 API 凭证；仅在服务层内部使用，接口永不回显明文。"""
    nonce, ciphertext = blob[:12], blob[12:]
    return AESGCM(_credential_key()).decrypt(nonce, ciphertext, None).decode("utf-8")
