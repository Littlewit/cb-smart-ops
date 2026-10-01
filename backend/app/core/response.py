"""统一成功响应包：{code, message, data}。

错误路径仍使用 FastAPI 的 HTTPException（{"detail": ...}），
由前端 axios 拦截器统一处理（见系统设计文档 §5）。
"""


def ok(data=None, message: str = "ok") -> dict:
    """构造成功响应包。code=0 表示业务成功。"""
    return {"code": 0, "message": message, "data": data}
