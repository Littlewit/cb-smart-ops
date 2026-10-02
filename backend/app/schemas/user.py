"""用户相关 Schema：注册 / 登录 / 改密 / 输出。"""

from typing import Literal

from pydantic import BaseModel, Field

# 极简邮箱格式校验（避免引入 email-validator 依赖；后端不做真实可达性验证）
EMAIL_PATTERN = r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$"


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, description="用户名，全局唯一")
    password: str = Field(min_length=6, max_length=128, description="明文密码，仅用于生成哈希")
    email: str = Field(
        pattern=EMAIL_PATTERN, description="邮箱，忘记密码时用于身份匹配"
    )
    # 演示项目简化：注册时可直接指定角色；生产环境应由管理员分配
    role: Literal["admin", "operator", "viewer"] = "operator"


class LoginRequest(BaseModel):
    """登录请求：需携带图形验证码（GET /api/auth/captcha 签发，一次性）。"""

    username: str
    password: str
    captcha_id: str = Field(min_length=1, description="验证码签发 ID")
    captcha_code: str = Field(min_length=1, max_length=8, description="用户输入的验证码")


class ResetPasswordRequest(BaseModel):
    """忘记密码：用户名 + 注册邮箱 匹配后设置新密码。

    安全说明（演示级）：无邮箱验证码/链接，生产环境必须改为
    "发送一次性验证码到邮箱"或时效性重置链接，防止邮箱枚举攻击。
    """

    username: str = Field(min_length=1)
    email: str = Field(pattern=EMAIL_PATTERN)
    new_password: str = Field(min_length=6, max_length=128)


class ChangePasswordRequest(BaseModel):
    """已登录用户修改密码：需验证旧密码。"""

    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6, max_length=128)


class UserOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    username: str
    role: str
