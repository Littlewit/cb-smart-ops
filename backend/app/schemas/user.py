"""用户相关 Schema：注册 / 登录 / 输出。"""

from typing import Literal

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, description="用户名，全局唯一")
    password: str = Field(min_length=6, max_length=128, description="明文密码，仅用于生成哈希")
    # 演示项目简化：注册时可直接指定角色；生产环境应由管理员分配
    role: Literal["admin", "operator", "viewer"] = "operator"


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    username: str
    role: str
